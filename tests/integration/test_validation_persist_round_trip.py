"""PARITY-GAP P1.1 — word validation must survive a fresh-store reload.

Live sweep C55 root cause: validate mutations only set the in-memory
``is_validated`` Python attribute; the serialized ``Word`` never carried the
state, so a server restart reverted validation to the fixture-seeded counts.

Fix under test: every validate/unvalidate writer also adds/removes the
``"validated"`` string in ``Word.word_labels`` — pdomain-book-tools serializes
``word_labels`` through ``to_dict``/``from_dict``
(``pdomain_book_tools/ocr/word.py:677/:737``), so the content blob written by
``save_page_content_to_store`` carries the state for free, and the existing
read-path fallback in ``core/page_to_line_matches.py`` maps it back to
``is_validated``.

Writers covered (all four):
1. single toggle  — ``POST .../words/{li}/{wi}/validated``
2. batch          — ``POST .../words/validate-batch``
3. line validate  — ``POST .../lines/{li}/validate`` (word propagation)
4. para validate  — ``POST .../paragraphs/{pi}/validate`` (word propagation)

Acceptance note: the e2e harness has no cheap server-restart hook
(``exercise_server`` is module-scoped and shared), so this fresh-store
reload suite IS the P1.1 acceptance gate — it simulates the restart by
closing the app and opening a brand-new ``LabelerPageStore`` over the same
on-disk events.db/blobs, exactly what a new process would do.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.page_to_line_matches import page_to_line_matches
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Callable

# ── Real book-tools Page builders (mirrors test_restart_reload_live_path) ────


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _word(text: str, *, word_labels: list[str] | None = None) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(0, 0, 10, 10),
        "word_labels": list(word_labels or []),
    }


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": _bbox(0, 0, 100, 20),
    }


def _para(lines: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "items": lines,
        "bounding_box": _bbox(0, 0, 100, 40),
    }


def _make_page(*, validated_first_word: bool = False) -> Page:
    """Page with one paragraph: line0 = ['teh', 'cat'], line1 = ['sat']."""
    first_labels = ["validated"] if validated_first_word else []
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [
            _para(
                [
                    _line([_word("teh", word_labels=first_labels), _word("cat")]),
                    _line([_word("sat")]),
                ]
            )
        ],
    }
    return Page.from_dict(page_dict)


# ── Harness ───────────────────────────────────────────────────────────────────


def _make_settings(tmp_path: Path, *, projects_root: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )


def _seed_page_in_store(store: LabelerPageStore, page_id: UUID, page_index: int) -> None:
    record = PageRecord(page_id=page_id, page_index=page_index, source="ocr")
    agg = PageAggregate(record)
    store.save_page(agg)


def _drive_and_reload(
    tmp_path: Path,
    mutate: Callable[[TestClient], None],
    *,
    page: Page | None = None,
) -> Page:
    """Run the app, seed a REAL book-tools Page, apply ``mutate`` via the API,
    close the app, then reload the page from a FRESH store (restart simulation).

    Returns the reloaded ``Page`` reconstructed via ``Page.from_dict`` from the
    content blob — exactly what a new process would see.
    """
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = _make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)

    live_page = page if page is not None else _make_page()
    page_id = uuid4()

    with TestClient(app) as client:
        resp = client.post("/api/projects/load", json={"project_root": str(proj_dir)})
        assert resp.status_code == 200, f"load failed: {resp.text}"

        live_store: LabelerPageStore | None = getattr(app.state, "page_store", None)
        assert live_store is not None, "app.state.page_store missing after load_project"
        _seed_page_in_store(live_store, page_id, page_index=0)

        project_state = app.state.project_state
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=live_page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.generation = 1
        pstate.last_saved_generation = 0
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        mutate(client)

    # ── Restart simulation: fresh store over the same on-disk data ──────────
    fresh_store = LabelerPageStore(project_dir=proj_dir)
    try:
        reloaded = load_page_from_store(fresh_store, page_id)
    finally:
        fresh_store.close()
    assert reloaded is not None, (
        "load_page_from_store returned None — the validate route never persisted a content blob"
    )
    return reloaded


def _labels(page: Page, li: int, wi: int) -> list[str]:
    return list(page.lines[li].words[wi].word_labels)


# ── Tests: all four writers ───────────────────────────────────────────────────


@pytest.mark.integration
def test_single_toggle_validate_persists_across_fresh_store_reload(tmp_path: Path) -> None:
    """P1.1 acceptance: validate one word → restart → still validated."""

    def mutate(client: TestClient) -> None:
        resp = client.post(
            "/api/projects/book1/pages/0/words/0/0/validated",
            json={"validated": True},
        )
        assert resp.status_code == 200, f"toggle_validated failed: {resp.text}"

    reloaded = _drive_and_reload(tmp_path, mutate)
    assert "validated" in _labels(reloaded, 0, 0), (
        f"validation lost on restart: word_labels={_labels(reloaded, 0, 0)!r}"
    )
    # Untouched words stay unvalidated.
    assert "validated" not in _labels(reloaded, 0, 1)

    # Read-path agreement: a fresh process building the payload must report
    # is_validated=True from the persisted label (no in-memory attr exists).
    _record, line_matches = page_to_line_matches(reloaded, 0, Path("001.png"))
    assert line_matches[0].word_matches[0].is_validated is True, (
        "read path did not map the persisted 'validated' label back to is_validated"
    )
    assert line_matches[0].word_matches[1].is_validated is False


@pytest.mark.integration
def test_single_unvalidate_removes_label_across_fresh_store_reload(tmp_path: Path) -> None:
    """Unvalidating a previously-validated word must REMOVE the label durably."""
    seeded = _make_page(validated_first_word=True)

    def mutate(client: TestClient) -> None:
        resp = client.post(
            "/api/projects/book1/pages/0/words/0/0/validated",
            json={"validated": False},
        )
        assert resp.status_code == 200, f"unvalidate failed: {resp.text}"

    reloaded = _drive_and_reload(tmp_path, mutate, page=seeded)
    assert "validated" not in _labels(reloaded, 0, 0), (
        f"unvalidate did not remove the persisted label: word_labels={_labels(reloaded, 0, 0)!r}"
    )


@pytest.mark.integration
def test_validate_batch_page_scope_persists_across_fresh_store_reload(tmp_path: Path) -> None:
    """Bulk validate (scope=page) must persist for every word on the page."""

    def mutate(client: TestClient) -> None:
        resp = client.post(
            "/api/projects/book1/pages/0/words/validate-batch",
            json={"scope": "page", "validated": True},
        )
        assert resp.status_code == 200, f"validate-batch failed: {resp.text}"

    reloaded = _drive_and_reload(tmp_path, mutate)
    for li, wi in [(0, 0), (0, 1), (1, 0)]:
        assert "validated" in _labels(reloaded, li, wi), (
            f"batch validation lost on restart for word ({li},{wi}): {_labels(reloaded, li, wi)!r}"
        )


@pytest.mark.integration
def test_validate_batch_unvalidate_removes_labels_across_fresh_store_reload(tmp_path: Path) -> None:
    """Bulk UNvalidate (scope=page) must remove persisted labels."""
    seeded = _make_page(validated_first_word=True)

    def mutate(client: TestClient) -> None:
        resp = client.post(
            "/api/projects/book1/pages/0/words/validate-batch",
            json={"scope": "page", "validated": False},
        )
        assert resp.status_code == 200, f"validate-batch failed: {resp.text}"

    reloaded = _drive_and_reload(tmp_path, mutate, page=seeded)
    assert "validated" not in _labels(reloaded, 0, 0), (
        f"batch unvalidate did not remove the persisted label: {_labels(reloaded, 0, 0)!r}"
    )


@pytest.mark.integration
def test_validate_line_persists_across_fresh_store_reload(tmp_path: Path) -> None:
    """Line validate must persist the propagated word labels (line 0 only)."""

    def mutate(client: TestClient) -> None:
        resp = client.post(
            "/api/projects/book1/pages/0/lines/0/validate",
            json={"validated": True},
        )
        assert resp.status_code == 200, f"validate_line failed: {resp.text}"

    reloaded = _drive_and_reload(tmp_path, mutate)
    assert "validated" in _labels(reloaded, 0, 0)
    assert "validated" in _labels(reloaded, 0, 1)
    assert "validated" not in _labels(reloaded, 1, 0), "line validation leaked onto line 1"


@pytest.mark.integration
def test_validate_paragraph_persists_across_fresh_store_reload(tmp_path: Path) -> None:
    """Paragraph validate must persist the propagated word labels for all words."""

    def mutate(client: TestClient) -> None:
        resp = client.post(
            "/api/projects/book1/pages/0/paragraphs/0/validate",
            json={"validated": True},
        )
        assert resp.status_code == 200, f"validate_paragraph failed: {resp.text}"

    reloaded = _drive_and_reload(tmp_path, mutate)
    for li, wi in [(0, 0), (0, 1), (1, 0)]:
        assert "validated" in _labels(reloaded, li, wi), (
            f"paragraph validation lost on restart for word ({li},{wi}): {_labels(reloaded, li, wi)!r}"
        )

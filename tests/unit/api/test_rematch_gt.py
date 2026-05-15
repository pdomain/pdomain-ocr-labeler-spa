"""Unit tests for ``POST .../pages/{idx}/rematch-gt`` (spec-23-F, issue #320).

Spec authority:
- ``specs/23-page-payload-backend.md §7`` — re-run page-level GT
  matching (``core/ground_truth_matcher.rematch_page``), replace
  ``page.line_matches``, discard per-word GT edits (legacy
  semantics), bump generation, return refreshed PagePayload.
- ``specs/23-page-payload-backend.md §13`` — per-page locking.

The legacy ``_rematch_page_ground_truth``
(``pd_ocr_labeler/state/page_state.py:2202``) implements the
"discard per-word GT edits" via the
``page.remove_ground_truth()`` → ``page.add_ground_truth(gt_text)``
pair: ``remove_ground_truth`` wipes every word's ``ground_truth_text``,
then ``add_ground_truth`` (which delegates to
``pd_book_tools.ocr.ground_truth_matching.update_page_with_ground_truth_text``)
re-derives GT from the canonical source string.

Pattern (mirrors ``test_words_mutate_gt.py``):

1. Seed a ``PageState`` with a stub Page whose words carry
   per-word GT edits.
2. Seed ``Project.ground_truth_map`` with the page's GT source.
3. POST ``/rematch-gt`` (empty body).
4. Assert 200 + ``PagePayload`` shape.
5. Assert ``page.remove_ground_truth`` was called (per-word GT discarded).
6. Assert ``page.add_ground_truth(gt_text)`` was called with the
   source GT text.
7. Assert ``pstate.generation`` incremented by exactly 1.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pd_ocr_labeler_spa.core.project_state import PageState
from pd_ocr_labeler_spa.settings import Settings

# ── Test fixtures ────────────────────────────────────────────────────


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    """Project layout with image filenames + a GT sidecar for page 0."""
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    (proj / "002.png").write_bytes(b"\x89PNG\r\n")
    # Drop a ``pages.json`` so the project loader populates
    # ``Project.ground_truth_map`` with an entry for page 0
    # (``001.png``) but NOT page 1 — exercises both the happy-path
    # (page 0 has GT) and the no-GT error path (page 1 has none).
    # Loader normalisation (``_normalize_entries``) keys aliases under
    # ``001.png`` / ``001`` / ``001.png`` lowercase. See
    # ``core/persistence/ground_truth.py:_normalize_entries`` for the
    # alias contract.
    (proj / "pages.json").write_text('{"001": "hello rematched world"}', encoding="utf-8")
    return root


# ── Stub Page that records rematch calls ─────────────────────────────


@dataclass
class _StubWord:
    text: str = "ocr"
    # Per-word GT edit pre-rematch; the rematch must discard it.
    ground_truth_text: str = "user-edited-gt"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Word",
            "text": self.text,
            "ground_truth_text": self.ground_truth_text,
        }


@dataclass
class _StubLine:
    words: list[_StubWord] = field(default_factory=list)


@dataclass
class _StubPage:
    """Page-stub recording ``remove_ground_truth`` / ``add_ground_truth`` calls.

    Mirrors the contract the ``rematch_page`` wrapper relies on
    (``core/ground_truth_matcher.py``) and the legacy
    ``Page.remove_ground_truth`` / ``Page.add_ground_truth`` pair.
    ``remove_ground_truth`` zeroes per-word ``ground_truth_text`` so
    assertions can verify the "per-word GT edits discarded" semantic
    on the underlying objects.
    """

    lines_: list[_StubLine] = field(default_factory=list)
    remove_called: int = 0
    add_calls: list[str] = field(default_factory=list)

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubLine]:
        return self.lines_

    @property
    def words(self) -> list[_StubWord]:
        return [w for ln in self.lines_ for w in ln.words]

    def remove_ground_truth(self) -> None:
        self.remove_called += 1
        for ln in self.lines_:
            for w in ln.words:
                w.ground_truth_text = ""

    def add_ground_truth(self, text: str) -> None:
        self.add_calls.append(text)
        # Simulate the matcher rebuilding per-word GT from the source
        # — assign the whole source string to the first word so the
        # test can observe that GT was re-derived from the input.
        if self.lines_ and self.lines_[0].words:
            self.lines_[0].words[0].ground_truth_text = text

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [{"words": [w.to_dict() for w in ln.words]} for ln in self.lines_],
            "paragraphs": [],
            "words": [w.to_dict() for w in self.words],
            "source_identifier": "stub.png",
        }


def _make_seeded_page() -> _StubPage:
    return _StubPage(
        lines_=[
            _StubLine(
                words=[
                    _StubWord(text="hello", ground_truth_text="user-edit-1"),
                    _StubWord(text="world", ground_truth_text="user-edit-2"),
                ]
            ),
        ],
    )


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


def _seed_page_state(client: TestClient, *, page_index: int, page: _StubPage) -> PageState:
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(
        page_index=page_index,
        source=PageSource.OCR,
        payload=page,
    )
    pstate = PageState(page_index=page_index, page_record=outcome)
    pstate.generation = 1
    pstate.last_saved_generation = 0
    project_state._page_states[page_index] = pstate
    return pstate


# ── Happy path ───────────────────────────────────────────────────────


def test_rematch_gt_invokes_pd_book_tools_and_discards_per_word_edits(
    loaded_client: TestClient,
) -> None:
    """Spec §7: rematch wipes per-word GT and re-runs page-level matching.

    Asserts:
    - 200 response with ``PagePayload`` shape.
    - ``page.remove_ground_truth`` invoked exactly once (per-word
      GT edits discarded — legacy semantics).
    - ``page.add_ground_truth(gt_text)`` invoked with the project
      ground-truth-map entry for the page's image filename.
    - ``pstate.generation`` advanced by exactly 1.
    """
    page = _make_seeded_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post("/api/projects/book1/pages/0/rematch-gt", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0
    # PagePayload shape sanity — line_matches must be present (empty
    # list pre-M3 when no matcher emits LineMatch wire shapes; the
    # spec contract is "the field is refreshed", not "non-empty").
    assert "line_matches" in body

    # Legacy "discards per-word GT edits": remove_ground_truth was called.
    assert page.remove_called == 1, (
        f"expected page.remove_ground_truth called exactly once; got {page.remove_called}"
    )

    # The page-level matcher was re-invoked with the project's GT
    # text for page 0 (filename "001.png" → "hello rematched world").
    # GT lookup goes through ``find_ground_truth_text`` which resolves
    # ``001.png`` → the value stored under the ``001`` key in
    # ``pages.json`` (after ``_normalize_entries`` registers ``001.png``
    # as an alias).
    assert page.add_calls == ["hello rematched world"], (
        f"expected add_ground_truth called with project GT text; got {page.add_calls}"
    )

    # Per-word GT edits actually discarded on the underlying words.
    # ``add_ground_truth`` (stub) re-derives GT for the first word from
    # the source string; the second word's pre-rematch user edit must
    # be wiped (remove_ground_truth) and not restored by the stub.
    assert page.lines[0].words[1].ground_truth_text == "", "per-word GT edit on word (0, 1) was not discarded"

    # PageState generation bumped exactly once.
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    pstate_after = project_state.page_states[0]
    assert pstate_after.generation == gen_before + 1


# ── Error paths ──────────────────────────────────────────────────────


def test_rematch_gt_returns_404_for_unknown_project(
    loaded_client: TestClient,
) -> None:
    """Unknown ``project_id`` → 404 ``project_not_found``."""
    resp = loaded_client.post("/api/projects/does-not-exist/pages/0/rematch-gt", json={})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "project_not_found"


def test_rematch_gt_returns_404_for_out_of_range_page(
    loaded_client: TestClient,
) -> None:
    """``page_index`` ≥ ``total_pages`` → 404 ``page_not_found``."""
    resp = loaded_client.post("/api/projects/book1/pages/99/rematch-gt", json={})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "page_not_found"


def test_rematch_gt_returns_400_when_page_not_loaded(
    loaded_client: TestClient,
) -> None:
    """No seeded ``PageState`` → 400 ``page_not_loaded``.

    Mirrors the spec-23-C1 word-mutation contract: rematch needs an
    in-memory Page object; the route can't synthesize one.
    """
    resp = loaded_client.post("/api/projects/book1/pages/0/rematch-gt", json={})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "page_not_loaded"


def test_rematch_gt_returns_400_when_no_ground_truth_available(
    loaded_client: TestClient,
) -> None:
    """No GT sidecar for the page → 400 ``no_ground_truth``.

    Page 1 (``002.png``) has no ``002.txt`` sidecar, so the
    ``Project.ground_truth_map`` has no entry for it. Legacy parity:
    ``_rematch_page_ground_truth`` raises ``_GroundTruthRematchSkippedError``
    and the legacy UI surfaces a "no GT" failure notification. The
    SPA returns 400 so the frontend can render the equivalent banner.
    """
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=1, page=page)

    resp = loaded_client.post("/api/projects/book1/pages/1/rematch-gt", json={})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "no_ground_truth"

    # The page must NOT have been mutated when GT is unavailable.
    assert page.remove_called == 0
    assert page.add_calls == []

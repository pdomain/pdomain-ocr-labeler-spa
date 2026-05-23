"""Unit / integration tests for ``POST .../save`` and ``POST .../load`` (spec-23-B2).

Spec authority:
- ``specs/23-page-payload-backend.md §4`` — POST /save: calls
  ``persist_page_to_file``, 409 on generation mismatch, 500 envelope on OSError.
- ``specs/23-page-payload-backend.md §5`` — POST /load: clear in-memory state,
  ``ensure_page_model(force_reload=True)``, return ``PagePayload``.

Issue: #308.

These tests inject a fake ``page_loader`` onto ``runner.context["page_loader"]``
so the /load path can be exercised end-to-end without DocTR. The /save path
needs no loader (it reads ``pstate.page_record`` directly).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import labeled_envelope_path
from pd_ocr_labeler_spa.core.project_state import PageState
from pd_ocr_labeler_spa.settings import Settings


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
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    (proj / "002.png").write_bytes(b"\x89PNG\r\n")
    return root


@dataclass
class _StubPage:
    """Minimal Page-stub exposing ``to_dict()`` for ``build_envelope``."""

    label: str = "stub"

    def to_dict(self) -> dict[str, Any]:
        return {
            "words": [],
            "paragraphs": [],
            "lines": [],
            "source_identifier": f"{self.label}.png",
        }


class _FakePageLoader:
    """Stand-in for ``LocalDoctrPageLoader`` for the /load path."""

    def __init__(self) -> None:
        self.run_ocr_calls: list[int] = []
        self.load_labeled_calls: list[int] = []
        self.load_cached_calls: list[int] = []

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        self.run_ocr_calls.append(page_index)
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload=_StubPage(label=f"ocr_{page_index}"),
        )

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        self.load_labeled_calls.append(page_index)
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        self.load_cached_calls.append(page_index)
        return None


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with project loaded and a fake page_loader wired."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()
    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


# ── POST /save ───────────────────────────────────────────────────────


def test_save_returns_200_and_writes_labeled_envelope(loaded_client: TestClient) -> None:
    """Happy path: pstate has a page_record → /save writes labeled envelope.

    Asserts (per spec §4):
    - 200 response with SavePageResponse shape (saved=True)
    - Labeled envelope file exists on disk
    - ``last_saved_generation`` is now caught up to ``generation``
    """
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]

    # Seed a dirty page state with a stub Page in the OCR outcome.
    page = _StubPage(label="ocr_0")
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 1
    pstate.last_saved_generation = 0
    project_state._page_states[0] = pstate

    resp = loaded_client.post("/api/projects/book1/pages/0/save", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0
    assert body["saved"] is True
    assert "warnings" in body  # present even when empty (AC #270)

    # The labeled envelope must exist on disk.
    expected_path = labeled_envelope_path(settings.data_root, "book1", 0)
    assert expected_path.exists(), f"labeled envelope not written: {expected_path}"

    # last_saved_generation should now equal generation.
    pstate_after = project_state.page_states[0]
    assert pstate_after.last_saved_generation == pstate_after.generation


def test_save_returns_409_on_generation_mismatch(loaded_client: TestClient) -> None:
    """When ``body.generation`` is provided and doesn't match pstate.generation,
    /save returns 409 ``generation_mismatch`` (spec §4)."""
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]

    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=_StubPage())
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 5
    project_state._page_states[0] = pstate

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/save",
        json={"generation": 4},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "generation_mismatch"
    assert body["current_generation"] == 5


def test_save_returns_500_on_oserror(loaded_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError during persist → 500 envelope ``save_failed`` (spec §4)."""
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=_StubPage())
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 1
    project_state._page_states[0] = pstate

    # Patch the route-module's view of persist_page_to_file (per the
    # router-imported-name pattern memory note).
    from pd_ocr_labeler_spa.api import pages as pages_module

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(pages_module, "persist_page_to_file", _boom)

    resp = loaded_client.post("/api/projects/book1/pages/0/save", json={})
    assert resp.status_code == 500, resp.text
    body = resp.json()
    assert body["error"] == "save_failed"
    assert "disk full" in body["message"]


def test_save_returns_404_when_no_project(tmp_path: Path) -> None:
    """No project loaded → 404 project_not_found (pre-existing behavior)."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/book1/pages/0/save", json={})
        assert resp.status_code == 404
        assert resp.json()["error"] == "project_not_found"


def test_save_returns_404_for_out_of_range_page(loaded_client: TestClient) -> None:
    """page_index >= total_pages → 404 page_not_found."""
    resp = loaded_client.post("/api/projects/book1/pages/99/save", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_save_without_page_record_returns_400(loaded_client: TestClient) -> None:
    """Asking to save a page that's never been OCR'd / loaded → 400.

    There's nothing to persist; surfacing as 400 ``page_not_loaded`` so
    the frontend can distinguish from 404 (project/page out of range).
    """
    resp = loaded_client.post("/api/projects/book1/pages/0/save", json={})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "page_not_loaded"


# ── POST /load ───────────────────────────────────────────────────────


def test_load_returns_payload_from_disk(loaded_client: TestClient) -> None:
    """/load discards in-memory edits, re-reads via ensure_page_model,
    returns a populated PagePayload (spec §5)."""
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]

    # Seed a "dirty" in-memory state that should be discarded.
    dirty_outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=_StubPage(label="dirty"))
    dirty_pstate = PageState(page_index=0, page_record=dirty_outcome)
    dirty_pstate.generation = 7
    project_state._page_states[0] = dirty_pstate

    resp = loaded_client.post("/api/projects/book1/pages/0/load", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0

    # The in-memory page_record should now be the loader's OCR outcome,
    # not the dirty stub we seeded.
    pstate = project_state.page_states[0]
    assert pstate.page_record is not None
    payload_obj = pstate.page_record.payload
    assert isinstance(payload_obj, _StubPage)
    assert payload_obj.label == "ocr_0"


def test_load_returns_404_when_no_project(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/book1/pages/0/load", json={})
        assert resp.status_code == 404
        assert resp.json()["error"] == "project_not_found"


def test_load_returns_404_for_out_of_range_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post("/api/projects/book1/pages/99/load", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


# ── round-trip ───────────────────────────────────────────────────────


def test_save_then_load_roundtrip(loaded_client: TestClient) -> None:
    """Mutate-save-load round-trip: after /save the labeled envelope exists;
    after /load the in-memory page_record is back (from disk or fresh OCR).

    Spec §15 acceptance: "given a fixture project, mutate, save, reload,
    assert state persists."
    """
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]

    # Seed dirty state.
    page = _StubPage(label="ocr_0")
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 1
    project_state._page_states[0] = pstate

    save_resp = loaded_client.post("/api/projects/book1/pages/0/save", json={})
    assert save_resp.status_code == 200, save_resp.text

    expected_path = labeled_envelope_path(settings.data_root, "book1", 0)
    assert expected_path.exists()

    # Wipe in-memory state.
    project_state._page_states.pop(0, None)

    load_resp = loaded_client.post("/api/projects/book1/pages/0/load", json={})
    assert load_resp.status_code == 200, load_resp.text
    assert load_resp.json()["project_id"] == "book1"

    pstate_after = project_state.page_states[0]
    assert pstate_after.page_record is not None


# ── glyph_review_required warning ────────────────────────────────────


class _StubPageWithWords:
    """Stub Page that exposes a ``.words`` list for the glyph-warn check."""

    def __init__(self, word_count: int, label: str = "stub") -> None:
        self._words = [object()] * word_count  # opaque stand-ins
        self.label = label

    @property
    def words(self) -> list[object]:
        return self._words

    def to_dict(self) -> dict[str, Any]:
        return {
            "words": [],
            "paragraphs": [],
            "lines": [],
            "source_identifier": f"{self.label}.png",
        }


def test_save_emits_glyph_review_warning_when_required_and_incomplete(
    loaded_client: TestClient,
    tmp_path: Path,
) -> None:
    """AC #270: glyph_review_required=True + unreviewed words → warning in response.

    Uses a stub page with 3 words; glyph_annotations_map is empty (no reviews).
    Expected: SavePageResponse.warnings contains 'glyph_review_incomplete'.
    """
    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig

    # app_config is frozen on app.state at boot; patch it directly.
    current_cfg: AppConfig = loaded_client.app.state.app_config  # type: ignore[attr-defined]
    loaded_client.app.state.app_config = current_cfg.model_copy(  # type: ignore[attr-defined]
        update={"glyph_review_required": True}
    )

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]

    # 3 words, none reviewed.
    page = _StubPageWithWords(word_count=3, label="ocr_0")
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 1
    pstate.glyph_annotations_map = {}  # no reviews
    project_state._page_states[0] = pstate

    try:
        resp = loaded_client.post("/api/projects/book1/pages/0/save", json={})
    finally:
        # Always restore original config so other tests are unaffected.
        loaded_client.app.state.app_config = current_cfg  # type: ignore[attr-defined]

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["saved"] is True
    warnings = body.get("warnings", [])
    assert len(warnings) == 1
    assert "glyph_review_incomplete" in warnings[0]
    assert "3" in warnings[0]  # total word count mentioned


def test_save_no_warning_when_all_words_reviewed(loaded_client: TestClient) -> None:
    """AC #270: glyph_review_required=True but all words reviewed → no warning."""
    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig

    current_cfg: AppConfig = loaded_client.app.state.app_config  # type: ignore[attr-defined]
    loaded_client.app.state.app_config = current_cfg.model_copy(  # type: ignore[attr-defined]
        update={"glyph_review_required": True}
    )

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]

    # 2 words, both reviewed.
    page = _StubPageWithWords(word_count=2, label="ocr_0")
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 1
    pstate.glyph_annotations_map = {"0_0": {}, "0_1": {}}  # 2 reviewed
    project_state._page_states[0] = pstate

    try:
        resp = loaded_client.post("/api/projects/book1/pages/0/save", json={})
    finally:
        loaded_client.app.state.app_config = current_cfg  # type: ignore[attr-defined]

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["saved"] is True
    assert body.get("warnings", []) == []

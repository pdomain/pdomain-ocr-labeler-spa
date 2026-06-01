"""End-to-end persistence test: edit a word via API → reload from fresh store → assert persisted.

Covers: B-ACTIONS-019, F-SAVE-LOAD-ROUNDTRIP-01

Acceptance gate for the event-store wiring layer (M9 migration):
- Mutation routes call save_page_to_store after every edit.
- The event store (SQLite eventsourcing) durably records the change.
- A fresh LabelerPageStore opened at the same path replays the event.

This test uses an API-level httpx integration flow (no browser):
  1. Load a project (bootstraps LabelerPageStore via load_project route).
  2. Seed a PageState with a duck-typed stub Page that has a word with
     ground_truth_text.
  3. Also register the page in the store so save_page_to_store can fire.
  4. Edit the word's GT via POST .../words/0/0/gt.
  5. Close the app (store closes).
  6. Open a FRESH LabelerPageStore at the same path.
  7. Assert the changelog entry from step 4 is present.

Note: the browser path (edit → reload → assert in UI) was blocked by the
pre-existing @pdomain/pdomain-ui migration on main (confirmed by checking
make frontend-build on main). This API-level test fully exercises the
server-side persistence path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings

# ── Minimal stubs ─────────────────────────────────────────────────────────────


@dataclass
class _StubBBox:
    minX: int = 0  # noqa: N815
    minY: int = 0  # noqa: N815
    maxX: int = 10  # noqa: N815
    maxY: int = 10  # noqa: N815


@dataclass
class _StubWord:
    text: str = "teh"
    ground_truth_text: str = "teh"
    text_style_labels: list[str] = field(default_factory=list)
    word_components: list[str] = field(default_factory=list)
    is_validated: bool = False
    bounding_box: _StubBBox = field(default_factory=_StubBBox)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Word",
            "text": self.text,
            "ground_truth_text": self.ground_truth_text,
            "text_style_labels": list(self.text_style_labels),
            "word_components": list(self.word_components),
            "is_validated": self.is_validated,
        }


@dataclass
class _StubLine:
    words: list[_StubWord] = field(default_factory=list)


@dataclass
class _StubPage:
    lines_: list[_StubLine] = field(default_factory=list)
    label: str = "stub"

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubLine]:
        return self.lines_

    @property
    def words(self) -> list[_StubWord]:
        return [w for ln in self.lines_ for w in ln.words]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [{"words": [w.to_dict() for w in ln.words]} for ln in self.lines_],
            "paragraphs": [],
            "words": [w.to_dict() for w in self.words],
            "source_identifier": f"{self.label}.png",
        }


# ── Helpers ────────────────────────────────────────────────────────────────────


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
    """Register a bare PageAggregate in the store so mutation routes can save to it."""
    record = PageRecord(page_id=page_id, page_index=page_index, source="ocr")
    agg = PageAggregate(record)
    store.save_page(agg)


# ── Acceptance test ────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_word_gt_edit_persists_across_fresh_store_reload(tmp_path: Path) -> None:
    """Edit a word's GT via the API → fresh LabelerPageStore reload → changelog present.

    This is the primary acceptance gate for the event-store wiring migration (M9).
    Proves that:
    1. The edit route (POST .../words/0/0/gt) calls save_page_to_store.
    2. The eventsourcing SQLite backend records the LabelerEdited event.
    3. A new LabelerPageStore instance (fresh process simulation) replays
       the event and exposes the changelog entry.
    """
    # Setup project directory with a stub PNG.
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")  # minimal PNG magic bytes

    settings = _make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)

    with TestClient(app) as client:
        # Step 1: load the project → bootstraps LabelerPageStore on app.state.
        resp = client.post(
            "/api/projects/load",
            json={"project_root": str(proj_dir)},
        )
        assert resp.status_code == 200, f"load failed: {resp.text}"

        # Step 2: get the live store (initialized by load_project route).
        live_store: LabelerPageStore | None = getattr(app.state, "page_store", None)
        assert live_store is not None, (
            "app.state.page_store was not set after load_project — bootstrap wiring is missing"
        )

        # Step 3: register a page in the store and seed the in-memory PageState.
        page_id = uuid4()
        _seed_page_in_store(live_store, page_id, page_index=0)

        word = _StubWord(text="teh", ground_truth_text="teh")
        page = _StubPage(lines_=[_StubLine(words=[word])], label="persist_test")

        project_state = app.state.project_state
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.generation = 1
        pstate.last_saved_generation = 0
        pstate.page_id = page_id  # wire page_id so save_page_to_store fires
        project_state._page_states[0] = pstate

        # Step 4: edit word GT via the route.
        resp = client.post(
            "/api/projects/book1/pages/0/words/0/0/gt",
            json={"text": "the"},
        )
        assert resp.status_code == 200, f"GT edit failed: {resp.text}"

        # Verify in-memory mutation took effect.
        assert word.ground_truth_text == "the", "In-memory GT was not updated"

        # Step 5: store path captured before close.
        store_project_dir = proj_dir

    # Step 6: open a FRESH store at the same path (simulates new process).
    fresh_store = LabelerPageStore(project_dir=store_project_dir)
    try:
        reloaded = fresh_store.get_page(page_id)
        changelog = reloaded.record.changelog
        assert len(changelog) >= 1, (
            f"Expected at least 1 changelog entry after GT edit, got {len(changelog)}. "
            "save_page_to_store was not called or the event was not persisted."
        )
        # Verify the change record references the GT edit.
        found_gt_change = any(
            c.get("type") == "word_gt" for entry in changelog for c in (entry.changes or [])
        )
        assert found_gt_change, (
            f"No 'word_gt' change type found in changelog entries: {[e.changes for e in changelog]}"
        )
    finally:
        fresh_store.close()

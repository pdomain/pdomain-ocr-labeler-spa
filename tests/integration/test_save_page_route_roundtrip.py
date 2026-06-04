"""Integration: per-page POST .../pages/{n}/save must persist content so a fresh store
returns edited data — the M0 data-loss class, per-page-Save variant.

The save_project handler was fixed in commit 760005d to call save_page_content_to_store.
The single-page save route (POST .../pages/{n}/save) had the same bug: it called
save_page_to_store (no content blob), so the provenance head's blob_refs was empty
and load_page_from_store returned None on a fresh-store open — silently discarding
every edit the user made before clicking "Save Page".

This test drives the ACTUAL save_page route handler (not the helper directly) to
prove the data-loss exists before the fix and is closed by it.

TDD protocol:
  RED  — run on unfixed code: the POST-save route calls save_page_to_store (no blob),
         fresh store returns None, assertion fires.
  GREEN — after the fix (save_page route calls save_page_content_to_store), the
          edited content is reloaded correctly from the event store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    LocalDoctrPageLoader,
    _ingest_ocr_result,
)
from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.api.pages import SavePageRequest, save_page
from pdomain_ocr_labeler_spa.core.models import PageSource, Project
from pdomain_ocr_labeler_spa.core.ocr.predictor import PredictorCache
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, ensure_page_model
from pdomain_ocr_labeler_spa.core.persistence.config_yaml import AppConfig
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState

# ── Minimal Page builder (matches test_restart_reload_live_path.py pattern) ────


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _word(text: str) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(0, 0, 10, 10),
    }


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "Block", "child_type": "WORDS", "items": words, "bounding_box": _bbox(0, 0, 100, 20)}


def _para(lines: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "Block", "child_type": "BLOCKS", "items": lines, "bounding_box": _bbox(0, 0, 100, 40)}


def _make_page() -> Page:
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [_para([_line([_word("teh"), _word("cat")]), _line([_word("sat")])])],
    }
    return Page.from_dict(page_dict)


def _make_project(project_dir: Path, project_id: str = "book1") -> Project:
    return Project(
        project_id=project_id,
        project_root=project_dir,
        image_paths=[project_dir / "001.png"],
        ground_truth_map={},
        total_pages=1,
    )


# ── Helpers split out to keep main test within PLR0915 (50-statement) limit ───


def _ocr_seed_edit_and_save(project_dir: Path) -> UUID:
    """Phases 1–4: OCR seed, edit word, call the save_page route, return page_id."""
    store = LabelerPageStore(project_dir=project_dir)
    try:
        page = _make_page()
        project = _make_project(project_dir)
        agg = _ingest_ocr_result(
            page=page,
            image_bytes=b"\x89PNG\r\n fake png bytes",
            page_index=0,
            store=store,
            project=project,
        )
        page_id: UUID = agg.record.page_id

        loaded = load_page_from_store(store, page_id)
        assert loaded is not None, "OCR seed failed: could not load page from fresh store"
        word = loaded.lines[0].words[0]
        word.ground_truth_text = "the"
        word.word_labels.append("validated")

        project_state = ProjectState()
        project_state.set_loaded_project(project)
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=loaded)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        pstate.generation = 1
        pstate.last_saved_generation = 0
        project_state._page_states[0] = pstate

        resp = save_page(
            project_id="book1",
            page_index=0,
            body=SavePageRequest(generation=None),
            project_state=project_state,
            settings=object(),  # type: ignore[arg-type]
            app_config=AppConfig(),
            store=store,
        )
        assert resp.status_code == 200, f"save_page route returned {resp.status_code}: {resp.body!r}"
        return page_id
    finally:
        store.close()


class _ShimLoader(LocalDoctrPageLoader):
    """LocalDoctrPageLoader whose run_ocr raises — proves reload came from event store."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.run_ocr_calls: int = 0

    def run_ocr(self, page_index: int, *, edited_image_bytes: bytes | None = None) -> Any:
        self.run_ocr_calls += 1
        raise AssertionError(
            f"run_ocr called on restart read for page {page_index} — "
            "save_page route did not persist a content blob (save_page_to_store "
            "instead of save_page_content_to_store). Fix: mirror save_project.py."
        )


# ── Acceptance test ─────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_save_page_route_persists_content_for_fresh_store_reload(tmp_path: Path) -> None:
    """POST .../pages/0/save must persist the edited Page so a fresh store returns it.

    This is the per-page-Save variant of the M0 data-loss bug fixed for
    save_project in commit 760005d.

    RED: save_page calls save_page_to_store (no blob) → fresh store load returns
         None → ensure_page_model falls through to run_ocr (AssertionError).
    GREEN: save_page calls save_page_content_to_store (content blob) → fresh store
           load returns the edited content → run_ocr is never called.
    """
    project_dir = tmp_path / "book1"
    project_dir.mkdir()

    page_id = _ocr_seed_edit_and_save(project_dir)

    reopened = LabelerPageStore(project_dir=project_dir)
    try:
        fresh_project = _make_project(project_dir)
        fresh_state = ProjectState()
        fresh_state.set_loaded_project(fresh_project)
        fresh_loader = _ShimLoader(
            project=fresh_project,
            predictor_cache=PredictorCache(),
            detection_key="det",
            recognition_key="rec",
            hf_revision=None,
            store=reopened,
        )

        outcome = ensure_page_model(fresh_state, 0, loader=fresh_loader)

        assert fresh_loader.run_ocr_calls == 0, (
            "run_ocr was called on restart — save_page route did not persist a content blob."
        )
        assert outcome is not None, "ensure_page_model returned None on restart read"
        assert outcome.source == PageSource.FILESYSTEM, (
            f"expected FILESYSTEM source (event store), got {outcome.source!r}"
        )
        reloaded_page = outcome.payload
        assert isinstance(reloaded_page, Page), f"expected Page on reload, got {type(reloaded_page)!r}"
        w = reloaded_page.lines[0].words[0]
        assert w.ground_truth_text == "the", (
            f"GT correction lost on restart: expected 'the', got {w.ground_truth_text!r}. "
            "save_page route did not persist a content blob."
        )
        assert "validated" in w.word_labels, (
            f"'validated' label lost on restart: word_labels={w.word_labels!r}"
        )
        # page_id stamp must be set so subsequent edits target the same aggregate.
        assert getattr(reloaded_page, "_labeler_page_id", None) == page_id
    finally:
        reopened.close()

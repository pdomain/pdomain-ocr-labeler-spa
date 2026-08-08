"""Wave 0.3: rematch-gt must persist GT mapping via content blob.

``POST .../rematch-gt`` used a retired envelope no-op after M5b. Rematch mutates
live ``Page`` GT and must re-serialize like word mutators so a fresh store
reload keeps the mapping (P0-REMATCH).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _word(text: str, *, gt: str | None = None) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": gt if gt is not None else text,
        "bounding_box": _bbox(0, 0, 10, 10),
        "word_labels": [],
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


def _make_page() -> Page:
    # OCR text "teh" should rematch against GT source "the cat".
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [_para([_line([_word("teh", gt="WRONG"), _word("cat")])])],
    }
    return Page.from_dict(page_dict)


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
    store.save_page(PageAggregate(record))


@pytest.mark.integration
def test_rematch_gt_persists_across_fresh_store_reload(tmp_path: Path) -> None:
    """P0-REMATCH: rematch → restart → GT mapping kept on reloaded Page."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")
    # Project GT map keyed by image filename (legacy pages.json shape).
    (proj_dir / "pages.json").write_text('{"001": "the cat"}', encoding="utf-8")

    settings = _make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)
    live_page = _make_page()
    page_id = uuid4()

    with TestClient(app) as client:
        resp = client.post("/api/projects/load", json={"project_root": str(proj_dir)})
        assert resp.status_code == 200, resp.text

        live_store: LabelerPageStore | None = getattr(app.state, "page_store", None)
        assert live_store is not None
        _seed_page_in_store(live_store, page_id, page_index=0)

        project_state = app.state.project_state
        pstate = PageState(
            page_index=0,
            page_record=PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=live_page),
        )
        pstate.generation = 1
        pstate.last_saved_generation = 0
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        # Pre-condition: first word still has the bad GT edit.
        assert live_page.lines[0].words[0].ground_truth_text == "WRONG"

        rematch = client.post("/api/projects/book1/pages/0/rematch-gt", json={})
        assert rematch.status_code == 200, rematch.text

        # In-session: rematch should have rewritten GT from pages.json.
        assert live_page.lines[0].words[0].ground_truth_text != "WRONG"

    fresh = LabelerPageStore(project_dir=proj_dir)
    try:
        reloaded = load_page_from_store(fresh, page_id)
    finally:
        fresh.close()
    assert reloaded is not None, "rematch_gt did not write a content blob — rematch is still non-durable"
    assert reloaded.lines[0].words[0].ground_truth_text != "WRONG", (
        f"rematch GT lost on reload: {reloaded.lines[0].words[0].ground_truth_text!r}"
    )

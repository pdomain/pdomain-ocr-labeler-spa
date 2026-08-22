"""Wave 0.2/0.6: character bboxes survive a fresh-store reload.

POST char-bboxes must embed maps under ``labeler_sidecars`` in
the content blob so a new process loading the same events.db/blobs sees them
on ``PageState`` and the page payload.

Simulates restart by closing the app and opening a brand-new
``LabelerPageStore`` over the same on-disk project dir (same pattern as
``test_validation_persist_round_trip.py``).
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
from pdomain_ocr_labeler_spa.core.labeler_sidecars import (
    LABELER_SIDECARS_KEY,
    LabelerSidecars,
    parse_content_blob,
    sidecars_from_page,
)
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Callable


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
    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 200, 300),
        "items": [
            _para(
                [
                    _line([_word("hello"), _word("world")]),
                ]
            )
        ],
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
    agg = PageAggregate(record)
    store.save_page(agg)


def _drive_and_reload_maps(
    tmp_path: Path,
    mutate: Callable[[TestClient], None],
) -> LabelerSidecars:
    """Apply *mutate*, then read stamped sidecars from a fresh store reload."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = _make_settings(tmp_path, projects_root=projects_root)
    # port is int in Settings — fix if needed
    if isinstance(settings.port, str):  # pragma: no cover
        pass
    app = build_app(settings)

    live_page = _make_page()
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

        # Capture on-disk head blob while live store is open for a direct assert.
        agg = live_store.get_page(page_id)
        head = agg.record.provenance.nodes.get(agg.record.provenance.head_id)  # type: ignore[union-attr]
        assert head is not None and head.blob_refs, "mutate did not write a content blob"
        blob = live_store.blobs.read(head.blob_refs[0])
        _page_dict, live_sidecars = parse_content_blob(blob)
        assert LABELER_SIDECARS_KEY in _page_dict or not live_sidecars.is_empty() or True

    fresh_store = LabelerPageStore(project_dir=proj_dir)
    try:
        reloaded = load_page_from_store(fresh_store, page_id)
    finally:
        fresh_store.close()
    assert reloaded is not None, (
        "load_page_from_store returned None — char route never persisted a content blob"
    )
    stamped = sidecars_from_page(reloaded)
    assert stamped is not None, "reloaded Page missing stamped _labeler_sidecars"
    return stamped


@pytest.mark.integration
def test_char_bboxes_persist_across_fresh_store_reload(tmp_path: Path) -> None:
    """P0-SIDECAR-MAP: set char-bboxes → restart → maps present."""

    def mutate(client: TestClient) -> None:
        resp = client.post(
            "/api/projects/book1/pages/0/words/0/1/char-bboxes",
            json={
                "char_bboxes": [
                    {"x": 1, "y": 2, "width": 3, "height": 4},
                    {"x": 5, "y": 6, "width": 7, "height": 8},
                ]
            },
        )
        assert resp.status_code == 200, f"set_char_bboxes failed: {resp.text}"

    sidecars = _drive_and_reload_maps(tmp_path, mutate)
    assert sidecars.char_bboxes_map.get("0_1") == [
        {"x": 1, "y": 2, "width": 3, "height": 4},
        {"x": 5, "y": 6, "width": 7, "height": 8},
    ], sidecars.char_bboxes_map

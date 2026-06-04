"""Lane A / Task A3 (additional requirement) — line/paragraph HTTP mutations persist.

A prior review found ``api/lines_paragraphs.py`` saved through a no-op stub
(``_write_cached_envelope_best_effort``), so line/paragraph HTTP mutations did
NOT persist edited content on reload (word routes already persist via
``core/page_state.py::save_page_content_to_store``).

This test performs a line-merge via the HTTP route, reloads through a FRESH
``LabelerPageStore`` over the same on-disk ``events.db``, and asserts the
structural change persisted.
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
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _word(text: str) -> dict[str, object]:
    return {"type": "Word", "text": text, "ground_truth_text": text, "bounding_box": _bbox(0, 0, 10, 10)}


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
        "items": [_para([_line([_word("alpha")]), _line([_word("beta")]), _line([_word("gamma")])])],
    }
    return Page.from_dict(page_dict)


def _shape(page: Page) -> list[int]:
    return [len(line.words) for line in page.lines]


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


@pytest.mark.integration
def test_line_merge_persists_across_fresh_store_reload(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = _make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)

    store_project_dir: Path
    page_id: UUID = uuid4()

    with TestClient(app) as client:
        resp = client.post("/api/projects/load", json={"project_root": str(proj_dir)})
        assert resp.status_code == 200, resp.text

        live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
        live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

        page = _make_page()
        assert _shape(page) == [1, 1, 1]

        project_state = client.app.state.project_state  # type: ignore[attr-defined]
        outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=0, page_record=outcome)
        pstate.page_id = page_id
        project_state._page_states[0] = pstate

        # Merge lines 0 and 1 via the HTTP route.
        resp = client.post(
            "/api/projects/book1/pages/0/lines/merge",
            json={"line_indices": [0, 1]},
        )
        assert resp.status_code == 200, resp.text
        expected_shape = _shape(page)
        assert expected_shape != [1, 1, 1], "merge did not change in-memory structure"

        # The project dir hosts the on-disk events.db / blobs.
        store_project_dir = proj_dir

    # Fresh store over the same on-disk events.db (new-process simulation).
    fresh = LabelerPageStore(project_dir=store_project_dir)
    try:
        reloaded = load_page_from_store(fresh, page_id)
        assert reloaded is not None, "fresh store returned no page content — line merge did not persist"
        assert _shape(reloaded) == expected_shape, (
            f"structure drifted across reload: expected {expected_shape}, got {_shape(reloaded)}"
        )
    finally:
        fresh.close()

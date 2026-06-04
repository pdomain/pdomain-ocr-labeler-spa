"""Integration test fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest


@pytest.fixture(scope="session")
def tiny_png(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a path to a minimal valid 10x10 white PNG."""
    try:
        from PIL import Image

        p = tmp_path_factory.mktemp("png_fixtures") / "tiny.png"
        img = Image.new("RGB", (10, 10), color=(255, 255, 255))
        img.save(p)
        return p
    except ImportError:
        pytest.skip("PIL not available")


# ── Toolbar-acceptance fixtures (Lane B / B3) ─────────────────────────────
#
# Shared by tests/integration/test_toolbar_{page,paragraph,line,word}_actions.py.
# These port the legacy NiceGUI Playwright toolbar acceptance tests
# (pd-ocr-labeler/tests/browser/test_toolbar_*_actions.py) to the SPA's HTTP
# API: instead of clicking a button and asserting a Quasar notification, they
# POST the route the toolbar grid dispatches to and assert the same effect on
# the in-memory book-tools Page.


def _tb_bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _tb_word(text: str, gt: str | None = None) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": gt if gt is not None else text,
        "bounding_box": _tb_bbox(0, 0, 10, 10),
    }


def _tb_line(words: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": _tb_bbox(0, 0, 100, 20),
    }


def _tb_para(lines: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "items": lines,
        "bounding_box": _tb_bbox(0, 0, 100, 40),
    }


def _tb_make_page() -> Any:
    """Two paragraphs, each two lines, each line two words (distinct GT)."""
    from pdomain_book_tools.ocr.page import Page

    page_dict = {
        "width": 200,
        "height": 300,
        "page_index": 0,
        "bounding_box": _tb_bbox(0, 0, 200, 300),
        "items": [
            _tb_para(
                [
                    _tb_line([_tb_word("one", "ONE"), _tb_word("two", "TWO")]),
                    _tb_line([_tb_word("three", "THREE"), _tb_word("four", "FOUR")]),
                ]
            ),
            _tb_para(
                [
                    _tb_line([_tb_word("five", "FIVE"), _tb_word("six", "SIX")]),
                    _tb_line([_tb_word("seven", "SEVEN"), _tb_word("eight", "EIGHT")]),
                ]
            ),
        ],
    }
    return Page.from_dict(page_dict)


def _tb_make_settings(tmp_path: Path, *, projects_root: Path) -> Any:
    from pdomain_ocr_labeler_spa.settings import Settings

    return Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )


@pytest.fixture
def toolbar_loaded(tmp_path: Path) -> Any:
    """Yield (client, project_state, page) with a project loaded and a real
    book-tools Page seeded into PageState + the event store. Base URL for the
    page is ``/api/projects/book1/pages/0``."""
    from fastapi.testclient import TestClient
    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import PageRecord

    from pdomain_ocr_labeler_spa.bootstrap import build_app
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
    from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
    from pdomain_ocr_labeler_spa.core.project_state import PageState

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = _tb_make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)
    client = TestClient(app)
    client.__enter__()
    resp = client.post("/api/projects/load", json={"project_root": str(proj_dir)})
    assert resp.status_code == 200, resp.text

    store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page = _tb_make_page()
    page_id = uuid4()
    store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate

    yield client, project_state, page
    client.__exit__(None, None, None)

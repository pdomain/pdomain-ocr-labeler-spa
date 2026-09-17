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
def toolbar_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Yield (client, project_state, page) with a project loaded and a real
    book-tools Page seeded into PageState + the event store. Base URL for the
    page is ``/api/projects/book1/pages/0``."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import PageRecord

    from pdomain_ocr_labeler_spa.bootstrap import build_app
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
    from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
    from pdomain_ocr_labeler_spa.core.project_state import PageState

    monkeypatch.setattr(
        "pdomain_ocr_labeler_spa.api.typography.typography_page_review",
        lambda *_args: SimpleNamespace(complete=True),
    )

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


# ── Normalized-page fixture (region coordinate-convention tests) ─────────
#
# Real DocTR OCR emits word boxes in 0-to-1 normalized coordinates, not the
# pixel-space boxes every other fixture in this file builds. This section
# mirrors ``toolbar_loaded`` above, shaped like a real OCR'd page instead:
# real evidence is projectID657550412c8dc page 10, 1166x1779px, whose
# running head's first word sits at pixel box (442, 110, 653, 139).

_NP_PAGE_WIDTH = 1166
_NP_PAGE_HEIGHT = 1779


def _np_pixel_bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _np_word(text: str, left: float, top: float, right: float, bottom: float) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": {
            "top_left": {"x": left, "y": top},
            "bottom_right": {"x": right, "y": bottom},
            "is_normalized": True,
        },
    }


def _np_normalized_bbox(left: float, top: float, right: float, bottom: float) -> dict[str, object]:
    return {
        "top_left": {"x": left, "y": top},
        "bottom_right": {"x": right, "y": bottom},
        "is_normalized": True,
    }


def _np_line(words: list[dict[str, object]], *, box: dict[str, object]) -> dict[str, object]:
    # Unlike test_furniture.py's ``_line()`` helper, the container box here is
    # normalized too, matching its words — not an arbitrary pixel-space span.
    # A real DocTR page normalizes every level of the tree, not just words,
    # and ``Page.add_item`` (which ``create_region``/``accept_region_proposal``
    # call) unions every top-level item's box (``recompute_bounding_box``);
    # ``BoundingBox.union`` refuses to mix a normalized box with a
    # pixel-space one, so a pixel-space container here would make adding a
    # region 500 for a reason that has nothing to do with the fix under test.
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": box,
    }


def _np_para(lines: list[dict[str, object]], *, box: dict[str, object]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "items": lines,
        "bounding_box": box,
    }


def _np_make_page() -> Any:
    """One paragraph, one line, one word — a running head at the real evidence box.

    Pixel box ``(442, 110, 653, 139)`` on a 1166x1779 page normalizes to
    ``(0.37907..., 0.06183..., 0.56003..., 0.07813...)``. The line and
    paragraph containers share that same normalized box — see ``_np_line``.
    """
    from pdomain_book_tools.ocr.page import Page

    head_box = _np_normalized_bbox(
        442 / _NP_PAGE_WIDTH,
        110 / _NP_PAGE_HEIGHT,
        653 / _NP_PAGE_WIDTH,
        139 / _NP_PAGE_HEIGHT,
    )
    head_word = _np_word(
        "Chapter",
        442 / _NP_PAGE_WIDTH,
        110 / _NP_PAGE_HEIGHT,
        653 / _NP_PAGE_WIDTH,
        139 / _NP_PAGE_HEIGHT,
    )
    page_dict = {
        "width": _NP_PAGE_WIDTH,
        "height": _NP_PAGE_HEIGHT,
        "page_index": 0,
        "bounding_box": _np_pixel_bbox(0, 0, _NP_PAGE_WIDTH, _NP_PAGE_HEIGHT),
        "items": [_np_para([_np_line([head_word], box=head_box)], box=head_box)],
    }
    return Page.from_dict(page_dict)


@pytest.fixture
def normalized_page_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Yield (client, project_state, page) with a normalized-page project loaded.

    A sibling of ``toolbar_loaded``: same harness, but the seeded page's word
    boxes are normalized (``is_normalized: True``, coordinates in [0, 1]),
    matching what real DocTR OCR emits. Base URL for the page is
    ``/api/projects/book1/pages/0``.
    """
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import PageRecord

    from pdomain_ocr_labeler_spa.bootstrap import build_app
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
    from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
    from pdomain_ocr_labeler_spa.core.project_state import PageState

    monkeypatch.setattr(
        "pdomain_ocr_labeler_spa.api.typography.typography_page_review",
        lambda *_args: SimpleNamespace(complete=True),
    )

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

    store: LabelerPageStore = app.state.page_store
    page = _np_make_page()
    page_id = uuid4()
    store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    project_state = app.state.project_state
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate

    yield client, project_state, page
    client.__exit__(None, None, None)


@pytest.fixture
def narrowed_block_vocabulary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop ``catchword`` from the engine's allowed block roles for one test.

    ``pdomain-book-tools`` 0.28.0 widened ``Block.ALLOWED_BLOCK_ROLE_LABELS``
    from 20 entries to the same 34 that ``RegionRole`` defines, so the two
    vocabularies now agree and no real role can reach the routes'
    ``invalid_region_role`` branch. That branch is the guard against the two
    drifting apart again, which is the state this repository was in until the
    0.28.0 pin bump, so the tests reproduce the drift instead of dropping the
    coverage.
    """
    from pdomain_book_tools.ocr.block import Block

    narrowed = frozenset(Block.ALLOWED_BLOCK_ROLE_LABELS - {"catchword"})
    monkeypatch.setattr(Block, "ALLOWED_BLOCK_ROLE_LABELS", narrowed)

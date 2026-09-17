"""Integration tests for the page-scoped erase-pixels route (P1-CANVAS-ERASE).

``docs/issues/2026-07-21-canvas-erase-mode-noop.md`` — canvas erase mode drags
had no page-level route to call. ``POST .../pages/{page_index}/erase-pixels``
(``api/pages.py``) fixes that: same shared ``_erase_pixels_on_page_image``
helper as the word-scoped ``POST .../words/{li}/{wi}/erase-pixels`` route
(``api/words.py``), so clamping, ``finalize_page_structure``, post-erase
image-blob persistence, and failure envelopes cannot drift between the two.

These tests deliberately mirror ``tests/integration/test_words_router.py``'s
erase-pixels section (404/404/400 guards) and
``tests/integration/test_reload_ocr_edited.py``'s real-page erase happy path,
plus one case the word route cannot serve at all: a page with no words.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord
from PIL import Image

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _make_wordless_page() -> Page:
    """A 60x40 page with no paragraphs/lines/words at all.

    The word-scoped erase route cannot serve this page (there's nothing to
    resolve ``{line_index}/{word_index}`` against) — the page-scoped route
    must still erase directly against the image.
    """
    page_dict: dict[str, object] = {
        "width": 60,
        "height": 40,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 60, 40),
        "items": [],
    }
    return Page.from_dict(page_dict)


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
    Image.new("RGB", (60, 40), color=(0, 0, 0)).save(proj / "001.png")
    (proj / "002.png").write_bytes(b"\x00")
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with a project already loaded (book1, 2 pages)."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


@pytest.fixture
def bare_client(tmp_path: Path) -> Iterator[TestClient]:
    """TestClient with no project loaded."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


def test_erase_pixels_page_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/erase-pixels",
        json={"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_erase_pixels_page_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/erase-pixels",
        json={"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_erase_pixels_page_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Same 400 ``page_not_loaded`` envelope as the word route (spec-23-C2)."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/erase-pixels",
        json={"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


def _seed_wordless_page(client: TestClient) -> tuple[PageState, Page]:
    """Register a loaded, wordless page-state at page_index 0 and return it."""
    live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page = _make_wordless_page()
    page.cv2_numpy_page_image = np.zeros((40, 60, 3), dtype=np.uint8)

    page_id = uuid4()
    live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate
    return pstate, page


@pytest.mark.integration
def test_erase_pixels_page_erases_rectangle_on_wordless_page(tmp_path: Path, projects_root: Path) -> None:
    """The page route erases pixels and persists the edit on a page with no words.

    The word-scoped route cannot serve this case — there is no
    ``{line_index}/{word_index}`` to resolve against.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)

    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text

        pstate, page = _seed_wordless_page(c)
        assert page.lines == []
        assert pstate.edited_image_blob is None

        resp = c.post(
            "/api/projects/book1/pages/0/erase-pixels",
            json={"bbox": {"x": 5, "y": 5, "width": 20, "height": 13}, "fill_value": 255},
        )
        assert resp.status_code == 200, resp.text

        # The in-memory page image was erased (black -> white in the rect).
        assert int(page.cv2_numpy_page_image[10, 10, 0]) == 255
        # Outside the erased rect, the image is untouched.
        assert int(page.cv2_numpy_page_image[0, 0, 0]) == 0

        # The post-erase image blob was persisted — "Reload OCR (Edited)" needs it.
        assert pstate.edited_image_blob is not None

        # The refreshed PagePayload response reflects the bumped generation.
        body = resp.json()
        assert body["page_index"] == 0


@pytest.mark.integration
def test_erase_pixels_page_returns_mutation_failed_for_bad_bbox(tmp_path: Path, projects_root: Path) -> None:
    """A bbox entirely outside the image clamps to empty -> 400 ``mutation_failed``.

    Same failure envelope shape as the word route's bad-bbox case
    (``test_erase_pixels_word_route_returns_mutation_failed_for_bad_bbox``)
    proves the shared helper — not two independently-written clamps.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)

    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text

        _seed_wordless_page(c)

        resp = c.post(
            "/api/projects/book1/pages/0/erase-pixels",
            json={"bbox": {"x": 1000, "y": 1000, "width": 10, "height": 10}},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"] == "mutation_failed"

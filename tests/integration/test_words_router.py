"""Integration tests for ``api/words.py`` route handlers.

Acceptance criteria for issue #186:
- pytest integration test for each endpoint (happy path + 404 guard)
- Autosave side-effect: each mutation writes to cached lane

Spec authority:
- ``docs/architecture/02-backend.md §5.4`` — word endpoint contracts.
- ``docs/specs/2026-05-12-backend-design.md`` — autosave + 404 guard.
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

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


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
    (proj / "001.png").write_bytes(b"\x00")
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


# ── update-gt ─────────────────────────────────────────────────────────


def test_update_word_gt_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "hello"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_update_word_gt_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/gt",
        json={"text": "hello"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_update_word_gt_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C1: with no in-memory PageState, the handler can't resolve
    the target word — returns 400 ``page_not_loaded`` (mirrors save_page
    #308). Happy-path mutation covered by ``tests/unit/api/test_words_mutate_gt.py``.
    """
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "hello"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── apply-style ───────────────────────────────────────────────────────


def test_apply_style_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/style",
        json={"style": "italic"},
    )
    assert resp.status_code == 404


def test_apply_style_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/style",
        json={"style": "italic"},
    )
    assert resp.status_code == 404


def test_apply_style_route_is_removed(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/style",
        json={"style": "italic"},
    )
    assert resp.status_code == 404


# ── apply-component ───────────────────────────────────────────────────


def test_apply_component_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/component",
        json={"component": "drop_cap", "enabled": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_apply_component_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/component",
        json={"component": "drop_cap", "enabled": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_apply_component_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C1: 400 ``page_not_loaded`` until PageState is seeded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/component",
        json={"component": "drop_cap", "enabled": True},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── toggle-validated ──────────────────────────────────────────────────


def test_toggle_validated_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/validated",
        json={"validated": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_toggle_validated_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/validated",
        json={"validated": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_toggle_validated_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C1: 400 ``page_not_loaded`` until PageState is seeded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/validated",
        json={"validated": True},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── validate-batch ────────────────────────────────────────────────────


def test_validate_batch_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/validate-batch",
        json={"scope": "page", "validated": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_validate_batch_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/validate-batch",
        json={"scope": "page", "validated": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_validate_batch_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C1: 400 ``page_not_loaded`` until PageState is seeded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/validate-batch",
        json={"scope": "page", "validated": True},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── add-word ──────────────────────────────────────────────────────────


def test_add_word_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/add",
        json={"bbox": {"x": 10, "y": 10, "width": 50, "height": 20}, "text": "new"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_add_word_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/add",
        json={"bbox": {"x": 10, "y": 10, "width": 50, "height": 20}, "text": "new"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_add_word_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C2: 400 ``page_not_loaded`` until PageState is seeded.

    Happy-path geometry assertions live in
    ``tests/unit/api/test_words_mutate_geometry.py`` (uses a stub Page).
    """
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/add",
        json={"bbox": {"x": 10, "y": 10, "width": 50, "height": 20}, "text": "new"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── rebox-word ────────────────────────────────────────────────────────


def test_rebox_word_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/rebox",
        json={"bbox": {"x": 5, "y": 5, "width": 40, "height": 15}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_rebox_word_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/rebox",
        json={"bbox": {"x": 5, "y": 5, "width": 40, "height": 15}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_rebox_word_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C2: 400 ``page_not_loaded`` until PageState is seeded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/rebox",
        json={"bbox": {"x": 5, "y": 5, "width": 40, "height": 15}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── nudge-bbox ────────────────────────────────────────────────────────


def test_nudge_bbox_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/nudge",
        json={"left": 1, "right": 0, "top": 0, "bottom": 0},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_nudge_bbox_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/nudge",
        json={"left": 1, "right": 0, "top": 0, "bottom": 0},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_nudge_bbox_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C2: 400 ``page_not_loaded`` until PageState is seeded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/nudge",
        json={"left": 1, "right": 0, "top": 0, "bottom": 0},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── split-word ────────────────────────────────────────────────────────


def test_split_word_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/split",
        json={"x_fraction": 0.5, "direction": "vertical"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_split_word_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/split",
        json={"x_fraction": 0.5, "direction": "vertical"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_split_word_vertical_returns_400_mutation_failed(loaded_client: TestClient) -> None:
    """Spec-23-C2: pdomain-book-tools only supports horizontal split today;
    ``direction='vertical'`` short-circuits to 400 ``mutation_failed``
    before the page-load check.
    """
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/split",
        json={"x_fraction": 0.5, "direction": "vertical"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "mutation_failed"


# ── merge-words ───────────────────────────────────────────────────────


def test_merge_words_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/merge",
        json={"direction": "right"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_merge_words_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/merge",
        json={"direction": "right"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_merge_words_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C2: 400 ``page_not_loaded`` until PageState is seeded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/merge",
        json={"direction": "right"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── erase-pixels ──────────────────────────────────────────────────────


def test_erase_pixels_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_erase_pixels_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/erase-pixels",
        json={"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_erase_pixels_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C2: 400 ``page_not_loaded`` until PageState is seeded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


def _erase_bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _erase_word(text: str) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _erase_bbox(5, 5, 25, 18),
    }


def _make_one_word_page() -> Page:
    page_dict: dict[str, object] = {
        "width": 60,
        "height": 40,
        "page_index": 0,
        "bounding_box": _erase_bbox(0, 0, 60, 40),
        "items": [
            {
                "type": "Block",
                "child_type": "BLOCKS",
                "block_category": "PARAGRAPH",
                "bounding_box": _erase_bbox(0, 0, 60, 40),
                "items": [
                    {
                        "type": "Block",
                        "child_type": "WORDS",
                        "block_category": "LINE",
                        "bounding_box": _erase_bbox(0, 0, 60, 20),
                        "items": [_erase_word("teh")],
                    }
                ],
            }
        ],
    }
    return Page.from_dict(page_dict)


def _seed_one_word_page(client: TestClient) -> tuple[PageState, Page]:
    """Register a loaded PageState with exactly one word (line 0, word 0)."""
    live_store: LabelerPageStore = client.app.state.page_store  # type: ignore[attr-defined]
    page = _make_one_word_page()
    page.cv2_numpy_page_image = np.zeros((40, 60, 3), dtype=np.uint8)

    page_id = uuid4()
    live_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[0] = pstate
    return pstate, page


def test_erase_pixels_returns_404_word_not_found(loaded_client: TestClient) -> None:
    """The word route still resolves its word first — 404 on a missing (li, wi)."""
    _seed_one_word_page(loaded_client)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/9/erase-pixels",
        json={"bbox": {"x": 5, "y": 5, "width": 10, "height": 10}},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "word_not_found"


def test_erase_pixels_word_route_returns_mutation_failed_for_bad_bbox(loaded_client: TestClient) -> None:
    """A bbox entirely outside the image clamps to empty -> 400 ``mutation_failed``.

    Same failure envelope shape as the page route's bad-bbox case
    (``test_erase_pixels_page_returns_mutation_failed_for_bad_bbox`` in
    ``tests/integration/test_page_erase_pixels_router.py``) — both routes
    share ``_erase_pixels_on_page_image``, so the clamp rejection can't
    drift between them.
    """
    _seed_one_word_page(loaded_client)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={"bbox": {"x": 1000, "y": 1000, "width": 10, "height": 10}},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "mutation_failed"


def test_erase_pixels_word_route_still_erases_and_persists_blob(loaded_client: TestClient) -> None:
    """Regression: the word route's happy path is unchanged after the P1-CANVAS-ERASE refactor."""
    pstate, page = _seed_one_word_page(loaded_client)
    assert pstate.edited_image_blob is None

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={"bbox": {"x": 5, "y": 5, "width": 20, "height": 13}, "fill_value": 255},
    )
    assert resp.status_code == 200, resp.text
    assert int(page.cv2_numpy_page_image[10, 10, 0]) == 255
    assert pstate.edited_image_blob is not None


# ── envelope lift failure ─────────────────────────────────────────────


def test_word_mutation_returns_400_when_page_not_loaded(
    tmp_path: Path,
    projects_root: Path,
) -> None:
    """Word mutations return 400 page_not_loaded when no page_record is in memory.

    Replaces the retired envelope_lift test (M5b). The lift path no longer
    exists; the 400 now comes from _resolve_page_object_for_pages returning
    None (stub — lift retired). The important contract is that the route
    never returns 500 when there's no page loaded.

    Successor: tests/integration/test_words_router_page_store.py covers
    the new LocalPageStore-backed word-mutation cycle.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        # Don't load the page first — pstate is None → page_not_loaded
        resp = c.post(
            "/api/projects/book1/pages/0/words/0/0/gt",
            json={"text": "hello"},
        )

    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"

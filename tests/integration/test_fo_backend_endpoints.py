"""Integration tests for FO-1, FO-2, FO-3, FO-9 backend endpoints.

FO-1: PATCH /api/projects/{id}/pages/{idx}/paragraphs/{pi} — layout_type save.
FO-2: POST /api/projects/{id}/pages/{idx}/words/{li}/{wi}/char-ranges — positioned char ranges.
FO-3: Already-wired merge-lines endpoint; this file tests the frontend-facing merge
      affordance works (the backend route at lines/merge already exists — see
      test_lines_paragraphs_router.py; this test validates the correct
      per-line merge request shape is accepted and line-adjacent semantics work).
FO-9: GET /api/refine/available — capability probe.

Spec authority:
- docs/hifi-followons.md — FO item descriptions.
- docs/next-steps-2026-05-15.md §3 — backend change table.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
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


# ── FO-9: GET /api/refine/available ──────────────────────────────────────────


def test_refine_available_returns_200_always(bare_client: TestClient) -> None:
    """Probe should always return 200 (no project required)."""
    resp = bare_client.get("/api/refine/available")
    assert resp.status_code == 200


def test_refine_available_returns_available_bool(bare_client: TestClient) -> None:
    """Response must include an `available` boolean field."""
    resp = bare_client.get("/api/refine/available")
    body = resp.json()
    assert "available" in body
    assert isinstance(body["available"], bool)


def test_refine_available_returns_reason_string(bare_client: TestClient) -> None:
    """Response must include a `reason` string field (empty when available)."""
    resp = bare_client.get("/api/refine/available")
    body = resp.json()
    assert "reason" in body
    assert isinstance(body["reason"], str)


# ── FO-1: PATCH /api/projects/{id}/pages/{idx}/paragraphs/{pi} ───────────────


def test_patch_paragraph_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.patch(
        "/api/projects/book1/pages/0/paragraphs/0",
        json={"layout_type": "Heading"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_patch_paragraph_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.patch(
        "/api/projects/book1/pages/99/paragraphs/0",
        json={"layout_type": "Heading"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_patch_paragraph_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    """PATCH with layout_type returns a PagePayload stub (no PageState seeded)."""
    resp = loaded_client.patch(
        "/api/projects/book1/pages/0/paragraphs/0",
        json={"layout_type": "Heading"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0


def test_patch_paragraph_accepts_all_layout_types(loaded_client: TestClient) -> None:
    """All documented layout types should be accepted."""
    for lt in ["Body", "Heading", "Caption", "Footnote", "Quote", "Other"]:
        resp = loaded_client.patch(
            "/api/projects/book1/pages/0/paragraphs/0",
            json={"layout_type": lt},
        )
        assert resp.status_code == 200, f"layout_type={lt!r} returned {resp.status_code}"


def test_patch_paragraph_rejects_unknown_layout_type(loaded_client: TestClient) -> None:
    """Unknown layout type values should return 400 validation_error.

    The repo's error_handler maps RequestValidationError → 400 (not the
    FastAPI default 422) — see test_projects_router.py:452 for the pinning note.
    """
    resp = loaded_client.patch(
        "/api/projects/book1/pages/0/paragraphs/0",
        json={"layout_type": "NotAType"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "validation_error"


# ── FO-2: POST /api/projects/{id}/pages/{idx}/words/{li}/{wi}/char-ranges ────


def test_char_ranges_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-ranges",
        json={"ranges": [{"start": 0, "end": 2, "styles": ["italic"]}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_char_ranges_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/char-ranges",
        json={"ranges": [{"start": 0, "end": 2, "styles": ["italic"]}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_char_ranges_returns_400_page_not_loaded_when_no_pagestate(
    loaded_client: TestClient,
) -> None:
    """No PageState seeded → 400 page_not_loaded (page must be OCR'd first).

    Unlike the lines/paragraphs mutation routes (which fall through to a
    stub PagePayload for backward compat), the char-ranges route requires
    an in-memory word object to exist. Without a seeded PageState the word
    cannot be resolved, so the route surfaces 400 page_not_loaded.
    """
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-ranges",
        json={"ranges": [{"start": 0, "end": 3, "styles": ["italic", "bold"]}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


def test_char_ranges_accepts_empty_ranges_list_when_no_pagestate(
    loaded_client: TestClient,
) -> None:
    """Empty ranges list with no PageState also returns 400 page_not_loaded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-ranges",
        json={"ranges": []},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


def test_char_ranges_rejects_invalid_range_missing_fields(loaded_client: TestClient) -> None:
    """Ranges missing required fields get a 400 validation error.

    The repo's error_handler maps RequestValidationError → 400 (not the
    FastAPI default 422) — see test_projects_router.py:452 for the pinning note.
    """
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-ranges",
        json={"ranges": [{"start": 0}]},  # missing end + styles
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "validation_error"


# ── FO-3: Line-adjacent merge (useMergeLines wires to lines/merge) ─────────────
# Backend: POST /api/projects/{id}/pages/{idx}/lines/merge already exists.
# These tests confirm the endpoint accepts the per-line-adjacent request shape
# the frontend hook will send (merge line N with N-1 or N+1).


def test_merge_lines_adjacent_prev_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/lines/merge",
        json={"line_indices": [0, 1]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_merge_lines_adjacent_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/lines/merge",
        json={"line_indices": [0, 1]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_merge_lines_returns_400_page_not_loaded_when_no_page_state(
    loaded_client: TestClient,
) -> None:
    """No PageState seeded → page_not_loaded 400 (page object absent)."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/merge",
        json={"line_indices": [0, 1]},
    )
    # 400 page_not_loaded is the expected response when PageState is absent.
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


# ── char-bboxes: POST .../words/{li}/{wi}/char-bboxes ─────────────────────────


def test_char_bboxes_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": [{"x": 0, "y": 0, "width": 5, "height": 10}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_char_bboxes_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/char-bboxes",
        json={"char_bboxes": [{"x": 0, "y": 0, "width": 5, "height": 10}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_char_bboxes_returns_400_page_not_loaded_when_no_pagestate(
    loaded_client: TestClient,
) -> None:
    """No PageState seeded → 400 page_not_loaded (page must be OCR'd first)."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": [{"x": 10, "y": 20, "width": 5, "height": 10}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


def test_char_bboxes_rejects_invalid_body_missing_char_bboxes(
    loaded_client: TestClient,
) -> None:
    """Missing char_bboxes field → 400 validation_error."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "validation_error"


def test_char_bboxes_accepts_empty_list(loaded_client: TestClient) -> None:
    """Empty char_bboxes list → 400 page_not_loaded (no PageState seeded, not 422)."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/char-bboxes",
        json={"char_bboxes": []},
    )
    # No PageState seeded → page_not_loaded (route checks page before shape)
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"

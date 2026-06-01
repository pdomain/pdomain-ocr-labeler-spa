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

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
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
    assert resp.json()["error"] == "project_not_found"


def test_apply_style_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/0/0/style",
        json={"style": "italic"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_apply_style_returns_400_when_page_not_loaded(loaded_client: TestClient) -> None:
    """Spec-23-C1: 400 ``page_not_loaded`` until PageState is seeded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/style",
        json={"style": "italic"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


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


# ── envelope lift failure ─────────────────────────────────────────────


@pytest.mark.skip(reason="envelope_lift retired in M5b")
def test_word_mutation_returns_400_on_corrupt_envelope(
    tmp_path: Path,
    projects_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When envelope lift fails, word mutations return 400 page_not_loaded (not 404 or 500)."""
    from pdomain_ocr_labeler_spa.core.envelope_lift import EnvelopeLiftError

    monkeypatch.setattr(
        "pdomain_ocr_labeler_spa.api.words.lift_envelope_to_page",
        lambda payload: EnvelopeLiftError(
            message="injected test failure",
            cause=ValueError("injected"),
        ),
    )

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        c.post("/api/projects/book1/pages/0/load", json={})
        resp = c.post(
            "/api/projects/book1/pages/0/words/0/0/gt",
            json={"text": "hello"},
        )

    # Lift failure → page can't be resolved → 400 page_not_loaded
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"

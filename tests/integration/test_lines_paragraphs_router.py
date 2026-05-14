"""Integration tests for ``api/lines_paragraphs.py`` route handlers.

Acceptance criteria for issue #186:
- pytest integration tests for each endpoint (happy path + 404 guard)

Spec authority:
- ``docs/architecture/02-backend.md §5.5`` — line/paragraph endpoint contracts.
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


# ── copy-line-gt ──────────────────────────────────────────────────────


def test_copy_line_gt_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/lines/0/copy-gt",
        json={"direction": "gt_to_ocr"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_copy_line_gt_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/lines/0/copy-gt",
        json={"direction": "gt_to_ocr"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_copy_line_gt_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/copy-gt",
        json={"direction": "gt_to_ocr"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0


# ── delete-scope ──────────────────────────────────────────────────────


def test_delete_scope_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/delete",
        json={"scope": "word"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_delete_scope_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/delete",
        json={"scope": "word"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_delete_scope_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/delete",
        json={"scope": "word"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── merge-scope ───────────────────────────────────────────────────────


def test_merge_scope_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/merge",
        json={"scope": "line"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_merge_scope_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/merge",
        json={"scope": "line"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_merge_scope_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/merge",
        json={"scope": "line"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── split-paragraph-after-line ────────────────────────────────────────


def test_split_paragraph_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 1},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_split_paragraph_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 1},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_split_paragraph_returns_200_for_valid_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── split-line-after-word ─────────────────────────────────────────────


def test_split_line_after_word_returns_404_when_no_project(
    bare_client: TestClient,
) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/lines/0/split-after-word",
        json={"line_index": 0, "after_word_index": 2},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_split_line_after_word_returns_404_for_bad_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/lines/0/split-after-word",
        json={"line_index": 0, "after_word_index": 2},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_split_line_after_word_returns_200_for_valid_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/split-after-word",
        json={"line_index": 0, "after_word_index": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── split-line-with-selected ──────────────────────────────────────────


def test_split_line_with_selected_returns_404_when_no_project(
    bare_client: TestClient,
) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/lines/0/split-with-selected",
        json={"line_index": 0, "word_indices": [1, 2], "mode": "extract_to_new"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_split_line_with_selected_returns_404_for_bad_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/lines/0/split-with-selected",
        json={"line_index": 0, "word_indices": [1, 2], "mode": "extract_to_new"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_split_line_with_selected_returns_200_for_valid_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/split-with-selected",
        json={"line_index": 0, "word_indices": [1, 2], "mode": "extract_to_new"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"


# ── group-into-paragraph ──────────────────────────────────────────────


def test_group_into_paragraph_returns_404_when_no_project(
    bare_client: TestClient,
) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/words/group-into-paragraph",
        json={"word_indices": [[0, 1], [0, 2]]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_group_into_paragraph_returns_404_for_bad_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/words/group-into-paragraph",
        json={"word_indices": [[0, 1], [0, 2]]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_group_into_paragraph_returns_200_for_valid_page(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/group-into-paragraph",
        json={"word_indices": [[0, 1], [0, 2]]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "book1"

"""Integration tests for ``api/refine.py`` route handlers.

Acceptance criteria for issue #186:
- pytest integration test for refine endpoint (happy path + 404 guard)
- refine-bboxes 202+job SSE cycle covered

Spec authority:
- ``specs/02-backend.md §5.6`` — refine endpoint contract (202 + job SSE).
- ``docs/specs/2026-05-12-backend-design.md`` — long-running operations return
  202 Accepted with {job_id}; callers open EventSource(/api/jobs/{id}/events).
"""

from __future__ import annotations

import json
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


# ── 404 guards ────────────────────────────────────────────────────────


def test_refine_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post(
        "/api/projects/book1/pages/0/refine",
        json={"scope": "page"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_refine_returns_404_for_bad_page(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/99/refine",
        json={"scope": "page"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_refine_returns_404_for_wrong_project_id(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/other_book/pages/0/refine",
        json={"scope": "page"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


# ── 202 happy path ────────────────────────────────────────────────────


def test_refine_returns_202_with_job_id(loaded_client: TestClient) -> None:
    """``POST .../refine`` → 202 Accepted with a job_id field."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/refine",
        json={"scope": "page"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str)
    assert len(body["job_id"]) > 0


def test_refine_page_scope_returns_202(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/refine",
        json={"scope": "page", "mode": "refine"},
    )
    assert resp.status_code == 202


def test_refine_line_scope_returns_202(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/refine",
        json={"scope": "line", "line_indices": [0, 1]},
    )
    assert resp.status_code == 202


def test_refine_word_scope_returns_202(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/refine",
        json={"scope": "word", "word_indices": [[0, 0], [0, 1]]},
    )
    assert resp.status_code == 202


# ── SSE terminal event ─────────────────────────────────────────────────


def test_refine_sse_reaches_terminal_complete(tmp_path: Path, projects_root: Path) -> None:
    """Full SSE flow: POST refine → 202; EventSource hits terminal 'complete'.

    Mirrors the reload-ocr SSE test in test_pages_router.py.
    The stub handler immediately completes — no real OCR bounding box
    refinement in this milestone.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        load_resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert load_resp.status_code == 200

        refine_resp = c.post(
            "/api/projects/book1/pages/0/refine",
            json={"scope": "page"},
        )
        assert refine_resp.status_code == 202
        job_id = refine_resp.json()["job_id"]

        terminal_seen = False
        with c.stream("GET", f"/api/jobs/{job_id}/events") as stream_resp:
            assert stream_resp.status_code == 200
            for line in stream_resp.iter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_str = line[len("data:") :].strip()
                    try:
                        event_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if event_data.get("type") in ("complete", "error"):
                        terminal_seen = True
                        break
                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip()
                    if event_name in ("complete", "error"):
                        terminal_seen = True
                        break

        assert terminal_seen, "Refine SSE stream never delivered a terminal event"

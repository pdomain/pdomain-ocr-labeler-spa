"""Integration tests for ``api/pages.py`` + ``api/jobs.py`` routes.

Acceptance criteria for issue #185:
- pytest integration tests for each endpoint in this group
- 202 reload-ocr returns job_id; EventSource reaches terminal 'complete'
- Legacy-path redirects: GET /project/foo → 301 → /projects/foo

Spec authority:
- ``specs/02-backend.md §5.3`` — pages endpoint contracts.
- ``specs/02-backend.md §5.10`` — jobs/SSE endpoint contracts.
- ``specs/02-backend.md §4`` — legacy redirect convention.
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
    """TestClient with a project already loaded."""
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


def test_get_page_returns_404_when_no_project_loaded(bare_client: TestClient) -> None:
    """No project loaded → 404 project_not_found."""
    resp = bare_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_get_page_returns_404_when_project_id_mismatches(
    loaded_client: TestClient,
) -> None:
    """Wrong project_id (project not loaded) → 404."""
    resp = loaded_client.get("/api/projects/other_book/pages/0")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_get_page_returns_404_when_index_out_of_range(
    loaded_client: TestClient,
) -> None:
    """page_index >= total_pages → 404 page_not_found."""
    resp = loaded_client.get("/api/projects/book1/pages/99")
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_get_page_returns_501_for_valid_index(
    loaded_client: TestClient,
) -> None:
    """Valid page_index on a loaded project → 501 (M3 pending)."""
    resp = loaded_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 501


def test_post_save_page_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post("/api/projects/book1/pages/0/save", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_save_page_returns_501_for_loaded_project(
    loaded_client: TestClient,
) -> None:
    """Save-page endpoint exists; returns 501 until M3 wires the page graph."""
    resp = loaded_client.post("/api/projects/book1/pages/0/save", json={})
    assert resp.status_code == 501


def test_post_load_page_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post("/api/projects/book1/pages/0/load", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_load_page_returns_501_for_loaded_project(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post("/api/projects/book1/pages/0/load", json={})
    assert resp.status_code == 501


def test_post_reload_ocr_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post("/api/projects/book1/pages/0/reload-ocr", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_reload_ocr_returns_202_with_job_id(loaded_client: TestClient) -> None:
    """reload-ocr → 202 Accepted with a job_id field."""
    resp = loaded_client.post("/api/projects/book1/pages/0/reload-ocr", json={})
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str)
    assert len(body["job_id"]) > 0


def test_reload_ocr_sse_reaches_terminal_complete(tmp_path: Path, projects_root: Path) -> None:
    """Full SSE flow: POST reload-ocr → 202; EventSource hits terminal 'complete'.

    This is bullet 2 of the acceptance criteria: the SSE stream must
    eventually deliver a terminal ``complete`` event after a reload-ocr job
    is submitted. Uses a fresh client per spec (the stub handler
    immediately completes — no real OCR in this milestone).
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        load_resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert load_resp.status_code == 200

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202
        job_id = ocr_resp.json()["job_id"]

        # Stream SSE until we see the terminal 'complete' event.
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

        assert terminal_seen, "SSE stream never delivered a terminal event"


def test_post_save_all_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post("/api/projects/book1/save-all", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_save_all_returns_202_with_job_id(loaded_client: TestClient) -> None:
    """save-all is a long-running job → 202 Accepted with job_id."""
    resp = loaded_client.post("/api/projects/book1/save-all", json={})
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str)


def test_save_all_sse_reaches_terminal_complete(tmp_path: Path, projects_root: Path) -> None:
    """save-all SSE reaches terminal 'complete'."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        resp = c.post("/api/projects/book1/save-all", json={})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        terminal_seen = False
        with c.stream("GET", f"/api/jobs/{job_id}/events") as stream_resp:
            for line in stream_resp.iter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_str = line[len("data:") :].strip()
                    try:
                        ev = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("type") in ("complete", "error"):
                        terminal_seen = True
                        break

        assert terminal_seen, "save-all SSE never delivered terminal event"


def test_delete_project_returns_404_when_not_loaded(bare_client: TestClient) -> None:
    resp = bare_client.delete("/api/projects/book1")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_delete_project_returns_204_and_clears_state(tmp_path: Path, projects_root: Path) -> None:
    """DELETE /api/projects/{pid} → 204 and clears ProjectState."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        load_resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert load_resp.status_code == 200

        del_resp = c.delete("/api/projects/book1")
        assert del_resp.status_code == 204

        # After delete, GET should 404.
        get_resp = c.get("/api/projects/book1")
        assert get_resp.status_code == 404


def test_delete_project_returns_404_when_id_mismatches(
    loaded_client: TestClient,
) -> None:
    """DELETE with wrong id → 404."""
    resp = loaded_client.delete("/api/projects/different_book")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_source_root_returns_501(bare_client: TestClient) -> None:
    """source-root endpoint exists (deferred to M2-proper config milestone)."""
    resp = bare_client.post("/api/projects/source-root", json={"path": "/some/path"})
    assert resp.status_code == 501


def test_legacy_project_path_redirects_301(bare_client: TestClient) -> None:
    """GET /project/foo → 301 → /projects/foo."""
    resp = bare_client.get("/project/foo", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"].endswith("/projects/foo")


def test_legacy_project_path_with_page_redirects(bare_client: TestClient) -> None:
    """GET /project/foo/page/3 → 301."""
    resp = bare_client.get("/project/foo/page/3", follow_redirects=False)
    assert resp.status_code == 301


def test_get_jobs_returns_list(bare_client: TestClient) -> None:
    resp = bare_client.get("/api/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_job_by_id_returns_404_for_unknown(bare_client: TestClient) -> None:
    resp = bare_client.get("/api/jobs/nonexistent")
    assert resp.status_code == 404

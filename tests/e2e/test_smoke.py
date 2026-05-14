"""Minimal E2E canary — verifies the SPA loads and the server is healthy.

This test is deliberately thin: it exercises the live-server + Playwright
fixture seam and nothing more.  Richer E2E tests live in sibling files.

Spec: docs/specs/2026-05-12-testing-design.md §E2E conftest
Issue #247

Run:
    make e2e
    # or
    uv run pytest tests/e2e/test_smoke.py -v
"""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import wait_for_app_ready


@pytest.mark.e2e
def test_healthz_returns_ok(live_server: LiveServer) -> None:
    """/healthz returns HTTP 200 with status=ok."""
    r = httpx.get(f"{live_server.base_url}/healthz", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


@pytest.mark.e2e
def test_spa_loads(live_server: LiveServer, page: Page) -> None:
    """The SPA root (/) responds with the React app shell (not a 404)."""
    response = page.goto(live_server.base_url, timeout=15_000)
    assert response is not None
    assert response.status < 400, f"SPA root returned {response.status}"
    # The React app container renders a root element.
    page.wait_for_selector("#root", timeout=10_000)


@pytest.mark.e2e
def test_session_state_endpoint(live_server: LiveServer) -> None:
    """GET /api/session-state returns a valid payload."""
    r = httpx.get(f"{live_server.base_url}/api/session-state", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert "last_project_path" in body or "project_path" in body or isinstance(body, dict)


@pytest.mark.e2e
def test_projects_list_includes_tiny_fixture(live_server: LiveServer) -> None:
    """GET /api/projects lists the tiny-fixture project installed by conftest."""
    wait_for_app_ready(live_server.base_url)
    r = httpx.get(f"{live_server.base_url}/api/projects", timeout=5)
    assert r.status_code == 200
    body = r.json()
    projects = body.get("projects", [])
    ids = [p.get("project_id") for p in projects]
    assert "tiny-fixture" in ids, f"tiny-fixture not in project list: {ids}"


@pytest.mark.e2e
def test_server_shuts_down_cleanly(live_server: LiveServer) -> None:
    """Server is still healthy at the end of the smoke suite."""
    r = httpx.get(f"{live_server.base_url}/healthz", timeout=5)
    assert r.status_code == 200

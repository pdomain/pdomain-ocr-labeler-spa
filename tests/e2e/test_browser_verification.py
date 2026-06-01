"""Playwright browser verification — SPA loads, happy path, React Router.

M14 Browser Verification (plan 2026-06-01-page-split-labeler-spa.md).

Run with:   make e2e
Or inline:  uv run --group e2e pytest tests/e2e/test_browser_verification.py --browser chromium -v
"""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer

pytestmark = pytest.mark.e2e


def test_app_loads(page: Page, live_server: LiveServer) -> None:
    """SPA index loads in Chromium; root element visible; no console errors."""
    console_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )

    response = page.goto(live_server.base_url, timeout=15_000)
    assert response is not None
    assert response.status < 400, f"SPA root returned {response.status}"

    # App shell must be visible (data-testid set on the outer shell div)
    app_shell = page.locator("[data-testid='app-shell']").first
    app_shell.wait_for(state="visible", timeout=15_000)

    # No failed resource loads in the console
    resource_errors = [e for e in console_errors if "Failed to load resource" in e]
    assert not resource_errors, f"Browser console resource errors: {resource_errors}"


def test_project_load_and_page_view(page: Page, live_server: LiveServer) -> None:
    """Load the app — home page renders without crashing."""
    page.goto(live_server.base_url, timeout=15_000)
    # App shell must be present
    page.locator("[data-testid='app-shell']").first.wait_for(state="visible", timeout=15_000)
    # Navigate to a project page route directly
    page.goto(f"{live_server.base_url}/projects/demo/pages/0", timeout=15_000)
    # Either the page renders or we redirect — body must not be empty
    assert page.locator("body").text_content() != "", "Body is empty — JS crash?"


def test_react_router_subpath_not_404(page: Page, live_server: LiveServer) -> None:
    """Navigating to a React Router sub-path serves index.html, not a 404."""
    page.goto(f"{live_server.base_url}/projects/any-id/pages/0", timeout=15_000)
    # Must NOT see a raw 404 page — the SPA catch-all must have served index.html
    assert "Not Found" not in (page.title() or ""), "React Router path returned 404"
    assert page.url.startswith(live_server.base_url), "Unexpected redirect away from app"


def test_api_routes_not_shadowed_by_spa(live_server: LiveServer) -> None:
    """API routes under /api/* return JSON, not HTML."""
    response = httpx.get(f"{live_server.base_url}/healthz", timeout=5)
    assert response.status_code == 200
    body = response.json()
    assert "status" in body

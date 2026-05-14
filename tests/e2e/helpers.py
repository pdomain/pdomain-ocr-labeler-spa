"""High-level E2E helper functions.

Thin wrappers over Playwright ``Page`` that encode the URL/testid
conventions from ``specs/13-driver-contract.md``. Tests import these
instead of calling ``page.goto`` / ``page.locator`` directly, so
URL-shape changes only need to be fixed here.

Spec: docs/specs/2026-05-12-driver-contract-design.md
Issue #247
"""

from __future__ import annotations

import httpx
from playwright.sync_api import Page


def wait_for_app_ready(base_url: str, timeout: float = 10.0) -> None:
    """Assert the server is healthy before the test starts.

    Raises ``RuntimeError`` on timeout; used by tests that need to
    make API calls before Playwright opens a page.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/healthz", timeout=0.5)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        import time as _t

        _t.sleep(0.1)
    raise RuntimeError(f"App at {base_url!r} did not become ready within {timeout}s")


def load_project(base_url: str, project_id: str) -> httpx.Response:
    """POST /api/projects/load for ``project_id`` and return the response.

    Uses the source root already configured in the live server's
    ``Settings.source_projects_root``.  The caller must have set
    ``source_projects_root`` before invoking this; the test conftest
    does so via ``Settings(source_projects_root=source_root)``.

    Returns the raw httpx response so callers can assert on status.
    """
    url = f"{base_url}/api/projects/load"
    # The project_root must be an absolute path under source_projects_root.
    # We can't know source_root here, so the caller must POST separately
    # when they need a custom root. This helper is for the standard
    # tiny-fixture case where the server already has source_root set and
    # the project is named ``project_id``.
    #
    # Use GET /api/projects first to discover the full path.
    list_resp = httpx.get(f"{base_url}/api/projects", timeout=5)
    if list_resp.status_code != 200:
        return list_resp
    projects = list_resp.json().get("projects", [])
    match = next((p for p in projects if p.get("project_id") == project_id), None)
    if match is None:
        # Fallback: POST a plausible path and let the server error.
        return httpx.post(url, json={"project_root": f"/nonexistent/{project_id}"}, timeout=5)
    project_path = match["source_path"]
    return httpx.post(url, json={"project_root": project_path}, timeout=5)


def wait_for_page_loaded(page: Page, base_url: str, timeout: float = 10_000) -> None:
    """Wait until the project page has rendered at least one line card or
    the status banner indicates the page is loaded.

    Driver-contract §2.8: ``[data-testid^="line-card-"]`` or
    ``[data-testid="project-page"]`` must be visible within ``timeout`` ms.
    """
    page.wait_for_selector('[data-testid="project-page"]', timeout=timeout)


def click_word_edit(page: Page, line_index: int, word_index: int) -> None:
    """Click the ``edit-word-button`` for word ``(line_index, word_index)``.

    Driver-contract §2.8: ``data-testid="edit-word-button-{l}-{w}"``.
    """
    testid = f"edit-word-button-{line_index}-{word_index}"
    page.click(f'[data-testid="{testid}"]')

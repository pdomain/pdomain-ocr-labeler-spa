"""M-Final V1 — Build the SPA and assert the app loads in a real browser.

This repo bundles + serves the React SPA from FastAPI, so a real-browser
milestone is mandatory (workspace CLAUDE.md "FastAPI + SPA repos" rule).

V1 opens the served server URL in Chromium and asserts:

  1. The root document loads (HTTP < 400) and the app shell renders.
  2. A loaded project page exposes the ``project-page`` root testid.
  3. There are no ``Failed to load resource`` console errors (the SPA's
     own JS/CSS/font assets all resolve under the StaticFiles mount).

Run:
    make e2e
    # or
    uv run --group e2e pytest tests/e2e/test_parity_app_loads.py --browser chromium -v

Spec: docs/plans/2026-06-03-labeler-spa-legacy-parity.md §M-Final V1
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.e2e.exercise_real_project import ExerciseServer

pytestmark = pytest.mark.e2e


def _attach_resource_error_collector(page: Page) -> list[str]:
    """Collect console errors that indicate a failed resource load."""
    errors: list[str] = []
    page.on(
        "console",
        lambda msg: errors.append(msg.text) if msg.type == "error" else None,
    )
    # Network-level failures (404s for chunks, fonts, etc.) surface here too.
    page.on("requestfailed", lambda req: errors.append(f"requestfailed: {req.url}"))
    return errors


def test_app_root_loads_without_resource_errors(exercise_server: ExerciseServer, page: Page) -> None:
    """The SPA root loads in Chromium with the app shell visible, no asset 404s."""
    errors = _attach_resource_error_collector(page)

    response = page.goto(exercise_server.base_url, timeout=20_000)
    assert response is not None, "page.goto returned no response"
    assert response.status < 400, f"SPA root returned HTTP {response.status}"

    # App shell renders (outer shell div carries data-testid="app-shell").
    page.locator("[data-testid='app-shell']").first.wait_for(state="visible", timeout=20_000)

    # No failed resource loads in the console / network layer. The SPA's own
    # bundle (JS chunks, CSS, fonts) must resolve under the StaticFiles mount.
    resource_errors = [e for e in errors if "Failed to load resource" in e or e.startswith("requestfailed:")]
    assert not resource_errors, f"Browser resource-load errors: {resource_errors}"


def test_loaded_project_page_exposes_project_page_testid(exercise_server: ExerciseServer, page: Page) -> None:
    """Navigating to a seeded project page renders the project-page root testid."""
    errors = _attach_resource_error_collector(page)

    url = f"{exercise_server.base_url}/projects/exercise-fixture/pages/pageno/1"
    response = page.goto(url, timeout=20_000)
    assert response is not None and response.status < 400, (
        f"Project page route returned HTTP {response.status if response else 'none'}"
    )

    # The assembled ProjectPage shell exposes the project-page root testid.
    page.locator("[data-testid='project-page']").first.wait_for(state="visible", timeout=20_000)

    resource_errors = [e for e in errors if "Failed to load resource" in e or e.startswith("requestfailed:")]
    assert not resource_errors, f"Browser resource-load errors on project page: {resource_errors}"

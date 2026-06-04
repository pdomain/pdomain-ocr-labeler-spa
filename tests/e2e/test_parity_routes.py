"""M-Final V5 — React Router sub-path renders (deep-link, not 404/blank).

The FastAPI catch-all must serve ``index.html`` for client-side routes so a
hard navigation (or a bookmark / refresh) to a project page sub-path renders
the page component rather than a 404 or a blank body.

Spec: docs/plans/2026-06-03-labeler-spa-legacy-parity.md §M-Final V5
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.e2e.exercise_real_project import (
    ExerciseServer,
    _wait_for_line_cards,
)

pytestmark = pytest.mark.e2e

_PROJECT_ID = "exercise-fixture"


def test_deep_link_project_page_subpath_renders(exercise_server: ExerciseServer, page: Page) -> None:
    """Direct navigation to a project page sub-path renders the page component."""
    page_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    # Deep-link straight to page 3 (a sub-path, not the SPA root).
    url = f"{exercise_server.base_url}/projects/{_PROJECT_ID}/pages/pageno/3"
    response = page.goto(url, timeout=20_000)
    assert response is not None, "no HTTP response for the deep-linked sub-path"
    # The catch-all serves index.html → 200 HTML (not a 404).
    assert response.status < 400, f"deep-link returned HTTP {response.status}"

    # The project-page component must actually render (not blank, not 404).
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    _wait_for_line_cards(page)

    # Body must not be empty and the title must not be a 404.
    body_text = page.locator("body").text_content()
    assert body_text is not None and body_text.strip() != "", "body is empty — JS crash?"
    assert "Not Found" not in (page.title() or ""), "deep-link returned a 404 title"

    # The URL stayed on the requested sub-path (no redirect away from the app).
    assert "/projects/" in page.url and "/pageno/3" in page.url, (
        f"unexpected URL after deep-link: {page.url!r}"
    )
    assert page_errors == [], f"page raised JS errors on deep-link: {page_errors}"


def test_react_router_subpath_serves_index_not_404(exercise_server: ExerciseServer, page: Page) -> None:
    """An arbitrary deep React Router path is served index.html, not a hard 404."""
    url = f"{exercise_server.base_url}/projects/{_PROJECT_ID}/pages/pageno/2"
    response = page.goto(url, timeout=20_000)
    assert response is not None and response.status < 400, (
        f"sub-path returned HTTP {response.status if response else 'none'}"
    )
    # App shell renders → the catch-all served the SPA, not a backend 404.
    page.locator("[data-testid='app-shell']").first.wait_for(state="visible", timeout=20_000)
    assert page.url.startswith(exercise_server.base_url), "redirected away from the app"

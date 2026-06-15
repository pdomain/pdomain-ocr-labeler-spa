"""Regression guards for panel-chrome bugs fixed in b193e9f and 7f22eef.

Four checks that each guard a specific failure mode caught by vitest but
missed by the prior e2e suite (which only ran ``make e2e`` headless against
the real app and never exercised collapse / re-open flows):

  P1 — Actions panel toggle: chevron direction reflects open/closed state;
       clicking collapses then expands the panel.

  P2b — Right panel re-open: after collapsing, ``right-panel-expand-btn``
        is visible, clickable, and restores the panel.

  P2a — Left Worklist drawer re-open: after collapsing, ``drawer-expand-btn``
        is visible (toBeVisible) AND has a non-zero bounding box width (the
        original bug was a zero-width clip where the element was in the DOM
        but hidden by overflow:hidden on its parent).

  P3 — Toolbar padding: the ``workspace-toolbar`` / ``.stage-toolbar`` element
       carries a non-zero computed paddingLeft, which breaks when the upstream
       CSS rule is missing.

These run against the real app via the ``exercise_server`` fixture (same as
``test_parity_chrome.py``, ``test_parity_grid_actions.py``, etc.) so the
frontend CSS and React state machines are exercised end-to-end, not mocked.

Spec: docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md
Ref commits: b193e9f (bug fixes), 7f22eef (pdomain-ui 0.9.0 / CSS migration)
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page

from tests.e2e.exercise_real_project import (
    ExerciseServer,
    _goto_project_page,
    _wait_for_line_cards,
)

pytestmark = pytest.mark.e2e

# ─── Shared navigation helper ────────────────────────────────────────────────


def _go_to_page1(page: Page, exercise_server: ExerciseServer) -> None:
    """Navigate to exercise-fixture page 1 and wait for line content."""
    _goto_project_page(page, exercise_server.base_url, 1)
    _wait_for_line_cards(page)


# ─── P1: Actions panel toggle chevron + collapse/expand cycle ────────────────


def test_actions_panel_chevron_open_state(exercise_server: ExerciseServer, page: Page) -> None:
    """P1a -- toolbar-grid-collapse shows DOWN chevron (v) when panel is OPEN.

    When the actions panel is open (toolbarGridCollapsed=false, the default),
    the chevron must point DOWN to indicate the panel can be collapsed.
    The vitest fixture asserts polyline points ``"6 9 12 15 18 9"``; the real-
    app e2e asserts ``aria-expanded="true"`` as the stable, accessible signal
    (the polyline is an implementation detail and changes with theming).
    """
    _go_to_page1(page, exercise_server)

    btn = page.locator('[data-testid="toolbar-grid-collapse"]').first
    btn.wait_for(state="visible", timeout=10_000)

    # Default state: panel open -- aria-expanded must be "true".
    aria_expanded = btn.get_attribute("aria-expanded")
    assert aria_expanded == "true", (
        f"toolbar-grid-collapse aria-expanded should be 'true' when panel is open, got {aria_expanded!r}"
    )

    # Panel body must be present and visible.
    grid_body = page.locator('[data-testid="toolbar-grid-body"]').first
    grid_body.wait_for(state="visible", timeout=5_000)
    assert grid_body.is_visible(), "toolbar-grid-body must be visible when panel is open"

    # Secondary check: DOWN chevron polyline points.
    polyline = btn.evaluate("btn => btn.querySelector('polyline')?.getAttribute('points')")
    if polyline is not None:
        assert polyline == "6 9 12 15 18 9", (
            f"DOWN chevron expected polyline '6 9 12 15 18 9', got {polyline!r}"
        )


def test_actions_panel_toggle_collapses_and_reopens(exercise_server: ExerciseServer, page: Page) -> None:
    """P1b -- clicking toolbar-grid-collapse collapses then re-expands the panel.

    Regression guard for Bug 1: the chevron direction must flip from DOWN (open)
    to UP (closed) and back again, and the panel content must hide/show.
    """
    _go_to_page1(page, exercise_server)

    btn = page.locator('[data-testid="toolbar-grid-collapse"]').first
    btn.wait_for(state="visible", timeout=10_000)

    # Confirm we start with the panel open.
    assert btn.get_attribute("aria-expanded") == "true", "panel must start open (aria-expanded='true')"
    page.locator('[data-testid="toolbar-grid-body"]').first.wait_for(state="visible", timeout=5_000)

    # -- Collapse --
    btn.click()
    page.wait_for_function(
        "document.querySelector(\"[data-testid='toolbar-grid-collapse']\")"
        "?.getAttribute('aria-expanded') === 'false'",
        timeout=5_000,
    )
    assert btn.get_attribute("aria-expanded") == "false", (
        "aria-expanded must flip to 'false' after collapse click"
    )

    # Panel body must be hidden (either removed or display:none).
    grid_body = page.locator('[data-testid="toolbar-grid-body"]')
    is_hidden = grid_body.count() == 0 or not grid_body.first.is_visible()
    assert is_hidden, "toolbar-grid-body must be hidden after collapsing the panel"

    # Secondary: chevron must now show UP points.
    polyline_closed = btn.evaluate("btn => btn.querySelector('polyline')?.getAttribute('points')")
    if polyline_closed is not None:
        assert polyline_closed == "18 15 12 9 6 15", (
            f"UP chevron expected '18 15 12 9 6 15', got {polyline_closed!r}"
        )

    # -- Re-expand --
    btn.click()
    page.wait_for_function(
        "document.querySelector(\"[data-testid='toolbar-grid-collapse']\")"
        "?.getAttribute('aria-expanded') === 'true'",
        timeout=5_000,
    )
    assert btn.get_attribute("aria-expanded") == "true", (
        "aria-expanded must return to 'true' after re-expand click"
    )

    # Panel body must be visible again.
    page.locator('[data-testid="toolbar-grid-body"]').first.wait_for(state="visible", timeout=5_000)
    assert page.locator('[data-testid="toolbar-action-grid"]').first.is_visible(), (
        "toolbar-action-grid must be visible after re-expanding the panel"
    )

    # Chevron back to DOWN.
    polyline_open = btn.evaluate("btn => btn.querySelector('polyline')?.getAttribute('points')")
    if polyline_open is not None:
        assert polyline_open == "6 9 12 15 18 9", (
            f"DOWN chevron expected '6 9 12 15 18 9', got {polyline_open!r}"
        )


# ─── P2b: Right panel re-open control ────────────────────────────────────────


def test_right_panel_expand_btn_visible_after_collapse(exercise_server: ExerciseServer, page: Page) -> None:
    """P2b-a -- collapsing the right panel shows the re-open control.

    Regression guard: after the fix the ``right-panel-expand-btn`` appears
    when the right panel is collapsed. Before the fix the control was absent
    and there was no way to restore the panel without reloading the app.
    """
    _go_to_page1(page, exercise_server)

    # Right panel starts open; collapse via the collapse button.
    collapse_btn = page.locator('[data-testid="right-panel-collapse"]').first
    collapse_btn.wait_for(state="visible", timeout=10_000)
    collapse_btn.click()

    # After collapse: right-panel must be gone; expand-btn must be visible.
    page.wait_for_selector('[data-testid="right-panel"]', state="hidden", timeout=5_000)

    expand_btn = page.locator('[data-testid="right-panel-expand-btn"]').first
    expand_btn.wait_for(state="visible", timeout=5_000)
    assert expand_btn.is_visible(), (
        "right-panel-expand-btn must be visible after the right panel is collapsed"
    )


def test_right_panel_expand_btn_restores_panel(exercise_server: ExerciseServer, page: Page) -> None:
    """P2b-b -- clicking the re-open control restores the right panel.

    This is the critical regression guard: the expand button must be both
    visible AND functional (clicking it re-opens the panel).
    """
    _go_to_page1(page, exercise_server)

    # Collapse.
    collapse_btn = page.locator('[data-testid="right-panel-collapse"]').first
    collapse_btn.wait_for(state="visible", timeout=10_000)
    collapse_btn.click()
    page.wait_for_selector('[data-testid="right-panel"]', state="hidden", timeout=5_000)

    # Re-open via the expand button.
    expand_btn = page.locator('[data-testid="right-panel-expand-btn"]').first
    expand_btn.wait_for(state="visible", timeout=5_000)
    expand_btn.click()

    # Right panel must reappear.
    page.wait_for_selector('[data-testid="right-panel"]', state="visible", timeout=5_000)
    assert page.locator('[data-testid="right-panel"]').first.is_visible(), (
        "right-panel must be visible again after clicking right-panel-expand-btn"
    )
    # And the expand button must be gone (panel is open).
    assert page.locator('[data-testid="right-panel-expand-btn"]').count() == 0, (
        "right-panel-expand-btn must not be present while the right panel is open"
    )


# ─── P2a: Left Worklist drawer re-open ───────────────────────────────────────


def test_drawer_expand_btn_visible_and_has_nonzero_width(exercise_server: ExerciseServer, page: Page) -> None:
    """P2a-a -- after collapsing the drawer, expand-btn has a non-zero bounding box.

    The original bug was a zero-width clip: the element was in the DOM and
    ``is_visible()`` returned True in some cases, but the element had
    ``overflow:hidden`` on an ancestor that clipped it to 0 px x N px,
    making it unclickable. We check both visibility AND the bounding box width.
    """
    _go_to_page1(page, exercise_server)

    # Drawer starts open; collapse via the collapse button.
    collapse_btn = page.locator('[data-testid="drawer-collapse-btn"]').first
    collapse_btn.wait_for(state="visible", timeout=10_000)
    collapse_btn.click()

    # Wait for drawer data-open to flip.
    page.wait_for_function(
        "document.querySelector(\"[data-testid='drawer']\")?.getAttribute('data-open') === 'false'",
        timeout=5_000,
    )

    # The expand button must exist and be visible.
    expand_btn = page.locator('[data-testid="drawer-expand-btn"]').first
    expand_btn.wait_for(state="visible", timeout=5_000)
    assert expand_btn.is_visible(), "drawer-expand-btn must be visible after collapsing the drawer"

    # Assert non-zero bounding box width -- the specific failure mode of Bug 2a.
    bbox = expand_btn.bounding_box()
    assert bbox is not None, "drawer-expand-btn must have a bounding box (not detached)"
    assert bbox["width"] > 0, (
        f"drawer-expand-btn bounding box width must be > 0, got {bbox['width']} "
        "(zero-width = the element is clipped by overflow:hidden on an ancestor)"
    )


def test_drawer_expand_btn_restores_drawer(exercise_server: ExerciseServer, page: Page) -> None:
    """P2a-b -- clicking drawer-expand-btn re-opens the drawer.

    Functional regression guard: the control must not only be visible but
    must also wire correctly so clicking it restores the full drawer panel.
    """
    _go_to_page1(page, exercise_server)

    # Collapse.
    collapse_btn = page.locator('[data-testid="drawer-collapse-btn"]').first
    collapse_btn.wait_for(state="visible", timeout=10_000)
    collapse_btn.click()
    page.wait_for_function(
        "document.querySelector(\"[data-testid='drawer']\")?.getAttribute('data-open') === 'false'",
        timeout=5_000,
    )

    # Re-open via expand button.
    expand_btn = page.locator('[data-testid="drawer-expand-btn"]').first
    expand_btn.wait_for(state="visible", timeout=5_000)
    expand_btn.click()

    # Drawer must return to open state.
    page.wait_for_function(
        "document.querySelector(\"[data-testid='drawer']\")?.getAttribute('data-open') === 'true'",
        timeout=5_000,
    )
    drawer = page.locator('[data-testid="drawer"]').first
    assert drawer.get_attribute("data-open") == "true", (
        "drawer data-open must return to 'true' after clicking drawer-expand-btn"
    )
    # The tab strip and content must be visible again.
    page.locator('[data-testid="drawer-header"]').first.wait_for(state="visible", timeout=3_000)


# ─── P3: WorkspaceToolbar / .stage-toolbar padding ───────────────────────────


def test_workspace_toolbar_has_nonzero_padding(exercise_server: ExerciseServer, page: Page) -> None:
    """P3 -- the workspace-toolbar element has non-zero computed padding.

    Regression guard for Bug 3: the ``.stage-toolbar`` CSS rule supplies
    ``padding: 8px 12px``. If the upstream ``primitives.css`` import is
    missing (the pre-fix state, where a local fork was deleted before the
    npm package was bumped to include the rule), both ``paddingLeft`` and
    ``paddingTop`` read as ``"0px"`` and toolbar buttons are flush to the
    edge with no breathing room.

    We read ``getComputedStyle`` via ``page.evaluate`` so the check runs
    against the real browser's cascade -- Playwright's ``element.style``
    only shows inline styles.
    """
    _go_to_page1(page, exercise_server)

    toolbar = page.locator('[data-testid="workspace-toolbar"]').first
    toolbar.wait_for(state="visible", timeout=10_000)

    padding = page.evaluate(
        """() => {
            const el = document.querySelector('[data-testid="workspace-toolbar"]');
            if (!el) return null;
            const cs = window.getComputedStyle(el);
            return {
                paddingLeft: cs.paddingLeft,
                paddingTop: cs.paddingTop,
            };
        }"""
    )
    assert padding is not None, "workspace-toolbar element not found in page DOM"

    def _px(value: str) -> float:
        """Parse a CSS px value like '12px' to a float."""
        return float(value.rstrip("px") or 0)

    padding_left = _px(padding["paddingLeft"])
    padding_top = _px(padding["paddingTop"])

    assert padding_left > 0, (
        f"workspace-toolbar computed paddingLeft must be > 0 (got {padding['paddingLeft']!r}); "
        "zero padding means the .stage-toolbar CSS rule from primitives.css is not loaded"
    )
    assert padding_top > 0, (
        f"workspace-toolbar computed paddingTop must be > 0 (got {padding['paddingTop']!r}); "
        "zero padding means the .stage-toolbar CSS rule from primitives.css is not loaded"
    )
    time.sleep(0.05)  # Allow any pending animations to settle before teardown.

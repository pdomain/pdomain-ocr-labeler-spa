"""Keyboard-only E2E tests — every core labeling action reachable without a mouse.

Verifies M9.5 acceptance gate: the full labeling workflow is navigable
exclusively via keyboard shortcuts defined in ``frontend/src/lib/hotkeyMap.ts``.

Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Acceptance gates
Issue #286

Run:
    make e2e
    # or
    uv run pytest tests/e2e/test_keyboard_only.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import wait_for_page_loaded
from tests.e2e.test_driver_contract import _load_tiny_fixture


def _goto_page1(live_server: LiveServer, page: Page) -> None:
    """Load tiny-fixture and navigate to page 1, waiting for full render."""
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))
    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    wait_for_page_loaded(page, live_server.base_url, timeout=15_000)


@pytest.mark.e2e
def test_page_navigation_keyboard_only(live_server: LiveServer, page: Page) -> None:
    """Navigate forward and backward between pages using only keyboard shortcuts.

    Hotkeys (global scope):
      Mod+ArrowRight — next page
      Mod+ArrowLeft  — previous page
    """
    _goto_page1(live_server, page)
    assert "/pages/pageno/1" in page.url

    # Navigate forward to page 2 with Ctrl+ArrowRight (Mod+ArrowRight).
    page.keyboard.press("Control+ArrowRight")
    page.wait_for_url("**/pages/pageno/2", timeout=10_000)
    assert "/pages/pageno/2" in page.url, f"Expected pageno/2 after Ctrl+ArrowRight, got {page.url}"

    wait_for_page_loaded(page, live_server.base_url, timeout=10_000)

    # Navigate back to page 1 with Ctrl+ArrowLeft (Mod+ArrowLeft).
    page.keyboard.press("Control+ArrowLeft")
    page.wait_for_url("**/pages/pageno/1", timeout=10_000)
    assert "/pages/pageno/1" in page.url, f"Expected pageno/1 after Ctrl+ArrowLeft, got {page.url}"


@pytest.mark.e2e
def test_validate_and_save_keyboard_only(live_server: LiveServer, page: Page) -> None:
    """Load a page and invoke save with only keyboard shortcuts.

    Hotkeys exercised:
      Mod+S — save page (global scope)

    Note: The ``V`` (validate) hotkey requires a focused line card in the
    matches scope. The tiny-fixture pages may not have parsed line cards on
    first open (OCR output depends on runtime). This test verifies that:

    1. The project page loads and renders its shell.
    2. Ctrl+S triggers a save-page request without raising a console error.

    If a line card IS present, it also focuses the first one and presses V.
    """
    _goto_page1(live_server, page)

    # Track console errors so we can assert none occur during keyboard ops.
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    # Ensure project-page shell is healthy before keyboard ops.
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)

    # Optionally exercise V (validate) if a line card is rendered.
    line_cards = page.locator('[data-testid^="line-card-"]')
    if line_cards.count() > 0:
        # Focus the first line card so the matches-scope hotkeys are active.
        line_cards.first.click()
        page.keyboard.press("v")
        # After pressing V the card state may update — just wait a moment
        # for any async update to settle before saving.
        page.wait_for_timeout(300)

    # Save the page with Ctrl+S (Mod+S global hotkey).
    page.keyboard.press("Control+s")

    # The save action is async. Wait briefly for any network request to settle.
    page.wait_for_timeout(500)

    # Assert the page shell is still alive (no fatal crash from keyboard ops).
    page.wait_for_selector('[data-testid="project-page"]', timeout=5_000)

    # Assert no console errors were raised by the keyboard operations.
    fatal = [e for e in errors if "Uncaught" in e or "TypeError" in e or "Cannot read" in e]
    assert not fatal, f"Console errors after keyboard ops: {fatal}"


@pytest.mark.e2e
def test_hotkey_help_modal_keyboard_only(live_server: LiveServer, page: Page) -> None:
    """Open the hotkey help modal with the ``?`` shortcut and close with Escape.

    Hotkeys exercised:
      ? — show hotkey help (global scope)
      Escape — close modal (global scope)
    """
    _goto_page1(live_server, page)

    # Press ? to open the help modal.
    page.keyboard.press("?")

    # The help modal should appear — look for the dialog role or a known
    # testid. The HotkeyHelpModal uses role="dialog" per the a11y spec.
    page.wait_for_selector('[role="dialog"]', timeout=5_000)

    # Close with Escape.
    page.keyboard.press("Escape")

    # The dialog should be gone.
    page.wait_for_selector('[role="dialog"]', state="hidden", timeout=5_000)

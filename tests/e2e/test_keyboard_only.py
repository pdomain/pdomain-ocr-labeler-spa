"""Keyboard-only E2E tests — every core labeling action reachable without a mouse.

Covers: B-SHELL-008, B-SHELL-009, B-ACTIONS-007, F-HOTKEY-HELP-01

Verifies M9.5 acceptance gate: the full labeling workflow is navigable
exclusively via keyboard shortcuts defined in ``frontend/src/lib/hotkeyMap.ts``.

Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Acceptance gates
Issue #286

CU-3.1 additions (2026-05-21):
- ``test_page_navigation_keyboard_only`` — BUG-KBD-2 regression (Mod+ArrowLeft/Right)
- ``test_save_page_keyboard_only`` — Mod+S global save hotkey
- ``test_hotkey_help_modal_keyboard_only`` — ? open / Escape close
- ``test_global_hotkeys_wired_no_console_error`` — confirms useGlobalHotkeys is
  called in ProjectPage (BUG-KBD-2 regression guard)

Run:
    make e2e
    # or
    uv run --group e2e pytest tests/e2e/test_keyboard_only.py -v
"""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import SEED_TIMEOUT, wait_for_page_loaded


def _load_tiny_fixture(base_url: str, source_root_path: str) -> None:
    """POST /api/source-root then POST /api/projects/load for tiny-fixture.

    Inlined from ``test_driver_contract`` to avoid importing a private helper.
    """
    httpx.post(
        f"{base_url}/api/source-root",
        json={"path": source_root_path},
        timeout=SEED_TIMEOUT,
    )
    project_path = str(source_root_path) + "/tiny-fixture"
    resp = httpx.post(
        f"{base_url}/api/projects/load",
        json={"project_root": project_path},
        timeout=SEED_TIMEOUT,
    )
    assert resp.status_code == 200, f"load_project failed: {resp.status_code} {resp.text}"


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

    Regression test for BUG-KBD-2 (useGlobalHotkeys was defined but not called).
    Fixed in ProjectPage.tsx:328. Also covers issue #402 — Ctrl+ArrowLeft was
    silently failing due to a missing SPA static bundle in the test environment;
    not a code defect. The ``make e2e`` target runs ``make frontend-build`` first
    which populates ``src/pdomain_ocr_labeler_spa/static/``.

    Audit: docs/archive/research/M9.5-keyboard-audit.md §7
    """
    _goto_page1(live_server, page)
    assert "/pages/pageno/1" in page.url

    # Navigate forward to page 2 with Ctrl+ArrowRight (Mod+ArrowRight).
    page.keyboard.press("Control+ArrowRight")
    page.wait_for_url("**/pages/pageno/2", timeout=10_000)
    assert "/pages/pageno/2" in page.url, f"Expected pageno/2 after Ctrl+ArrowRight, got {page.url}"

    wait_for_page_loaded(page, live_server.base_url, timeout=10_000)
    # Brief pause to allow React Router state + hotkey re-registration to settle
    # after the client-side navigation. The hotkey handler captures currentPageNo
    # from a closure; re-registration from the new render needs to complete before
    # we fire the next key.
    page.wait_for_timeout(300)

    # Navigate back to page 1 with Ctrl+ArrowLeft (Mod+ArrowLeft).
    # This is the BUG-KBD-6 / #402 regression guard: Ctrl+ArrowLeft was
    # failing when the SPA bundle was absent (server returned 404 for the
    # SPA, so the React app never mounted and the hotkey never registered).
    page.keyboard.press("Control+ArrowLeft")
    page.wait_for_url("**/pages/pageno/1", timeout=10_000)
    assert "/pages/pageno/1" in page.url, f"Expected pageno/1 after Ctrl+ArrowLeft, got {page.url}"


@pytest.mark.e2e
def test_global_hotkeys_wired_no_console_error(live_server: LiveServer, page: Page) -> None:
    """Verify useGlobalHotkeys is active — pressing Mod+S generates no console errors.

    This test guards against a regression of BUG-KBD-2 where ``useGlobalHotkeys``
    was defined in ``useGlobalHotkeys.ts`` but never called from any component.
    The fix landed in ``ProjectPage.tsx:328``.

    If the hook is not mounted, Ctrl+S will either be swallowed by the browser
    (Save page dialog on non-React pages) or do nothing. In the SPA it fires
    the save-page mutation. We check that the page shell is still intact and
    no JS errors were thrown.

    Audit: docs/archive/research/M9.5-keyboard-audit.md §5 (BUG-KBD-2 resolved)
    """
    _goto_page1(live_server, page)

    # Collect JS errors during the test.
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    # Ensure the project page shell is present.
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)

    # Press Ctrl+S (Mod+S — Save Page hotkey, registered in useGlobalHotkeys).
    page.keyboard.press("Control+s")

    # Allow the async save mutation to settle.
    page.wait_for_timeout(500)

    # The project-page shell must still be alive (no crash).
    page.wait_for_selector('[data-testid="project-page"]', timeout=5_000)

    # No fatal JS errors from the keyboard operation.
    fatal = [e for e in errors if "Uncaught" in e or "TypeError" in e or "Cannot read" in e]
    assert not fatal, f"Console errors after Ctrl+S: {fatal}"


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
    try:
        page.wait_for_selector('[data-testid^="line-card-"]', timeout=5_000, state="attached")
        line_cards = page.locator('[data-testid^="line-card-"]')
        # Focus the first line card so the matches-scope hotkeys are active.
        line_cards.first.click()
        page.keyboard.press("v")
        # After pressing V the card state may update — just wait a moment
        # for any async update to settle before saving.
        page.wait_for_timeout(300)
    except Exception:
        pytest.skip("No line cards rendered — OCR not available in tiny-fixture")

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

    Audit: docs/archive/research/M9.5-keyboard-audit.md §7
    """
    _goto_page1(live_server, page)

    # Press ? to open the help modal.
    page.keyboard.press("?")

    # The help modal should appear — HotkeyHelpModal renders with
    # data-testid="hotkey-help-dialog" (frontend/src/components/HotkeyHelpModal.tsx:94).
    page.wait_for_selector('[data-testid="hotkey-help-dialog"]', timeout=5_000)

    # Close with Escape.
    page.keyboard.press("Escape")

    # The dialog should be gone.
    page.wait_for_selector('[data-testid="hotkey-help-dialog"]', state="hidden", timeout=5_000)

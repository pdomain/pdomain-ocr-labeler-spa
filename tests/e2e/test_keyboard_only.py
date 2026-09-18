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
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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
    # Wait for the page-number input (ProjectNavigationControls, testid
    # nav-page-input) to reflect page 2 before firing the next hotkey. Its
    # value is derived straight from the route param, so once it reads "2"
    # the component has re-rendered with the new currentPageNo and the
    # Mod+ArrowLeft handler's closure is current — a fixed sleep here was a
    # guess at how long that re-render takes, and guesses are what make a
    # test flaky under machine load.
    expect(page.locator('[data-testid="nav-page-input"]')).to_have_value("2", timeout=10_000)

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

    # Press Ctrl+S (Mod+S — Save Page hotkey, registered in useGlobalHotkeys)
    # and wait for the save request it fires, rather than a fixed sleep that
    # merely guesses how long the mutation takes.
    with page.expect_response(lambda r: r.url.endswith("/save")) as save_resp_info:
        page.keyboard.press("Control+s")
    assert save_resp_info.value.status == 200, (
        f"Save request failed: {save_resp_info.value.status} {save_resp_info.value.text()}"
    )

    # The project-page shell must still be alive (no crash).
    page.wait_for_selector('[data-testid="project-page"]', timeout=5_000)

    # No fatal JS errors from the keyboard operation.
    fatal = [e for e in errors if "Uncaught" in e or "TypeError" in e or "Cannot read" in e]
    assert not fatal, f"Console errors after Ctrl+S: {fatal}"


@pytest.mark.e2e
def test_validate_and_save_keyboard_only(live_server: LiveServer, page: Page) -> None:
    """Load a page and invoke validate + save with only keyboard shortcuts.

    Hotkeys exercised:
      J     — select the first line card (matches scope)
      V     — validate the selected line (matches scope)
      Mod+S — save page (global scope)

    Finding (superseding the old docstring's claim that clicking a line
    card "focuses" it for the matches scope): ``LineCard``'s outer element
    carries no click handler, and the matches-scope hotkeys read
    ``worklistStore.selectedLineIndex`` — which nothing in ``LineCard`` or
    ``WordMatchView`` ever sets. A mouse click on the card previously used
    here does not select anything; worse, because ``LineCard`` renders each
    word's editable GT ``<input>`` inline, Playwright's element-center click
    reliably lands inside one of those inputs instead, which (a) leaves V/U/D
    and Mod+S silently inert — ``enableOnFormTags`` is ``False`` for both
    scopes — and (b) types the literal "v" into the ground-truth text,
    corrupting it. That combination made the old test pass while proving
    nothing and, incidentally, mutating fixture data on every run.

    ``J`` (next line, matches scope) is the actual, product-correct way to
    select a line with the keyboard — it calls ``focusWorklistLine``, which
    is the one function that sets ``selectedLineIndex``. Using it here also
    keeps this test true to its own file's charter: keyboard only, no mouse.

    tiny-fixture page 1 is deterministically seeded with one line of word
    content (see conftest.py's ``_seed_tiny_fixture_page0_words``,
    P0-CI-SOFT), so a line card is always present here — this is not an
    OCR-availability guess. This test verifies that:

    1. The project page loads and renders its shell.
    2. J selects the first line; V validates it — asserted via the
       validate-batch response status and the Validate button flipping to
       "Unvalidate".
    3. Ctrl+S saves the page — asserted via the save response status and
       body, not just "no console error".
    """
    _goto_page1(live_server, page)

    # Track console errors so we can assert none occur during keyboard ops.
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    # Ensure project-page shell is healthy before keyboard ops.
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)

    # Exercise V (validate) on the first line card.
    try:
        page.wait_for_selector('[data-testid^="line-card-"]', timeout=10_000, state="attached")
    except PlaywrightTimeoutError as exc:
        # word-match-view (the Matches-tab scroll container LineCard renders
        # into) collapses to computed height 0 with real word content — its
        # className="flex-1 overflow-auto" only sizes it under a flex parent,
        # but TextTabs.tsx wraps `children` in a plain block div, and
        # style={{contain: "strict"}} then blocks the content-derived
        # fallback height. With a 0-height scroll container the
        # @tanstack/react-virtual virtualizer mounts zero items, so no
        # line-card-* ever attaches. Only surfaces with real word content
        # (tiny-fixture always had zero words before). Reported to
        # maintainers as a real product gap (P0-CI-SOFT follow-up) rather
        # than papered over here.
        raise AssertionError(
            "No line-card-* attached to the DOM after loading tiny-fixture page 1 "
            "with real word content. Suspected cause: word-match-view collapses to "
            "zero height (CSS flex/contain mismatch in WordMatchView.tsx / "
            "TextTabs.tsx), so the virtualizer renders no rows. This is a suspected "
            "product bug, not a stale test expectation; see the P0-CI-SOFT "
            "follow-up report before changing this assertion."
        ) from exc

    validate_button = page.locator('[data-testid="line-validate-button-0"]')
    expect(validate_button).to_have_text("Validate")

    # J selects line 0 (focusWorklistLine) so the matches-scope V hotkey has
    # a line to act on.
    page.keyboard.press("j")

    # V validates the selected line. Wait for the validate-batch response
    # itself (not a timer), then assert it succeeded and that the button
    # flips to "Unvalidate" — proof the validate actually happened, not just
    # that the app didn't crash.
    with page.expect_response(lambda r: r.url.endswith("/words/validate-batch")) as validate_resp_info:
        page.keyboard.press("v")
    validate_resp = validate_resp_info.value
    assert validate_resp.status == 200, (
        f"Validate request failed: {validate_resp.status} {validate_resp.text()}"
    )
    expect(validate_button).to_have_text("Unvalidate", timeout=5_000)

    # Save the page with Ctrl+S (Mod+S global hotkey). Wait for the save
    # response itself and assert it succeeded — a 500 here must fail the test.
    with page.expect_response(lambda r: r.url.endswith("/save")) as save_resp_info:
        page.keyboard.press("Control+s")
    save_resp = save_resp_info.value
    assert save_resp.status == 200, f"Save request failed: {save_resp.status} {save_resp.text()}"
    save_body = save_resp.json()
    assert save_body.get("saved") is True, f"Save response did not report success: {save_body}"

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

    # Press ? to open the help modal. Playwright's press("?") synthesizes
    # code=Slash but leaves shiftKey=False (it produces the "?" character
    # directly rather than replaying an actual Shift+/ chord), while the
    # frontend registers this hotkey as "shift+slash" — a real physical-code
    # match that requires shiftKey=True. "Shift+Slash" replays the actual
    # chord a hardware keyboard sends.
    page.keyboard.press("Shift+Slash")

    # The help modal should appear — HotkeyHelpModal renders with
    # data-testid="hotkey-help-dialog" (frontend/src/components/HotkeyHelpModal.tsx:94).
    page.wait_for_selector('[data-testid="hotkey-help-dialog"]', timeout=5_000)

    # Close with Escape.
    page.keyboard.press("Escape")

    # The dialog should be gone.
    page.wait_for_selector('[data-testid="hotkey-help-dialog"]', state="hidden", timeout=5_000)

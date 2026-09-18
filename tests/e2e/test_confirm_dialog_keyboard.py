"""ConfirmDialog keyboard verification — BUG-KBD-4.

``docs/context/open-findings.md`` BUG-KBD-4: ``ConfirmDialog`` relies on its
focused button and has no explicit Escape/Enter bindings; the finding asked
for the destructive-action flow to be verified in a browser rather than
trusted from Radix's AlertDialog docstring.

This drives the Matches pane's "delete line" flow (F-035: the ``D`` hotkey
routes through ``ConfirmDialog`` before deleting) entirely by keyboard —
``J`` selects the line, ``D`` opens the confirm — and checks each claim
against the server, not the screen:

1. Escape cancels; the line is not deleted (server-side line_matches diff).
2. Tab-to-Confirm + Enter confirms; the line really is deleted.
3. Focus lands on the Cancel button when the dialog opens, and the first Tab
   moves to the Confirm button — not left "behind" the dialog on the page.
4. Focus does not stay pinned to the just-removed dialog after either
   close path.

Destructive (deletes the fixture's only seeded line) — runs on its own
function-scoped server, mirroring the ``mut_server`` pattern in
``test_selection_operations_parity.py``, so it cannot corrupt the
session-scoped ``live_server`` other files share.

Run:
    uv run --group e2e pytest tests/e2e/test_confirm_dialog_keyboard.py -v
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from playwright.sync_api import Page, Request, expect

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.conftest import (
    LiveServer,
    _install_tiny_fixture,
    _pick_free_port,
    _spa_built,
    _wait_until,
)
from tests.e2e.helpers import SEED_TIMEOUT, wait_for_page_loaded

pytestmark = pytest.mark.e2e

_PROJECT_ID = "tiny-fixture"


@pytest.fixture
def isolated_live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveServer]:
    """Function-scoped tiny-fixture server, isolated for a destructive test.

    Confirming the delete in this test really removes tiny-fixture page 0's
    one seeded line. The session-scoped ``live_server`` fixture is shared by
    every other e2e file, several of which depend on that line existing
    (e.g. ``test_keyboard_only.py``) — reusing it here would make this test's
    pass/fail order-dependent on the rest of the suite. A fresh server with
    its own tmp source/data roots avoids that.
    """
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) before E2E tests")

    data_root = tmp_path_factory.mktemp("kbd-confirm-data")
    cache_root = tmp_path_factory.mktemp("kbd-confirm-cache")
    config_root = tmp_path_factory.mktemp("kbd-confirm-config")
    source_root = tmp_path_factory.mktemp("kbd-confirm-source")

    _install_tiny_fixture(source_root)

    port = _pick_free_port()
    settings = Settings(
        host="127.0.0.1",
        port=port,
        data_root=data_root,
        cache_root=cache_root,
        config_root=config_root,
        source_projects_root=source_root,
        mode="normal",
    )
    app = build_app(settings)
    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{settings.host}:{settings.port}"
    try:
        _wait_until(f"{base_url}/healthz")
    except RuntimeError:
        server.should_exit = True
        thread.join(timeout=2)
        raise

    yield LiveServer(base_url=base_url, settings=settings, source_root=source_root)

    server.should_exit = True
    thread.join(timeout=5)


def _load_and_goto_page1(live: LiveServer, page: Page) -> None:
    """Load tiny-fixture and navigate to page 1 (page_index 0), fully rendered."""
    httpx.post(
        f"{live.base_url}/api/projects/source-root",
        json={"path": str(live.source_root)},
        timeout=SEED_TIMEOUT,
    )
    project_path = str(live.source_root / _PROJECT_ID)
    resp = httpx.post(
        f"{live.base_url}/api/projects/load",
        json={"project_root": project_path},
        timeout=SEED_TIMEOUT,
    )
    assert resp.status_code == 200, f"load_project failed: {resp.status_code} {resp.text}"

    url = f"{live.base_url}/projects/{_PROJECT_ID}/pages/pageno/1"
    page.goto(url, timeout=15_000)
    wait_for_page_loaded(page, live.base_url, timeout=15_000)


def _get_line_matches(base_url: str) -> list[dict[str, object]]:
    """Server truth for page 0's line_matches — never trust the screen alone."""
    r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=SEED_TIMEOUT)
    assert r.status_code == 200, f"GET page 0 failed: {r.status_code} {r.text}"
    line_matches = r.json()["line_matches"]
    assert isinstance(line_matches, list)
    return line_matches


def _focused_testid(page: Page) -> str | None:
    """``data-testid`` of ``document.activeElement``, or ``None`` if unset/absent."""
    return page.evaluate("() => document.activeElement?.getAttribute('data-testid') ?? null")


@pytest.mark.e2e
def test_confirm_dialog_delete_line_keyboard_only(isolated_live_server: LiveServer, page: Page) -> None:
    """Drive the Matches-pane delete-line confirm entirely by keyboard.

    ``J`` (matches scope) selects line 0; ``D`` opens ``ConfirmDialog``
    (ProjectPage.tsx's ``onDelete`` — F-035). Chosen over WordFooter's
    per-word delete or MultiLineDetail's bulk delete because it needs no
    mouse-driven setup (hierarchy tree clicks, multi-select) to reach —
    the whole flow, selection included, is two keystrokes — and because
    tiny-fixture page 0 is deterministically seeded with exactly one line,
    giving a clean, unambiguous server-side signal: 1 line_match before,
    1 after Escape, 0 after a confirmed delete.
    """
    live = isolated_live_server
    _load_and_goto_page1(live, page)

    initial_lines = _get_line_matches(live.base_url)
    assert len(initial_lines) == 1, f"expected tiny-fixture's one seeded line, got {initial_lines}"

    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    delete_requests: list[str] = []

    def _record_delete_request(req: Request) -> None:
        if "delete-batch" in req.url:
            delete_requests.append(req.url)

    page.on("request", _record_delete_request)

    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)

    # J selects line 0 (matches scope) so D has a line to act on.
    page.keyboard.press("j")

    # D opens the confirm dialog rather than deleting directly (F-035).
    page.keyboard.press("d")
    dialog = page.locator('[data-testid="confirm-dialog"]')
    expect(dialog).to_be_visible(timeout=5_000)

    # --- (3) Focus on open ---------------------------------------------
    # Radix's AlertDialog default-focuses Cancel, not Confirm, as a safety
    # default for destructive dialogs. The finding's "relies on its focused
    # button" premise turns out to name the wrong button: an Enter pressed
    # the instant the dialog opens would cancel, not confirm.
    assert _focused_testid(page) == "confirm-dialog-cancel", (
        f"Expected initial focus on confirm-dialog-cancel, got {_focused_testid(page)!r}"
    )

    # The first Tab moves to the dialog's other control — Confirm — which is
    # where a person tabbing forward from Cancel would expect to land, not
    # out of the dialog and back to the page behind it.
    page.keyboard.press("Tab")
    assert _focused_testid(page) == "confirm-dialog-confirm", (
        f"Expected Tab to move focus to confirm-dialog-confirm, got {_focused_testid(page)!r}"
    )

    # --- (1) Escape cancels ----------------------------------------------
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden(timeout=5_000)
    assert not delete_requests, f"Escape must not delete anything; saw requests: {delete_requests}"

    after_cancel = _get_line_matches(live.base_url)
    assert after_cancel == initial_lines, (
        f"Escape must not mutate server state; line_matches changed: {initial_lines} -> {after_cancel}"
    )

    # --- (4) Focus after close, Escape path -------------------------------
    # The Cancel button that had focus is now gone from the DOM — focus must
    # not still read as pointing at it (a dangling reference into removed
    # DOM would be a keyboard trap). Re-firing J/D below is the stronger
    # proof: it only succeeds if the page, not a phantom dialog, has focus.
    assert _focused_testid(page) != "confirm-dialog-cancel", (
        f"Focus should not remain on the removed dialog's Cancel button: {_focused_testid(page)!r}"
    )

    # Re-open to prove keyboard control returned to the page, not trapped
    # behind the now-closed dialog.
    page.keyboard.press("d")
    expect(dialog).to_be_visible(timeout=5_000)
    assert _focused_testid(page) == "confirm-dialog-cancel", (
        "Re-opened dialog should focus Cancel again, same as the first open"
    )

    # --- (2) Enter confirms when Confirm has focus ------------------------
    # Tab to Confirm first — native focused-button behavior alone lands on
    # Cancel (see above), so an Enter here without the Tab would cancel.
    page.keyboard.press("Tab")
    assert _focused_testid(page) == "confirm-dialog-confirm"

    with page.expect_response(lambda r: "delete-batch" in r.url) as delete_resp_info:
        page.keyboard.press("Enter")
    delete_resp = delete_resp_info.value
    assert delete_resp.status == 200, f"delete-batch failed: {delete_resp.status} {delete_resp.text()}"

    expect(dialog).to_be_hidden(timeout=5_000)

    after_confirm = _get_line_matches(live.base_url)
    assert after_confirm == [], f"Enter-confirm should have deleted line 0; line_matches is {after_confirm}"

    # --- (4) Focus after close, Enter/confirm path -------------------------
    assert _focused_testid(page) != "confirm-dialog-confirm", (
        f"Focus should not remain on the removed dialog's Confirm button: {_focused_testid(page)!r}"
    )

    # The page shell is still alive and no fatal JS errors were raised by
    # the keyboard-only flow.
    page.wait_for_selector('[data-testid="project-page"]', timeout=5_000)
    fatal = [e for e in errors if "Uncaught" in e or "TypeError" in e or "Cannot read" in e]
    assert not fatal, f"Console errors during keyboard confirm-dialog flow: {fatal}"

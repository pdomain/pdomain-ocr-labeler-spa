"""E2E — the AppShell suite launcher shows an honest empty state.

docs/issues/2026-07-21-suite-launcher-app-shims.md (P1-SUITE). Follows the
``live_server`` fixture pattern used by ``test_export_manifest_and_trainer.py``
(read first).

This sandbox has no sibling pdomain-* app installed — ``/api/suite/installed``
is backed by a local TOML registry (``pdomain_ops.suite.registry``) that a
sibling app populates by calling ``register_self`` at *its own* startup, and
no such process runs here. That rules out a real end-to-end test of "lists an
installed sibling" or "launches one" — this file covers the one flow that
*is* honestly drivable without external apps installed: what a person sees
when the suite has no siblings to offer. The list/launch/refused-launch
outcomes are covered at the vitest level instead (real, unmocked
SuiteSiblingsProvider/LauncherSlot/LauncherTile against MSW — see
frontend/src/components/shell/SuiteLauncher.test.tsx), where an installed
sibling can be simulated.

Before P1-SUITE, App.tsx's ``fetchInstalled`` shim always resolved `[]` too
— so this same DOM state existed, but for the wrong reason (a hard-coded
stub, not a real, validated fetch), and pdomain-ui's own ``LauncherSlot``
renders nothing at all for an empty list, so nobody could tell "no siblings"
from "the launcher is broken." This test proves the real backend route drives
a real, honest, visible message instead.

Run with:
    uv run --group e2e pytest tests/e2e/test_suite_launcher_empty.py \
        --browser chromium -v
"""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import wait_for_app_ready

pytestmark = pytest.mark.e2e


def test_suite_launcher_shows_no_apps_installed(page: Page, live_server: LiveServer) -> None:
    """No siblings installed: the header says so instead of showing nothing.

    Asserts the real precondition first (this sandbox's suite registry is
    empty) so a future environment where a sibling *is* installed fails
    loudly here rather than silently passing on a state this test never
    actually drove.
    """
    wait_for_app_ready(live_server.base_url)

    installed_resp = httpx.get(f"{live_server.base_url}/api/suite/installed", timeout=5)
    assert installed_resp.status_code == 200
    assert installed_resp.json() == [], (
        "expected no installed sibling apps in this sandbox — if a sibling "
        "is legitimately installed here now, this file's docstring "
        "assumption is stale and the 'lists what the route returns' case "
        "should move from vitest to a real e2e test instead"
    )

    page.goto(live_server.base_url, timeout=20_000)
    page.locator("[data-testid='header-bar']").wait_for(state="visible", timeout=20_000)

    empty_notice = page.locator("[data-testid='suite-launcher-empty']")
    expect(empty_notice).to_be_visible(timeout=10_000)
    expect(empty_notice).to_have_text("No other suite apps installed")

    # The two failure/success surfaces this environment can't exercise stay
    # absent — proves this is the real empty state, not a broken fetch that
    # happens to render similarly.
    expect(page.locator("[data-testid='suite-launcher-unavailable']")).to_have_count(0)
    expect(page.locator("[aria-label^='Launch ']")).to_have_count(0)

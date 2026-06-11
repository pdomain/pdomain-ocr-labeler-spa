"""Environment sanity canary for the e2e browser tier.

Runs first (alphabetically early, and trivially fast — it needs no
``live_server``) so a broken browser environment surfaces as ONE clear
failure instead of dozens of cryptic click-timeout failures plus an
apparent suite hang.

Ported from ``pdomain-ocr-simple-gui`` (commit 29a481f) after the
2026-06-10 stale-``DISPLAY`` preflight incident there; this repo's
Playwright tier has identical exposure (the wedge reproduces in this
workspace with the inherited devcontainer ``DISPLAY``).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

_RAF_PROBE = """() => new Promise((resolve) => {
    let fired = false;
    requestAnimationFrame(() => { fired = true; resolve(true); });
    setTimeout(() => { if (!fired) resolve(false); }, 3000);
})"""


def test_animation_frames_fire(page: Page) -> None:
    """``requestAnimationFrame`` must fire in the test browser.

    If this fails, headless chromium is not producing compositor frames, so
    EVERY Playwright actionability check in this tier (click, drag, the
    "stable" wait) will burn its full timeout and the run will look like
    dozens of unrelated failures followed by an apparent hang.

    Known cause (2026-06-10 incident in pdomain-ocr-simple-gui, reproduced
    in this workspace): a stale ``DISPLAY`` env var — a devcontainer
    X-forwarding socket left over from a previous editor session — wedges
    headless chromium's frame production even though the page reports
    ``visibilityState === "visible"``.  ``tests/e2e/conftest.py`` strips
    ``DISPLAY`` for headless runs; if this test fails, check for new env
    leakage into the browser environment (and that the conftest guard still
    runs before the browser launches).
    """
    _ = page.goto("data:text/html,<title>e2e environment canary</title>")
    fired = bool(page.evaluate(_RAF_PROBE))
    assert fired, (
        "requestAnimationFrame did not fire within 3s — headless chromium is "
        "not producing frames. Every click in this tier would time out. "
        "Most likely cause: a stale DISPLAY env var reached the browser "
        "process (see this test's docstring)."
    )

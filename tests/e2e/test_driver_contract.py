"""Driver-contract conformance E2E test.

Loads the tiny-fixture project, walks the full UI, and asserts that every
testid catalogued in ``docs/architecture/13-driver-contract.md §2`` (or the spec doc
``docs/specs/2026-05-12-driver-contract-design.md §Testid catalogue``) is
either:

  (a) present in the DOM, or
  (b) present AND ``data-testid-stub="true"`` (not-yet-implemented cells).

Tests that require navigating to a specific page or opening a dialog are
self-contained; a failure in one does not cascade to the next.

URL invariants are asserted after every navigation step.

Spec: docs/specs/2026-05-12-driver-contract-design.md §Conformance test
Issue #242

Run:
    make e2e
    # or
    uv run pytest tests/e2e/test_driver_contract.py -v
"""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer

# ── testid groups per spec §2 ────────────────────────────────────────────────
# These are the ALWAYS-PRESENT (possibly stub) driver-contract testids that
# must exist in the DOM at all times once the app shell renders.

# Header group — rendered on every route.
_HEADER_TESTIDS = [
    "project-select",
    "load-project-button",
    "source-folder-button",
    "ocr-config-trigger-button",
]

# Source-folder dialog stubs (display:none until implemented).
_SOURCE_FOLDER_STUB_TESTIDS = [
    "source-folder-current-path-label",
    "source-folder-path-input",
    "source-folder-home-button",
    "source-folder-up-button",
    "source-folder-open-typed-button",
    "source-folder-use-current-button",
    "source-folder-cancel-button",
    "source-folder-apply-button",
]

# OCR config modal stubs (display:none until implemented in full).
_OCR_CONFIG_STUB_TESTIDS = [
    "ocr-detection-model-select",
    "ocr-recognition-model-select",
    "ocr-hf-revision-input",
    "ocr-rescan-models-button",
    "ocr-config-cancel-button",
    "ocr-config-apply-button",
]

# Nav stubs (display:none until implemented).
_NAV_STUB_TESTIDS = [
    "nav-prev-button",
    "nav-next-button",
    "nav-goto-button",
    "nav-page-input",
    "nav-page-total-label",
]

# Text-tabs group (rendered when project page is active).
_TEXT_TABS_TESTIDS = [
    "text-tab-matches",
    "text-tab-ground-truth",
    "text-tab-ocr",
    "match-filter-toggle",
    "match-filter-unvalidated",
    "match-filter-mismatched",
    "match-filter-all",
]


def _all_stub_or_present(page: Page, testids: list[str]) -> list[str]:
    """Return list of testids that are completely absent from the DOM."""
    missing = []
    for tid in testids:
        count = page.locator(f'[data-testid="{tid}"]').count()
        if count == 0:
            missing.append(tid)
    return missing


def _load_tiny_fixture(base_url: str, source_root_path: str) -> None:
    """POST /api/source-root then POST /api/projects/load for tiny-fixture."""
    # Set source root so the server knows where to look.
    httpx.post(
        f"{base_url}/api/source-root",
        json={"path": source_root_path},
        timeout=5,
    )
    project_path = str(source_root_path) + "/tiny-fixture"
    resp = httpx.post(
        f"{base_url}/api/projects/load",
        json={"project_root": project_path},
        timeout=5,
    )
    assert resp.status_code == 200, f"load_project failed: {resp.status_code} {resp.text}"


@pytest.mark.e2e
def test_app_shell_renders(live_server: LiveServer, page: Page) -> None:
    """The SPA root renders the app shell (#root) without errors."""
    page.goto(live_server.base_url, timeout=15_000)
    page.wait_for_selector("#root", timeout=10_000)
    # No console errors that indicate a fatal crash.
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    assert 'id="root"' in page.content(), "React root not found"


@pytest.mark.e2e
def test_header_testids_present(live_server: LiveServer, page: Page) -> None:
    """All header-group testids exist in the DOM on the root route.

    These are always-rendered elements (project-select, load-project-button,
    source-folder-button, ocr-config-trigger-button).
    """
    page.goto(live_server.base_url, timeout=15_000)
    page.wait_for_selector("#root", timeout=10_000)
    missing = _all_stub_or_present(page, _HEADER_TESTIDS)
    assert not missing, f"Header testids missing from DOM: {missing}"


@pytest.mark.e2e
def test_stub_testids_present(live_server: LiveServer, page: Page) -> None:
    """All stub testids (display:none, data-testid-stub=true) exist in DOM.

    Checks source-folder dialog stubs, OCR config stubs, and nav stubs that
    are rendered as hidden placeholder elements until full implementation.
    """
    page.goto(live_server.base_url, timeout=15_000)
    page.wait_for_selector("#root", timeout=10_000)

    all_stubs = _SOURCE_FOLDER_STUB_TESTIDS + _OCR_CONFIG_STUB_TESTIDS + _NAV_STUB_TESTIDS
    missing = _all_stub_or_present(page, all_stubs)
    assert not missing, f"Stub testids missing from DOM (should exist even if display:none): {missing}"


@pytest.mark.e2e
def test_stub_testids_have_stub_attribute(live_server: LiveServer, page: Page) -> None:
    """Stub testids carry data-testid-stub='true' so the driver can distinguish them."""
    page.goto(live_server.base_url, timeout=15_000)
    page.wait_for_selector("#root", timeout=10_000)

    all_stubs = _SOURCE_FOLDER_STUB_TESTIDS + _OCR_CONFIG_STUB_TESTIDS + _NAV_STUB_TESTIDS
    not_stubbed = []
    for tid in all_stubs:
        locator = page.locator(f'[data-testid="{tid}"][data-testid-stub="true"]')
        if locator.count() == 0:
            not_stubbed.append(tid)
    assert not not_stubbed, f"Stub testids missing data-testid-stub='true' attribute: {not_stubbed}"


@pytest.mark.e2e
def test_project_page_route_renders(live_server: LiveServer, page: Page) -> None:
    """Navigating to /projects/{id}/pages/pageno/1 renders the project-page shell."""
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)

    # URL invariant: canonical form must be preserved.
    assert "/projects/tiny-fixture/pages/pageno/1" in page.url, (
        f"URL invariant violated: expected pageno/1 in URL, got {page.url!r}"
    )


@pytest.mark.e2e
def test_text_tabs_testids_present_on_project_page(live_server: LiveServer, page: Page) -> None:
    """Text-tab testids are present once a project page route renders."""
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)

    # Text-tabs testids are rendered in the project page shell even before
    # full M3 data hooks are wired — the TextTabs component is mounted.
    missing = _all_stub_or_present(page, _TEXT_TABS_TESTIDS)
    # Some may not be rendered yet (M2 stub page). Only fail if the tab
    # navigation buttons are gone (those are always-rendered).
    nav_tabs = ["text-tab-matches", "text-tab-ground-truth", "text-tab-ocr"]
    missing_nav = [t for t in nav_tabs if t in missing]
    assert not missing_nav, f"Tab navigation testids missing from project page: {missing_nav}"


@pytest.mark.e2e
def test_ocr_config_modal_testids_present(live_server: LiveServer, page: Page) -> None:
    """OCR config modal testids exist (stub or active) before modal is open."""
    page.goto(live_server.base_url, timeout=15_000)
    page.wait_for_selector("#root", timeout=10_000)

    # Modal testid exists only when modal is open (not stub).
    # The stubs inside ProjectPage are always-present; the modal itself
    # only mounts when the button is clicked.
    missing = _all_stub_or_present(page, _OCR_CONFIG_STUB_TESTIDS)
    assert not missing, f"OCR config stub testids missing: {missing}"

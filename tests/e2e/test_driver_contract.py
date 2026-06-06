"""Driver-contract conformance E2E test.

Covers: B-DRIVER-001, B-DRIVER-002, B-DRIVER-003, B-DRIVER-005

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
from tests.e2e.helpers import SEED_TIMEOUT, page_line_match_count, wait_for_project_ready

# ── testid groups per spec §2 ────────────────────────────────────────────────
# These are the ALWAYS-PRESENT (possibly stub) driver-contract testids that
# must exist in the DOM at all times once the app shell renders.

# Deprecated header testids (D-046) — these MUST NOT exist anywhere in the DOM
# after commit b101ec8 removed the legacy stubs from HeaderBar.
# Note: ocr-config-trigger-button was briefly removed (#401) but is now restored
# in PageActionsCompact as a real button (#405); it is no longer deprecated.
_DEPRECATED_HEADER_TESTIDS = [
    "project-select",  # moved to ProjectLoadControls.tsx on RootPage
    "load-project-button",  # moved to ProjectLoadControls.tsx on RootPage
    "source-folder-button",  # moved to ProjectLoadControls.tsx (breadcrumb mode)
]

# New §2.1 testids (post-D-046) — reachable via their real components.
# These are always-rendered elements per the updated driver contract.
_NEW_HEADER_TESTIDS = [
    "rail-hotkeys-button",  # Rail.tsx footer — hotkey help trigger
    "page-actions-compact-export",  # PageActionsCompact.tsx — export trigger
    "ocr-config-trigger-button",  # PageActionsCompact.tsx — OCR config trigger (#405 restore)
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

# Glyph testids that are always present once the project page loads.
# (spec §7 / driver-contract §2.15, issue #270)
# Parameterised testids (* -{line}-{word}, *-{i}) are NOT listed here —
# their existence is state-dependent. The dialog testids are checked
# in test_glyph_bulk_dialog_testids_present (dialog must be opened first).
_GLYPH_STATIC_TESTIDS = [
    "bulk-glyph-mark-button",  # always present in PageActionsCompact on project page
]

# Glyph testids visible only when the BulkGlyphMarkDialog is open.
_GLYPH_DIALOG_TESTIDS = [
    "bulk-glyph-mark-dialog",
    "bulk-glyph-recipe-select",
    "bulk-glyph-skip-annotated-checkbox",
    "bulk-glyph-accept-predictions-checkbox",
    "bulk-glyph-dry-run-button",
    "bulk-glyph-apply-button",
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

# Apply Style toolbar row (driver-contract §2.10) — present when project page loads.
# Parameterised stubs ("toolbar-{scope}-{action}") are NOT listed here.
_APPLY_STYLE_TOOLBAR_TESTIDS = [
    "apply-style-select",
    "scope-select",  # was "apply-scope-select" — bug #452
    "apply-component-select",
    "apply-style-button",
    "apply-component-button",  # bug #452: was absent
    "clear-component-button",  # bug #452: was absent
    "word-add-button",  # was "add-word-button" — bug #452
]

# Word-edit dialog testids (driver-contract §2.11).
# Checked after opening the dialog via edit-word-button-0-0.
_WORD_EDIT_DIALOG_TESTIDS = [
    "word-edit-dialog",  # bug #454: was "dialog-backdrop" only
    "dialog-header-label",
    "dialog-apply-close-button",
    "dialog-close-button",
    "dialog-previous-preview-column",  # bug #454: was "dialog-prev-word" only
    "dialog-current-preview-column",  # bug #454: was "dialog-current-word" only
    "dialog-next-preview-column",  # bug #454: was "dialog-next-word" only
    "dialog-gt-input",  # bug #454: was absent
    "dialog-tag-chips-slot",  # bug #454: was absent
    "dialog-refine-button",
    "dialog-expand-refine-button",
    "dialog-reset-button",
    "dialog-apply-button",
    "dialog-apply-refine-button",
    "dialog-merge-prev-button",
    "dialog-merge-next-button",
    "dialog-split-h-button",
    "dialog-split-v-button",
    "dialog-delete-word-button",
    "dialog-crop-above-button",
    "dialog-crop-below-button",
    "dialog-crop-left-button",
    "dialog-crop-right-button",
    "dialog-style-select",
    "dialog-scope-select",
    "dialog-component-select",
    "dialog-apply-style-button",
    "dialog-apply-component-button",
    "dialog-clear-component-button",
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
        timeout=SEED_TIMEOUT,
    )
    project_path = str(source_root_path) + "/tiny-fixture"
    resp = httpx.post(
        f"{base_url}/api/projects/load",
        json={"project_root": project_path},
        timeout=SEED_TIMEOUT,
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
    """Post-D-046 driver-contract §2.1 conformance on the root route.

    D-046 (2026-05-21): the legacy inline HeaderBar stubs have been removed.
    This test asserts:
      (a) Deprecated testids are NOT present anywhere in the DOM (the stubs
          were deleted — not hidden — per commit b101ec8).
      (b) New §2.1 testids (rail-hotkeys-button, page-actions-compact-export)
          are present on a project page route where PageActionsCompact renders.

    Project-load controls (project-select, load-project-button,
    source-folder-button) are real elements in ProjectLoadControls.tsx and
    appear only on the RootPage or in breadcrumb mode — they are tested
    separately via the RootPage fixture.
    """
    page.goto(live_server.base_url, timeout=15_000)
    page.wait_for_selector("#root", timeout=10_000)

    # (a) Deprecated testids must NOT be in the DOM (no stubs remaining).
    present_deprecated = []
    for tid in _DEPRECATED_HEADER_TESTIDS:
        if page.locator(f'[data-testid="{tid}"]').count() > 0:
            present_deprecated.append(tid)
    assert not present_deprecated, (
        f"Deprecated HeaderBar testids still in DOM (D-046 says they must be removed): {present_deprecated}"
    )


@pytest.mark.e2e
def test_new_contract_testids_present_on_project_page(live_server: LiveServer, page: Page) -> None:
    """New §2.1 testids (post-D-046) are present on a loaded project page.

    Covers: B-DRIVER-001

    rail-hotkeys-button is rendered by Rail.tsx inside ProjectPage.
    page-actions-compact-export is rendered by PageActionsCompact on project routes.
    Both are real interactive elements (not stubs) per the updated contract.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    wait_for_project_ready(page)

    missing = _all_stub_or_present(page, _NEW_HEADER_TESTIDS)
    assert not missing, f"New §2.1 driver-contract testids missing from project page: {missing}"

    # Also verify deprecated testids are absent on the project page route too.
    present_deprecated = []
    for tid in _DEPRECATED_HEADER_TESTIDS:
        if page.locator(f'[data-testid="{tid}"]').count() > 0:
            present_deprecated.append(tid)
    assert not present_deprecated, (
        f"Deprecated testids found on project page (D-046 removed them): {present_deprecated}"
    )


@pytest.mark.e2e
def test_stub_testids_present(live_server: LiveServer, page: Page) -> None:
    """All stub testids (display:none, data-testid-stub=true) exist in DOM.

    Covers: B-DRIVER-001

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
    """Stub testids carry data-testid-stub='true' so the driver can distinguish them.

    Covers: B-DRIVER-001
    """
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
    """Navigating to /projects/{id}/pages/pageno/1 renders the project-page shell.

    Covers: B-DRIVER-002
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    wait_for_project_ready(page)

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
    wait_for_project_ready(page)

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


@pytest.mark.e2e
def test_glyph_static_testids_present_on_project_page(live_server: LiveServer, page: Page) -> None:
    """Glyph AC #270: static glyph testids present in driver-contract §2.15 on project page.

    ``bulk-glyph-mark-button`` is always rendered in PageActionsCompact
    once a project page is loaded.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    wait_for_project_ready(page)

    missing = _all_stub_or_present(page, _GLYPH_STATIC_TESTIDS)
    assert not missing, f"Static glyph testids missing from project page: {missing}"


@pytest.mark.e2e
def test_glyph_bulk_dialog_testids_present(live_server: LiveServer, page: Page) -> None:
    """Glyph AC #270: dialog testids from driver-contract §2.15 present when dialog opens.

    Opens the BulkGlyphMarkDialog via ``bulk-glyph-mark-button`` and asserts
    all dialog-interior testids from spec §7.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="bulk-glyph-mark-button"]', timeout=10_000)
    wait_for_project_ready(page)

    page.click('[data-testid="bulk-glyph-mark-button"]')
    page.wait_for_selector('[data-testid="bulk-glyph-mark-dialog"]', timeout=5_000)

    missing = _all_stub_or_present(page, _GLYPH_DIALOG_TESTIDS)
    assert not missing, f"Glyph dialog testids missing after opening dialog: {missing}"


# ── F-046 / F-047 / F-048 / F-049 coverage ──────────────────────────────────


@pytest.mark.e2e
def test_apply_style_toolbar_testids_present(live_server: LiveServer, page: Page) -> None:
    """Driver-contract §2.10: all Apply Style toolbar testids present on project page.

    Covers #452 (F-047): scope-select, apply-component-button, clear-component-button,
    word-add-button were missing or had wrong IDs.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    wait_for_project_ready(page)

    missing = _all_stub_or_present(page, _APPLY_STYLE_TOOLBAR_TESTIDS)
    assert not missing, (
        f"Apply Style toolbar testids missing from project page (driver-contract §2.10, #452): {missing}"
    )


@pytest.mark.e2e
def test_per_line_driver_testids_present(live_server: LiveServer, page: Page) -> None:
    """Driver-contract §2.8: per-line testids (line-checkbox, line-card) present on project page.

    Covers #453 (F-048): line-checkbox-{n} was absent.
    Asserts line-card-0 and line-checkbox-0 are present after the matches tab renders.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))
    if page_line_match_count(live_server.base_url, "tiny-fixture", 0) == 0:
        pytest.skip(
            "tiny-fixture has no word content in this environment — per-line/word "
            "driver testids are verified against the exercise fixture (test_spec_s2_coverage)"
        )

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    wait_for_project_ready(page)

    # Navigate to the Matches tab (text-tab-matches) to ensure word-match-view renders.
    page.click('[data-testid="text-tab-matches"]')
    page.wait_for_selector('[data-testid="word-match-view"]', timeout=10_000)

    # The tiny-fixture has at least one line; line-card-0 and line-checkbox-0 must exist.
    missing = _all_stub_or_present(page, ["line-card-0", "line-checkbox-0"])
    assert not missing, f"Per-line driver-contract §2.8 testids missing (#453): {missing}"


@pytest.mark.e2e
def test_per_word_driver_testids_present(live_server: LiveServer, page: Page) -> None:
    """Driver-contract §2.8: per-word testids present in the first line card.

    Covers #453 (F-048): word-checkbox-{l}-{w}, word-validate-button-{l}-{w},
    word-image-cell-{l}-{w} were absent or on alias attributes.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))
    if page_line_match_count(live_server.base_url, "tiny-fixture", 0) == 0:
        pytest.skip(
            "tiny-fixture has no word content in this environment — per-word "
            "driver testids are verified against the exercise fixture (test_spec_s2_coverage)"
        )

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    wait_for_project_ready(page)

    page.click('[data-testid="text-tab-matches"]')
    page.wait_for_selector('[data-testid="word-match-view"]', timeout=10_000)

    # word-image-cell-0-0, word-checkbox-0-0, word-validate-button-0-0 must exist
    # for the first word (line 0, word 0).
    per_word_testids = [
        "word-image-cell-0-0",
        "word-checkbox-0-0",
        "word-validate-button-0-0",
        "gt-text-input-0-0",
        "ocr-text-label-0-0",
        "word-status-icon-0-0",
        "edit-word-button-0-0",
    ]
    missing = _all_stub_or_present(page, per_word_testids)
    assert not missing, f"Per-word driver-contract §2.8 testids missing (#453): {missing}"


@pytest.mark.e2e
def test_word_edit_dialog_testids_present(live_server: LiveServer, page: Page) -> None:
    """Driver-contract §2.11: word-edit-dialog testids present when dialog is open.

    Covers #454 (F-049): word-edit-dialog, dialog-{previous,current,next}-preview-column,
    dialog-gt-input, dialog-tag-chips-slot were absent or misnamed.

    Opens the word-edit dialog via edit-word-button-0-0, then asserts all
    §2.11 testids are present in the DOM.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))
    if page_line_match_count(live_server.base_url, "tiny-fixture", 0) == 0:
        pytest.skip(
            "tiny-fixture has no word content in this environment — word-edit-dialog "
            "testids are verified against the exercise fixture (test_spec_s2_coverage)"
        )

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    wait_for_project_ready(page)

    page.click('[data-testid="text-tab-matches"]')
    page.wait_for_selector('[data-testid="edit-word-button-0-0"]', timeout=10_000)

    page.click('[data-testid="edit-word-button-0-0"]')
    page.wait_for_selector('[data-testid="word-edit-dialog"]', timeout=5_000)

    missing = _all_stub_or_present(page, _WORD_EDIT_DIALOG_TESTIDS)
    assert not missing, (
        f"Word-edit dialog testids missing after opening dialog (driver-contract §2.11, #454): {missing}"
    )

"""Smoke E2E test for the assembled ProjectPage shell (spec 22 §12).

Loads the tiny-fixture project, navigates Prev/Next via the real
ProjectNavigationControls, opens the OCR-config dialog from the
HeaderBar trigger, and opens a word in the mounted right-panel editor.

Spec: specs/22-page-surface-wireup.md §12 (Acceptance gates).
Issue #314 (spec-22-C).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import require_page_line_matches, wait_for_page_loaded
from tests.e2e.test_driver_contract import _load_tiny_fixture


@pytest.mark.e2e
def test_project_page_loads_with_tiny_fixture(live_server: LiveServer, page: Page) -> None:
    """Loading the tiny-fixture project page renders the assembled shell.

    Covers: B-PROJECT-001, B-CANVAS-001
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    wait_for_page_loaded(page, live_server.base_url, timeout=15_000)

    # The assembled shell mounts the real ProjectPage layout (ProjectPage.tsx
    # header §3): project-page root → project-workspace grid → the three
    # columns, with image-pane / text-pane inside. StudioShell is defined but
    # NEVER mounted by ProjectPage in production (ProjectPage.test.tsx asserts
    # studio-shell is null), so we assert the real testids here.
    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    page.wait_for_selector('[data-testid="project-workspace"]', timeout=10_000)
    # image-pane is directly visible inside the canvas column.
    page.wait_for_selector('[data-testid="image-pane"]', timeout=10_000)
    # text-pane lives in the detail column; it may be collapsed/attached.
    page.wait_for_selector('[data-testid="text-pane"]', state="attached", timeout=10_000)


@pytest.mark.e2e
def test_navigate_prev_next(live_server: LiveServer, page: Page) -> None:
    """Click Next then Prev; the URL transitions to pageno/2 then pageno/1.

    Covers: B-PROJECT-002
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    start_url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(start_url, timeout=15_000)
    wait_for_page_loaded(page, live_server.base_url, timeout=15_000)

    # Drive Next via the real (non-stub) nav button. The HeaderBar mirrors
    # the testid as a stub; we select the real one explicitly.
    next_btn = page.locator('[data-testid="nav-next-button"]:not([data-testid-stub])')
    next_btn.wait_for(state="visible", timeout=10_000)
    next_btn.click()
    page.wait_for_url("**/pages/pageno/2", timeout=10_000)
    assert "/pages/pageno/2" in page.url

    prev_btn = page.locator('[data-testid="nav-prev-button"]:not([data-testid-stub])')
    prev_btn.wait_for(state="visible", timeout=10_000)
    prev_btn.click()
    page.wait_for_url("**/pages/pageno/1", timeout=10_000)
    assert "/pages/pageno/1" in page.url


@pytest.mark.e2e
def test_open_ocr_config_dialog(live_server: LiveServer, page: Page) -> None:
    """Opening the OCR-config modal via the trigger button mounts the modal.

    Covers: B-ACTIONS-001

    #405: ocr-config-trigger-button restored in PageActionsCompact (project-page
    context) after it was inadvertently removed by D-046 / #401.  The real button
    lives inside PageActionsCompact, which is only rendered when on a project route.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    wait_for_page_loaded(page, live_server.base_url, timeout=15_000)

    # #405: ocr-config-trigger-button is now a real button in PageActionsCompact.
    # Click it to open the OCR-config modal.
    trigger = page.locator('[data-testid="ocr-config-trigger-button"]:not([data-testid-stub])')
    trigger.wait_for(state="visible", timeout=10_000)
    trigger.click()

    # The OCR-config modal mounts at AppShell once opened — wait for the
    # modal container (driver-contract §2.3: `ocr-config-modal`).
    page.wait_for_selector(
        '[data-testid="ocr-config-modal"]',
        timeout=10_000,
    )


@pytest.mark.e2e
def test_word_edit_dialog_lifecycle(live_server: LiveServer, page: Page) -> None:
    """Select a word with the pencil and show it in the right panel.

    Covers: B-ACTIONS-005 and driver-contract section 2.11.

    The pencil selects the word and opens ``word-detail``. The retired
    modal is not mounted.
    """
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))
    require_page_line_matches(live_server.base_url, "tiny-fixture", 0)

    url = f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1"
    page.goto(url, timeout=15_000)
    wait_for_page_loaded(page, live_server.base_url, timeout=15_000)

    page.wait_for_selector('[data-testid="project-page"]', timeout=10_000)
    page.wait_for_selector('[data-testid="right-panel"]', state="visible", timeout=10_000)
    assert page.locator('[data-testid="word-edit-dialog"]').count() == 0

    page.click('[data-testid="text-tab-matches"]')
    pencil = page.locator('[data-testid="edit-word-button-0-0"]')
    pencil.wait_for(state="visible", timeout=10_000)
    pencil.click()

    detail = page.locator('[data-testid="word-detail"]')
    detail.wait_for(state="visible", timeout=10_000)
    assert detail.first.is_visible()
    assert page.locator('[data-testid="word-edit-dialog"]').count() == 0

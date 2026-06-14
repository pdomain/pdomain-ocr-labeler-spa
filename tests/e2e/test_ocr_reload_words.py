"""TDD test: Reload OCR → words appear on canvas.

Bug: after clicking "Reload OCR" the OCR complete notification toast
appears (via the notification stream) but NO words appear in the worklist
or canvas overlay. The page query is never invalidated when the job
actually finishes.

Root cause: ProjectPage.tsx (the toolbar Reload OCR call site) is missing
the terminal-status useEffect. handleReloadOcr invalidates the page query
through the mutation's onSettled, which fires on the 202 response — long
before OCR has actually run. There is no later useEffect watching
jobProgress?.status === "complete" to re-invalidate when the SSE terminal
event arrives, so the worklist / canvas stay stale.

The correct pattern already lives in PageActionsCompact.tsx (lines 32-50):
a useEffect keyed on jobProgress?.status that, on "complete", calls
qc.invalidateQueries(["page", projectId, pageIndex]) and clears the active
job id. The toolbar Reload OCR button flows through ProjectPage's handler,
not PageActionsCompact's, so it never reaches that invalidation. The fix
extracts the inline effect into a shared hook (useJobCompletionInvalidation)
used by both call sites.

useJobProgress.ts itself is correct — it was already fixed in commit
1c6e313 to listen for "complete" / "error" SSE event types in addition
to "progress".

This test targets http://localhost:8080 (the running dev server) with
the real project. It skips when the server or project is unavailable.

Run:
    uv run --group e2e pytest tests/e2e/test_ocr_reload_words.py -v -s
"""

from __future__ import annotations

import time

import httpx
import pytest
from playwright.sync_api import Page

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8080"
PROJECT_ID = "projectID629292e7559a8"
PAGE_URL = f"{BASE_URL}/projects/{PROJECT_ID}/pages/pageno/1"

# OCR on real scanned pages can take up to 90s with a cold model.
OCR_TIMEOUT_MS = 120_000


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def running_server() -> str:
    """Return BASE_URL if the dev server is up; skip otherwise."""
    try:
        r = httpx.get(f"{BASE_URL}/healthz", timeout=3.0)
        if r.status_code != 200:
            pytest.skip(f"Server at {BASE_URL} returned {r.status_code}")
    except httpx.HTTPError as exc:
        pytest.skip(f"Dev server not reachable at {BASE_URL}: {exc}")

    # Confirm the specific project exists.
    try:
        r = httpx.get(f"{BASE_URL}/api/projects", timeout=5.0)
        projects = r.json().get("projects", [])
        ids = [p.get("project_id") for p in projects]
        if PROJECT_ID not in ids:
            pytest.skip(f"Project {PROJECT_ID!r} not loaded on server (found: {ids})")
    except Exception as exc:
        pytest.skip(f"Could not enumerate projects: {exc}")

    return BASE_URL


# ── Helpers ───────────────────────────────────────────────────────────────────


def _wait_for_ocr_complete_notification(page: Page, timeout_ms: int = OCR_TIMEOUT_MS) -> None:
    """Wait for the 'OCR complete' notification toast (positive kind).

    The notification comes through the notification stream (SSE), which is
    separate from the job-progress SSE stream. It should appear even when the
    job-progress hook is broken, so we use it as the timing signal.
    """
    # The notification stream toasts land as Sonner toasts; the driver-contract
    # testid pattern is notification-positive-{id} (spec §2.9).
    # Fallback: also accept any Sonner toast whose text contains "OCR complete".
    page.wait_for_selector(
        '[data-testid^="notification-positive-"], [data-sonner-toast][data-type="success"]',
        timeout=timeout_ms,
    )


def _count_worklist_rows(page: Page) -> int:
    """Return the current number of WorklistRow items in the worklist queue."""
    rows = page.locator('[data-testid="worklist-queue"] [role="option"]')
    return rows.count()


def _count_api_line_matches(page_index: int = 0) -> int:
    """Direct API call — how many line_matches does the server currently return?"""
    r = httpx.get(
        f"{BASE_URL}/api/projects/{PROJECT_ID}/pages/{page_index}",
        timeout=10.0,
    )
    if r.status_code != 200:
        return 0
    return len(r.json().get("line_matches", []))


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.e2e
def test_ocr_reload_refreshes_page_data(running_server: str, page: Page) -> None:
    """After Reload OCR completes, line_matches must appear in the UI.

    Failing state (before fix):
    - OCR runs, notification toast fires, but worklist stays empty because
      the page query is never invalidated.

    Passing state (after fix):
    - useJobProgress receives the "complete" SSE event, triggers
      invalidateQueries, page data is re-fetched, worklist shows lines.
    """
    page.goto(PAGE_URL, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=15_000)

    # Open the drawer so the worklist is visible.
    drawer_expand = page.locator('[data-testid="drawer-expand-btn"]')
    if drawer_expand.is_visible():
        drawer_expand.click()
    page.wait_for_selector('[data-testid="worklist-queue"]', timeout=5_000)

    initial_rows = _count_worklist_rows(page)

    # Click Reload OCR.
    reload_btn = page.locator('[data-testid="reload-ocr-button"]')
    reload_btn.wait_for(state="visible", timeout=5_000)
    reload_btn.click()

    # H-D (event-store undo U-6): Reload OCR now opens a confirm dialog
    # warning that the page's edit history resets. Approve it.
    confirm_btn = page.locator('[data-testid="confirm-dialog-confirm"]')
    confirm_btn.wait_for(state="visible", timeout=5_000)
    confirm_btn.click()

    # A loading toast should appear immediately.
    page.wait_for_selector(
        "[data-sonner-toast]",
        timeout=5_000,
    )

    # Wait for OCR to complete (may take up to 2 minutes).
    # The notification stream fires "OCR complete for page N" as a positive toast.
    _wait_for_ocr_complete_notification(page, timeout_ms=OCR_TIMEOUT_MS)

    # Give React a moment to process the invalidation and re-render.
    # The failing bug manifests as a timeout here because the worklist never updates.
    page.wait_for_function(
        """() => {
            const queue = document.querySelector('[data-testid="worklist-queue"]');
            if (!queue) return false;
            const rows = queue.querySelectorAll('[role="option"]');
            return rows.length > 0;
        }""",
        timeout=10_000,
    )

    final_rows = _count_worklist_rows(page)
    assert final_rows > 0, (
        f"Expected worklist to show lines after OCR, but found {final_rows} rows. "
        f"(started with {initial_rows}). "
        "Root cause: ProjectPage.handleReloadOcr only invalidates the page query "
        "via the mutation's onSettled (fires on the 202 response, before OCR runs). "
        "No useEffect watches jobProgress?.status === 'complete' to re-invalidate "
        "when the SSE terminal event arrives, so the worklist stays stale."
    )


@pytest.mark.e2e
def test_ocr_reload_api_returns_line_matches(running_server: str, page: Page) -> None:
    """Backend sanity: GET /pages/0 returns line_matches after OCR runs.

    This confirms the backend is correct; the bug is purely frontend.
    If this test fails too, the problem is in the backend OCR pipeline.
    """
    page.goto(PAGE_URL, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=15_000)

    reload_btn = page.locator('[data-testid="reload-ocr-button"]')
    reload_btn.wait_for(state="visible", timeout=5_000)
    reload_btn.click()

    # H-D (event-store undo U-6): Reload OCR now opens a confirm dialog
    # warning that the page's edit history resets. Approve it.
    confirm_btn = page.locator('[data-testid="confirm-dialog-confirm"]')
    confirm_btn.wait_for(state="visible", timeout=5_000)
    confirm_btn.click()

    _wait_for_ocr_complete_notification(page, timeout_ms=OCR_TIMEOUT_MS)

    # Poll the API directly — backend should have line_matches now.
    deadline = time.monotonic() + 5
    line_count = 0
    while time.monotonic() < deadline:
        line_count = _count_api_line_matches(0)
        if line_count > 0:
            break
        time.sleep(0.5)

    assert line_count > 0, (
        f"GET /api/projects/{PROJECT_ID}/pages/0 returned 0 line_matches after OCR. "
        "This indicates a backend problem, not a frontend invalidation bug."
    )

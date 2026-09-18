"""E2E — persistent jobs surface (jobs pill + AppShell docked Jobs panel).

Plan: docs/plans/2026-07-21-pgdp-alignment-remaining.md item 4.

Covers the plan's own acceptance criterion: a job started from a dialog
stays visible in the persistent jobs surface after the dialog that started
it is closed — the surface is rebuilt from ``GET /api/jobs`` (the source of
truth), not from the per-dialog SSE subscription that used to be the only
place a job's state was visible.

Prerequisite: ``make frontend-build`` (or ``make e2e``) must have run.

Run with:
    uv run --group e2e pytest tests/e2e/test_jobs_surface.py \
        --browser chromium -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import wait_for_app_ready
from tests.e2e.test_export_manifest_and_trainer import (
    _complete_typography_review,
    _load_tiny_fixture,
)

pytestmark = pytest.mark.e2e


def test_job_visible_in_jobs_pill_after_leaving_dialog(page: Page, live_server: LiveServer) -> None:
    """Start an export, close the dialog that started it, then find the job
    in the header jobs pill's docked panel.

    Mirrors ``test_export_manifest_and_trainer.test_export_dialog_opens_and_runs``'s
    setup and export-run steps, then goes one step further: closes the
    dialog (proving the job is not merely visible while the dialog that
    started it is still open) and opens the independent jobs pill surface to
    find the same job there.
    """
    wait_for_app_ready(live_server.base_url)

    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))
    _complete_typography_review(live_server.base_url, "tiny-fixture", page_index=0)

    page.goto(
        f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1",
        timeout=20_000,
    )
    page.locator("[data-testid='project-page']").wait_for(state="attached", timeout=20_000)

    # The jobs pill is chrome — present on every route once the app shell
    # mounts, independent of any dialog.
    page.locator("[data-testid='jobs-pill']").wait_for(state="visible", timeout=10_000)

    # Open the export dialog and start an export — same flow as
    # test_export_dialog_opens_and_runs. Wait on the POST response (no
    # sleep) to know the job was actually accepted before moving on.
    page.evaluate("() => { window.__DIALOG_STORE_OPEN?.('export'); }")
    page.locator("[data-testid='export-dialog']").wait_for(state="visible", timeout=10_000)

    with page.expect_response(
        lambda r: r.url.endswith("/export") and r.request.method == "POST"
    ) as export_resp_info:
        page.evaluate(
            """() => {
                const dialog = document.querySelector("[data-testid='export-dialog']");
                const btn = dialog?.querySelector("[data-testid='export-button']");
                if (btn) btn.click();
            }"""
        )
    assert export_resp_info.value.status == 202, (
        f"export POST failed: {export_resp_info.value.status} {export_resp_info.value.text()}"
    )

    # Wait for the run to finish inside the dialog (export-results appears
    # once the terminal event lands) — the same signal
    # test_export_dialog_opens_and_runs waits on. The dialog's Close button
    # stays disabled while the job is still running, so this is also the
    # earliest point closing the dialog is possible.
    page.locator("[data-testid='export-results']").wait_for(state="visible", timeout=30_000)

    # Leave the dialog that started the job — the whole point of the
    # persistent surface is that this must not lose the job's state.
    page.locator("[data-testid='export-close-button']").click()
    page.locator("[data-testid='export-dialog']").wait_for(state="hidden", timeout=10_000)

    # Open the jobs pill's docked panel and find the job there — rebuilt
    # from GET /api/jobs, not from the (now-unmounted) dialog's own SSE
    # subscription. The list was already refreshed the moment the job's
    # terminal SSE event landed (useJobProgress signals jobsBus on every
    # terminal transition — see hooks/useJobsList.ts), so this may render
    # from cache rather than firing a fresh request; wait on the row itself
    # rather than assuming a network round trip happens on click.
    page.locator("[data-testid='jobs-pill']").click()
    page.locator("[data-testid='jobs-panel-body']").wait_for(state="visible", timeout=10_000)
    page.locator("[data-testid='job-row']").first.wait_for(state="visible", timeout=10_000)

    assert page.locator("[data-testid='job-row']").count() >= 1, (
        "no job-row visible in the jobs panel after starting an export and leaving its dialog"
    )

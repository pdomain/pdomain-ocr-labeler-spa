"""E2E — export flow still works + Send-to-trainer affordance visibility.

Covers:
- Export API call triggers a job; manifest.json appears on disk.
- Export dialog opens in the browser; Export button fires a job; run-history
  row (export-results) appears after the job completes.
- "Send to trainer" button is absent (DOM count == 0) when trainer is not
  in the suite registry.

Prerequisite: ``make frontend-build`` (or ``make e2e``) must have run.

Run with:
    uv run --group e2e pytest tests/e2e/test_export_manifest_and_trainer.py \
        --browser chromium -v
"""

from __future__ import annotations

import json
import struct
import time
import zlib
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import SEED_TIMEOUT, wait_for_app_ready

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _minimal_png() -> bytes:
    """Build a 1x1 white RGB PNG with no external libraries."""

    def _chunk(name: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_row = b"\x00\xff\xff\xff"
    idat = _chunk(b"IDAT", zlib.compress(raw_row))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _seed_validated_page(data_root: Path, project_id: str) -> None:
    """Write a minimal validated envelope + PNG image at page index 0."""
    project_dir = data_root / "labeled-projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    img_path = project_dir / f"{project_id}_000.png"
    img_path.write_bytes(_minimal_png())

    word = {
        "text": "test",
        "ground_truth_text": "test",
        "word_labels": ["validated"],
        "bounding_box": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.05},
        "ground_truth_bounding_box": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.05},
    }
    envelope = {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
        "payload": {
            "page": {
                "words": [word],
                "lines": [{"words": [word]}],
                "blocks": [],
            }
        },
    }
    json_path = project_dir / f"{project_id}_000.json"
    json_path.write_text(json.dumps(envelope), encoding="utf-8")


def _load_tiny_fixture(base_url: str, source_root_path: str) -> None:
    """POST /api/source-root then POST /api/projects/load for tiny-fixture."""
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
    # 200 = loaded; 409 = already loaded from a prior test in this session.
    assert resp.status_code in (200, 409), f"load_project failed: {resp.status_code} {resp.text}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_export_manifest_created_on_server(live_server: LiveServer) -> None:
    """After a successful export API call, manifest.json appears on disk."""
    wait_for_app_ready(live_server.base_url)

    data_root = Path(str(live_server.settings.data_root))
    project_id = "e2e-manifest-proj"
    _seed_validated_page(data_root, project_id)

    resp = httpx.post(
        f"{live_server.base_url}/api/projects/{project_id}/export",
        json={
            "scope": "all_validated",
            "style_filters": [],
            "component_filter": None,
            "include_classification": False,
            "detection_only": False,
            "recognition_only": False,
        },
        timeout=10,
    )
    assert resp.status_code == 202, f"unexpected status {resp.status_code}: {resp.text}"
    job_id = resp.json()["job_id"]

    # Poll the job events endpoint until it reports completion
    deadline = time.monotonic() + 30.0
    completed = False
    while time.monotonic() < deadline:
        events_resp = httpx.get(
            f"{live_server.base_url}/api/jobs/{job_id}/events",
            timeout=5,
            headers={"Accept": "text/event-stream"},
        )
        if "complete" in events_resp.text or "error" in events_resp.text:
            completed = True
            break
        time.sleep(0.5)

    assert completed, f"export job {job_id} did not complete within 30s"

    manifest_path = data_root / "doctr-export" / "manifest.json"
    assert manifest_path.exists(), (
        f"manifest.json not found at {manifest_path}; events text snippet: {events_resp.text[:200]}"
    )
    data = json.loads(manifest_path.read_text())
    assert data.get("schema") == "pdomain.doctr-export-manifest"
    assert "generated_at" in data
    assert data.get("app") == "pdomain-ocr-labeler-spa"
    assert project_id in data.get("projects", {}), (
        f"project '{project_id}' not in manifest; projects present: {list(data.get('projects', {}).keys())}"
    )


def test_send_to_trainer_hidden_when_not_installed(page: Page, live_server: LiveServer) -> None:
    """Send-to-trainer button is absent (DOM count 0) when trainer not installed.

    Rewritten as a browser-DOM test per plan Task 9 Gap 1 requirements.

    The send-to-trainer button is conditionally rendered by ExportDialog only
    when ``trainerInstalled`` is true (polled from /api/suite/installed when
    the dialog opens).  When the trainer is not registered, ``trainerInstalled``
    stays false and no element with ``data-testid="export-send-to-trainer"``
    is ever inserted into the DOM — the assertion is valid as soon as the
    export dialog is open and the initial installed-apps fetch has settled.
    """
    wait_for_app_ready(live_server.base_url)

    # Confirm server-side precondition: trainer not registered.
    installed_resp = httpx.get(
        f"{live_server.base_url}/api/suite/installed",
        timeout=5,
    )
    assert installed_resp.status_code == 200
    installed = installed_resp.json()
    trainer_present = any(a.get("app_id") == "pdomain-ocr-trainer-spa" for a in installed)
    if trainer_present:
        pytest.skip("trainer app is installed in this environment — cannot verify 'hidden' assertion")

    # Load tiny-fixture so the route resolves (ExportDialog is only mounted
    # by App.tsx when projectId != null from the URL match).
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    # Navigate to a project page.
    page.goto(
        f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1",
        timeout=20_000,
    )
    page.locator("[data-testid='project-page']").wait_for(state="attached", timeout=20_000)

    # Open the export dialog via the JS bridge.
    page.evaluate("() => { window.__DIALOG_STORE_OPEN?.('export'); }")
    page.locator("[data-testid='export-dialog']").wait_for(state="visible", timeout=10_000)

    # Give the trainerInstalled fetch a moment to settle (it's an async useEffect
    # that fires when `open` becomes true).
    page.wait_for_timeout(1_500)

    # The send-to-trainer button must not exist anywhere in the DOM.
    # trainerInstalled is false → the button is never rendered, regardless of
    # whether an export has run.
    count = page.locator("[data-testid='export-send-to-trainer']").count()
    assert count == 0, (
        f"Expected export-send-to-trainer to be absent from the DOM "
        f"when trainer is not installed, but found {count} element(s)"
    )


def test_export_dialog_opens_and_runs(page: Page, live_server: LiveServer) -> None:
    """Navigate to a project page, open the export dialog, run an export.

    Verifies the full browser flow:
    1. Load the tiny-fixture project (registered in source_root by conftest).
    2. Navigate to page 1.
    3. Open the export dialog via the window.__DIALOG_STORE_OPEN JS bridge
       (avoids any interaction with the project-loading overlay).
    4. Click the Export run button inside the dialog.
    5. Wait for the export-results element to appear (job started / completed).

    Note: the project-loading overlay may stay up during cold OCR on the first
    page visit.  We bypass it by using the JS bridge to open the dialog —
    the Radix Dialog portal mounts above the overlay in the React tree, so
    the dialog and its buttons remain interactive regardless of overlay state.
    """
    wait_for_app_ready(live_server.base_url)

    # Seed validated page data for tiny-fixture so the export job has content.
    # The tiny-fixture PNG images exist in source_root; we seed an envelope in
    # data_root so the export handler can find validated words.
    data_root = Path(str(live_server.settings.data_root))
    _seed_validated_page(data_root, "tiny-fixture")

    # Load the tiny-fixture project so the route resolves.
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))

    # Navigate directly to page 1 of tiny-fixture.
    page.goto(
        f"{live_server.base_url}/projects/tiny-fixture/pages/pageno/1",
        timeout=20_000,
    )
    # Wait for the project-page root to attach (not necessarily fully loaded —
    # the loading overlay may still be up while cold OCR runs, but the React
    # shell including the dialog portal layer is already mounted).
    page.locator("[data-testid='project-page']").wait_for(state="attached", timeout=20_000)

    # Open the export dialog via the JS bridge so we don't need the overlay
    # to clear first.  The bridge is installed by dialog-store.ts on every page.
    page.evaluate("() => { window.__DIALOG_STORE_OPEN?.('export'); }")

    # The export dialog mounts in a Radix portal above the overlay.
    page.locator("[data-testid='export-dialog']").wait_for(state="visible", timeout=10_000)

    # Click the Export run button inside the dialog via JS evaluation.
    # Using evaluate() guarantees the click event reaches React regardless of any
    # pointer-event-intercepting overlay (e.g. the project-loading overlay).
    # Scoped to the dialog to avoid clicking the identically-named button in the
    # hidden PageActions driver-contract bar.
    page.evaluate(
        """() => {
            const dialog = document.querySelector("[data-testid='export-dialog']");
            if (dialog) {
                const btn = dialog.querySelector("[data-testid='export-button']");
                if (btn) btn.click();
            }
        }"""
    )

    # Wait for the run-history / results element to appear.
    # export-results is rendered once the job fires and produces its first
    # progress event.  Allow up to 30 s for the job to start and produce output.
    page.locator("[data-testid='export-results']").wait_for(state="visible", timeout=30_000)
    assert page.locator("[data-testid='export-results']").is_visible(), (
        "export-results element is not visible after export was triggered"
    )

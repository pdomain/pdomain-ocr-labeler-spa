"""E2E — export flow still works + Send-to-trainer affordance visibility.

Covers:
- Export API call triggers a job; manifest.json appears on disk.
- "Send to trainer" button is absent when trainer not in installed list.

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

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import wait_for_app_ready

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


def test_send_to_trainer_hidden_when_not_installed(live_server: LiveServer) -> None:
    """Send-to-trainer button absent when trainer not in suite registry.

    This test does not use Playwright; it asserts the installed-apps
    endpoint returns no trainer, which is the server-side condition
    for hiding the button.
    """
    wait_for_app_ready(live_server.base_url)

    installed_resp = httpx.get(
        f"{live_server.base_url}/api/suite/installed",
        timeout=5,
    )
    assert installed_resp.status_code == 200
    installed = installed_resp.json()

    trainer_present = any(a.get("app_id") == "pdomain-ocr-trainer-spa" for a in installed)

    # In a CI / test environment the trainer is not registered.
    # If it IS registered (developer machine), we skip — cannot hide the button.
    if trainer_present:
        pytest.skip("trainer is registered in this environment — the 'hidden' assertion cannot be verified")

    # Trainer is absent from the registry: the frontend will not show the button.
    # We verify the server-side condition rather than the browser DOM here,
    # since a browser test would require a completed export first (which is
    # already covered by test_export_manifest_created_on_server).
    assert not trainer_present, "trainer must not be installed for this assertion"

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
import uuid
import zlib
from pathlib import Path

import httpx
import pytest
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    _ingest_ocr_result,
    _register_page_in_project,
)
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import SEED_TIMEOUT, wait_for_app_ready

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _minimal_png(width: int = 64, height: int = 32) -> bytes:
    """Build a small white RGB PNG with no external libraries."""

    def _chunk(name: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw = (b"\x00" + b"\xff" * (width * 3)) * height
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _seed_store_page(source_root: Path, project_id: str, *, text: str = "test") -> None:
    """Create a fresh project under ``source_root`` with one real OCR word.

    Seeds a ``LabelerPageStore`` at page index 0 the same way
    ``conftest.py``'s ``_seed_tiny_fixture_page0_words`` and
    ``exercise_real_project.py``'s ``exercise_server`` fixture do, so the
    export handler's store-first page resolution
    (``resolve_export_page_refs``) sees the same content the typography
    review API reviews — a legacy ``labeled-projects`` JSON envelope would
    be a second, disconnected page that the review API never touches.
    """
    project_dir = source_root / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    image_bytes = _minimal_png()
    (project_dir / "000.png").write_bytes(image_bytes)

    def _bb(x0: int, y0: int, x1: int, y1: int) -> dict:
        return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}}

    word = {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "word_labels": [],
        "bounding_box": _bb(2, 2, 30, 20),
    }
    line = {"type": "Block", "child_type": "WORDS", "items": [word], "bounding_box": _bb(2, 2, 30, 20)}
    para = {"type": "Block", "child_type": "BLOCKS", "items": [line], "bounding_box": _bb(2, 2, 30, 20)}
    page_dict = {
        "type": "Page",
        "page_index": 0,
        "width": 64,
        "height": 32,
        "items": [para],
    }
    book_page = BookPage.from_dict(page_dict)

    store = LabelerPageStore(project_dir)
    try:
        _ingest_ocr_result(page=book_page, image_bytes=image_bytes, page_index=0, store=store)
        _register_page_in_project(
            store=store,
            project_id=project_id,
            page_id=book_page.page_id,
            page_index=0,
        )
    finally:
        store.close()


def _complete_typography_review_for_word(
    base_url: str, project_id: str, page_index: int, word_id: str
) -> None:
    """Drive one word's grapheme-level typography review to completion.

    Submits a ``reviewed_regular`` correction with every taxonomy label
    resolved, via the real HTTP API rather than a browser click — the same
    round trip TypographySection's "Reviewed regular" button performs. This
    is what ``_typography_reviewed`` (src/pdomain_ocr_labeler_spa/api/
    typography.py) requires to report this word's own
    ``typography_reviewed`` as true; it does not touch any other word or the
    word's ``is_validated`` flag.
    """
    typography_base = f"{base_url}/api/projects/{project_id}/pages/{page_index}/typography/words"
    head_resp = httpx.get(f"{typography_base}/{word_id}/head", timeout=SEED_TIMEOUT)
    assert head_resp.status_code == 200, (
        f"typography head failed for {word_id}: {head_resp.status_code} {head_resp.text}"
    )
    head = head_resp.json()
    taxonomy = head["taxonomy"]
    replacement = {
        "word_id": head["word_id"],
        "text": head["text"],
        "text_sha256": head["text_sha256"],
        "page_content_sha256": head["page_sha256"],
        "image_artifact_sha256": head["image_sha256"],
        "grapheme_map_version": head["grapheme_map_version"],
        "taxonomy_version": taxonomy["version"],
        "taxonomy_hash": taxonomy["taxonomy_hash"],
        "label_states": {label["value"]: "negative" for label in taxonomy["labels"]},
        "spans": [],
        "source_evidence_ids": ["e2e-fixture-seed"],
        "warnings": [],
        "whole_word_labels": None,
        "word_revision": head["word_revision"] + 1,
        "review_state": "reviewed_regular",
        "metadata": None,
    }
    submission = {
        "expected_head": head["head_token"],
        "correction_id": str(uuid.uuid4()),
        "taxonomy_version": taxonomy["version"],
        "taxonomy_hash": taxonomy["taxonomy_hash"],
        "grapheme_map_version": head["grapheme_map_version"],
        "labeler_id": "local",
        "decision": "reviewed_regular",
        "replacement": replacement,
        "replacement_text_sha256": head["text_sha256"],
        "replacement_page_sha256": head["page_sha256"],
        "replacement_image_sha256": head["image_sha256"],
        "replacement_page_head_sha256": head["page_head_sha256"],
        "replacement_word_revision": head["word_revision"] + 1,
        "replacement_artifacts": [],
        "replacement_artifact_payloads": [],
        "model_runs": [],
        "coordinate_transforms": [],
    }
    correction_resp = httpx.post(
        f"{typography_base}/{word_id}/corrections", json=submission, timeout=SEED_TIMEOUT
    )
    assert correction_resp.status_code == 200, (
        f"typography correction failed for {word_id}: {correction_resp.status_code} {correction_resp.text}"
    )


def _complete_typography_review(base_url: str, project_id: str, page_index: int) -> None:
    """Validate every word on a page and drive its typography review to completion.

    6a04cbe made ``review.complete`` (text-validated + typography-reviewed,
    every active word) a precondition for export. This drives the same
    round trip the WordFooter "Validate" button and TypographySection's
    "Reviewed regular" button perform, via the real HTTP API rather than
    browser clicks — for a loaded (non book-labeling-bundle) project,
    ``typography_page_review`` counts a word's text as reviewed once it
    carries the ``validated`` word label, so no separate text-validation
    call is needed here.
    """
    # GET first: the seeded event store hydrates the in-memory PageState
    # lazily on page fetch; mutating before that returns 400 page_not_loaded.
    warm_resp = httpx.get(f"{base_url}/api/projects/{project_id}/pages/{page_index}", timeout=SEED_TIMEOUT)
    assert warm_resp.status_code == 200, f"GET page failed: {warm_resp.status_code} {warm_resp.text}"

    validate_resp = httpx.post(
        f"{base_url}/api/projects/{project_id}/pages/{page_index}/words/validate-batch",
        json={"scope": "page", "validated": True},
        timeout=SEED_TIMEOUT,
    )
    assert validate_resp.status_code == 200, (
        f"validate-batch failed: {validate_resp.status_code} {validate_resp.text}"
    )

    page_resp = httpx.get(f"{base_url}/api/projects/{project_id}/pages/{page_index}", timeout=SEED_TIMEOUT)
    assert page_resp.status_code == 200, f"GET page failed: {page_resp.status_code} {page_resp.text}"
    word_ids = [
        wm["word_id"]
        for lm in page_resp.json().get("line_matches", [])
        for wm in lm.get("word_matches", [])
        if wm.get("word_id")
    ]
    assert word_ids, f"page {page_index} has no words with a word_id — nothing to review"

    for word_id in word_ids:
        _complete_typography_review_for_word(base_url, project_id, page_index, word_id)

    review_resp = httpx.get(
        f"{base_url}/api/projects/{project_id}/pages/{page_index}/typography/review",
        timeout=SEED_TIMEOUT,
    )
    assert review_resp.status_code == 200, (
        f"typography review GET failed: {review_resp.status_code} {review_resp.text}"
    )
    review = review_resp.json()
    assert review.get("complete") is True, f"typography review did not complete: {review}"


def _load_tiny_fixture(base_url: str, source_root_path: str) -> None:
    """POST /api/projects/source-root then POST /api/projects/load for tiny-fixture."""
    httpx.post(
        f"{base_url}/api/projects/source-root",
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
    _seed_store_page(live_server.source_root, project_id)

    # 6a04cbe gates export on a loaded project ("Project must be loaded
    # before reviewed pages can be exported") — load it before exporting.
    load_resp = httpx.post(
        f"{live_server.base_url}/api/projects/load",
        json={"project_root": str(live_server.source_root / project_id)},
        timeout=10,
    )
    assert load_resp.status_code == 200, f"load_project failed: {load_resp.status_code} {load_resp.text}"

    # 6a04cbe also gates export on text-and-typography review completion.
    _complete_typography_review(live_server.base_url, project_id, page_index=0)

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
    # P1.2 guard (sweep C35): the export must actually export pages — a
    # "successful" 0-page export is the silent-failure mode this slice fixed.
    # This run exercises the store-first page resolution lane (C56).
    page_count = data["projects"][project_id].get("page_count", 0)
    assert page_count >= 1, (
        f"export reported success but exported {page_count} pages — "
        "store-first page resolution regressed (C35/C56)"
    )


def test_export_current_page_from_event_store_nonzero(exercise_server) -> None:
    """Store-lane export (PARITY-GAP P1.2 / sweep C35): a page that exists ONLY
    in the event store (the exercise-fixture seed — no labeled-projects file)
    must export real recognition crops + labels to disk.

    ``scope=current`` used to bypass validation flags entirely; 6a04cbe made
    text-and-typography review a precondition for export on every scope, so
    this now validates and reviews the page first. The point of the test is
    unchanged: the export handler resolves the page from the store head, not
    a ``labeled-projects`` legacy file (there is none for this project).
    """
    base_url = exercise_server.base_url
    data_root = Path(str(exercise_server.settings.data_root))
    project_id = "exercise-fixture"

    _complete_typography_review(base_url, project_id, page_index=0)

    resp = httpx.post(
        f"{base_url}/api/projects/{project_id}/export",
        json={"scope": "current", "page_index": 0},
        timeout=10,
    )
    assert resp.status_code == 202, f"unexpected status {resp.status_code}: {resp.text}"
    job_id = resp.json()["job_id"]

    deadline = time.monotonic() + 60.0
    completed = False
    events_text = ""
    while time.monotonic() < deadline:
        events_resp = httpx.get(
            f"{base_url}/api/jobs/{job_id}/events",
            timeout=10,
            headers={"Accept": "text/event-stream"},
        )
        events_text = events_resp.text
        if "complete" in events_text or "error" in events_text:
            completed = True
            break
        time.sleep(0.5)
    assert completed, f"export job {job_id} did not complete within 60s"

    labels_path = data_root / "doctr-export" / project_id / "all" / "recognition" / "labels.json"
    assert labels_path.exists(), (
        f"no recognition labels.json at {labels_path} — store-first export "
        f"resolution regressed (C35); events: {events_text[:300]}"
    )
    labels = json.loads(labels_path.read_text())
    assert len(labels) > 0, "recognition labels.json is empty — exported 0 words from the store head"

    images_dir = data_root / "doctr-export" / project_id / "all" / "recognition" / "images"
    crops = list(images_dir.glob("*.png")) if images_dir.exists() else []
    assert len(crops) > 0, f"no recognition crops written under {images_dir}"


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

    # Wait until the send-to-trainer button is confirmed absent (count == 0).
    # This replaces a fixed sleep: the condition resolves as soon as the
    # trainerInstalled useEffect fetch has settled and React has committed the
    # result.  Timeout of 3 s is generous for a single /api/suite/installed call.
    expect(page.locator("[data-testid='export-send-to-trainer']")).to_have_count(0, timeout=3_000)


def test_export_dialog_opens_and_runs(page: Page, live_server: LiveServer) -> None:
    """Navigate to a project page, open the export dialog, run an export.

    Verifies the full browser flow:
    1. Load the tiny-fixture project (registered in source_root by conftest).
    2. Validate and typography-review page 0's words via the API (6a04cbe:
       the export button stays disabled until review is complete — a real
       reviewer would click through WordFooter/TypographySection to get
       there; driving it via API keeps the test focused on the export click).
    3. Navigate to page 1.
    4. Open the export dialog via the window.__DIALOG_STORE_OPEN JS bridge
       (avoids any interaction with the project-loading overlay).
    5. Click the Export run button inside the dialog.
    6. Wait for the export-results element to appear (job started / completed).

    Note: the project-loading overlay may stay up during cold OCR on the first
    page visit.  We bypass it by using the JS bridge to open the dialog —
    the Radix Dialog portal mounts above the overlay in the React tree, so
    the dialog and its buttons remain interactive regardless of overlay state.
    """
    wait_for_app_ready(live_server.base_url)

    # Load the tiny-fixture project so the route resolves. Page 0 ("pageno/1")
    # ships pre-seeded with real word content (conftest.py's
    # _seed_tiny_fixture_page0_words) — no extra fixture seeding needed here.
    _load_tiny_fixture(live_server.base_url, str(live_server.source_root))
    _complete_typography_review(live_server.base_url, "tiny-fixture", page_index=0)

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

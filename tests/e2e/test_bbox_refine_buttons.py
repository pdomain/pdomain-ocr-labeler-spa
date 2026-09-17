"""E2E: the BBoxSection "Expand" button queues a real `refine_bboxes` job.

P1-BBOX-UI (docs/issues/2026-07-21-bbox-refine-crop-misleading.md): Refine,
Expand+Refine and Crop used to all call the plain rebox mutation — no refine
or crop ever ran. They now queue the real `refine_bboxes` job
(`POST .../refine`), and "Crop" was renamed "Expand" (`mode: "expand_only"`).

Self-contained fixture-server pattern, following
`test_review_queue_panel.py` / `test_image_click_selection.py` (read first):
a synthetic one-word project seeded via `_ingest_ocr_result`, no OCR model
involved.

Why "Expand" (`mode: "expand_only"`) is the one button this test can drive
honestly without GPU OCR: `core/jobs/handlers/refine.py`'s `"refine"` and
`"expand_then_refine"` modes call `Word.refine_bbox` /
`Word.expand_then_refine_bbox`, which need the page's `cv2_numpy_page_image`
attached to do anything — that attachment only happens in
`LocalDoctrPageLoader._run_ocr_on_path` (the real DocTR OCR path;
`local_doctr.py:507-517`). A page seeded via `_ingest_ocr_result` (this
fixture's seeding path, shared with `test_undo_redo.py` /
`test_review_queue_panel.py` / `test_image_click_selection.py`) never runs
that path, so `cv2_numpy_page_image` is absent; `Word.refine_bbox(None, ...)`
and `Word.expand_then_refine_bbox(None)` both no-op (return `False` without
raising — `pdomain_book_tools.ocr.image_utilities.refine_word_bbox` returns
`False` on `image is None`) — the job would still complete, but the bbox
would never change, so an E2E asserting on Refine / Expand+Refine here would
only prove the job pipeline runs, not that either button does what its name
says. `Word.expand_bbox` (the `expand_only` handler branch) takes no image
argument at all — it only needs `page_width` / `page_height`, which the
handler falls back to `page.width` / `page.height` (`_page_dimensions`) when
no image is attached — so "Expand" is the one button whose real effect (the
bbox growing by the padding on every side, clamped to page bounds) this
fixture can drive and verify end to end: button click → POST /refine →
202 job id → SSE → `handle_refine_bboxes` actually mutates the word →
`useJobCompletionInvalidation` invalidates the page query → the bbox inputs
show the new, larger box.

Spec authority:
- docs/architecture/02-backend.md §5.6 (refine endpoint contract).
- docs/architecture/27-right-panel-sections.md §5/§6 (BBoxSection actions,
  testid table).
"""

from __future__ import annotations

import json
import socket
import struct
import threading
import time
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import uvicorn
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "bbox-refine-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# Comfortably inside the page on every side, so the +4px expand (the
# handler's `expand_only` padding — matches BBoxSection's
# `EXPAND_ONLY_PADDING_PX`) never clamps to a page edge.
_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2 = 300, 400, 500, 440
_EXPAND_PADDING_PX = 4


def _spa_built() -> bool:
    static = Path(__file__).resolve().parents[2] / "src" / "pdomain_ocr_labeler_spa" / "static"
    return (static / "index.html").is_file()


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready at {url!r} within {timeout}s")


def _make_png(width: int, height: int) -> bytes:
    """Minimal grayscale PNG (solid white) — content is irrelevant to the test."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(bytes([0]) + bytes([255] * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _make_page(page_index: int) -> BookPage:
    """One Block(WORDS) → Block(BLOCKS) → single Word, pixel (non-normalized) boxes.

    Mirrors `test_undo_redo.py`'s `_make_page` — the proven no-OCR seeding
    shape for `_ingest_ocr_result`.
    """
    word = {
        "type": "Word",
        "text": "Gutenberg",
        "ground_truth_text": "Gutenberg",
        "bounding_box": _bbox(_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2),
    }
    line = {
        "type": "Block",
        "child_type": "WORDS",
        "items": [word],
        "bounding_box": _bbox(_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2),
    }
    para = {
        "type": "Block",
        "child_type": "BLOCKS",
        "items": [line],
        "bounding_box": _bbox(_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2),
    }
    return BookPage.from_dict(
        {
            "width": _IMAGE_W,
            "height": _IMAGE_H,
            "page_index": page_index,
            "bounding_box": _bbox(0, 0, _IMAGE_W, _IMAGE_H),
            "items": [para],
        }
    )


@dataclass
class BBoxRefineServer:
    base_url: str


@pytest.fixture(scope="module")
def bbox_refine_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[BBoxRefineServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("bbox-refine-data")
    cache_root = tmp_path_factory.mktemp("bbox-refine-cache")
    config_root = tmp_path_factory.mktemp("bbox-refine-config")
    source_root = tmp_path_factory.mktemp("bbox-refine-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": "Gutenberg"}))

    # Seed the event store directly — no OCR model, no cv2 image attached
    # (see the module docstring for why that matters to this test's choice
    # of button).
    book_page = _make_page(page_index=0)
    store = LabelerPageStore(dest)
    try:
        _ingest_ocr_result(page=book_page, image_bytes=image_bytes, page_index=0, store=store)
        _register_page_in_project(
            store=store, project_id=_PROJECT_ID, page_id=book_page.page_id, page_index=0
        )
    finally:
        store.close()

    port = _pick_free_port()
    settings = Settings(
        host="127.0.0.1",
        port=port,
        data_root=data_root,
        cache_root=cache_root,
        config_root=config_root,
        source_projects_root=source_root,
        mode="normal",
    )
    app = build_app(settings)
    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{settings.host}:{settings.port}"
    try:
        _wait_until(f"{base_url}/healthz")
    except RuntimeError:
        server.should_exit = True
        thread.join(timeout=2)
        raise

    r = httpx.post(f"{base_url}/api/projects/source-root", json={"path": str(source_root)}, timeout=10)
    assert r.status_code in (200, 204), f"source-root POST failed: {r.status_code} {r.text}"
    r = httpx.post(f"{base_url}/api/projects/load", json={"project_root": str(dest)}, timeout=30)
    assert r.status_code == 200, f"load project failed: {r.status_code} {r.text}"

    yield BBoxRefineServer(base_url=base_url)

    server.should_exit = True
    thread.join(timeout=5)


def _click_word_on_canvas(page: Page, base_url: str) -> dict[str, float]:
    """Click the seeded word's bbox on the Konva canvas; return its API bbox.

    Reuses the click-math from `test_image_click_selection.py`: the page
    payload's bbox is in encoded (possibly downscaled) pixel space, so the
    on-screen click point is computed via `encoded_dims.scale` and the
    rendered canvas's fit scale, not the raw fixture coordinates.
    """
    resp = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10.0)
    assert resp.status_code == 200, f"page payload GET failed: {resp.status_code}"
    payload = resp.json()
    encoded = payload["encoded_dims"]
    assert encoded is not None, "page payload must carry encoded_dims"
    display_width = encoded["display_width"]
    scale = encoded["scale"]

    word = payload["line_matches"][0]["word_matches"][0]
    bbox = word["bbox"]
    assert bbox["width"] > 4 and bbox["height"] > 4, f"planted bbox went degenerate: {bbox}"

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    viewport = page.locator('[data-testid="image-viewport"]').first
    viewport.wait_for(state="visible", timeout=10_000)
    stage_canvas = viewport.locator("canvas").first
    stage_canvas.wait_for(state="visible", timeout=10_000)
    box = stage_canvas.bounding_box()
    assert box is not None, "rendered canvas must have an on-screen bounding box"

    fit_scale = box["width"] / display_width
    display_bbox = {
        "x": bbox["x"] * scale,
        "y": bbox["y"] * scale,
        "width": bbox["width"] * scale,
        "height": bbox["height"] * scale,
    }
    cx = box["x"] + (display_bbox["x"] + display_bbox["width"] / 2) * fit_scale
    cy = box["y"] + (display_bbox["y"] + display_bbox["height"] / 2) * fit_scale

    page.mouse.click(cx, cy)
    page.wait_for_selector('[data-testid="word-header-id"]', timeout=10_000)

    return bbox


def _open_bbox_accordion(page: Page) -> None:
    """Open the WordDetail "Bounding Box" accordion item.

    Radix removes closed accordion content from the DOM (§5 of
    docs/architecture/27-right-panel-sections.md), so `bbox-input-x` and the
    Refine/Expand+Refine/Expand buttons only attach once this trigger is
    clicked — same pattern as `test_ui_coverage.py`'s `_open_accordion_item`.
    """
    accordion = page.locator('[data-testid="word-detail-accordion"]')
    accordion.wait_for(state="attached", timeout=10_000)
    trigger = accordion.locator('button:has-text("Bounding Box")').first
    trigger.wait_for(state="visible", timeout=5_000)
    trigger.click()
    page.wait_for_selector('[data-testid="bbox-input-x"]', state="visible", timeout=5_000)


@pytest.mark.e2e
def test_expand_button_queues_real_refine_job_and_grows_bbox(
    bbox_refine_server: BBoxRefineServer,
    page: Page,
) -> None:
    """Clicking Expand posts scope=word/mode=expand_only and the bbox actually grows.

    Covers P1-BBOX-UI end to end: the button queues `POST .../refine`, the
    `refine_bboxes` job runs `Word.expand_bbox` for real (no OCR image
    needed for this mode), completion invalidates the page query, and the
    coordinate inputs show the new, larger box — not the unchanged one a
    plain rebox would have produced.
    """
    base_url = bbox_refine_server.base_url
    bbox = _click_word_on_canvas(page, base_url)
    _open_bbox_accordion(page)

    x_input = page.locator('[data-testid="bbox-input-x"]')
    y_input = page.locator('[data-testid="bbox-input-y"]')
    w_input = page.locator('[data-testid="bbox-input-w"]')
    h_input = page.locator('[data-testid="bbox-input-h"]')

    original_x = float(x_input.input_value())
    original_y = float(y_input.input_value())
    original_w = float(w_input.input_value())
    original_h = float(h_input.input_value())
    assert original_x == pytest.approx(bbox["x"], abs=1.0)
    assert original_y == pytest.approx(bbox["y"], abs=1.0)

    expand_button = page.locator('[data-testid="bbox-expand-button"]')
    expand_button.wait_for(state="visible", timeout=5_000)
    expect(expand_button).to_be_enabled(timeout=5_000)
    expand_button.click()

    # A loading toast should appear immediately (job pattern — see
    # docs/architecture/27-right-panel-sections.md §5 BBoxSection).
    page.wait_for_selector("[data-sonner-toast]", timeout=5_000)

    # Job runs synchronously in-process; wait for the terminal toast and the
    # invalidated page query to land in the coordinate inputs.
    completion_toast = page.locator("[data-sonner-toast]", has_text="Bbox refine complete")
    expect(completion_toast).to_be_visible(timeout=10_000)

    expected_x = original_x - _EXPAND_PADDING_PX
    expected_y = original_y - _EXPAND_PADDING_PX
    expected_w = original_w + 2 * _EXPAND_PADDING_PX
    expected_h = original_h + 2 * _EXPAND_PADDING_PX

    expect(x_input).to_have_value(str(int(expected_x)), timeout=10_000)
    expect(y_input).to_have_value(str(int(expected_y)), timeout=10_000)
    expect(w_input).to_have_value(str(int(expected_w)), timeout=10_000)
    expect(h_input).to_have_value(str(int(expected_h)), timeout=10_000)

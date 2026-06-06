"""E2E: clicking a word's bbox ON THE IMAGE opens WordDetail for that word.

This is the real-browser coverage for the bbox-click selection path
(#bbox-click-selection). The other word-detail E2E tests reach WordDetail via
the Hierarchy/worklist tree; this one exercises a click that lands inside a word
bounding box drawn on the Konva image canvas. The click flows through
pdomain-ui's ``onStagePointer*`` slot callbacks and the scroll- + scale-aware
Konva pointer position — the path that replaced the old hand-rolled DOM
event-capture overlay whose coordinate math ignored scroll and recomputed its
own scale, causing clicks to miss the bboxes.

The shared exercise-/tiny-fixture projects store word bounding boxes in
normalized 0..1 coordinates. This module builds a self-contained one-page
project with normalized OCR boxes so the E2E covers the lift path that must
scale normalized coordinates into real image/display boxes before painting.

Spec ref: ``docs/architecture/21-konva-renderer.md`` (Konva renderer),
``docs/architecture/13-driver-contract.md`` §2 (``image-viewport``).
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
from io import BytesIO
from pathlib import Path

import httpx
import pytest
import uvicorn
from pdomain_book_tools.ocr.page import Page as BookPage
from PIL import Image
from playwright.sync_api import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    _ingest_ocr_result,
    _register_page_in_project,
)
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "click-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# A single word placed at a comfortable pixel rectangle, well clear of the page
# edges so the click lands squarely inside it after fit-scaling.
_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2 = 300, 400, 700, 470


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


def _normalized_bbox(x1: int, y1: int, x2: int, y2: int) -> dict:
    return {
        "top_left": {"x": x1 / _IMAGE_W, "y": y1 / _IMAGE_H, "is_normalized": True},
        "bottom_right": {"x": x2 / _IMAGE_W, "y": y2 / _IMAGE_H, "is_normalized": True},
        "is_normalized": True,
    }


def _build_envelope() -> dict:
    """One Block → Paragraph → Line → single Word with normalized boxes."""
    word = {
        "type": "Word",
        "text": "Gutenberg",
        "bounding_box": _normalized_bbox(_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2),
        "ocr_confidence": 0.95,
        "word_labels": [],
        "ground_truth_text": "Gutenberg",
        "ground_truth_bounding_box": None,
        "ground_truth_match_keys": {"match_score": 100},
    }
    line = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _normalized_bbox(_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2),
        "items": [word],
    }
    para = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _normalized_bbox(_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2),
        "items": [line],
    }
    block = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _normalized_bbox(_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2),
        "items": [para],
    }
    page = {
        "type": "Page",
        "page_index": 0,
        "width": _IMAGE_W,
        "height": _IMAGE_H,
        "items": [block],
    }
    return {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
        "provenance": {
            "saved_at": "2026-05-28T00:00:00.000Z",
            "saved_by": "Save Page",
            "source_lane": "labeled",
            "app": {
                "name": "pdomain_ocr_labeler_spa",
                "version": "0.1.0",
                "git_commit": "click-fixture",
            },
            "toolchain": {
                "python": "3.13.0",
                "pdomain_book_tools": "0.9.0",
                "opencv_python": "4.10.0.84",
            },
            "ocr": {
                "engine": "doctr",
                "engine_version": "0.10.0",
                "models": [
                    {"name": "detection", "version": "stock", "weights_id": "db_resnet50"},
                    {"name": "recognition", "version": "stock", "weights_id": "crnn_vgg16_bn"},
                ],
                "config_fingerprint": "a" * 64,
            },
        },
        "source": {
            "project_id": _PROJECT_ID,
            "page_index": 0,
            "page_number": 1,
            "image_path": "001.png",
            "project_root": f"/test/{_PROJECT_ID}",
            "image_fingerprint": {
                "size": _IMAGE_W * _IMAGE_H,
                "mtime_ns": 1715000000000000000,
                "sha256": "cc" * 32,
            },
        },
        "payload": {"page": page, "word_attributes": {}},
        "cached_images": {},
    }


def _assert_word_overlay_paints(page: Page, bbox: dict, canvas_box: dict, fit_scale: float) -> None:
    """The fixture image is white; a painted word overlay tints the bbox interior."""
    sx = int(canvas_box["x"] + (bbox["x"] + bbox["width"] / 2) * fit_scale)
    sy = int(canvas_box["y"] + (bbox["y"] + bbox["height"] / 2) * fit_scale)

    image = Image.open(BytesIO(page.screenshot(full_page=True))).convert("RGB")
    left = max(0, sx - 4)
    top = max(0, sy - 4)
    right = min(image.width, sx + 5)
    bottom = min(image.height, sy + 5)

    pixels = [image.getpixel((x, y)) for y in range(top, bottom) for x in range(left, right)]
    assert pixels, f"sample point ({sx}, {sy}) fell outside screenshot {image.size}"

    # The source PNG is pure white. The word overlay fill should make at least
    # part of this sample visibly non-white.
    assert any(pixel != (255, 255, 255) for pixel in pixels), (
        f"word bbox overlay did not paint near screen point ({sx}, {sy}); "
        f"sample={pixels[:5]}, bbox={bbox}, canvas_box={canvas_box}, fit_scale={fit_scale}"
    )


@dataclass
class ClickServer:
    base_url: str


@pytest.fixture(scope="module")
def click_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ClickServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("click-data")
    cache_root = tmp_path_factory.mktemp("click-cache")
    config_root = tmp_path_factory.mktemp("click-config")
    source_root = tmp_path_factory.mktemp("click-source")

    # Source project: image + pages.json.
    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": "Gutenberg"}))

    # Seed the event store so load_labeled reconstructs the page without OCR.
    # (Writing the envelope into data_root/labeled-projects/ predates the
    # event-store load_labeled lane (M5b) and silently no-ops — load_labeled
    # resolves the project aggregate from the store, not flat JSON files.)
    book_page = BookPage.from_dict(_build_envelope()["payload"]["page"])
    store = LabelerPageStore(dest)
    try:
        _ingest_ocr_result(
            page=book_page,
            image_bytes=image_bytes,
            page_index=0,
            store=store,
        )
        _register_page_in_project(
            store=store,
            project_id=_PROJECT_ID,
            page_id=book_page.page_id,
            page_index=0,
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

    yield ClickServer(base_url=base_url)

    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.e2e
def test_click_word_bbox_on_image_opens_word_detail(
    click_server: ClickServer,
    page: Page,
) -> None:
    """Click the word's bbox on the canvas image; WordDetail opens for that word.

    Covers: B-CANVAS-002, B-RIGHT-001
    """
    # Confirm the payload carries the pixel bbox we planted (guards against a
    # future page_to_line_matches change that would zero it out again).
    resp = httpx.get(
        f"{click_server.base_url}/api/projects/{_PROJECT_ID}/pages/0",
        timeout=10.0,
    )
    assert resp.status_code == 200, f"page payload GET failed: {resp.status_code}"
    payload = resp.json()
    encoded = payload["encoded_dims"]
    assert encoded is not None, "page payload must carry encoded_dims"
    display_width = encoded["display_width"]
    scale = encoded["scale"]

    word = payload["line_matches"][0]["word_matches"][0]
    bbox = word["bbox"]
    assert bbox["width"] > 4 and bbox["height"] > 4, f"planted bbox went degenerate: {bbox}"

    page.goto(
        f"{click_server.base_url}/projects/{_PROJECT_ID}/pages/pageno/1",
        timeout=20_000,
    )
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    # Wait for the loading overlay to clear before clicking the canvas, or the
    # fixed inset-0 overlay intercepts the mouse click under load.
    wait_for_project_ready(page)

    viewport = page.locator('[data-testid="image-viewport"]').first
    viewport.wait_for(state="visible", timeout=10_000)
    stage_canvas = viewport.locator("canvas").first
    stage_canvas.wait_for(state="visible", timeout=10_000)
    box = stage_canvas.bounding_box()
    assert box is not None, "rendered canvas must have an on-screen bounding box"

    # The outer image-viewport may be wider or taller than the fitted Konva
    # stage. Project through the rendered canvas box so tall-page fit scaling
    # lands on the actual word pixels, not unused viewport space.
    fit_scale = box["width"] / display_width
    display_bbox = {
        "x": bbox["x"] * scale,
        "y": bbox["y"] * scale,
        "width": bbox["width"] * scale,
        "height": bbox["height"] * scale,
    }
    cx = box["x"] + (display_bbox["x"] + display_bbox["width"] / 2) * fit_scale
    cy = box["y"] + (display_bbox["y"] + display_bbox["height"] / 2) * fit_scale
    _assert_word_overlay_paints(page, display_bbox, box, fit_scale)

    page.mouse.click(cx, cy)

    # WordDetail opens bound to the clicked word — identity header is 1-based.
    header = page.locator('[data-testid="word-header-id"]').first
    header.wait_for(state="visible", timeout=10_000)
    line_index = word["line_index"]
    word_index = word["word_index"]
    header_text = header.inner_text()
    assert f"Line {line_index + 1}" in header_text and f"Word {word_index + 1}" in header_text, (
        f"WordDetail header {header_text!r} should reference the clicked word "
        f"(line {line_index + 1}, word {word_index + 1}); scale={scale}, fit={fit_scale}"
    )


@pytest.mark.e2e
def test_click_word_in_hierarchy_opens_word_detail_without_blank_page(
    click_server: ClickServer,
    page: Page,
) -> None:
    """Click the hierarchy word picker; the page must not crash or go blank.

    Covers: B-DRAWER-002
    """
    page_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    page.goto(
        f"{click_server.base_url}/projects/{_PROJECT_ID}/pages/pageno/1",
        timeout=20_000,
    )
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    # Wait for the loading overlay to clear before clicking, or the fixed
    # inset-0 overlay intercepts the drawer-tab click under load.
    wait_for_project_ready(page)

    page.locator('[data-testid="drawer-tab-hierarchy"]').first.click()
    page.wait_for_selector('[data-testid="hierarchy"]', state="visible", timeout=10_000)

    block_nodes = page.locator('[data-testid^="hierarchy-node-block-"]')
    if block_nodes.count() > 0:
        first_block = block_nodes.first
        first_block.click()
        assert page.locator('[data-testid="project-page"]').count() == 1, page_errors
        page.keyboard.press("ArrowRight")

    first_para = page.locator('[data-testid^="hierarchy-node-para-"]').first
    first_para.wait_for(state="visible", timeout=10_000)
    first_para.click()
    assert page.locator('[data-testid="project-page"]').count() == 1, page_errors
    page.keyboard.press("ArrowRight")

    first_line = page.locator('[data-testid^="hierarchy-node-line-"]').first
    first_line.wait_for(state="visible", timeout=10_000)
    first_line.click()
    assert page.locator('[data-testid="project-page"]').count() == 1, page_errors
    page.keyboard.press("ArrowRight")

    first_word = page.locator('[data-testid^="hierarchy-node-word-"]').first
    first_word.wait_for(state="visible", timeout=10_000)
    first_word.click()

    header = page.locator('[data-testid="word-header-id"]').first
    header.wait_for(state="visible", timeout=10_000)
    assert page_errors == []
    assert page.locator('[data-testid="project-page"]').count() == 1

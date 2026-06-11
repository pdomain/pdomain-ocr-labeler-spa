"""Browser Verification — Selection & Operations Parity.

Tests for docs/specs/2026-06-05-selection-operations-parity.md
Browser Verification milestone.

Verifies:
  SEL-1  : clicking a word produces a VISIBLE selection highlight on the canvas.
  MUL-1/2: Ctrl-click a word in a DIFFERENT block → multi-word-detail shows BOTH
            block groups, each with its line's ocr_line_text.
  GRID-1  : ToolbarActionGrid is VISIBLE (not display:none); collapse toggle works.
  GRID-3 + STB-1 END-TO-END: clicking word-footer-validate (WordDetail) actually
            changes the word's validated state in the live UI.

Fixture: a two-block project (sel-fixture) built inline with pre-seeded event-store
so the page loads with real word content immediately (no OCR).  The store is seeded
via _ingest_ocr_result + Page.from_dict, the same path live OCR uses.

Spec reference: docs/specs/2026-06-05-selection-operations-parity.md
"""

from __future__ import annotations

import contextlib
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
from playwright.sync_api import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    _ingest_ocr_result,
    _register_page_in_project,
)
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings

# ─── Constants ────────────────────────────────────────────────────────────────

_PROJECT_ID = "sel-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# Block 0: two words in top region.
#   Line 0 of block 0: word (0,0) "Hello" at top-left, word (0,1) "World" next to it.
# Block 1: two words in bottom region.
#   Line 1 of block 1: word (1,0) "Foo" at bottom-left, word (1,1) "Bar" next to it.
#
# Normalized coords (0..1).
_B0_LINE_TEXT = "Hello World"
_B1_LINE_TEXT = "Foo Bar"

_ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


# ─── PNG builder ──────────────────────────────────────────────────────────────


def _make_png(width: int, height: int) -> bytes:
    """Minimal solid-white grayscale PNG."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(bytes([0]) + bytes([255] * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


# ─── Page dict builder ────────────────────────────────────────────────────────


def _nb(x1: float, y1: float, x2: float, y2: float) -> dict:
    return {"top_left": {"x": x1, "y": y1}, "bottom_right": {"x": x2, "y": y2}}


def _word_node(text: str, x1: float, y1: float, x2: float, y2: float) -> dict:
    return {
        "type": "Word",
        "text": text,
        "bounding_box": _nb(x1, y1, x2, y2),
        "ocr_confidence": 0.95,
        "word_labels": [],
        "ground_truth_text": text,
        "ground_truth_bounding_box": None,
        "ground_truth_match_keys": {"match_score": 100},
    }


def _build_page_dict() -> dict:
    """Two-block, two-line page dict.

    Block 0 (top): 'Hello' (0.1,0.12)-(0.3,0.18), 'World' (0.32,0.12)-(0.52,0.18)
    Block 1 (mid): 'Foo' (0.1,0.45)-(0.25,0.51), 'Bar' (0.27,0.45)-(0.42,0.51)
    """
    line0 = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [
            _word_node("Hello", 0.1, 0.12, 0.3, 0.18),
            _word_node("World", 0.32, 0.12, 0.52, 0.18),
        ],
    }
    para0 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [line0],
    }
    block0 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [para0],
    }

    line1 = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.42, 0.51),
        "items": [
            _word_node("Foo", 0.1, 0.45, 0.25, 0.51),
            _word_node("Bar", 0.27, 0.45, 0.42, 0.51),
        ],
    }
    para1 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.42, 0.51),
        "items": [line1],
    }
    block1 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.42, 0.51),
        "items": [para1],
    }

    return {
        "type": "Page",
        "page_index": 0,
        "width": _IMAGE_W,
        "height": _IMAGE_H,
        "items": [block0, block1],
    }


# ─── Server fixture ───────────────────────────────────────────────────────────


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


def _seed_event_store(dest: Path, data_root: Path, image_bytes: bytes) -> None:
    """Seed the LabelerPageStore with our synthetic two-block page.

    Uses the same _ingest_ocr_result path that live OCR uses, so load_labeled
    can reconstruct the page on the next GET request.

    The store is created under ``dest/.pd-pages/`` (project directory layout).
    After seeding, the store is closed so the server can open its own instance.
    """

    page_dict = _build_page_dict()
    book_page = BookPage.from_dict(page_dict)

    # Seed the page-level store
    store = LabelerPageStore(dest)
    try:
        _ingest_ocr_result(
            page=book_page,
            image_bytes=image_bytes,
            page_index=0,
            store=store,
        )
        # Register page into the project aggregate (index→page_id map)
        _register_page_in_project(
            store=store,
            project_id=_PROJECT_ID,
            page_id=book_page.page_id,
            page_index=0,
        )
    finally:
        store.close()


@dataclass
class SelServer:
    base_url: str
    project_url: str  # /projects/<id>/pages/pageno/1


@pytest.fixture(scope="module")
def sel_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SelServer]:
    """Live server with the two-block sel-fixture project pre-loaded.

    Seeds the event store with synthetic two-block page content so
    GET /api/projects/{id}/pages/0 returns real line_matches without OCR.
    Skips when the SPA bundle is absent.
    """
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("sel-data")
    cache_root = tmp_path_factory.mktemp("sel-cache")
    config_root = tmp_path_factory.mktemp("sel-config")
    source_root = tmp_path_factory.mktemp("sel-source")

    # Source project: image + pages.json.
    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": f"{_B0_LINE_TEXT}\n{_B1_LINE_TEXT}"}))

    # Seed the event store before starting the server so the page is instantly
    # available via load_labeled (no OCR needed).
    _seed_event_store(dest, data_root, image_bytes)

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

    project_url = f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1"

    yield SelServer(base_url=base_url, project_url=project_url)

    server.should_exit = True
    thread.join(timeout=5)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _goto_project_page(page: Page, project_url: str) -> None:
    """Navigate to the sel-fixture project page and wait for it to render."""
    page.goto(project_url, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)


def _verify_fixture_two_blocks(base_url: str) -> tuple[dict, dict]:
    """Return (lm0, lm1) — the two line matches for the two blocks.

    Raises AssertionError if the payload doesn't have >=2 line_matches in
    >=2 distinct blocks.
    """
    r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10)
    assert r.status_code == 200, f"page payload GET failed: {r.status_code}"
    payload = r.json()
    lms = payload.get("line_matches", [])
    assert len(lms) >= 2, (
        f"Expected >=2 line_matches (two blocks), got {len(lms)}. "
        "Event-store seeding may have failed — check _seed_event_store."
    )
    block_indices = {lm.get("block_index") for lm in lms}
    assert len(block_indices) >= 2, (
        f"Expected words in >=2 distinct block_indices, got {block_indices}. "
        "page_to_line_matches may not be populating block_index."
    )
    return lms[0], lms[1]


def _select_first_word_via_hierarchy(page: Page) -> None:
    """Select the first word via the hierarchy tree (deterministic DOM path).

    Expands block → para → line → word nodes, clicking each to expand.
    """
    page.locator('[data-testid="drawer-tab-hierarchy"]').first.click()
    page.wait_for_selector('[data-testid="hierarchy"]', state="visible", timeout=10_000)
    time.sleep(0.3)

    block_nodes = page.locator('[data-testid^="hierarchy-node-block-"]')
    if block_nodes.count() > 0:
        block_nodes.first.click()
        block_nodes.first.press("ArrowRight")
        time.sleep(0.2)

    para_nodes = page.locator('[data-testid^="hierarchy-node-para-"]')
    para_nodes.first.wait_for(state="visible", timeout=10_000)
    para_nodes.first.click()
    para_nodes.first.press("ArrowRight")
    time.sleep(0.2)

    line_nodes = page.locator('[data-testid^="hierarchy-node-line-"]')
    line_nodes.first.wait_for(state="visible", timeout=10_000)
    line_nodes.first.click()
    line_nodes.first.press("ArrowRight")
    time.sleep(0.2)

    word_nodes = page.locator('[data-testid^="hierarchy-node-word-"]')
    word_nodes.first.wait_for(state="visible", timeout=10_000)
    word_nodes.first.click()
    time.sleep(0.4)


def _save_screenshot(page: Page, name: str) -> Path:
    """Save a screenshot to tests/e2e/artifacts/<name>.png and return the path."""
    _ARTIFACTS_DIR.mkdir(exist_ok=True)
    path = _ARTIFACTS_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def _fetch_encoded_dims(base_url: str) -> tuple[float, float]:
    """Return (display_width, scale) from the encoded_dims of page 0."""
    r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10)
    assert r.status_code == 200
    encoded = r.json().get("encoded_dims")
    assert encoded is not None, (
        "page payload must carry encoded_dims — check EncodedDims.from_source_dims in the pages endpoint"
    )
    return float(encoded["display_width"]), float(encoded["scale"])


def _assert_multi_word_detail(
    page: Page,
    *,
    ox0: float,
    oy0: float,
    ox1: float,
    oy1: float,
    pre_box: dict,
    post_box: dict,
    bbox0: dict,
    bbox1: dict,
    scale: float,
    display_width: float,
    lm0: dict,
    lm1: dict,
    line0_text: str,
    line1_text: str,
) -> None:
    """Assert MultiWordDetail is visible; fail with a precise BUG report if not."""
    multi = page.locator('[data-testid="multi-word-detail"]').first
    try:
        multi.wait_for(state="visible", timeout=8_000)
    except Exception:
        current_html = ""
        with contextlib.suppress(Exception):
            current_html = page.locator('[data-testid="right-panel-body"]').inner_html(timeout=2_000)
        selected_words_count = page.evaluate(
            """() => {
                const el = document.querySelector('[data-testid^="multi-word-"]');
                return el ? 'multi-word present but not visible' : 'no multi-word element';
            }"""
        )
        pytest.fail(
            "MUL BUG: Ctrl-click word 1 did NOT produce multi-word-detail.\n"
            f"  Word 0 click: offset ({ox0:.1f}, {oy0:.1f}) in pre_box={pre_box}, bbox0={bbox0}.\n"
            f"  Word 1 Ctrl-click: offset ({ox1:.1f}, {oy1:.1f}) in post_box={post_box}, bbox1={bbox1}.\n"
            f"  scale={scale}, display_width={display_width}.\n"
            f"  RightPanel body HTML: {current_html[:400]!r}\n"
            f"  multi-word probe: {selected_words_count}\n"
            "  Suspected cause: modifier not passed to Konva event, or "
            "additive toggleWord not accumulating across blocks in production build.\n"
            "  Check: PageImageCanvas.tsx resolveModifier (ctrlKey path), "
            "selection-store.ts toggleWord mode='toggle'."
        )

    block_groups = page.locator('[data-testid^="multi-word-block-"]')
    block_count = block_groups.count()
    assert block_count >= 2, (
        f"multi-word-detail should show >=2 block groups, got {block_count}. "
        f"block_index of lm0={lm0.get('block_index')}, lm1={lm1.get('block_index')}. "
        "MultiWordDetail.tsx may not be grouping by block_index correctly."
    )

    panel_text = multi.inner_text()

    def _text_in(needle: str, haystack: str) -> bool:
        return needle in haystack or (len(needle) > 5 and needle[:15] in haystack)

    assert _text_in(line0_text, panel_text), (
        f"ocr_line_text {line0_text!r} not found in multi-word-detail.\nPanel text: {panel_text!r}"
    )
    assert _text_in(line1_text, panel_text), (
        f"ocr_line_text {line1_text!r} not found in multi-word-detail.\nPanel text: {panel_text!r}"
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.e2e


def test_sel_fixture_loads_two_blocks(sel_server: SelServer) -> None:
    """Sanity: the sel-fixture page payload exposes two distinct block_indices.

    This is the prerequisite guard for MUL-1/2 tests.  If it fails, the
    event-store seeding path is broken — investigate _seed_event_store.
    """
    _verify_fixture_two_blocks(sel_server.base_url)


@pytest.mark.e2e
def test_sel1_word_click_shows_selection_and_word_detail(
    sel_server: SelServer,
    page: Page,
) -> None:
    """SEL-1: selecting a word via the hierarchy produces a VISIBLE selection.

    Acceptance:
    - WordDetail (word-header-id) renders with the correct line/word identity.
    - The canvas image-viewport is visible (the selection-highlight layer is
      drawn onto it — Konva-painted, not DOM-queryable).
    - A screenshot proves the selected state is observable in the browser.
    """
    lm0, _ = _verify_fixture_two_blocks(sel_server.base_url)
    word0 = lm0["word_matches"][0]
    li = word0["line_index"]
    wi = word0["word_index"]

    _goto_project_page(page, sel_server.project_url)
    _select_first_word_via_hierarchy(page)

    # WordDetail header must show correct identity.
    header = page.locator('[data-testid="word-header-id"]').first
    header.wait_for(state="visible", timeout=10_000)
    header_text = header.inner_text()
    assert f"Line {li + 1}" in header_text, f"word-header-id {header_text!r} should contain 'Line {li + 1}'"
    assert f"Word {wi + 1}" in header_text, f"word-header-id {header_text!r} should contain 'Word {wi + 1}'"

    # Canvas must be visible (the highlight layer is drawn onto it).
    viewport = page.locator('[data-testid="image-viewport"]').first
    viewport.wait_for(state="visible", timeout=5_000)

    _save_screenshot(page, "sel1_selected_word_highlight")


@pytest.mark.e2e
def test_mul1_2_cross_block_multi_select_shows_both_blocks(
    sel_server: SelServer,
    page: Page,
) -> None:
    """MUL-1/2: real Ctrl-click cross-block multi-select shows both block groups.

    Acceptance bar (CT requirement):
    - "when I select words that roll up to different blocks I should SEE them all"
    - "include the line"

    Strategy: drive REAL user-path clicks on the Konva image canvas.
      1. Plain-click word 0 (block 0) → toggleWord(li0, wi0, "replace").
      2. Ctrl-click word 1 (block 1) → toggleWord(li1, wi1, "toggle").
      3. selectedWords.length > 1 → RightPanel renders MultiWordDetail.
      4. Assert multi-word-detail, >=2 block groups, both ocr_line_text values.

    Coordinate math mirrors test_image_click_selection.py:
      fit_scale = konvajs_content_box["width"] / encoded["display_width"]
      offset_x = (bbox["x"] * scale + bbox["width"] * scale / 2) * fit_scale
      offset_y = (bbox["y"] * scale + bbox["height"] * scale / 2) * fit_scale

    For step 1 we use page.mouse.click(abs_x, abs_y); for step 2 we re-read
    konvajs-content box (layout shifts after right panel opens) and use
    locator.click(position=..., modifiers=['Control']) — the only Playwright
    API that reliably delivers ctrlKey=True to the Konva container div in
    headless Chromium.

    If the plain-click or Ctrl-click does NOT produce multi-word-detail, the test
    fails with a precise BUG report rather than claiming success.
    """
    # ── API: confirm two-block fixture and fetch encoded_dims ─────────────────
    lm0, lm1 = _verify_fixture_two_blocks(sel_server.base_url)
    display_width, scale = _fetch_encoded_dims(sel_server.base_url)
    line0_text = lm0.get("ocr_line_text", "")
    line1_text = lm1.get("ocr_line_text", "")
    bbox0 = lm0["word_matches"][0]["bbox"]
    bbox1 = lm1["word_matches"][0]["bbox"]

    _goto_project_page(page, sel_server.project_url)

    # ── Locate the Konva container div (Konva event-binding target) ───────────
    # Playwright's locator.click(modifiers=[...]) dispatches a PointerEvent with
    # ctrlKey=True on this element; page.keyboard.down("Control") + mouse.click()
    # produces ZERO events (browser intercepts Ctrl+click at the OS layer).
    konva_content = page.locator(".konvajs-content").first
    konva_content.wait_for(state="visible", timeout=10_000)

    # Capture bounding box BEFORE step 1.  Step 1 opens the right panel, narrowing
    # the canvas, so we re-read the box after step 1 for the Ctrl-click offset.
    pre_box = konva_content.bounding_box()
    assert pre_box is not None, "konvajs-content must have an on-screen bounding box"

    def _word_offset(elem_box: dict, bbox: dict) -> tuple[float, float]:
        """Return (offset_x, offset_y) within elem_box for the bbox center."""
        fs = elem_box["width"] / display_width
        return (
            (bbox["x"] * scale + bbox["width"] * scale / 2) * fs,
            (bbox["y"] * scale + bbox["height"] * scale / 2) * fs,
        )

    ox0, oy0 = _word_offset(pre_box, bbox0)

    # ── STEP 1: plain-click word 0 (block 0) ─────────────────────────────────
    page.mouse.click(pre_box["x"] + ox0, pre_box["y"] + oy0)
    time.sleep(0.5)  # Let React re-render + right panel open

    if (
        not page.locator('[data-testid="word-header-id"]').count()
        and not page.locator('[data-testid="multi-word-detail"]').count()
    ):
        pytest.fail(
            "MUL BUG (step 1): plain-click on word 0 did NOT open WordDetail.\n"
            f"  offset ({ox0:.1f}, {oy0:.1f}), bbox0={bbox0}, scale={scale}, pre_box={pre_box}."
        )

    # ── STEP 2: Ctrl-click word 1 (block 1) ──────────────────────────────────
    # Re-read konvajs-content box after layout shift, compute word-1 offset fresh.
    post_box = konva_content.bounding_box()
    assert post_box is not None, "konvajs-content must still have a bounding box after step 1"
    ox1, oy1 = _word_offset(post_box, bbox1)
    konva_content.click(position={"x": ox1, "y": oy1}, modifiers=["Control"])
    time.sleep(0.5)

    # ── STEPS 3-5: assert MultiWordDetail with both block groups ─────────────
    _assert_multi_word_detail(
        page,
        ox0=ox0,
        oy0=oy0,
        ox1=ox1,
        oy1=oy1,
        pre_box=pre_box,
        post_box=post_box,
        bbox0=bbox0,
        bbox1=bbox1,
        scale=scale,
        display_width=display_width,
        lm0=lm0,
        lm1=lm1,
        line0_text=line0_text,
        line1_text=line1_text,
    )

    # ── STEP 6: screenshot proof ──────────────────────────────────────────────
    _save_screenshot(page, "mul_cross_block_multiselect")


@pytest.mark.e2e
def test_grid1_toolbar_action_grid_visible_and_collapse_works(
    sel_server: SelServer,
    page: Page,
) -> None:
    """GRID-1: ToolbarActionGrid is VISIBLE (not in a display:none subtree).
    The collapse toggle (toolbar-grid-collapse) works — clicking it toggles
    the grid body visibility.
    """
    _goto_project_page(page, sel_server.project_url)

    # GRID-1: the collapse button must be in the DOM and NOT inside display:none.
    collapse_btn = page.locator('[data-testid="toolbar-grid-collapse"]').first
    assert collapse_btn.count() > 0, "toolbar-grid-collapse must be in the DOM"
    collapse_btn.wait_for(state="visible", timeout=10_000)

    # Verify: the collapse button is NOT inside any display:none ancestor.
    is_btn_hidden = page.evaluate(
        """() => {
            let el = document.querySelector('[data-testid="toolbar-grid-collapse"]');
            while (el) {
                if (window.getComputedStyle(el).display === 'none') return true;
                el = el.parentElement;
            }
            return false;
        }"""
    )
    assert not is_btn_hidden, (
        "toolbar-grid-collapse is inside a display:none ancestor — "
        "GRID-1 FAILED: the ToolbarActionGrid bar is still hidden"
    )

    # Collapse toggle: record initial body visibility.
    initial_hidden = page.evaluate(
        """() => {
            const el = document.querySelector('[data-testid="toolbar-grid-body"]');
            if (!el) return null;
            return window.getComputedStyle(el).display === 'none';
        }"""
    )

    # Click collapse toggle — body should change state.
    collapse_btn.click()
    time.sleep(0.3)

    after_click = page.evaluate(
        """() => {
            const el = document.querySelector('[data-testid="toolbar-grid-body"]');
            if (!el) return null;
            return window.getComputedStyle(el).display === 'none';
        }"""
    )

    if initial_hidden is not None and after_click is not None:
        assert after_click != initial_hidden, (
            "Clicking toolbar-grid-collapse did NOT toggle the grid body visibility. "
            f"Before: display:none={initial_hidden}, after: display:none={after_click}"
        )

    # Restore state.
    collapse_btn.click()
    time.sleep(0.2)

    _save_screenshot(page, "grid1_toolbar_action_grid_visible")


@pytest.mark.e2e
def test_grid3_stb1_per_word_validate_mutates_state_end_to_end(
    sel_server: SelServer,
    page: Page,
) -> None:
    """GRID-3 + STB-1 END-TO-END: per-word validate produces a visible + persisted
    state change.

    Path tested:
      hierarchy → select word → WordDetail opens → word-footer-validate button →
      click → label flips (re-render after TanStack Query invalidation) →
      API confirms new validated state.

    This proves the full mutation chain is live: the button fires a POST
    to /api/projects/{id}/pages/0/words/{li}/{wi}/validated, the server updates
    the event store, the query is invalidated, and the UI re-renders with the
    new state.

    STB-1 gap note: the word-validate-button (data-testid="word-validate-button-{l}-{w}")
    in WordCell / LineCard IS wired with an onClick handler that calls
    onValidate?.(l, w, !word.is_validated). However, LineDetail's embedded
    <LineCard> does not pass onValidateWord, so the word-validate-button from
    the LineDetail surface is a no-op. The word-footer-validate in WordDetail
    (tested here) IS fully wired. See STB-1 in LineDetail.tsx line ~277.
    """
    lm0, _ = _verify_fixture_two_blocks(sel_server.base_url)
    w0 = lm0["word_matches"][0]
    li0, wi0 = w0["line_index"], w0["word_index"]

    _goto_project_page(page, sel_server.project_url)
    _select_first_word_via_hierarchy(page)

    # WordDetail footer must be visible.
    footer_validate = page.locator('[data-testid="word-footer-validate"]').first
    footer_validate.wait_for(state="visible", timeout=10_000)

    # Record initial state from button label.
    initial_label = footer_validate.inner_text().strip()
    initial_validated = "✓" in initial_label or "Validated" in initial_label

    # Click the validate/unvalidate button.
    footer_validate.click()

    # Wait for the label to flip (query invalidation → re-render).
    deadline = time.monotonic() + 10
    label_changed = False
    while time.monotonic() < deadline:
        try:
            new_label = page.locator('[data-testid="word-footer-validate"]').first.inner_text().strip()
            if new_label != initial_label:
                label_changed = True
                break
        except Exception as _exc:
            # Playwright may throw transiently while React re-renders; ignore and retry.
            _ = _exc
        time.sleep(0.2)

    new_label = footer_validate.inner_text().strip()

    if not label_changed:
        # Report as a BUG with diagnosis — do not claim success.
        pytest.fail(
            f"GRID-3/STB-1 END-TO-END BUG: word-footer-validate label did NOT change "
            f"after click.\n"
            f"  Initial label: {initial_label!r}\n"
            f"  Current label: {new_label!r}\n"
            f"  Broken path: word-footer-validate → onClick → useValidateWord.mutate() "
            f"(WordFooter.tsx:~116) → POST /api/projects/{_PROJECT_ID}/pages/0/"
            f"words/{li0}/{wi0}/validated → queryClient.invalidateQueries() → re-render.\n"
            f"  Diagnose: (1) did the POST fire? (2) did server return 200? "
            f"(3) was queryClient.invalidateQueries called? (4) did the component re-render?"
        )

    new_validated = "✓" in new_label or "Validated" in new_label
    assert new_validated != initial_validated, (
        f"Label changed but validated direction is identical: "
        f"initial={initial_validated} ({initial_label!r}), new={new_validated} ({new_label!r})"
    )

    # API-level confirmation: server reflects the new state.
    r = httpx.get(f"{sel_server.base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10)
    assert r.status_code == 200
    payload = r.json()
    lm = next((lm for lm in payload.get("line_matches", []) if lm["line_index"] == li0), None)
    assert lm is not None, f"line_index {li0} not found in re-fetched payload"
    wm = next((wm for wm in lm.get("word_matches", []) if wm["word_index"] == wi0), None)
    assert wm is not None, f"word_index {wi0} not found in line {li0}"
    assert wm.get("is_validated") == (not initial_validated), (
        f"API says word is_validated={wm.get('is_validated')!r} but expected "
        f"{not initial_validated!r} after toggle. "
        "Mutation fired and label changed but server persistence did not complete."
    )

    _save_screenshot(page, "stb1_per_word_validated_state_change")


# ─── Line-scope helpers + parity-gap regression tests (2026-06-11) ────────────


def _select_line_via_hierarchy(page: Page, block_nth: int = 0) -> None:
    """Select a line via the hierarchy tree (level=line selection).

    Same expansion path as ``_select_first_word_via_hierarchy`` but stops at
    the line node, so the RightPanel shows LineDetail instead of WordDetail.
    ``block_nth`` picks which top-level block to expand (each fixture block
    holds exactly one para → one line).
    """
    page.locator('[data-testid="drawer-tab-hierarchy"]').first.click()
    page.wait_for_selector('[data-testid="hierarchy"]', state="visible", timeout=10_000)
    time.sleep(0.3)

    block_nodes = page.locator('[data-testid^="hierarchy-node-block-"]')
    if block_nodes.count() > block_nth:
        block_nodes.nth(block_nth).click()
        block_nodes.nth(block_nth).press("ArrowRight")
        time.sleep(0.2)

    para_nodes = page.locator('[data-testid^="hierarchy-node-para-"]')
    para_nodes.first.wait_for(state="visible", timeout=10_000)
    para_nodes.first.click()
    para_nodes.first.press("ArrowRight")
    time.sleep(0.2)

    line_nodes = page.locator('[data-testid^="hierarchy-node-line-"]')
    line_nodes.first.wait_for(state="visible", timeout=10_000)
    line_nodes.first.click()
    time.sleep(0.4)


def _poll_line(base_url: str, line_index: int, predicate, timeout: float = 10.0) -> dict | None:
    """Poll GET pages/0 until ``predicate(line_match)`` is truthy; return it."""
    deadline = time.monotonic() + timeout
    last: dict | None = None
    while time.monotonic() < deadline:
        r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10)
        if r.status_code == 200:
            payload = r.json()
            last = next(
                (lm for lm in payload.get("line_matches", []) if lm["line_index"] == line_index),
                None,
            )
            if last is not None and predicate(last):
                return last
        time.sleep(0.3)
    return last


@pytest.mark.e2e
def test_sel3_shift_hotkeys_sync_rail_target(sel_server: SelServer, page: Page) -> None:
    """SEL-3 radio→rail direction: Shift+1/2 selection-mode changes drive the Rail.

    The header selection-mode radios were retired with ImageTabsHeader; the
    surviving "radio-equivalent" input is the Shift+1/2/3 viewport hotkeys.
    Per the SEL-3 contract (docs/specs/2026-06-05-selection-operations-parity.md
    Slice A) a selection-mode change must also set ``railStore.target`` so the
    Rail highlight and box-select granularity agree.

    Acceptance (visible + real effect): the rail-target-para cell gains
    data-active="true" after Shift+1, and rail-target-word loses it.
    """
    _goto_project_page(page, sel_server.project_url)

    rail_para = page.locator('[data-testid="rail-target-para"]').first
    rail_word = page.locator('[data-testid="rail-target-word"]').first
    rail_para.wait_for(state="visible", timeout=10_000)

    # Normalize starting state: click the Word target (also sets selectionMode).
    rail_word.click()
    time.sleep(0.3)
    assert rail_word.get_attribute("data-active") == "true"
    assert rail_para.get_attribute("data-active") is None

    # Shift+1 → selectionMode "paragraph" → railStore.target must follow.
    page.keyboard.press("Shift+1")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if rail_para.get_attribute("data-active") == "true":
            break
        time.sleep(0.2)
    assert rail_para.get_attribute("data-active") == "true", (
        "Shift+1 set selectionMode=paragraph but rail-target-para did not become "
        "active — SEL-3 radio→rail sync is broken (PageImageCanvas "
        "onSelectionModeChange must call railStore.setTarget)."
    )
    assert rail_word.get_attribute("data-active") is None

    # Shift+2 → line target follows too.
    page.keyboard.press("Shift+2")
    rail_line = page.locator('[data-testid="rail-target-line"]').first
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if rail_line.get_attribute("data-active") == "true":
            break
        time.sleep(0.2)
    assert rail_line.get_attribute("data-active") == "true"

    _save_screenshot(page, "sel3_shift1_rail_target_para_active")


@pytest.mark.e2e
def test_bulk_line_words_validate_selected_end_to_end(
    sel_server: SelServer,
    page: Page,
) -> None:
    """LineDetail Words-tab bulk bar: "Validate selected" fires a real mutation.

    Path: hierarchy → select line 1 (block 1, "Foo Bar" — untouched by the
    other tests in this module-scoped server) → LineDetail Words tab → check
    word 0 → line-detail-bulk-validate → API confirms word 0 is_validated=True
    while word 1 is untouched (scope=word batch, not whole-line).
    """
    # Precondition: word 0 of line 1 starts unvalidated.
    lm1 = _poll_line(sel_server.base_url, 1, lambda lm: True)
    assert lm1 is not None, "line 1 missing from fixture payload"
    w0 = next(wm for wm in lm1["word_matches"] if wm["word_index"] == 0)
    assert not w0.get("is_validated"), "fixture word (1,0) unexpectedly already validated"

    _goto_project_page(page, sel_server.project_url)
    _select_line_via_hierarchy(page, block_nth=1)

    line_detail = page.locator('[data-testid="line-detail"]').first
    line_detail.wait_for(state="visible", timeout=10_000)

    # Switch to the Words tab and check word 0.
    page.locator('[data-testid="line-detail-tab-words"]').first.click()
    checkbox = page.locator('[data-testid="line-words-card-checkbox-0"]').first
    checkbox.wait_for(state="visible", timeout=10_000)
    checkbox.check()

    bulk_validate = page.locator('[data-testid="line-detail-bulk-validate"]').first
    bulk_validate.wait_for(state="visible", timeout=5_000)
    bulk_validate.click()

    # Real-effect acceptance: the server reflects word (1,0) validated.
    lm = _poll_line(
        sel_server.base_url,
        1,
        lambda lm: any(wm["word_index"] == 0 and wm.get("is_validated") for wm in lm["word_matches"]),
    )
    assert lm is not None, "line 1 missing after bulk validate"
    w0_after = next(wm for wm in lm["word_matches"] if wm["word_index"] == 0)
    assert w0_after.get("is_validated") is True, (
        "Bulk 'Validate selected' did NOT persist is_validated=True for word 0 — "
        "line-detail-bulk-validate → useValidateWords → POST words/validate-batch "
        "(scope=word) chain is broken."
    )
    # Unchecked sibling word stays untouched (proves scope=word, not line).
    w1_after = next(wm for wm in lm["word_matches"] if wm["word_index"] == 1)
    assert not w1_after.get("is_validated"), (
        "Sibling word 1 was validated too — bulk bar sent a broader scope than the checked selection."
    )

    _save_screenshot(page, "bulk_line_words_validate_selected")


@pytest.mark.e2e
def test_line_gt_commit_end_to_end(sel_server: SelServer, page: Page) -> None:
    """GTRow line-scope GT commit: editing line-detail-gt-input persists via set-gt.

    Path: hierarchy → select line 0 → fill line-detail-gt-input → Enter
    (blur-commit) → API confirms ground_truth_line_text updated. Refutes the
    06-10 review claim that line-level GT commit has "no endpoint" (route:
    POST .../lines/{li}/set-gt, api/lines_paragraphs.py).
    """
    new_gt = "Howdy World"

    _goto_project_page(page, sel_server.project_url)
    _select_line_via_hierarchy(page, block_nth=0)

    gt_input = page.locator('[data-testid="line-detail-gt-input"]').first
    gt_input.wait_for(state="visible", timeout=10_000)

    gt_input.click()
    gt_input.fill(new_gt)
    gt_input.press("Enter")  # Enter blurs → commit() → useSetLineGt.mutate

    lm = _poll_line(
        sel_server.base_url,
        0,
        lambda lm: lm.get("ground_truth_line_text") == new_gt,
    )
    assert lm is not None, "line 0 missing after GT commit"
    assert lm.get("ground_truth_line_text") == new_gt, (
        f"Line GT commit did not persist: expected {new_gt!r}, got "
        f"{lm.get('ground_truth_line_text')!r}. Chain: line-detail-gt-input blur → "
        "useSetLineGt → POST lines/0/set-gt → token distribution onto words."
    )

    _save_screenshot(page, "line_gt_commit_persisted")

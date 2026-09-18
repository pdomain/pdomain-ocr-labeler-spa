"""E2E: selecting a word and marking glyph review reaches the API (M11 Task 9).

Covers: F-GLYPH-REVIEW-01

Plan: docs/plans/2026-07-21-glyph-annotations-completion.md — Task 9.
Issue: docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md.

Self-contained fixture-server pattern, following `test_bbox_refine_buttons.py`
/ `test_review_queue_panel.py` (read first): a synthetic one-word project
seeded via `_ingest_ocr_result`, no OCR model involved.

Scope note (why this covers "mark reviewed", not "accept prediction"): the
classifier adapter seam (`IGlyphPredictor`) is intentionally unwired —
`glyph_predictions_map` is never populated by any production code path
(only a direct POST to `.../accept-prediction` after something else wrote
predictions could reach it, and nothing does). A fixture seeded through
`_ingest_ocr_result` — the same no-OCR seeding path every other e2e in this
directory uses — has no way to plant `glyph_predictions` on a word without
reaching into `PageState` internals the way a browser-driven user never
could, so a browser test cannot honestly drive "accept a predicted mark".
That path is covered at the vitest level instead —
`WordDetail.test.tsx`'s "accepts a prediction, posting to the
accept-prediction route" test.

What this test drives for real: selecting a word on the canvas, opening the
"Glyphs" accordion item GlyphAnnotationPanel lives in, clicking "Mark
reviewed (no marks)", and confirming the resulting `glyph_annotations`
actually landed on the server (not just that the button click didn't
error) — a plain GET of the page payload after the click.
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

_PROJECT_ID = "glyph-panel-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# Comfortably inside the page image, matching test_bbox_refine_buttons.py's
# placement convention.
_WORD_X1, _WORD_Y1, _WORD_X2, _WORD_Y2 = 300, 400, 500, 440
_WORD_TEXT = "action"


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

    Mirrors `test_bbox_refine_buttons.py`'s `_make_page` — the proven no-OCR
    seeding shape for `_ingest_ocr_result`. GT text contains "ct" (an M11
    ligature substring) purely so the fixture would also serve a future
    bulk-mark e2e; this test only marks reviewed with no marks.
    """
    word = {
        "type": "Word",
        "text": _WORD_TEXT,
        "ground_truth_text": _WORD_TEXT,
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
class GlyphPanelServer:
    base_url: str


@pytest.fixture(scope="module")
def glyph_panel_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[GlyphPanelServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("glyph-panel-data")
    cache_root = tmp_path_factory.mktemp("glyph-panel-cache")
    config_root = tmp_path_factory.mktemp("glyph-panel-config")
    source_root = tmp_path_factory.mktemp("glyph-panel-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": _WORD_TEXT}))

    # Seed the event store directly — no OCR model needed for this flow.
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

    yield GlyphPanelServer(base_url=base_url)

    server.should_exit = True
    thread.join(timeout=5)


def _click_word_on_canvas(page: Page, base_url: str) -> None:
    """Click the seeded word's bbox on the Konva canvas to select it.

    Reuses the click-math from `test_bbox_refine_buttons.py` /
    `test_image_click_selection.py`: the page payload's bbox is in encoded
    (possibly downscaled) pixel space, so the on-screen click point is
    computed via `encoded_dims.scale` and the rendered canvas's fit scale.
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


def _open_glyphs_accordion(page: Page) -> None:
    """Open the WordDetail "Glyphs" accordion item.

    Radix removes closed accordion content from the DOM, so
    `glyph-panel-0-0` and its buttons only attach once this trigger is
    clicked — same pattern as `test_bbox_refine_buttons.py`'s
    `_open_bbox_accordion`.
    """
    accordion = page.locator('[data-testid="word-detail-accordion"]')
    accordion.wait_for(state="attached", timeout=10_000)
    trigger = accordion.locator('button:has-text("Glyphs")').first
    trigger.wait_for(state="visible", timeout=5_000)
    trigger.click()
    page.wait_for_selector('[data-testid="glyph-panel-0-0"]', state="visible", timeout=5_000)


@pytest.mark.e2e
def test_mark_reviewed_no_marks_reaches_the_api(
    glyph_panel_server: GlyphPanelServer,
    page: Page,
) -> None:
    """Select a word, mark glyph review with no marks, confirm the API has it.

    Covers the M11 Task 9 acceptance path: chip/badge staleness and the
    payload-inject gap this epic tracked are both upstream fixes (already
    on master) — this test is the browser-level proof that a real click,
    through the real mutation hook and the real route, produces a durable
    `glyph_annotations` value a plain GET of the page can see, not just
    that the button exists.
    """
    base_url = glyph_panel_server.base_url

    # Before any review: the word carries neither annotations nor
    # predictions (the tri-state "not reviewed" per spec §3).
    before = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10.0).json()
    before_word = before["line_matches"][0]["word_matches"][0]
    assert before_word["glyph_annotations"] is None

    _click_word_on_canvas(page, base_url)
    _open_glyphs_accordion(page)

    mark_reviewed_button = page.locator('[data-testid="glyph-panel-mark-reviewed-empty"]')
    mark_reviewed_button.wait_for(state="visible", timeout=5_000)
    mark_reviewed_button.click()

    # The panel's own reflection of state: "Reset" only renders once
    # annotations != null, confirming the client saw a successful response.
    reset_button = page.locator('[data-testid="glyph-panel-reset"]')
    expect(reset_button).to_be_visible(timeout=10_000)

    # The actual proof this test exists for: an independent GET (no
    # dependency on client-side cache state) shows the mutation reached
    # the server and persisted.
    after = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10.0).json()
    after_word = after["line_matches"][0]["word_matches"][0]
    assert after_word["glyph_annotations"] == {
        "ligatures": [],
        "long_s_positions": [],
        "swash": False,
        "source": "human",
    }


def _click_glyph_chip(page: Page, base_url: str, testid: str) -> None:
    """Navigate to the project page, open the Matches tab, and click a glyph chip.

    The word-match list ("Matches" tab) is `TextTabs`' default active tab,
    but `test_driver_contract.py`'s per-word tests click `text-tab-matches`
    explicitly rather than relying on that default (it once collapsed to
    zero height with real word content — see that file's
    `_wait_word_match_view_visible`) — this does the same, defensively.
    """
    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    page.click('[data-testid="text-tab-matches"]')
    page.wait_for_selector('[data-testid="word-match-view"]', timeout=10_000)

    chip = page.locator(f'[data-testid="{testid}"]')
    chip.wait_for(state="visible", timeout=10_000)
    chip.click()


@pytest.mark.e2e
def test_glyph_chip_click_selects_word_and_opens_panel(
    glyph_panel_server: GlyphPanelServer,
    page: Page,
) -> None:
    """Clicking a real glyph chip selects that word and opens its panel.

    Covers the M11 Task 6 fix (2026-09-18): `WordCell`'s glyph chips were
    `/* future: open panel */` no-ops; they now call the same
    select-word-and-open-right-panel path the pencil edit button
    (`onEditWord`) does. Seeds a confirmed "ct" ligature directly through
    the glyph-annotations route (not through the panel — B-GLYPH-002
    already covers that path) so a real, non-predicted chip renders in the
    word-match list, without this test also re-proving the mark-setting
    flow.

    The click itself is a pure client-side selection change (`selectWord` +
    `rightPanelOpen`) with no network request, so this waits on the
    resulting DOM (the right panel's word header, then the Glyphs
    accordion content) rather than a fixed sleep — following
    `test_keyboard_only.py`'s response-waiting approach of asserting on the
    real signal an action produces instead of a guessed delay.
    """
    base_url = glyph_panel_server.base_url

    ann = {
        "ligatures": [{"kind": "ct", "char_span": None}],
        "long_s_positions": [],
        "swash": False,
        "source": "human",
    }
    resp = httpx.post(
        f"{base_url}/api/projects/{_PROJECT_ID}/pages/0/words/0/0/glyph-annotations",
        json={"annotations": ann},
        timeout=10.0,
    )
    assert resp.status_code == 200, f"seed glyph-annotations failed: {resp.status_code} {resp.text}"

    try:
        _click_glyph_chip(page, base_url, "word-glyph-chip-0-0-ct")

        # Lands on *that word's* panel: the header shows its 1-based
        # line/word id (this fixture has exactly one word, at line 0 /
        # word 0), and the Glyphs accordion — keyed to the same word — opens.
        header_id = page.locator('[data-testid="word-header-id"]')
        expect(header_id).to_be_visible(timeout=10_000)
        expect(header_id).to_have_text("Line 1 · Word 1")

        _open_glyphs_accordion(page)
    finally:
        # glyph_panel_server is module-scoped and shared with
        # test_mark_reviewed_no_marks_reaches_the_api, whose own "before"
        # assertion depends on glyph_annotations starting at None — leave
        # the fixture as this test found it regardless of pass/fail.
        reset = httpx.post(
            f"{base_url}/api/projects/{_PROJECT_ID}/pages/0/words/0/0/glyph-annotations",
            json={"annotations": None},
            timeout=10.0,
        )
        assert reset.status_code == 200, f"reset glyph-annotations failed: {reset.status_code} {reset.text}"

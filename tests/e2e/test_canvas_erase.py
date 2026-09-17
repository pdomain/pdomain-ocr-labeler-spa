"""E2E: canvas erase mode actually erases against the backend (P1-CANVAS-ERASE).

Before this fix, ``ProjectPage`` mounted ``PageImageCanvas`` without
``onErasePixels`` — a canvas erase drag showed the mode pill, the drag
preview, and reset the mode to "select" on completion, but never called the
backend. The UI *looked* like it worked; nothing was ever erased. See
``docs/issues/2026-07-21-canvas-erase-mode-noop.md``.

This test enters erase mode from the Rail's mode card
(``rail-mode-erase`` — the click path into the same ``viewportStore`` "erase"
mode the ``Shift+E`` hotkey targets; see the note on ``_enter_erase_mode``
below for why the hotkey itself is not used here), drags a rectangle over a
known page-space area with ``page.mouse``, and then proves the backend
actually processed the erase — not merely that the UI reacted — by polling
the page payload's ``history.undo_available`` flag the same way
``test_undo_redo.py`` proves other mutations reached the store:
``_erase_pixels_on_page_image`` (``api/pages.py``) calls
``_save_to_store_best_effort`` on every successful erase, which appends a new
provenance version and flips ``undo_available`` from ``False`` (a freshly
ingested page has nothing to undo) to ``True``. A UI-only no-op (the pre-fix
behavior) leaves the flag ``False`` forever.

Follows the self-contained fixture-server pattern established in
``test_review_queue_panel.py`` / ``test_region_layer_visibility.py``.

Run with:   make e2e AI=1
Or inline:  PLAYWRIGHT_BROWSERS_PATH=/cache/shared-ai/ms-playwright \
            uv run --group e2e pytest tests/e2e/test_canvas_erase.py -n 0 -p no:cacheprovider --no-cov
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
import numpy as np
import pytest
import uvicorn
from fastapi import FastAPI
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "canvas-erase-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# Well inside the page image, away from the "canvas-mode-pill" viewport-mode
# indicator pinned at `top-10 left-2` (see test_region_layer_visibility.py's
# `_CONFIRMED_LTRB` comment — a rect placed near image-space (100, 100) lands
# under that pill at this fixture's viewport size).
_ERASE_LTRB = (600, 700, 900, 900)


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
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(bytes([0]) + bytes([255] * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def _seed_cv2_page_image(app: FastAPI, page_index: int, width: int, height: int) -> None:
    """Attach an in-memory ``cv2_numpy_page_image`` to the already-loaded page.

    ``_erase_pixels_on_page_image`` (``api/pages.py``) requires
    ``page.cv2_numpy_page_image`` — but that field is only ever set by a real
    cold-OCR run (``LocalDoctrPageLoader._run_ocr_on_path`` calling
    ``cv2.imread`` on the source file). The ``_ingest_ocr_result`` +
    ``/api/projects/load`` seeding path this fixture otherwise shares with
    ``test_review_queue_panel.py`` / ``test_region_layer_visibility.py``
    reconstructs the served ``Page`` via ``Page.from_dict`` over the stored
    JSON blob (``LocalDoctrPageLoader.load_labeled``), which never carries
    this transient, unserialized field — so it is always ``None`` after that
    path alone, and the erase route always 400s. Those other fixtures never
    hit this because they never call erase; this one does, so it must attach
    the array itself — the same technique
    ``test_page_erase_pixels_router.py``'s ``_seed_wordless_page`` uses for
    the same reason, applied here to the live in-process server (this
    fixture's ``app`` and the running ``uvicorn.Server`` share one process).
    Call this only after a request that has already caused
    ``load_labeled``/``run_ocr`` to populate the page state (e.g. one GET of
    the page payload) — otherwise ``get_page_state`` returns ``None``.
    """
    project_state = app.state.project_state
    pstate = project_state.get_page_state(page_index)
    assert pstate is not None, f"page {page_index} was not loaded before seeding its cv2 image"
    payload = pstate.page_record.payload if pstate.page_record is not None else None
    assert payload is not None, f"page {page_index} has no in-memory Page payload to seed"
    # White, matching the synthetic fixture PNG (_make_png fills every row
    # with 255) — the erase target rect is otherwise indistinguishable from
    # its surroundings, which is fine here since this test proves the
    # *mutation was recorded*, not a visual pixel diff.
    payload.cv2_numpy_page_image = np.full((height, width, 3), 255, dtype=np.uint8)


@dataclass
class CanvasEraseServer:
    base_url: str
    project_root: Path


@pytest.fixture(scope="module")
def canvas_erase_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[CanvasEraseServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("canvas-erase-data")
    cache_root = tmp_path_factory.mktemp("canvas-erase-cache")
    config_root = tmp_path_factory.mktemp("canvas-erase-config")
    source_root = tmp_path_factory.mktemp("canvas-erase-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": ""}))

    # No blocks/words needed — the page-scoped erase-pixels route (this
    # issue's fix) erases directly against the page image with no word to
    # anchor to, unlike the word-scoped route the right panel uses.
    book_page = BookPage(width=_IMAGE_W, height=_IMAGE_H, page_index=0, blocks=[])

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

    # Establish the page-0 PageState (load_labeled, from the store seeded
    # above) before attaching the cv2 image the erase route needs.
    r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10)
    assert r.status_code == 200, f"initial page GET failed: {r.status_code} {r.text}"
    _seed_cv2_page_image(app, page_index=0, width=_IMAGE_W, height=_IMAGE_H)

    yield CanvasEraseServer(base_url=base_url, project_root=dest)

    server.should_exit = True
    thread.join(timeout=5)


def _api_page(server: CanvasEraseServer) -> dict:
    r = httpx.get(f"{server.base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10.0)
    assert r.status_code == 200, f"page payload GET failed: {r.status_code} {r.text}"
    return r.json()


def _drag_erase_rect(page: Page, ltrb: tuple[int, int, int, int], scale: float, display_width: float) -> None:
    """Drag an erase rectangle over page-space ``ltrb``.

    Coordinate math mirrors ``test_multi_line_detail.py``'s
    ``_drag_across_two_lines``: display_coord = source_coord * scale, then a
    canvas fit_scale accounts for the rendered Konva stage being narrower
    than its logical display_width.
    """
    konva_content = page.locator(".konvajs-content").first
    konva_content.wait_for(state="visible", timeout=10_000)
    box = konva_content.bounding_box()
    assert box is not None, "konvajs-content must be on-screen"
    fit_scale = box["width"] / display_width

    left, top, right, bottom = ltrb
    start_x = box["x"] + left * scale * fit_scale
    start_y = box["y"] + top * scale * fit_scale
    end_x = box["x"] + right * scale * fit_scale
    end_y = box["y"] + bottom * scale * fit_scale

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y, steps=5)
    page.mouse.up()


def _enter_erase_mode(page: Page) -> None:
    """Enter viewport "erase" mode via the Rail's mode card.

    ``useViewportHotkeys`` binds ``Shift+E`` to the same ``viewportStore``
    erase toggle, but ``useRailHotkeys`` independently binds the *unshifted*
    ``E``/``e`` key to ``railStore.setMode("erase")`` — and accepts the
    shifted form too (``MODE_KEYS`` lists both ``e`` and ``E``). Both
    listeners are separate ``document`` keydown handlers, so a single
    ``Shift+E`` keypress fires both: whichever attaches first wins the
    logical race, and observed behavior is a net no-op (viewport toggles to
    "erase" then immediately back to "select" once the rail→viewport mode
    sync effect in ``PageImageCanvas`` re-applies "erase" and the rail
    hotkey's own toggle fires second, or vice versa depending on mount
    order). That collision is a separate, pre-existing issue from
    P1-CANVAS-ERASE (this test's onErasePixels wiring) — clicking the Rail's
    ``rail-mode-erase`` card sidesteps it entirely by driving
    ``railStore.setMode("erase")`` through a single code path, which the
    same rail→viewport sync effect then mirrors onto ``viewportStore`` once,
    reliably.
    """
    rail_erase = page.locator('[data-testid="rail-mode-erase"]').first
    rail_erase.wait_for(state="visible", timeout=10_000)
    rail_erase.click()


@pytest.mark.e2e
def test_canvas_erase_drag_reaches_the_backend(canvas_erase_server: CanvasEraseServer, page: Page) -> None:
    """A canvas erase drag actually erases via the API, not just in the UI.

    1. A fresh page has nothing to undo (``history.undo_available`` is
       ``False``) — the baseline the erase must flip.
    2. Enter erase mode via the Rail's mode card (see ``_enter_erase_mode``
       for why not the ``Shift+E`` hotkey) — the mode pill reads "ERASE".
    3. Drag a rectangle over a known page-space area with ``page.mouse``.
    4. The mode pill resets to "VIEW" (PageImageCanvas resets to "select" on
       a completed erase drag) — the UI reacted.
    5. The backend actually recorded the erase: polling the page payload,
       ``history.undo_available`` becomes ``True`` — a new provenance
       version was persisted by ``_erase_pixels_on_page_image`` /
       ``_save_to_store_best_effort``. This is the assertion that matters:
       step 4 alone is exactly what the pre-fix no-op also produced (the
       mode pill still reset even though ``onErasePixels`` was undefined).
    """
    pre_payload = _api_page(canvas_erase_server)
    assert pre_payload["history"]["undo_available"] is False, (
        f"fixture page already has undo history before any edit: {pre_payload['history']}"
    )
    encoded = pre_payload["encoded_dims"]
    assert encoded is not None
    display_width = float(encoded["display_width"])
    scale = float(encoded["scale"])

    page.goto(f"{canvas_erase_server.base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    viewport = page.locator('[data-testid="image-viewport"]').first
    viewport.wait_for(state="visible", timeout=10_000)

    mode_pill = page.locator('[data-testid="canvas-mode-pill"]').first
    expect(mode_pill).to_have_text("VIEW", timeout=10_000)

    # Step 2: enter erase mode.
    _enter_erase_mode(page)
    expect(mode_pill).to_have_text("ERASE", timeout=5_000)

    # Step 3: drag the erase rect.
    _drag_erase_rect(page, _ERASE_LTRB, scale, display_width)

    # Step 4: the UI reacted — mode reset to select after the drag.
    expect(mode_pill).to_have_text("VIEW", timeout=5_000)

    # Step 5: the backend actually recorded the erase.
    deadline = time.monotonic() + 10.0
    post_payload = pre_payload
    while time.monotonic() < deadline:
        post_payload = _api_page(canvas_erase_server)
        if post_payload["history"]["undo_available"] is True:
            break
        time.sleep(0.2)
    assert post_payload["history"]["undo_available"] is True, (
        "canvas erase drag completed in the UI but the backend recorded no "
        f"mutation (history={post_payload['history']}) — P1-CANVAS-ERASE regressed: "
        "onErasePixels is unwired again."
    )

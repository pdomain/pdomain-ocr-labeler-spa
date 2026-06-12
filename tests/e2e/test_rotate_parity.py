"""E2E — rotate feature round-trips (parity-audit C28/C29, slice P2).

C28 found the rotate surface broken in three places:
1. rotate buttons existed only inside the ``display:none`` PageActions stub;
2. rotation metadata never surfaced on the page payload (badge dead);
3. re-OCR after rotate left served words in the pre-rotate coordinate space
   (book-tools internal ``auto_rotate=True`` silently de-rotated the probe).
C29 found auto-rotate-all had no UI trigger at all.

These tests drive the FIXED chain end-to-end in a real Chromium against a
live server with real DocTR:

- The fixture page image carries REAL TEXT stored sideways on disk (the
  upright landscape image rotated 270° clockwise → portrait). Clicking
  Rotate CW (+90°) makes it upright, so the post-rotate re-OCR finds real
  words whose x-extent exceeds the old portrait width — an orientation-
  space proof, not just a "content changed" smoke.
- The event store is pre-seeded with synthetic portrait words so the page
  renders instantly and we can also prove the rotate REPLACED the content.

Rotate is destructive (pixels rotated in place on disk) — every test gets a
function-scoped server (same pattern as ``test_selection_operations_parity
.mut_server``).

Selector note: the legacy testids also exist inside the hidden PageActions
stub wrapper (``data-testid-stub="page-actions-hidden"``), so locators here
always scope with ``:visible``.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
import uvicorn
from pdomain_book_tools.ocr.page import Page as BookPage
from pdomain_book_tools.ocr.rotation import rotate_image
from playwright.sync_api import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    _ingest_ocr_result,
    _register_page_in_project,
)
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings

pytestmark = pytest.mark.e2e

_PROJECT_ID = "rot-fixture"

# Upright (post-rotate) image is LANDSCAPE; on disk it starts sideways
# (portrait). Chosen so the orientation of the word coordinate space is
# unambiguous: portrait width 1200 < landscape word x-extents.
_UPRIGHT_W, _UPRIGHT_H = 1600, 1200

_TEXT_LINES = [
    "The quick brown fox jumps over the lazy dog today",
    "Pack my box with five dozen liquor jugs and bottles",
    "How vexingly quick daft zebras jump over the fence",
]

_DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

# Real OCR runs in these tests; first predictor load can be slow.
_OCR_JOB_TIMEOUT = 180.0


# ─── Fixture image + seed content ────────────────────────────────────────────


def _render_upright_text_png() -> bytes:
    """Render real text into an upright landscape RGB PNG (PIL)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (_UPRIGHT_W, _UPRIGHT_H), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(_DEJAVU), 56) if _DEJAVU.is_file() else ImageFont.load_default()
    for i, line in enumerate(_TEXT_LINES):
        draw.text((60, 180 + i * 140), line, fill="black", font=font)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _sideways_png(upright_png: bytes) -> bytes:
    """Rotate the upright PNG 270° clockwise → portrait sideways-text image.

    ``rotate_image(x, 270)`` then UI Rotate CW (+90°) restores upright
    (270 + 90 = 360).
    """
    data = np.frombuffer(upright_png, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    assert img is not None
    rotated = rotate_image(img, 270)
    ok, buf = cv2.imencode(".png", rotated)
    assert ok
    return buf.tobytes()


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _seed_page_dict(width: int, height: int) -> dict[str, object]:
    """Synthetic seeded page content (portrait coords) with a real items tree."""
    words = [
        {
            "type": "Word",
            "text": f"seeded{i}",
            "ground_truth_text": f"seeded{i}",
            "bounding_box": _bbox(50 + i * 120, 100, 150 + i * 120, 140),
        }
        for i in range(3)
    ]
    return {
        "width": width,
        "height": height,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, width, height),
        "items": [
            {
                "type": "Block",
                "child_type": "BLOCKS",
                "bounding_box": _bbox(40, 80, 600, 160),
                "items": [
                    {
                        "type": "Block",
                        "child_type": "WORDS",
                        "bounding_box": _bbox(40, 80, 600, 160),
                        "items": words,
                    }
                ],
            }
        ],
    }


# ─── Server plumbing ─────────────────────────────────────────────────────────


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


@dataclass
class RotServer:
    base_url: str
    project_url: str
    project_dir: Path


@contextlib.contextmanager
def _rot_server_ctx(
    tmp_path_factory: pytest.TempPathFactory,
    label: str,
    *,
    page0_manual_rotation: bool = False,
) -> Iterator[RotServer]:
    """Live server with the rot-fixture project: one sideways real-text page.

    ``page0_manual_rotation=True`` additionally stamps a durable MANUAL
    rotation on page 0's aggregate (for the auto-rotate-all skip-honor test).
    """
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp(f"{label}-data")
    cache_root = tmp_path_factory.mktemp(f"{label}-cache")
    config_root = tmp_path_factory.mktemp(f"{label}-config")
    source_root = tmp_path_factory.mktemp(f"{label}-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)

    upright_png = _render_upright_text_png()
    sideways_png = _sideways_png(upright_png)
    (dest / "001.png").write_bytes(sideways_png)
    (dest / "pages.json").write_text(json.dumps({"001.png": " ".join(_TEXT_LINES)}))

    # Seed the event store so the page renders without a cold OCR pass.
    # Seeded coords are PORTRAIT (the on-disk sideways dims).
    book_page = BookPage.from_dict(_seed_page_dict(_UPRIGHT_H, _UPRIGHT_W))
    store = LabelerPageStore(dest)
    try:
        agg = _ingest_ocr_result(
            page=book_page,
            image_bytes=sideways_png,
            page_index=0,
            store=store,
        )
        _register_page_in_project(
            store=store,
            project_id=_PROJECT_ID,
            page_id=book_page.page_id,
            page_index=0,
        )
        if page0_manual_rotation:
            agg.rotation_updated(degrees=90, source="manual")
            store.save_page(agg)
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

    project_url = f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1"
    try:
        yield RotServer(base_url=base_url, project_url=project_url, project_dir=dest)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def rot_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RotServer]:
    """Function-scoped: rotate is destructive (pixels rotated in place)."""
    with _rot_server_ctx(tmp_path_factory, "rot") as srv:
        yield srv


@pytest.fixture
def rot_server_manual(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RotServer]:
    """Function-scoped server whose page 0 carries a durable MANUAL rotation."""
    with _rot_server_ctx(tmp_path_factory, "rotman", page0_manual_rotation=True) as srv:
        yield srv


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _goto_project_page(page: Page, project_url: str) -> None:
    page.goto(project_url, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)


def _fetch_page_payload(base_url: str) -> dict:
    r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _word_texts_and_max_extent(payload: dict) -> tuple[list[str], int]:
    """All OCR word texts + the max ``x + width`` over their pixel bboxes."""
    texts: list[str] = []
    max_extent = 0
    for lm in payload.get("line_matches", []):
        for wm in lm.get("word_matches", []):
            if wm.get("ocr_text"):
                texts.append(wm["ocr_text"])
            bbox = wm.get("bbox") or {}
            extent = int(bbox.get("x", 0)) + int(bbox.get("width", 0))
            max_extent = max(max_extent, extent)
    return texts, max_extent


def _png_size(path: Path) -> tuple[int, int]:
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    assert img is not None
    h, w = img.shape[:2]
    return w, h


def _wait_for_job_terminal(base_url: str, job_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        r = httpx.get(f"{base_url}/api/jobs/{job_id}", timeout=10)
        if r.status_code == 200:
            last = r.json()
            if last.get("status") in ("complete", "error", "cancelled"):
                return last
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} not terminal after {timeout}s: {last}")


def _open_overflow(page: Page) -> None:
    page.locator('[data-testid="page-actions-compact-overflow"]:visible').click()
    page.wait_for_selector('[data-testid="page-actions-compact-overflow-menu"]', timeout=5_000)


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_rotate_cw_round_trip_realigns_words_with_rotated_pixels(rot_server: RotServer, page: Page) -> None:
    """C28 links 1+3+4: visible rotate button → pixels + coords + badge all flip.

    Asserts the full effect chain, not testid existence:
    1. rotate buttons VISIBLE + ENABLED in the page-actions overflow;
    2. on-disk image dims transpose (portrait → landscape), durable;
    3. served words are REPLACED by a fresh OCR pass whose bbox coordinate
       space matches the rotated dims — max(x + width) exceeds the old
       portrait width, which is impossible in the pre-rotate space;
    4. payload carries rotation_degrees=90 / rotation_source=manual and the
       rotation badge renders visibly.
    """
    base = rot_server.base_url

    # Pre-rotate state: seeded portrait content.
    pre = _fetch_page_payload(base)
    pre_texts, pre_extent = _word_texts_and_max_extent(pre)
    assert pre_texts, "seeding regression: no seeded words on page 0"
    assert pre["encoded_dims"]["src_width"] == _UPRIGHT_H  # portrait on disk
    assert pre["encoded_dims"]["src_height"] == _UPRIGHT_W
    assert pre_extent <= _UPRIGHT_H, "seeded coords must start in portrait space"

    _goto_project_page(page, rot_server.project_url)

    # 1. Visible + enabled rotate buttons (scoped :visible — the same testids
    #    also exist inside the hidden PageActions stub).
    _open_overflow(page)
    for testid in ("rotate-cw-button", "rotate-ccw-button", "rotate-180-button"):
        btn = page.locator(f'[data-testid="{testid}"]:visible')
        assert btn.count() == 1, f"{testid} not visible in the overflow menu"
        assert btn.is_enabled(), f"{testid} visible but disabled"

    # Click Rotate CW and capture the 202 job id from the network response.
    with page.expect_response(lambda r: r.url.endswith("/pages/0/rotate")) as resp_info:
        page.locator('[data-testid="rotate-cw-button"]:visible').click()
    resp = resp_info.value
    assert resp.status == 202, f"rotate POST returned {resp.status}"
    job_id = resp.json()["job_id"]

    job = _wait_for_job_terminal(base, job_id, _OCR_JOB_TIMEOUT)
    assert job.get("status") == "complete", f"rotate job failed: {job}"

    # 2. Durable pixel rotation on disk.
    assert _png_size(rot_server.project_dir / "001.png") == (_UPRIGHT_W, _UPRIGHT_H)

    # 3+4. Served payload: fresh landscape-space OCR words + rotation metadata.
    post = _fetch_page_payload(base)
    assert post["encoded_dims"]["src_width"] == _UPRIGHT_W
    assert post["encoded_dims"]["src_height"] == _UPRIGHT_H

    post_texts, post_extent = _word_texts_and_max_extent(post)
    assert post_texts != pre_texts, (
        "served words are byte-identical to the seeded pre-rotate content — "
        "the post-rotate re-OCR result was not applied (C28 link 4 regression)"
    )
    assert any("quick" in t.lower() for t in post_texts), (
        f"post-rotate OCR did not read the now-upright text; words={post_texts[:10]}"
    )
    assert post_extent > _UPRIGHT_H, (
        f"word bbox coordinate space did not flip with the orientation: "
        f"max(x+width)={post_extent} <= portrait width {_UPRIGHT_H} — "
        "coords are still in the pre-rotate space (C28 link 4 regression)"
    )

    record = post["page_record"]
    assert record["rotation_degrees"] == 90, record
    assert record["rotation_source"] == "manual", record

    # Badge renders visibly in the UI with the rotation it carries.
    badge = page.locator('[data-testid="rotation-badge"]:visible')
    badge.wait_for(state="visible", timeout=20_000)
    assert "90" in (badge.text_content() or "")
    assert "manual" in (badge.text_content() or "")


def test_auto_rotate_all_ui_trigger_runs_job_and_honors_manual_skip(
    rot_server_manual: RotServer, page: Page
) -> None:
    """C29: auto-rotate-all has a working UI trigger; manual rotations skipped.

    The fixture page carries ``rotation_source="manual"`` so the batch pass
    must SKIP it (overwrite_manual defaults to False) — its on-disk pixels and
    durable metadata must be untouched no matter what detection does.

    KNOWN UPSTREAM LIMITATION (tracked for pdomain-book-tools): the production
    detection path can crash per-page with "incorrect input shape: all pages
    are expected to be multi-channel 2D images" (C29; grayscale/odd-channel
    decode feeding doctr). The job still completes (per-page failures are
    caught). This test therefore asserts the trigger + job lifecycle + skip
    honor — the parts owned by this repo — and only the detection EFFECT is
    conditional: when nothing was rotated we cannot distinguish "skip honored"
    from "detection crashed", both of which leave the page untouched, so the
    invariant asserted (page unchanged) holds either way.
    """
    base = rot_server_manual.base_url

    pre_size = _png_size(rot_server_manual.project_dir / "001.png")
    pre_record = _fetch_page_payload(base)["page_record"]
    assert pre_record["rotation_degrees"] == 90
    assert pre_record["rotation_source"] == "manual"

    _goto_project_page(page, rot_server_manual.project_url)

    # Trigger lives in the page-actions overflow menu.
    _open_overflow(page)
    btn = page.locator('[data-testid="auto-rotate-all-button"]:visible')
    assert btn.count() == 1, "auto-rotate-all-button not visible in the overflow menu"
    assert btn.is_enabled(), "auto-rotate-all-button visible but disabled"

    with page.expect_response(lambda r: r.url.endswith("/auto-rotate-all")) as resp_info:
        btn.click()
    resp = resp_info.value
    assert resp.status == 202, (
        f"auto-rotate-all POST returned {resp.status} (503 = rotation module unavailable): {resp.text()}"
    )
    job_id = resp.json()["job_id"]

    job = _wait_for_job_terminal(base, job_id, _OCR_JOB_TIMEOUT)
    assert job.get("status") == "complete", f"auto-rotate-all job failed: {job}"

    # Manual-skip honor: the manually-rotated page is untouched — pixels,
    # dims, and durable rotation metadata all unchanged.
    assert _png_size(rot_server_manual.project_dir / "001.png") == pre_size, (
        "auto-rotate-all rotated a page with rotation_source='manual' — overwrite_manual=False honor broken"
    )
    post_record = _fetch_page_payload(base)["page_record"]
    assert post_record["rotation_degrees"] == 90, post_record
    assert post_record["rotation_source"] == "manual", post_record

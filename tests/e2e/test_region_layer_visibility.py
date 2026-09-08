"""E2E: a confirmed region and a proposal render as visibly different colors.

The guard against treating model output as data — the split design's own
words. Seeds one confirmed region (a real Block with block_role_labels and a
region_id) and one proposal (via RegionProposalLog) on the same page, loads
it in a real browser, and samples two known screen points.
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
from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_contracts.geometry.bounding_box import BoundingBox
from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
from pdomain_book_tools.ocr.page import Page as BookPage
from PIL import Image
from playwright.sync_api import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal
from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "region-visibility-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600
_CONFIRMED_LTRB = (100, 100, 400, 300)
_PROPOSED_LTRB = (100, 500, 400, 700)


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


def _sample_center(
    page: Page, ltrb: tuple[int, int, int, int], canvas_box: dict, fit_scale: float
) -> tuple[int, int, int]:
    left, top, right, bottom = ltrb
    cx = int(canvas_box["x"] + (left + right) / 2 * fit_scale)
    cy = int(canvas_box["y"] + (top + bottom) / 2 * fit_scale)
    image = Image.open(BytesIO(page.screenshot(full_page=True))).convert("RGB")
    return image.getpixel((cx, cy))


@dataclass
class RegionServer:
    base_url: str


@pytest.fixture(scope="module")
def region_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RegionServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("region-data")
    cache_root = tmp_path_factory.mktemp("region-cache")
    config_root = tmp_path_factory.mktemp("region-config")
    source_root = tmp_path_factory.mktemp("region-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": ""}))

    confirmed_block = Block(
        items=[],
        bounding_box=BoundingBox.from_ltrb(*_CONFIRMED_LTRB, is_normalized=False),
        child_type=BlockChildType.WORDS,
        block_category=BlockCategory.BLOCK,
        block_role_labels=["poetry"],
        additional_block_attributes={"region_id": "confirmed-1"},
    )
    book_page = BookPage(width=_IMAGE_W, height=_IMAGE_H, page_index=0, blocks=[confirmed_block])

    store = LabelerPageStore(dest)
    try:
        _ingest_ocr_result(page=book_page, image_bytes=image_bytes, page_index=0, store=store)
        _register_page_in_project(
            store=store, project_id=_PROJECT_ID, page_id=book_page.page_id, page_index=0
        )

        proposal_log = RegionProposalLog(dest)
        proposal_log.append_run(
            ProposalRun(
                run_id="r1",
                model_id="fixture-detector",
                model_version="0.0.0",
                created_at="2026-09-08T10:00:00+00:00",
                page_facet_digests={},
                depends_on=frozenset(),
                page_kind_decision_ref=None,
                page_kind_was_confirmed=False,
            )
        )
        proposal_log.append_proposals(
            [
                RegionProposal(
                    proposal_id="proposed-1",
                    run_id="r1",
                    page_index=0,
                    role=RegionRole.BLOCKQUOTE,
                    box=_PROPOSED_LTRB,
                    confidence=0.6,
                    evidence={"signal": "indent"},
                )
            ]
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

    yield RegionServer(base_url=base_url)

    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.e2e
def test_a_proposed_region_renders_a_different_color_than_a_confirmed_one(
    region_server: RegionServer,
    page: Page,
) -> None:
    resp = httpx.get(f"{region_server.base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10.0)
    assert resp.status_code == 200, f"page payload GET failed: {resp.status_code}"
    payload = resp.json()
    encoded = payload["encoded_dims"]
    assert encoded is not None
    regions = payload["regions"]
    assert any(r["confirmed"] and r["region_id"] == "confirmed-1" for r in regions)
    assert any(not r["confirmed"] and r["proposal_id"] == "proposed-1" for r in regions)

    page.goto(f"{region_server.base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    viewport = page.locator('[data-testid="image-viewport"]').first
    viewport.wait_for(state="visible", timeout=10_000)
    stage_canvas = viewport.locator("canvas").first
    stage_canvas.wait_for(state="visible", timeout=10_000)
    canvas_box = stage_canvas.bounding_box()
    assert canvas_box is not None
    fit_scale = canvas_box["width"] / encoded["display_width"]

    confirmed_pixel = _sample_center(page, _CONFIRMED_LTRB, canvas_box, fit_scale)
    proposed_pixel = _sample_center(page, _PROPOSED_LTRB, canvas_box, fit_scale)
    white = (255, 255, 255)

    assert confirmed_pixel != white, f"confirmed region did not paint: {confirmed_pixel}"
    assert proposed_pixel != white, f"proposed region did not paint: {proposed_pixel}"
    assert confirmed_pixel != proposed_pixel, (
        f"confirmed and proposed regions rendered the same color: {confirmed_pixel} == {proposed_pixel} "
        "— they must be visibly distinct or model output risks being treated as data"
    )

"""E2E: the book-wide review queue Drawer panel (driver-contract §2.18).

Slice 8's queue panel, confidence order and cross-page click-to-navigate in
one pass: opening the Drawer's "Queue" tab lists every undecided region
proposal in the book; switching to confidence order re-lists them lowest
confidence first; clicking an item on another page navigates there and
selects that proposal, same as `]`/`[` do. Follows the self-contained
fixture-server pattern in `test_review_queue_navigation.py` (read first),
duplicated here per that file's own established convention.

Seeds a two-page project: page 0 carries a high-confidence proposal, page 1
carries a lower-confidence one — so confidence order puts page 1's proposal
first, ahead of page 0's, the reverse of reading order.

Plan: docs/plans/2026-09-17-region-review-surface.md — Task 5.
Spec: docs/specs/2026-09-17-book-review-queue-design.md.
"""

from __future__ import annotations

import json
import re
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
from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal
from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "review-queue-panel-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600
_PAGE_COUNT = 2

# Well inside the page image, away from the bottom-left neutral-click corner
# (see test_review_queue_navigation.py's `_aim_rail_at_region`).
_PROPOSAL_LTRB = (600, 700, 900, 900)
_PAGE0_PROPOSAL_ID = "proposal-page0-high-confidence"
_PAGE1_PROPOSAL_ID = "proposal-page1-low-confidence"
_PAGE0_ROLE = RegionRole.TABLE
_PAGE1_ROLE = RegionRole.FORMULA
_PAGE0_CONFIDENCE = 0.9
_PAGE1_CONFIDENCE = 0.2
_RUN_ID = "r1"


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


@dataclass
class ReviewQueuePanelServer:
    base_url: str
    project_root: Path


@pytest.fixture(scope="module")
def review_queue_panel_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ReviewQueuePanelServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("review-queue-panel-data")
    cache_root = tmp_path_factory.mktemp("review-queue-panel-cache")
    config_root = tmp_path_factory.mktemp("review-queue-panel-config")
    source_root = tmp_path_factory.mktemp("review-queue-panel-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    image_names = [f"{i + 1:03d}.png" for i in range(_PAGE_COUNT)]
    for name in image_names:
        (dest / name).write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps(dict.fromkeys(image_names, "")))

    store = LabelerPageStore(dest)
    try:
        book_pages = [
            BookPage(width=_IMAGE_W, height=_IMAGE_H, page_index=i, blocks=[]) for i in range(_PAGE_COUNT)
        ]
        for page_index, book_page in enumerate(book_pages):
            _ingest_ocr_result(page=book_page, image_bytes=image_bytes, page_index=page_index, store=store)
            _register_page_in_project(
                store=store, project_id=_PROJECT_ID, page_id=book_page.page_id, page_index=page_index
            )

        proposal_log = RegionProposalLog(dest)
        proposal_log.append_run(
            ProposalRun(
                run_id=_RUN_ID,
                model_id="fixture-detector",
                model_version="0.0.0",
                created_at="2026-09-17T10:00:00+00:00",
                page_facet_digests={},
                depends_on=frozenset(),
                page_kind_decision_ref=None,
                page_kind_was_confirmed=False,
            )
        )
        # Page 0's proposal is high confidence; page 1's is lower — so
        # confidence order lists page 1 first, reading order lists page 0
        # first. Distinct roles let RegionDetail's role text identify which
        # one is selected after a click.
        proposal_log.append_proposals(
            [
                RegionProposal(
                    proposal_id=_PAGE0_PROPOSAL_ID,
                    run_id=_RUN_ID,
                    page_index=0,
                    role=_PAGE0_ROLE,
                    box=_PROPOSAL_LTRB,
                    confidence=_PAGE0_CONFIDENCE,
                    evidence={"signal": "table-rule"},
                ),
                RegionProposal(
                    proposal_id=_PAGE1_PROPOSAL_ID,
                    run_id=_RUN_ID,
                    page_index=1,
                    role=_PAGE1_ROLE,
                    box=_PROPOSAL_LTRB,
                    confidence=_PAGE1_CONFIDENCE,
                    evidence={"signal": "formula-layout"},
                ),
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

    yield ReviewQueuePanelServer(base_url=base_url, project_root=dest)

    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.e2e
def test_confidence_order_click_navigates_and_selects(
    review_queue_panel_server: ReviewQueuePanelServer,
    page: Page,
) -> None:
    """Confidence order lists the lower-confidence item first; clicking it jumps to its page.

    1. Open page 0 (its own proposal is the higher-confidence one).
    2. Open the Drawer's Queue tab.
    3. Switch to confidence order — page 1's lower-confidence proposal now
       sorts first, ahead of page 0's.
    4. Click page 1's item: the page navigates to page 2 (pageno/2), and
       RegionDetail shows page 1's role — the item was both navigated to
       and selected, matching what `]` does (test_review_queue_navigation.py).
    """
    base_url = review_queue_panel_server.base_url

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    # Step 2: open the Queue tab.
    page.click('[data-testid="drawer-tab-queue"]')
    page.wait_for_selector('[data-testid="review-queue-panel"]', timeout=10_000)

    page1_item = page.locator(f'[data-testid="review-queue-item-1-{_PAGE1_PROPOSAL_ID}"]')
    page1_item.wait_for(state="visible", timeout=10_000)

    # Step 3: switch to confidence order.
    page.click('[data-testid="review-queue-order-confidence"]')
    expect(page.locator('[data-testid="review-queue-order-confidence"]')).to_have_attribute(
        "aria-pressed", "true", timeout=5_000
    )

    # The list re-fetched under confidence order: page 1's item (lower
    # confidence) is still present and is now the first row.
    page1_item = page.locator(f'[data-testid="review-queue-item-1-{_PAGE1_PROPOSAL_ID}"]')
    page1_item.wait_for(state="visible", timeout=10_000)
    first_row = page.locator('[data-testid="review-queue-list"] li').first
    expect(first_row.locator(f'[data-testid="review-queue-item-1-{_PAGE1_PROPOSAL_ID}"]')).to_have_count(1)

    # Step 4: click page 1's item — navigates to page 2 and selects its role.
    page1_item.click()
    expect(page).to_have_url(re.compile(r"/pages/pageno/2$"), timeout=10_000)
    role_locator = page.locator('[data-testid="region-detail-role"]')
    expect(role_locator).to_contain_text(_PAGE1_ROLE.value, timeout=10_000)

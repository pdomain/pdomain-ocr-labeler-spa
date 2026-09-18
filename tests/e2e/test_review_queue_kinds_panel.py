"""E2E: the per-kind book review queue (rail badge, kind selector, `[`/`]`).

Spec: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-review-
next.md "How the SPA uses the new route".

Follows the self-contained fixture-server pattern in
`test_review_queue_navigation.py` (read first), duplicated here per that
file's own established convention.

This fixture never proposes or confirms any page's kind — the same choice
`test_review_queue_navigation.py` makes — so `page_kind` is outstanding for
every page and never blocked, making it the book's "next kind" by the
design's rule (first kind, in list order, with outstanding work and no
`blocked_by`). One region proposal is seeded directly (no page-kind run), so
`region` is also outstanding but `blocked_by: "page_kind"`: this book can
produce two kinds of outstanding work at once without materializing real
words or typography corrections, which is the honesty this test exercises —
a blocked kind must say what it is waiting for, not look finished, and the
default kind must be the first *unblocked* one, not simply the first kind in
list order.

Word and typography are not driven through the browser here: producing
non-zero, non-lower-bound outstanding work for them means saving real page
content (`save_page_content_to_store`), which this fixture-server pattern
does not do. Their unavailable/lower-bound/blocked presentations are covered
at the vitest level instead (`ReviewQueuePanel.test.tsx`,
`useRegionReviewHotkeys.test.tsx`, `Rail.test.tsx`, `useBookReviewQueue.test.tsx`).
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

_PROJECT_ID = "review-queue-kinds-panel-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600
_PAGE_COUNT = 3

_PROPOSAL_LTRB = (600, 700, 900, 900)
_REGION_PROPOSAL_ID = "proposal-page1"
_REGION_ROLE = RegionRole.TABLE
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
class ReviewQueueKindsServer:
    base_url: str
    project_root: Path


@pytest.fixture(scope="module")
def review_queue_kinds_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ReviewQueueKindsServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("review-queue-kinds-data")
    cache_root = tmp_path_factory.mktemp("review-queue-kinds-cache")
    config_root = tmp_path_factory.mktemp("review-queue-kinds-config")
    source_root = tmp_path_factory.mktemp("review-queue-kinds-source")

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

        # No page-kind proposal or confirmation for any page — page_kind is
        # outstanding for all three and never blocked, so it is the book's
        # "next kind". One region proposal, seeded directly with no
        # page-kind run behind it, makes region outstanding too but blocked
        # by page_kind (backend rule: blocked only when no page anywhere in
        # the book carries any kind state at all).
        proposal_log = RegionProposalLog(dest)
        proposal_log.append_run(
            ProposalRun(
                run_id=_RUN_ID,
                model_id="fixture-detector",
                model_version="0.0.0",
                created_at="2026-09-18T10:00:00+00:00",
                page_facet_digests={},
                depends_on=frozenset(),
                page_kind_decision_ref=None,
                page_kind_was_confirmed=False,
            )
        )
        proposal_log.append_proposals(
            [
                RegionProposal(
                    proposal_id=_REGION_PROPOSAL_ID,
                    run_id=_RUN_ID,
                    page_index=1,
                    role=_REGION_ROLE,
                    box=_PROPOSAL_LTRB,
                    confidence=0.85,
                    evidence={"signal": "table-rule"},
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

    yield ReviewQueueKindsServer(base_url=base_url, project_root=dest)

    server.should_exit = True
    thread.join(timeout=5)


def _open_queue_tab(page: Page) -> None:
    drawer = page.locator('[data-testid="drawer"]')
    if drawer.get_attribute("data-open") != "true":
        page.locator('[data-testid="drawer-expand-btn"]').click()
        expect(drawer).to_have_attribute("data-open", "true", timeout=5_000)
    page.locator('[data-testid="drawer-tab-queue"]').click()


@pytest.mark.e2e
def test_rail_badge_selector_and_bracket_keys_follow_the_next_kind(
    review_queue_kinds_server: ReviewQueueKindsServer,
    page: Page,
) -> None:
    """The book's next kind (page_kind), honest blocked state (region), and
    `[`/`]` following the selected kind, all in one pass.

    1. Load page 3 (index 2). The rail's "next kind" badge names page_kind
       with a count of 3 — the first kind with outstanding, unblocked work.
    2. Open the Queue drawer tab: the kind selector defaults to page_kind,
       showing "3 of 3 outstanding" and a button to start at page 1.
    3. Switch the selector to region: it shows region's own seeded proposal
       in the unchanged item list below a banner naming what it is waiting
       for (page_kind) — a blocked kind must not look finished.
    4. Switch back to page_kind and click "Start at page 1": the SPA
       navigates there.
    5. Navigate (in-app, so the Queue drawer's explicit kind selection
       survives — the SPA never unmounts) back to page 3 and press `]`: it
       still lands on page 1, honoring the selected kind rather than
       requiring the rail's region target, which `]` was never aimed at in
       this test. Bracket-key following is opt-in: only once a person has
       explicitly picked a kind in the Queue drawer, exactly what step 3-4
       did. A fresh page load with no explicit pick falls back to the
       original, rail-target-gated region behavior instead — unaffected by
       this test, and covered by test_review_queue_navigation.py.
    """
    base_url = review_queue_kinds_server.base_url

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/3", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    # Step 1.
    rail_badge = page.locator('[data-testid="rail-queue-next"]')
    expect(rail_badge).to_be_visible(timeout=10_000)
    expect(rail_badge).to_contain_text("Page kind")
    expect(rail_badge).to_contain_text("3")

    # Step 2.
    _open_queue_tab(page)
    page_kind_button = page.locator('[data-testid="review-queue-kind-select-page_kind"]')
    expect(page_kind_button).to_have_attribute("aria-pressed", "true", timeout=10_000)
    count = page.locator('[data-testid="review-queue-kind-count"]')
    expect(count).to_contain_text("3 of 3 outstanding")
    start_button = page.locator('[data-testid="review-queue-kind-start"]')
    expect(start_button).to_contain_text("Start at page 1")

    # Step 3.
    page.locator('[data-testid="review-queue-kind-select-region"]').click()
    blocked = page.locator('[data-testid="review-queue-kind-blocked"]')
    expect(blocked).to_contain_text("Page kind")
    expect(page.locator(f'[data-testid="review-queue-item-1-{_REGION_PROPOSAL_ID}"]')).to_be_visible()

    # Step 4.
    page.locator('[data-testid="review-queue-kind-select-page_kind"]').click()
    page.locator('[data-testid="review-queue-kind-start"]').click()
    expect(page).to_have_url(re.compile(r"/pages/pageno/1$"), timeout=10_000)

    # Step 5. In-app navigation (the real Next-page button, not page.goto)
    # keeps the SPA mounted, so the explicit reviewQueueKind: "page_kind"
    # pick from steps 3-4 survives the trip back to page 3.
    next_button = page.locator('[data-testid="nav-next-button"]:not([data-testid-stub])')
    next_button.click()
    expect(page).to_have_url(re.compile(r"/pages/pageno/2$"), timeout=10_000)
    next_button.click()
    expect(page).to_have_url(re.compile(r"/pages/pageno/3$"), timeout=10_000)
    page.keyboard.press("BracketRight")
    expect(page).to_have_url(re.compile(r"/pages/pageno/1$"), timeout=10_000)

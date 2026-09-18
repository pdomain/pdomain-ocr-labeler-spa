"""E2E: the book review queue's `[`/`]` page navigation and rail badge.

Slice 8's cross-page review queue in one pass: with the rail aimed at
`region` (key `5`), `]`/`[` jump between pages that still have undecided
region proposals — skipping pages with none — and select the first (or
last) proposal on arrival. A decision that empties a page's proposals
reports how many are left in the book; running out of pages to jump to
reports that instead of navigating. The rail's one review-queue badge
(`rail-queue-next`) names the book's first kind with outstanding, unblocked
work and its count throughout. Each step is checked against the live API,
not only the DOM, following the pattern in `test_region_review_loop.py`.

Seeds a three-page project: page 0 and page 2 each carry one undecided
proposal (distinct roles, so `RegionDetail`'s role text identifies which one
is selected); page 1 carries none, so it must be skipped by both keys. Every
page's kind is confirmed too (pdomain-ocr-synth's docs/specs/2026-09-18-
one-answer-to-what-to-review-next.md "How the SPA uses the new route"):
`region` is blocked_by page_kind whenever no page anywhere carries kind
state, and the rail badge and `]`/`[` both follow `firstActionableKind` (the
first kind, in list order, with outstanding work and no `blocked_by`) — so
without this, `page_kind` (outstanding on every unconfirmed page) would be
the book's first kind with work, not `region`, and this file's actual
subject — region bracket-key stepping — would never run. Confirming every
page's kind makes `region` genuinely first, the state a book in active
region review is actually in.

Follows the self-contained fixture-server pattern in
`test_region_review_loop.py`, duplicated here rather than imported per that
file's own established convention.

Plan: docs/plans/2026-09-17-region-review-surface.md — Task 5.
Spec: docs/specs/2026-09-17-book-review-queue-design.md.
Spec: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-
  review-next.md.
"""

from __future__ import annotations

import json
import re
import socket
import struct
import threading
import time
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import uvicorn
from pdomain_book_contracts.annotation import PageKind, RegionRole
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal
from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "review-queue-navigation-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600
_PAGE_COUNT = 3

# One proposal each on page 0 and page 2; page 1 carries none and must be
# skipped by both `]` and `[`. Well inside the page image and away from the
# bottom-left corner the test clicks as a neutral, unfocusing spot.
_PROPOSAL_LTRB = (600, 700, 900, 900)
_PAGE0_PROPOSAL_ID = "proposal-page0"
_PAGE2_PROPOSAL_ID = "proposal-page2"
_PAGE0_ROLE = RegionRole.TABLE
_PAGE2_ROLE = RegionRole.FORMULA
_RUN_ID = "r1"

_POLL_TIMEOUT = 20.0
_POLL_INTERVAL = 0.2

_NO_PROPOSALS_ON_PAGE_MESSAGE = "No undecided proposals left on this page"
_NO_NEXT_PAGE_MESSAGE = "No more pages with undecided proposals after this page."


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


def _page_regions(base_url: str, page_index: int) -> list[dict[str, object]]:
    resp = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/{page_index}", timeout=10.0)
    assert resp.status_code == 200, f"page {page_index} payload GET failed: {resp.status_code} {resp.text}"
    regions = resp.json()["regions"]
    assert isinstance(regions, list)
    return regions


def _poll_until(description: str, check: Callable[[], bool], *, timeout: float = _POLL_TIMEOUT) -> None:
    """Poll ``check`` on a bounded interval until it returns True, or raise.

    Never a bare ``time.sleep``: the failure message names what was being
    waited for, so a timeout here reads as a specific, actionable failure
    rather than looking like any other assertion.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(_POLL_INTERVAL)
    raise AssertionError(f"Timed out after {timeout}s waiting for: {description}")


@dataclass
class ReviewQueueServer:
    base_url: str
    project_root: Path


@pytest.fixture(scope="module")
def review_queue_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ReviewQueueServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("review-queue-data")
    cache_root = tmp_path_factory.mktemp("review-queue-cache")
    config_root = tmp_path_factory.mktemp("review-queue-config")
    source_root = tmp_path_factory.mktemp("review-queue-source")

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

        # Every page's kind confirmed — see the module docstring for why:
        # without this, page_kind (not region) would be the book's first
        # kind with outstanding work, and this file's bracket-key/badge
        # coverage would be exercising page_kind instead of region.
        reviewed_store = PageKindReviewedStore(dest)
        for page_index in range(_PAGE_COUNT):
            reviewed_store.mark_reviewed(
                page_index, "2026-09-18T09:00:00+00:00", kind=PageKind.BODY, method="single"
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
        # Page 0 and page 2 each get one undecided proposal; page 1 gets
        # none, so the bracket keys must skip over it.
        proposal_log.append_proposals(
            [
                RegionProposal(
                    proposal_id=_PAGE0_PROPOSAL_ID,
                    run_id=_RUN_ID,
                    page_index=0,
                    role=_PAGE0_ROLE,
                    box=_PROPOSAL_LTRB,
                    confidence=0.9,
                    evidence={"signal": "table-rule"},
                ),
                RegionProposal(
                    proposal_id=_PAGE2_PROPOSAL_ID,
                    run_id=_RUN_ID,
                    page_index=2,
                    role=_PAGE2_ROLE,
                    box=_PROPOSAL_LTRB,
                    confidence=0.8,
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

    yield ReviewQueueServer(base_url=base_url, project_root=dest)

    server.should_exit = True
    thread.join(timeout=5)


def _assert_seed_state(base_url: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """One undecided proposal on page 0 and on page 2; none on page 1."""
    page0_regions = _page_regions(base_url, 0)
    assert len(page0_regions) == 1 and not page0_regions[0]["confirmed"]
    assert page0_regions[0]["proposal_id"] == _PAGE0_PROPOSAL_ID
    assert _page_regions(base_url, 1) == []
    page2_regions = _page_regions(base_url, 2)
    assert len(page2_regions) == 1 and not page2_regions[0]["confirmed"]
    assert page2_regions[0]["proposal_id"] == _PAGE2_PROPOSAL_ID
    return page0_regions, page2_regions


def _aim_rail_at_region(page: Page) -> None:
    """Neutral-click the canvas, then press 5 to aim the rail at the region target.

    The click puts focus somewhere that is definitely not a form field
    before the first hotkey — the canvas's bottom-left corner, clear of the
    proposal box (x 600-900) and of the fixed "canvas-mode-pill" indicator
    (see test_region_review_loop.py's neutral-click comment for why a plain
    ``Locator.click()`` is not used here).
    """
    viewport = page.locator('[data-testid="image-viewport"]').first
    viewport.wait_for(state="visible", timeout=10_000)
    stage_canvas = viewport.locator("canvas").first
    stage_canvas.wait_for(state="visible", timeout=10_000)
    canvas_box = stage_canvas.bounding_box()
    assert canvas_box is not None
    page.mouse.click(canvas_box["x"] + 10, canvas_box["y"] + canvas_box["height"] - 10)
    page.keyboard.press("5")
    region_target = page.locator('[data-testid="rail-target-region"]')
    expect(region_target).to_have_attribute("data-active", "true", timeout=5_000)


def _page_fully_decided(base_url: str, page_index: int) -> bool:
    regions = _page_regions(base_url, page_index)
    confirmed = [r for r in regions if r["confirmed"]]
    unconfirmed = [r for r in regions if not r["confirmed"]]
    return len(confirmed) == 1 and len(unconfirmed) == 0


@pytest.mark.e2e
def test_bracket_keys_navigate_pages_with_undecided_proposals(
    review_queue_server: ReviewQueueServer,
    page: Page,
) -> None:
    """`]`/`[` skip the empty middle page; the badge and end-of-page toast track the book.

    1. Open page 0, press 5 to aim the rail at the region target, and check
       the rail badge names "Region" (the book's first kind with
       outstanding, unblocked work, every page's kind being confirmed) with
       a count of 2 undecided proposals.
    2. Press `]`: it lands on page 2 (skipping empty page 1) with that
       page's proposal selected.
    3. Press Enter to accept it: the API settles at one confirmed region and
       no proposal left on page 2, the toast reports 1 left in the book, and
       the badge settles at 1.
    4. Press `]` again: no later page has work, so a toast says so and the
       page does not move.
    5. Press `[`: it lands back on page 0, with its proposal selected.
    """
    base_url = review_queue_server.base_url
    page0_regions, page2_regions = _assert_seed_state(base_url)

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    # Step 1. One badge now (pdomain-ocr-synth's docs/specs/2026-09-18-one-
    # answer-to-what-to-review-next.md): it names the kind, not only the
    # count, so both are asserted rather than an exact text match.
    _aim_rail_at_region(page)
    badge = page.locator('[data-testid="rail-queue-next"]')
    expect(badge).to_contain_text("Region", timeout=10_000)
    expect(badge).to_contain_text("2", timeout=10_000)
    role_locator = page.locator('[data-testid="region-detail-role"]')

    # Step 2: `]` jumps over the empty page 1 straight to page 2, selecting
    # its (only) proposal.
    page.keyboard.press("BracketRight")
    expect(page).to_have_url(re.compile(r"/pages/pageno/3$"), timeout=10_000)
    expect(role_locator).to_contain_text(_PAGE2_ROLE.value, timeout=10_000)

    # Nothing changed on the server from a pure navigation + selection.
    assert _page_regions(base_url, 0) == page0_regions
    assert _page_regions(base_url, 2) == page2_regions

    # Step 3: Enter accepts page 2's selected proposal. Poll the API until
    # it settles at one confirmed region and no proposal left on page 2.
    page.keyboard.press("Enter")
    _poll_until(
        "page 2's proposal accepted and confirmed",
        lambda: _page_fully_decided(base_url, 2),
    )

    # Accepting page 2's only proposal empties the page: the toast reports
    # how many are left in the book (page 0's one proposal), and the rail
    # badge settles at the same count.
    end_of_page_toast = page.locator(
        "[data-sonner-toast]",
        has_text=f"{_NO_PROPOSALS_ON_PAGE_MESSAGE}. 1 left in the book; press ] for the next.",
    )
    expect(end_of_page_toast).to_be_visible(timeout=5_000)
    expect(badge).to_contain_text("Region", timeout=10_000)
    expect(badge).to_contain_text("1", timeout=10_000)

    # Step 4: `]` again — no later page has undecided work, so a toast says
    # so and the page does not move.
    url_before_second_bracket = page.url
    page.keyboard.press("BracketRight")
    no_next_page_toast = page.locator("[data-sonner-toast]", has_text=_NO_NEXT_PAGE_MESSAGE)
    expect(no_next_page_toast).to_be_visible(timeout=5_000)
    assert page.url == url_before_second_bracket, "no next page with work: the page must not navigate"

    # Step 5: `[` walks back to page 0, the only page with work left, and
    # selects its proposal.
    page.keyboard.press("BracketLeft")
    expect(page).to_have_url(re.compile(r"/pages/pageno/1$"), timeout=10_000)
    expect(role_locator).to_contain_text(_PAGE0_ROLE.value, timeout=10_000)

    # Page 0's proposal is still untouched by any of this.
    assert _page_regions(base_url, 0) == page0_regions

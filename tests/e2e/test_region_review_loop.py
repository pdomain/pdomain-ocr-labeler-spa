"""E2E: review two region proposals from the keyboard, top to bottom.

Slice 3's whole review loop in one pass: press ``5`` to aim the rail at
``region``, ``n`` to select the topmost undecided proposal, ``enter`` to
accept it, and ``x`` to reject the one auto-advance leaves selected. Each
step is checked against the live API rather than only the DOM, so a
decision that shows in the browser but never reaches the server — or vice
versa — fails the test.

Seeds two proposals and no confirmed regions on one page, one clearly above
the other, following the self-contained fixture-server pattern in
``test_region_layer_visibility.py`` and ``test_image_click_selection.py``.

Plan: docs/plans/2026-09-17-region-review-surface.md — Task 7.
Spec: docs/specs/2026-09-17-region-review-surface-design.md.
"""

from __future__ import annotations

import json
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
from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog
from pdomain_ocr_labeler_spa.core.regions.models import Disposition, ProposalRun, RegionProposal
from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "region-review-loop-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# Two proposals, one clearly above the other, both well inside the page
# image. Their x-range (600-900) sits away from the bottom-left corner the
# test clicks as a neutral, unfocusing spot before the first hotkey.
_TOP_LTRB = (600, 700, 900, 900)
_BOTTOM_LTRB = (600, 1100, 900, 1300)
_TOP_PROPOSAL_ID = "proposal-top"
_BOTTOM_PROPOSAL_ID = "proposal-bottom"
_TOP_ROLE = RegionRole.BLOCKQUOTE
_BOTTOM_ROLE = RegionRole.CAPTION
_RUN_ID = "r1"

_POLL_TIMEOUT = 20.0
_POLL_INTERVAL = 0.2


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


def _page_regions(base_url: str) -> list[dict[str, object]]:
    resp = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10.0)
    assert resp.status_code == 200, f"page payload GET failed: {resp.status_code} {resp.text}"
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
class RegionReviewServer:
    base_url: str
    project_root: Path


@pytest.fixture(scope="module")
def region_review_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RegionReviewServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("region-review-data")
    cache_root = tmp_path_factory.mktemp("region-review-cache")
    config_root = tmp_path_factory.mktemp("region-review-config")
    source_root = tmp_path_factory.mktemp("region-review-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": ""}))

    book_page = BookPage(width=_IMAGE_W, height=_IMAGE_H, page_index=0, blocks=[])

    store = LabelerPageStore(dest)
    try:
        _ingest_ocr_result(page=book_page, image_bytes=image_bytes, page_index=0, store=store)
        _register_page_in_project(
            store=store, project_id=_PROJECT_ID, page_id=book_page.page_id, page_index=0
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
        proposal_log.append_proposals(
            [
                RegionProposal(
                    proposal_id=_TOP_PROPOSAL_ID,
                    run_id=_RUN_ID,
                    page_index=0,
                    role=_TOP_ROLE,
                    box=_TOP_LTRB,
                    confidence=0.9,
                    evidence={"signal": "running-head"},
                ),
                RegionProposal(
                    proposal_id=_BOTTOM_PROPOSAL_ID,
                    run_id=_RUN_ID,
                    page_index=0,
                    role=_BOTTOM_ROLE,
                    box=_BOTTOM_LTRB,
                    confidence=0.7,
                    evidence={"signal": "indent"},
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

    yield RegionReviewServer(base_url=base_url, project_root=dest)

    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.e2e
def test_review_two_proposals_from_the_keyboard(
    region_review_server: RegionReviewServer,
    page: Page,
) -> None:
    """Step through both proposals with n / enter / x, checked against the API.

    1. Open the page, press 5 to aim the rail at the region target.
    2. Press n: nothing on the server has changed yet, and the right panel
       shows the topmost proposal's role.
    3. Press enter: the API settles at exactly one confirmed region and one
       still-undecided proposal, and the panel auto-advances to it.
    4. Press x: the API settles at exactly one confirmed region and no
       proposal left, and the decision journal records the rejection.
    """
    base_url = region_review_server.base_url

    # Seed sanity: two undecided proposals, nothing confirmed yet.
    initial_regions = _page_regions(base_url)
    assert len(initial_regions) == 2, f"expected 2 seeded regions, got {initial_regions}"
    assert all(not r["confirmed"] for r in initial_regions)
    seeded_proposal_ids = {r["proposal_id"] for r in initial_regions}
    assert seeded_proposal_ids == {_TOP_PROPOSAL_ID, _BOTTOM_PROPOSAL_ID}

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    # Step 1: put focus somewhere that is definitely not a form field before
    # the first hotkey. Click the canvas's bottom-left corner — clear of
    # both proposal boxes (x 600-900) and of the fixed "canvas-mode-pill"
    # indicator pinned at top-10 left-2 (see test_region_layer_visibility.py's
    # _CONFIRMED_LTRB comment) — then press 5 to aim the rail at "region".
    viewport = page.locator('[data-testid="image-viewport"]').first
    viewport.wait_for(state="visible", timeout=10_000)
    stage_canvas = viewport.locator("canvas").first
    stage_canvas.wait_for(state="visible", timeout=10_000)
    canvas_box = stage_canvas.bounding_box()
    assert canvas_box is not None
    # A plain Locator.click() runs Playwright's actionability checks, which
    # time out here: some other element (e.g. a Konva overlay layer's own
    # canvas) stacks above the stage canvas and "intercepts pointer events"
    # even though nothing about it should consume this neutral click.
    # test_image_click_selection.py's real bbox click uses the same
    # page.mouse.click(x, y) escape hatch for the same reason.
    page.mouse.click(canvas_box["x"] + 10, canvas_box["y"] + canvas_box["height"] - 10)

    page.keyboard.press("5")
    region_target = page.locator('[data-testid="rail-target-region"]')
    expect(region_target).to_have_attribute("data-active", "true", timeout=5_000)

    # Step 2: n selects the topmost undecided proposal. Nothing on the
    # server changes from a pure selection key.
    page.keyboard.press("n")
    role_locator = page.locator('[data-testid="region-detail-role"]')
    expect(role_locator).to_contain_text(_TOP_ROLE.value, timeout=5_000)
    unchanged_regions = _page_regions(base_url)
    assert unchanged_regions == initial_regions, (
        "pressing n must not change server state, only selection: "
        f"before={initial_regions}, after={unchanged_regions}"
    )

    # Step 3: enter accepts the selected (topmost) proposal. Poll the API
    # until it settles at one confirmed region and one still-undecided
    # proposal — the bottom one, left untouched.
    page.keyboard.press("Enter")

    def _one_confirmed_one_unconfirmed() -> bool:
        regions = _page_regions(base_url)
        confirmed = [r for r in regions if r["confirmed"]]
        unconfirmed = [r for r in regions if not r["confirmed"]]
        return len(confirmed) == 1 and len(unconfirmed) == 1

    _poll_until(
        "exactly one confirmed region and one unconfirmed proposal after accept",
        _one_confirmed_one_unconfirmed,
    )
    after_accept = _page_regions(base_url)
    remaining_proposal_ids = {r["proposal_id"] for r in after_accept if not r["confirmed"]}
    assert remaining_proposal_ids == {_BOTTOM_PROPOSAL_ID}, (
        f"expected only the bottom proposal left undecided after accepting the top one, got {after_accept}"
    )

    # Auto-advance should have moved the selection to the bottom proposal,
    # the only one left undecided.
    expect(role_locator).to_contain_text(_BOTTOM_ROLE.value, timeout=5_000)

    # Step 4: x rejects the now-selected (bottom) proposal. Poll the API
    # until it settles at one confirmed region and no proposal left.
    page.keyboard.press("x")

    def _one_confirmed_none_unconfirmed() -> bool:
        regions = _page_regions(base_url)
        confirmed = [r for r in regions if r["confirmed"]]
        unconfirmed = [r for r in regions if not r["confirmed"]]
        return len(confirmed) == 1 and len(unconfirmed) == 0

    _poll_until(
        "exactly one confirmed region and no unconfirmed proposal after reject",
        _one_confirmed_none_unconfirmed,
    )

    # No undecided proposals are left on the page; the review hook should
    # have cleared the selection and shown its toast.
    no_proposals_toast = page.locator(
        "[data-sonner-toast]", has_text="No undecided proposals left on this page"
    )
    expect(no_proposals_toast).to_be_visible(timeout=5_000)

    # The rejection must be a recorded fact, not just an absence from
    # page.regions — read the decision journal the fixture wrote to.
    decision_log = RegionDecisionLog(region_review_server.project_root)
    decision = decision_log.decision_for(_BOTTOM_PROPOSAL_ID, run_id=_RUN_ID)
    assert decision is not None, f"no decision recorded for {_BOTTOM_PROPOSAL_ID!r} in {decision_log.path}"
    assert decision.disposition is Disposition.REJECTED, (
        f"expected the bottom proposal's decision to be rejected, got {decision.disposition!r}"
    )

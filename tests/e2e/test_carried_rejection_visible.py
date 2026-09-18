"""E2E: reject a proposal, re-run region detection, see the suppression, undo it.

Drives the real gap this closes end to end: a person rejects a proposal, a
re-run carries that rejection forward onto a newly detected, overlapping
proposal rather than asking again — and until this change, nothing in the
product showed that suppression or let a person reverse it
(docs/context/current-state.md, region carry-forward's "Open" note).

1. Reject a seeded proposal from the keyboard (``5``, ``n``, ``x``).
2. Start a real "Propose regions" run through the page-actions overflow menu,
   with the book's region detector swapped for a fixture stub that always
   redetects the same box/role — deterministically carrying the rejection
   forward, the same IoU/role rule ``core/jobs/handlers/propose_regions.py``
   always applies, exercised here through the real job runner rather than
   simulated.
3. See the carried-rejections summary count it, expand it, and click "Bring
   back" — with no region-level selection active, since rejecting the only
   seeded proposal auto-cleared it and the carried proposal is, by design,
   invisible to select. Confirms the summary is genuinely reachable on a
   page whose only work is a suppression, not merely a decoration on an
   already-open region review panel.
4. See the proposal undecided again through the API — the same journal a
   direct rejection and reject/re-run would produce, verified rather than
   assumed.

Every wait is on a real response or a real toast (job completion, the SSE
channel's terminal message) — never a fixed sleep — following
``test_keyboard_only.py``'s convention.

Plan: this session's carried-rejection-visible work, following
``test_region_review_loop.py``'s self-contained fixture-server pattern.
"""

from __future__ import annotations

import json
import socket
import struct
import threading
import time
import zlib
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from pdomain_book_contracts.annotation import PageKind, RegionRole
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.regions.detector import DetectedRegion
from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal
from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import open_page_actions_overflow, wait_for_project_ready

_PROJECT_ID = "carried-rejection-visible-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# One proposal, well inside the page image, away from the bottom-left corner
# the test clicks as a neutral, unfocusing spot before the first hotkey (same
# reasoning as test_region_review_loop.py's _TOP_LTRB).
_LTRB = (600, 700, 900, 900)
_PROPOSAL_ID = "proposal-seed"
_ROLE = RegionRole.SIDENOTE
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


def _redetect_same_box(detector_input: Any) -> Sequence[DetectedRegion]:
    """Fixture region detector: always redetects the seeded box/role.

    Deterministic IoU-1.0 overlap with the seeded proposal, so a re-run's
    carry-forward match (core/jobs/handlers/propose_regions.py's
    ``_best_iou_match``, threshold 0.7) always fires — the test does not
    depend on a real detector's judgment, only on the carry-forward rule
    this feature makes visible.
    """
    del detector_input
    return [DetectedRegion(role=_ROLE, box=_LTRB, confidence=0.75, evidence={"signal": "fixture-redetect"})]


def _proposals(base_url: str) -> list[dict[str, object]]:
    resp = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0/regions/proposals", timeout=10.0)
    assert resp.status_code == 200, f"proposal list GET failed: {resp.status_code} {resp.text}"
    proposals = resp.json()["proposals"]
    assert isinstance(proposals, list)
    return proposals


def _page_regions(base_url: str) -> list[dict[str, object]]:
    resp = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10.0)
    assert resp.status_code == 200, f"page payload GET failed: {resp.status_code} {resp.text}"
    regions = resp.json()["regions"]
    assert isinstance(regions, list)
    return regions


@dataclass
class CarriedRejectionServer:
    base_url: str
    project_root: Path


@pytest.fixture(scope="module")
def carried_rejection_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[CarriedRejectionServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("carried-rejection-data")
    cache_root = tmp_path_factory.mktemp("carried-rejection-cache")
    config_root = tmp_path_factory.mktemp("carried-rejection-config")
    source_root = tmp_path_factory.mktemp("carried-rejection-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": ""}))

    # page_kind set directly, so the seeded page is eligible for a region
    # proposal run with no separate page-kind proposal/review step — see
    # propose_regions.py's ``_is_kind_confirmed``.
    book_page = BookPage(width=_IMAGE_W, height=_IMAGE_H, page_index=0, blocks=[], page_kind=PageKind.BODY)

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
                created_at="2026-09-18T10:00:00+00:00",
                page_facet_digests={},
                depends_on=frozenset(),
                page_kind_decision_ref=None,
                page_kind_was_confirmed=True,
            )
        )
        proposal_log.append_proposals(
            [
                RegionProposal(
                    proposal_id=_PROPOSAL_ID,
                    run_id=_RUN_ID,
                    page_index=0,
                    role=_ROLE,
                    box=_LTRB,
                    confidence=0.9,
                    evidence={"signal": "seed"},
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
    # Swap the book's real detector for a deterministic fixture stub so a
    # "Propose regions" re-run through the real job runner always redetects
    # the seeded box/role — see _redetect_same_box's docstring. Set before
    # the server thread starts, so no request can race this assignment.
    app.state.job_runner.context["region_detector"] = _redetect_same_box
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

    yield CarriedRejectionServer(base_url=base_url, project_root=dest)

    server.should_exit = True
    thread.join(timeout=5)


def _reject_seeded_proposal_from_keyboard(page: Page, base_url: str) -> None:
    """Steps 1-2: select and reject the seeded proposal, keyboard-only.

    Neutral click (clear of the proposal box and the fixed canvas-mode-pill
    — see test_region_review_loop.py's own comment on this exact click),
    then 5 to aim the rail at the region target, n to select the seeded
    proposal, x to reject it — waiting on the real reject response, not a
    sleep.
    """
    viewport = page.locator('[data-testid="image-viewport"]').first
    viewport.wait_for(state="visible", timeout=10_000)
    stage_canvas = viewport.locator("canvas").first
    stage_canvas.wait_for(state="visible", timeout=10_000)
    canvas_box = stage_canvas.bounding_box()
    assert canvas_box is not None
    page.mouse.click(canvas_box["x"] + 10, canvas_box["y"] + canvas_box["height"] - 10)

    page.keyboard.press("5")
    expect(page.locator('[data-testid="rail-target-region"]')).to_have_attribute(
        "data-active", "true", timeout=5_000
    )

    page.keyboard.press("n")
    expect(page.locator('[data-testid="region-detail-role"]')).to_contain_text(_ROLE.value, timeout=5_000)

    # No carried-rejections summary yet — nothing has been rejected.
    expect(page.locator('[data-testid="carried-rejections-summary"]')).to_have_count(0)

    with page.expect_response(
        lambda r: "/regions/proposals/" in r.url and r.url.endswith("/reject")
    ) as reject_resp_info:
        page.keyboard.press("x")
    assert reject_resp_info.value.status == 200, (
        f"reject failed: {reject_resp_info.value.status} {reject_resp_info.value.text()}"
    )
    _poll_until("the page has no unconfirmed region left after reject", lambda: _page_regions(base_url) == [])


def _rerun_regions_and_wait_for_carry(page: Page) -> None:
    """Step 3: real "Propose regions" run through the page-actions overflow menu.

    The book's region detector is the deterministic fixture stub set on
    ``app.state.job_runner.context`` in the server fixture, so the re-run
    always redetects the seeded box/role — see ``_redetect_same_box``. Waits
    on the start response, then on the completion toast naming a carried
    decision — never a sleep.
    """
    open_page_actions_overflow(page)
    with page.expect_response(lambda r: r.url.endswith("/regions/propose")) as propose_resp_info:
        page.click('[data-testid="propose-regions-button"]')
    assert propose_resp_info.value.status == 202, (
        f"propose regions failed to start: {propose_resp_info.value.status} {propose_resp_info.value.text()}"
    )
    carried_toast = page.locator("[data-sonner-toast]", has_text="Carried 1 decision")
    expect(carried_toast).to_be_visible(timeout=15_000)


def _carried_rejection_proposal_id(base_url: str) -> str:
    """Step 4: the re-run's new proposal, carried-rejected against the seed.

    Confirmed against the API: still zero visible (unconfirmed) regions, but
    a proposal record naming ``_PROPOSAL_ID`` as what it carried from — the
    suppression the product previously never showed.
    """
    assert _page_regions(base_url) == []
    carried = [
        p
        for p in _proposals(base_url)
        if p["disposition"] == "rejected" and p.get("carried_from_proposal_id") == _PROPOSAL_ID
    ]
    assert len(carried) == 1, f"expected exactly one carried rejection, got {_proposals(base_url)}"
    carried_proposal_id = carried[0]["proposal_id"]
    assert isinstance(carried_proposal_id, str)
    assert carried_proposal_id != _PROPOSAL_ID
    return carried_proposal_id


def _see_and_bring_back(page: Page, carried_proposal_id: str) -> None:
    """Steps 5-6: see the suppression, collapsed and counted, then undo it.

    Rejecting the last undecided proposal earlier auto-cleared the region
    selection (useRegionReviewHotkeys's "No undecided proposals left"
    branch), and nothing else on the page is left to click — so the summary
    must be visible with no region-level selection at all, which is exactly
    what CarriedRejectionsPanel is for (see its own doc comment in
    RegionDetail.tsx): unlike <RegionDetail> it is not gated on
    selection-store.level, or a suppression-only page could never reach it.
    "Bring back" waits on the real unreject response, not a sleep.
    """
    summary_count = page.locator('[data-testid="carried-rejections-count"]')
    expect(summary_count).to_contain_text("1 rejected proposal carried from an earlier decision")

    toggle = page.locator('[data-testid="carried-rejections-toggle"]')
    expect(toggle).to_have_attribute("aria-expanded", "false")
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    item = page.locator(f'[data-testid="carried-rejections-item-{carried_proposal_id}"]')
    expect(item).to_be_visible(timeout=5_000)
    expect(item).to_contain_text(_ROLE.value)

    bring_back = page.locator(f'[data-testid="carried-rejections-bring-back-{carried_proposal_id}"]')
    with page.expect_response(
        lambda r: "/regions/proposals/" in r.url and r.url.endswith("/unreject")
    ) as unreject_resp_info:
        bring_back.click()
    assert unreject_resp_info.value.status == 200, (
        f"unreject failed: {unreject_resp_info.value.status} {unreject_resp_info.value.text()}"
    )


def _assert_reopened_and_provenance_intact(base_url: str, carried_proposal_id: str) -> None:
    """Step 7: undecided again, and both journal entries hold their own facts.

    Verified against the API, not only the DOM: the reopened proposal is
    undecided again (behaves like any other), and the original rejection it
    reversed is untouched — provenance survives the reversal, not just
    before it.
    """
    _poll_until(
        "the reopened proposal is undecided again",
        lambda: any(r.get("proposal_id") == carried_proposal_id for r in _page_regions(base_url)),
    )

    latest_carried_view = next(p for p in _proposals(base_url) if p["proposal_id"] == carried_proposal_id)
    assert latest_carried_view["disposition"] == "reopened"

    original_view = next(p for p in _proposals(base_url) if p["proposal_id"] == _PROPOSAL_ID)
    assert original_view["disposition"] == "rejected"
    assert original_view.get("carried_from_proposal_id") is None


@pytest.mark.e2e
def test_reject_rerun_see_suppression_bring_one_back(
    carried_rejection_server: CarriedRejectionServer,
    page: Page,
) -> None:
    base_url = carried_rejection_server.base_url

    # Seed sanity: one undecided proposal.
    initial = _page_regions(base_url)
    assert len(initial) == 1, f"expected 1 seeded region, got {initial}"
    assert initial[0]["proposal_id"] == _PROPOSAL_ID

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    _reject_seeded_proposal_from_keyboard(page, base_url)
    _rerun_regions_and_wait_for_carry(page)
    carried_proposal_id = _carried_rejection_proposal_id(base_url)
    _see_and_bring_back(page, carried_proposal_id)
    expect(page.locator('[data-testid="carried-rejections-summary"]')).to_have_count(0, timeout=5_000)
    _assert_reopened_and_provenance_intact(base_url, carried_proposal_id)

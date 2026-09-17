"""E2E: confirm one page's kind from the toolbar, then bulk confirm the rest.

Slice 5's second increment: a person sees and confirms every page's kind,
one page or a whole book at a time. This test drives both surfaces the
design adds to the SPA — the page-toolbar kind control and the book-wide
Review page kinds dialog — and checks each step against the live API, not
only the DOM, following the pattern in ``test_region_review_loop.py``.

Seeds a three-page project, each page carrying one page-kind proposal in the
page-kind proposal journal (mirrors how ``tests/integration/test_page_kinds_
router.py`` seeds ``PageKindProposalLog``). Flow:

1. Open page 1 (index 0). Its toolbar kind control shows the proposed kind
   preselected; confirm it. Check the single-page API response and the
   book-wide list both report it reviewed.
2. Open the Review page kinds dialog from the page-actions overflow menu.
   The default "Unreviewed" filter now shows only pages 2 and 3 (index 1
   and 2) — page 1 dropped out once reviewed.
3. Select all visible rows and click "Confirm as proposed". Check the
   book-wide list reports all three pages reviewed, each with its proposed
   kind as the confirmed kind.

Follows the self-contained fixture-server pattern in
``test_review_queue_navigation.py``, duplicated here rather than imported
per that file's own established convention.

Plan: docs/plans/2026-09-17-region-review-surface.md's sibling design,
pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md.
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
from pdomain_book_contracts.annotation import PageKind
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal, PageKindProposalRun
from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import open_page_actions_overflow, wait_for_project_ready

_PROJECT_ID = "page-kind-review-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600
_PAGE_COUNT = 3
_RUN_ID = "r1"

# One proposal per page, each a real (non-"unknown") kind so every page is
# eligible for "Confirm as proposed" in the bulk dialog.
_PROPOSED_KINDS = [PageKind.CHAPTER_OPENING, PageKind.BODY, PageKind.BODY]
_CONFIDENCES = [0.86, 0.92, 0.77]

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


@dataclass
class PageKindReviewServer:
    base_url: str
    project_root: Path


@pytest.fixture(scope="module")
def page_kind_review_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[PageKindReviewServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("page-kind-review-data")
    cache_root = tmp_path_factory.mktemp("page-kind-review-cache")
    config_root = tmp_path_factory.mktemp("page-kind-review-config")
    source_root = tmp_path_factory.mktemp("page-kind-review-source")

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

        proposal_log = PageKindProposalLog(dest)
        proposal_log.append_run(
            PageKindProposalRun(
                run_id=_RUN_ID,
                model_id="fixture-classifier",
                model_version="0.0.0",
                created_at="2026-09-17T10:00:00+00:00",
                page_count=_PAGE_COUNT,
            )
        )
        proposal_log.append_proposals(
            [
                PageKindProposal(
                    proposal_id=f"proposal-page{i}",
                    run_id=_RUN_ID,
                    page_index=i,
                    kind=_PROPOSED_KINDS[i],
                    confidence=_CONFIDENCES[i],
                    evidence={"page_class": _PROPOSED_KINDS[i].value},
                )
                for i in range(_PAGE_COUNT)
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

    yield PageKindReviewServer(base_url=base_url, project_root=dest)

    server.should_exit = True
    thread.join(timeout=5)


def _page_kinds(base_url: str) -> dict[str, object]:
    resp = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/page-kinds", timeout=10.0)
    assert resp.status_code == 200, f"GET page-kinds failed: {resp.status_code} {resp.text}"
    return resp.json()


def _row(base_url: str, page_index: int) -> dict[str, object]:
    resp = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/page-kinds", timeout=10.0)
    assert resp.status_code == 200, f"GET page-kinds failed: {resp.status_code} {resp.text}"
    rows = resp.json()["pages"]
    assert isinstance(rows, list)
    row = next(r for r in rows if r["page_index"] == page_index)
    assert isinstance(row, dict)
    return row


@pytest.mark.e2e
def test_confirm_from_toolbar_then_bulk_confirm_from_the_list(
    page_kind_review_server: PageKindReviewServer,
    page: Page,
) -> None:
    """Confirm page 1 from the toolbar, then bulk confirm pages 2 and 3 from the list.

    1. Open page 1 (index 0). The toolbar kind control shows the proposed
       kind, preselected in the select. Confirm it.
    2. Check the API: page 0 is reviewed, with its proposed kind confirmed.
    3. Open Review page kinds from the overflow menu. The default
       "Unreviewed" filter shows only pages 2 and 3 (page 1 dropped out).
    4. Select all visible rows and click "Confirm as proposed".
    5. Check the API: every page is now reviewed, each with its proposed
       kind as the confirmed kind.
    """
    base_url = page_kind_review_server.base_url

    # Seed sanity: nothing is reviewed yet.
    seeded = _page_kinds(base_url)
    assert seeded["reviewed_count"] == 0
    assert seeded["total_pages"] == _PAGE_COUNT

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    # Step 1: confirm page 1 (index 0) from the toolbar. The status button
    # shows the proposed kind; opening it preselects that kind in the select.
    status_button = page.locator('[data-testid="page-kind-status-button"]')
    expect(status_button).to_contain_text(_PROPOSED_KINDS[0].value, timeout=10_000)
    status_button.click()
    kind_select = page.locator('[data-testid="page-kind-select"]')
    expect(kind_select).to_have_value(_PROPOSED_KINDS[0].value)
    page.click('[data-testid="page-kind-confirm-button"]')

    # Step 2: the API settles at page 0 reviewed, with its proposed kind
    # confirmed.
    _poll_until(
        "page 0 confirmed via the toolbar",
        lambda: _row(base_url, 0)["reviewed"] is True,
    )
    row0 = _row(base_url, 0)
    assert row0["confirmed_kind"] == _PROPOSED_KINDS[0].value
    assert _page_kinds(base_url)["reviewed_count"] == 1

    # Step 3: open Review page kinds from the overflow menu. The default
    # "Unreviewed" filter now shows only pages 2 and 3.
    open_page_actions_overflow(page)
    page.click('[data-testid="review-page-kinds-button"]')
    dialog = page.locator('[data-testid="page-kinds-dialog"]')
    expect(dialog).to_be_visible(timeout=10_000)
    expect(page.locator('[data-testid="page-kinds-row-1"]')).to_be_visible(timeout=10_000)
    expect(page.locator('[data-testid="page-kinds-row-2"]')).to_be_visible()
    expect(page.locator('[data-testid="page-kinds-row-0"]')).to_have_count(0)

    # Step 4: select all visible rows and confirm as proposed.
    page.click('[data-testid="page-kinds-select-all-visible"]')
    expect(page.locator('[data-testid="page-kinds-bulk-count"]')).to_have_text("2 selected", timeout=5_000)
    page.click('[data-testid="page-kinds-bulk-confirm-as-proposed"]')

    # Step 5: the API settles at every page reviewed, each with its proposed
    # kind as the confirmed kind.
    _poll_until(
        "pages 1 and 2 bulk-confirmed as proposed",
        lambda: _page_kinds(base_url)["reviewed_count"] == _PAGE_COUNT,
    )
    for i in range(_PAGE_COUNT):
        row = _row(base_url, i)
        assert row["reviewed"] is True, f"page {i} not reviewed: {row}"
        assert row["confirmed_kind"] == _PROPOSED_KINDS[i].value, f"page {i}: {row}"

    # The dialog's own list reflects the same state once it refetches: the
    # Unreviewed filter (still active) now shows no rows.
    expect(page.locator('[data-testid="page-kinds-empty"]')).to_be_visible(timeout=10_000)

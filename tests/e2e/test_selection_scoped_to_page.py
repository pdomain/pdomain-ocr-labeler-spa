"""E2E: a line selection does not silently resolve against another page.

Issue: docs/issues/2026-09-17-a-word-or-line-selection-jumps-to-another-item-
on-page-change.md (P2-SELECTION-PAGE).

A block/para/line/word ``SelectionPath`` now carries the page index it was
made on (``selectionStore``). Selecting line 0 on page 1, then navigating to
page 2 — which has a DIFFERENT line 0 — must not resolve the still-held
selection against page 2's line 0: the right panel must show no selection,
not page 2's content under the old highlight. Returning to page 1 restores
the original selection.

Follows the self-contained fixture-server pattern in
``test_review_queue_navigation.py`` / ``test_match_nav_selection_sync.py``
(read first), duplicated here per that convention. Each page is seeded with
one line, one word, at line_index 0 — the SAME index on both pages, with
DISTINCT ground-truth text, so an unfixed resolver would silently show page
2's real (but wrong) text under the page-1 selection instead of showing no
selection at all.

Run with:   make e2e AI=1
Or inline:  uv run --group e2e pytest tests/e2e/test_selection_scoped_to_page.py -v
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

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    _ingest_ocr_result,
    _register_page_in_project,
)
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings

pytestmark = pytest.mark.e2e

_PROJECT_ID = "selection-page-scope-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# Same line_index (0) and word_index (0) on both pages, distinct text — a
# stale, unscoped resolve would show PAGE2_TEXT under the page-1 selection
# rather than "no selection".
_PAGE0_TEXT = "PageOneWord"
_PAGE1_TEXT = "PageTwoWord"


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


def _nb(x1: float, y1: float, x2: float, y2: float) -> dict:
    return {"top_left": {"x": x1, "y": y1}, "bottom_right": {"x": x2, "y": y2}}


def _word_node(text: str, x1: float, y1: float, x2: float, y2: float) -> dict:
    return {
        "type": "Word",
        "text": text,
        "bounding_box": _nb(x1, y1, x2, y2),
        "ocr_confidence": 0.95,
        "word_labels": [],
        "ground_truth_text": text,
        "ground_truth_bounding_box": None,
        "ground_truth_match_keys": {"match_score": 100},
    }


def _build_single_line_page_dict(page_index: int, text: str) -> dict:
    """One line, one word, at line_index 0 / word_index 0 — `text` varies per page."""
    line = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [_word_node(text, 0.1, 0.12, 0.52, 0.18)],
    }
    para = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [line],
    }
    block = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [para],
    }
    return {
        "type": "Page",
        "page_index": page_index,
        "width": _IMAGE_W,
        "height": _IMAGE_H,
        "items": [block],
    }


def _seed_event_store(dest: Path, image_bytes: bytes) -> None:
    """Seed the LabelerPageStore with two single-line pages — no OCR needed."""
    store = LabelerPageStore(dest)
    try:
        for page_index, text in enumerate([_PAGE0_TEXT, _PAGE1_TEXT]):
            book_page = BookPage.from_dict(_build_single_line_page_dict(page_index, text))
            _ingest_ocr_result(page=book_page, image_bytes=image_bytes, page_index=page_index, store=store)
            _register_page_in_project(
                store=store,
                project_id=_PROJECT_ID,
                page_id=book_page.page_id,
                page_index=page_index,
            )
    finally:
        store.close()


@dataclass
class SelectionPageScopeServer:
    base_url: str
    project_url: str  # /projects/<id>/pages/pageno/1


@pytest.fixture(scope="module")
def selection_page_scope_server(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[SelectionPageScopeServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("selection-page-scope-data")
    cache_root = tmp_path_factory.mktemp("selection-page-scope-cache")
    config_root = tmp_path_factory.mktemp("selection-page-scope-config")
    source_root = tmp_path_factory.mktemp("selection-page-scope-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "002.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": _PAGE0_TEXT, "002.png": _PAGE1_TEXT}))

    _seed_event_store(dest, image_bytes)

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

    yield SelectionPageScopeServer(base_url=base_url, project_url=project_url)

    server.should_exit = True
    thread.join(timeout=5)


def _goto_project_page(page: Page, project_url: str) -> None:
    page.goto(project_url, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)


def test_line_selection_does_not_resolve_against_another_page(
    selection_page_scope_server: SelectionPageScopeServer,
    page: Page,
) -> None:
    """Select line 0 on page 1, page to page 2, then back — panel never lies.

    1. On page 1, click the worklist row for line 0 — selects it (breadcrumb
       + LineDetail GT input show page 1's text).
    2. Click Next to page 2, which seeds a DIFFERENT line 0. The right panel
       must show no selection — not page 2's line 0 silently standing in for
       the page-1 selection, and not page 1's stale text either.
    3. Click Prev back to page 1 — the original selection is intact again.
    """
    _goto_project_page(page, selection_page_scope_server.project_url)
    page.wait_for_selector('[data-testid="worklist-queue"]', timeout=10_000)

    # Step 1: select line 0 on page 1 via the worklist row.
    page.locator('[data-testid="worklist-row-0"]').click()
    crumb = page.locator('[data-testid="breadcrumb-chip-line"]')
    expect(crumb).to_have_attribute("data-active", "true", timeout=10_000)
    gt_input = page.locator('[data-testid="line-detail-gt-input"]')
    expect(gt_input).to_have_value(_PAGE0_TEXT, timeout=10_000)

    # Step 2: navigate to page 2 — same line_index, different content.
    next_btn = page.locator('[data-testid="nav-next-button"]:not([data-testid-stub])')
    next_btn.wait_for(state="visible", timeout=10_000)
    next_btn.click()
    page.wait_for_url("**/pages/pageno/2", timeout=10_000)
    page.wait_for_selector('[data-testid="worklist-row-0"]', timeout=10_000)

    # The right panel shows no selection: no line chip, no LineDetail, and
    # the panel body's own level attribute reads "none" — the honest,
    # production-real signal (right-panel-body carries data-level in every
    # branch RightPanel renders, unlike its child components).
    expect(page.locator('[data-testid="breadcrumb-chip-line"]')).to_have_count(0)
    expect(page.locator('[data-testid="line-detail"]')).to_have_count(0)
    expect(page.locator('[data-testid="right-panel-body"]')).to_have_attribute(
        "data-level", "none", timeout=10_000
    )
    # Neither page's text leaked into a GT input that shouldn't be showing.
    expect(page.locator('[data-testid="line-detail-gt-input"]')).to_have_count(0)

    # Step 3: back to page 1 — the original selection resolves again.
    prev_btn = page.locator('[data-testid="nav-prev-button"]:not([data-testid-stub])')
    prev_btn.wait_for(state="visible", timeout=10_000)
    prev_btn.click()
    page.wait_for_url("**/pages/pageno/1", timeout=10_000)

    crumb = page.locator('[data-testid="breadcrumb-chip-line"]')
    expect(crumb).to_have_attribute("data-active", "true", timeout=10_000)
    gt_input = page.locator('[data-testid="line-detail-gt-input"]')
    expect(gt_input).to_have_value(_PAGE0_TEXT, timeout=10_000)

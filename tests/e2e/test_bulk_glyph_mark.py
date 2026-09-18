"""E2E: the bulk glyph-mark dialog applies for real (M11 plan Task 9 Step 2).

Covers: B-GLYPH-004

Plan: docs/plans/2026-07-21-glyph-annotations-completion.md — Task 9, Step 2.
Issue: docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md.

Self-contained fixture-server pattern, following `test_glyph_panel.py` (read
first): a synthetic two-word project seeded via `_ingest_ocr_result`, no OCR
model involved.

Bulk apply already has backend-integration coverage
(`tests/integration/test_glyph_routes.py`'s
`test_glyph_bulk_mark_apply_stamps_words_and_bumps_generation`) and
frontend-unit coverage (`BulkGlyphMarkDialog.test.tsx`, mocked `fetch`).
Neither proves a real click, through the real dialog, through the real
route, changes what the *server* holds — a unit test's mocked fetch never
touches `api/pages.py`, and the integration test never touches the dialog
component. This test drives the dialog in a real browser and then makes an
independent GET (no dependency on client-side cache state) to confirm the
mark landed on the server, not only on the screen — the same proof pattern
`test_glyph_panel.py` uses for the single-word mark-reviewed flow.
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

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result, _register_page_in_project
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "bulk-glyph-mark-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# Two words on one line: "victor" contains the "ct" substring the
# ct_substring recipe (the dialog's default) marks; "plain" does not — its
# absence from the server's response after apply proves the recipe (and the
# real route behind it) ran, rather than every word being stamped blindly.
_WORD_1_TEXT = "victor"
_WORD_2_TEXT = "plain"
_WORD_1_BOX = (300, 400, 500, 440)
_WORD_2_BOX = (520, 400, 700, 440)


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
    """Minimal grayscale PNG (solid white) — content is irrelevant to the test."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(bytes([0]) + bytes([255] * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _make_page(page_index: int) -> BookPage:
    """One Block(WORDS) with two words: 'victor' and 'plain'.

    Mirrors `test_glyph_panel.py`'s `_make_page` — the proven no-OCR seeding
    shape for `_ingest_ocr_result`.
    """
    word_1 = {
        "type": "Word",
        "text": _WORD_1_TEXT,
        "ground_truth_text": _WORD_1_TEXT,
        "bounding_box": _bbox(*_WORD_1_BOX),
    }
    word_2 = {
        "type": "Word",
        "text": _WORD_2_TEXT,
        "ground_truth_text": _WORD_2_TEXT,
        "bounding_box": _bbox(*_WORD_2_BOX),
    }
    line = {
        "type": "Block",
        "child_type": "WORDS",
        "items": [word_1, word_2],
        "bounding_box": _bbox(_WORD_1_BOX[0], _WORD_1_BOX[1], _WORD_2_BOX[2], _WORD_2_BOX[3]),
    }
    para = {
        "type": "Block",
        "child_type": "BLOCKS",
        "items": [line],
        "bounding_box": _bbox(_WORD_1_BOX[0], _WORD_1_BOX[1], _WORD_2_BOX[2], _WORD_2_BOX[3]),
    }
    return BookPage.from_dict(
        {
            "width": _IMAGE_W,
            "height": _IMAGE_H,
            "page_index": page_index,
            "bounding_box": _bbox(0, 0, _IMAGE_W, _IMAGE_H),
            "items": [para],
        }
    )


@dataclass
class BulkGlyphMarkServer:
    base_url: str


@pytest.fixture
def bulk_glyph_mark_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[BulkGlyphMarkServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("bulk-glyph-data")
    cache_root = tmp_path_factory.mktemp("bulk-glyph-cache")
    config_root = tmp_path_factory.mktemp("bulk-glyph-config")
    source_root = tmp_path_factory.mktemp("bulk-glyph-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": f"{_WORD_1_TEXT} {_WORD_2_TEXT}"}))

    # Seed the event store directly — no OCR model needed for this flow.
    book_page = _make_page(page_index=0)
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

    yield BulkGlyphMarkServer(base_url=base_url)

    server.should_exit = True
    thread.join(timeout=5)


def _get_page(base_url: str) -> dict[str, object]:
    resp = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10.0)
    assert resp.status_code == 200, f"page payload GET failed: {resp.status_code} {resp.text}"
    return resp.json()


@pytest.mark.e2e
def test_bulk_mark_dialog_apply_reaches_the_api(
    bulk_glyph_mark_server: BulkGlyphMarkServer,
    page: Page,
) -> None:
    """Open the bulk dialog, preview, apply, and confirm the server has the marks.

    Covers the M11 Task 9 Step 2 gap this epic tracked: bulk apply was only
    proven at the backend-integration and frontend-unit levels — this is the
    browser-level proof that a real click through the real dialog, through
    the real route, produces `glyph_annotations` a plain GET of the page can
    see, matching the recipe's own selectivity (the "ct" word is stamped,
    the other word is not).
    """
    base_url = bulk_glyph_mark_server.base_url

    # Before any bulk mark: neither word has been reviewed.
    before = _get_page(base_url)
    before_lines = before["line_matches"]
    assert isinstance(before_lines, list)
    before_words = before_lines[0]["word_matches"]  # type: ignore[index]
    assert before_words[0]["glyph_annotations"] is None
    assert before_words[1]["glyph_annotations"] is None

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    wait_for_project_ready(page)

    open_button = page.locator('[data-testid="bulk-glyph-mark-button"]')
    open_button.wait_for(state="visible", timeout=10_000)
    open_button.click()

    dialog = page.locator('[data-testid="bulk-glyph-mark-dialog"]')
    expect(dialog).to_be_visible(timeout=10_000)

    # Recipe defaults to "ct_substring" — leave it as-is; only "victor"
    # (word 0) contains "ct".
    preview_button = page.locator('[data-testid="bulk-glyph-dry-run-button"]')
    preview_button.click()
    preview_count = page.locator('[data-testid="bulk-glyph-preview-count"]')
    expect(preview_count).to_be_visible(timeout=10_000)
    expect(preview_count).to_have_text("1 word will be modified")

    # Preview must not mutate — the dry-run's own contract, re-checked here
    # at the browser level before the apply click that follows.
    mid = _get_page(base_url)
    mid_words = mid["line_matches"][0]["word_matches"]  # type: ignore[index]
    assert mid_words[0]["glyph_annotations"] is None

    apply_button = page.locator('[data-testid="bulk-glyph-apply-button"]')
    apply_button.click()

    # A successful apply closes the dialog (BulkGlyphMarkDialog.handleApply).
    expect(dialog).to_be_hidden(timeout=10_000)

    # The actual proof this test exists for: an independent GET (no
    # dependency on client-side cache state) shows the mutation reached the
    # server and persisted, selectively — only the "ct" word is stamped.
    after = _get_page(base_url)
    after_words = after["line_matches"][0]["word_matches"]  # type: ignore[index]
    assert after_words[0]["glyph_annotations"] == {
        "ligatures": [{"kind": "ct", "char_span": [2, 4]}],
        "long_s_positions": [],
        "swash": False,
        "source": "human",
    }
    assert after_words[1]["glyph_annotations"] is None

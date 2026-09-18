"""E2E: the Matches pane's per-word GT input and Delete button are wired for real.

Regression coverage for the Matches-pane unwired-handlers defect: ``ProjectPage``
mounted ``WordMatchView`` with only ``lines``, ``filter``, ``onEditWord``, and
``onSelectLine`` — ``onValidate``, ``onDelete``, ``onCopyGtToOcr``,
``onCopyOcrToGt``, and ``onCommitGt`` were never passed. ``LineCard``/``WordCell``
declare all of those as optional and call them with ``?.()``, so every Validate,
Delete, GT→OCR, and OCR→GT button in the Matches pane — and, worst, the inline
per-word ground-truth ``<input>`` — silently no-op'd: a person could type a
correction, blur the field, and it would vanish.

This is the one a person would notice first, verified against the real backend
and a real page reload (not a mocked mutation):

  1. Edit a word's ground truth via the Matches-pane ``gt-text-input-{l}-{w}``,
     blur it, and confirm the request that fires and its response.
  2. Reload the page and confirm the edited value is still there — proof the
     edit landed in the store, not just in local component state.
  3. Click the Matches-pane Delete button and confirm it opens the same
     confirm-first dialog the D-key hotkey for this same pane already uses
     (F-035) — not an unguarded delete-on-click.

Follows the self-contained fixture-server pattern in
``test_match_nav_selection_sync.py`` (one seeded line, no cold-OCR wait, so
``line-card-0`` / ``gt-text-input-0-0`` are deterministically present) and the
response-waiting pattern in ``test_keyboard_only.py`` — every assertion waits
on the real HTTP response Playwright observes, never a fixed sleep.

Run with:   make e2e AI=1
Or inline:  uv run --group e2e pytest tests/e2e/test_matches_pane_gt_commit.py -v
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

_PROJECT_ID = "gt-commit-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600
# Two independent lines so the GT-edit test (line 0) and the delete test
# (line 1) never touch the same data — a module-scoped fixture server is
# shared across both tests in this file, and xdist may or may not preserve
# file order across workers.
_LINE0_TEXT = "Corvus"
_LINE1_TEXT = "Delenda"
_NEW_GT_TEXT = "Corvusx"


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


def _build_page_dict() -> dict:
    """Two-line page dict: line 0 = ``_LINE0_TEXT``, line 1 = ``_LINE1_TEXT``."""
    line0 = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.5, 0.18),
        "items": [_word_node(_LINE0_TEXT, 0.1, 0.12, 0.5, 0.18)],
    }
    para0 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.5, 0.18),
        "items": [line0],
    }
    block0 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.5, 0.18),
        "items": [para0],
    }

    line1 = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.5, 0.51),
        "items": [_word_node(_LINE1_TEXT, 0.1, 0.45, 0.5, 0.51)],
    }
    para1 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.5, 0.51),
        "items": [line1],
    }
    block1 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.5, 0.51),
        "items": [para1],
    }

    return {
        "type": "Page",
        "page_index": 0,
        "width": _IMAGE_W,
        "height": _IMAGE_H,
        "items": [block0, block1],
    }


def _seed_event_store(dest: Path, image_bytes: bytes) -> None:
    """Seed the LabelerPageStore with the one-line page — no OCR needed."""
    book_page = BookPage.from_dict(_build_page_dict())
    store = LabelerPageStore(dest)
    try:
        _ingest_ocr_result(page=book_page, image_bytes=image_bytes, page_index=0, store=store)
        _register_page_in_project(
            store=store, project_id=_PROJECT_ID, page_id=book_page.page_id, page_index=0
        )
    finally:
        store.close()


@dataclass
class GtCommitServer:
    base_url: str
    project_url: str  # /projects/<id>/pages/pageno/1


@pytest.fixture(scope="module")
def gt_commit_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[GtCommitServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("gt-commit-data")
    cache_root = tmp_path_factory.mktemp("gt-commit-cache")
    config_root = tmp_path_factory.mktemp("gt-commit-config")
    source_root = tmp_path_factory.mktemp("gt-commit-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": f"{_LINE0_TEXT}\n{_LINE1_TEXT}"}))

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

    yield GtCommitServer(base_url=base_url, project_url=project_url)

    server.should_exit = True
    thread.join(timeout=5)


def _goto_project_page(page: Page, project_url: str) -> None:
    page.goto(project_url, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    page.wait_for_selector('[data-testid^="line-card-"]', timeout=10_000, state="attached")


def test_matches_pane_gt_edit_persists_across_reload(
    gt_commit_server: GtCommitServer,
    page: Page,
) -> None:
    """Editing a word's GT in the Matches pane and blurring survives a reload.

    Before the fix, ``WordCell``'s ``onCommitGt`` was never called with a real
    handler — the input looked editable but the edit was discarded on blur.
    """
    _goto_project_page(page, gt_commit_server.project_url)

    gt_input = page.locator('[data-testid="gt-text-input-0-0"]')
    expect(gt_input).to_have_value(_LINE0_TEXT)

    gt_input.fill(_NEW_GT_TEXT)

    # Blur commits (WordCell.handleBlur). Wait for the real PATCH-equivalent
    # POST the commit fires, not a fixed sleep, and assert it succeeded.
    with page.expect_response(lambda r: r.url.endswith("/words/0/0/gt")) as commit_resp_info:
        page.keyboard.press("Tab")
    commit_resp = commit_resp_info.value
    assert commit_resp.status == 200, f"GT commit failed: {commit_resp.status} {commit_resp.text()}"

    # Confirm the backend actually persisted it (not just an optimistic UI
    # value) via a direct GET, before even reloading the page.
    page_payload = httpx.get(f"{gt_commit_server.base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10)
    assert page_payload.status_code == 200
    word0 = page_payload.json()["line_matches"][0]["word_matches"][0]
    assert word0["ground_truth_text"] == _NEW_GT_TEXT, f"Backend did not persist the GT edit: {word0}"

    # Reload the page in the browser and confirm the edited value survives —
    # proof it landed in the store, not just in local component state.
    page.reload(timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)
    page.wait_for_selector('[data-testid^="line-card-"]', timeout=10_000, state="attached")
    expect(page.locator('[data-testid="gt-text-input-0-0"]')).to_have_value(_NEW_GT_TEXT, timeout=10_000)


def test_matches_pane_delete_requires_confirmation(
    gt_commit_server: GtCommitServer,
    page: Page,
) -> None:
    """Clicking Delete in the Matches pane opens a confirm dialog first.

    F-035: destructive actions confirm before mutating. The D-key hotkey for
    this same pane already routes through ``dialogStore.openConfirm`` — the
    click-driven Delete button must too, not delete on a single unguarded
    click from a scrollable list of many lines.

    Targets line 1 (not line 0) so this test's mutation never touches the
    line the GT-edit test above depends on, regardless of xdist ordering —
    both tests share this module-scoped fixture server.
    """
    _goto_project_page(page, gt_commit_server.project_url)

    delete_button = page.locator('[data-testid="line-delete-button-1"]')
    delete_button.click()

    confirm_dialog = page.locator('[data-testid="confirm-dialog"]')
    expect(confirm_dialog).to_be_visible(timeout=5_000)
    expect(confirm_dialog).to_contain_text("Delete line?")

    # The line must still be present — clicking Delete alone must not have
    # mutated anything yet.
    expect(page.locator('[data-testid="line-card-1"]')).to_be_visible()

    # Confirming fires the real delete request.
    with page.expect_response(lambda r: r.url.endswith("/lines/delete-batch")) as delete_resp_info:
        page.locator('[data-testid="confirm-dialog-confirm"]').click()
    delete_resp = delete_resp_info.value
    assert delete_resp.status == 200, f"Delete request failed: {delete_resp.status} {delete_resp.text()}"

    # The line is gone from the page's Matches pane once the store refetches.
    expect(page.locator('[data-testid="line-card-1"]')).not_to_be_attached(timeout=10_000)

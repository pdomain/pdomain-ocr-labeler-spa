"""E2E: matches J/K hotkeys keep the worklist, breadcrumb, and right panel in sync.

Issue: docs/issues/2026-07-21-match-nav-selection-desync.md (P1-MATCH-NAV).

Before this fix, J/K only moved ``worklistStore.selectedLineIndex`` — the
worklist row highlight moved, but the canvas / breadcrumb / right panel (all
driven by ``selectionStore``) did not follow, unlike a Worklist row click,
which dual-writes both stores. `focusWorklistLine` (frontend/src/stores/
worklist-focus.ts) is now the single function both a row click and J/K call.

This test proves that wiring is real in a live browser, not just in the
mocked-canvas Vitest suite: pressing J/K updates the worklist row's
``aria-selected``, the Breadcrumb's line chip (``breadcrumb-chip-line``,
driven directly by ``selectionStore`` — the same store the canvas's
``selection-lines`` overlay layer reads), and the right panel's LineDetail
GT text, all together, for both lines and both directions. The canvas's own
overlay item-count sidecar (``bbox-overlay-*``) is a dev/test-only affordance
stripped from the production bundle this suite exercises (see
BBoxOverlay.tsx), so the breadcrumb + right panel are the honest,
production-real proof that the shared selection state the canvas also reads
actually changed.

Follows the self-contained fixture-server pattern in
``test_review_queue_navigation.py`` (read first), duplicated here per that
file's own established convention. The two-line, two-word page content is
seeded via the same ``BookPage.from_dict`` + ``_ingest_ocr_result`` path
``test_selection_operations_parity.py`` uses, so the fixture loads with real
line_matches immediately (no OCR wait).

Run with:   make e2e AI=1
Or inline:  uv run --group e2e pytest tests/e2e/test_match_nav_selection_sync.py -v
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

_PROJECT_ID = "match-nav-fixture"
_IMAGE_W = 1200
_IMAGE_H = 1600

# Line 0 (top): "Alpha One". Line 1 (below): "Beta Two". Distinct text per
# line so the right panel's GT text unambiguously identifies which line is
# selected after each keypress.
_LINE0_TEXT = "Alpha One"
_LINE1_TEXT = "Beta Two"


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
    """Two-line page dict: line 0 "Alpha One" (top), line 1 "Beta Two" (below)."""
    line0 = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [
            _word_node("Alpha", 0.1, 0.12, 0.3, 0.18),
            _word_node("One", 0.32, 0.12, 0.52, 0.18),
        ],
    }
    para0 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [line0],
    }
    block0 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.52, 0.18),
        "items": [para0],
    }

    line1 = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.42, 0.51),
        "items": [
            _word_node("Beta", 0.1, 0.45, 0.25, 0.51),
            _word_node("Two", 0.27, 0.45, 0.42, 0.51),
        ],
    }
    para1 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.42, 0.51),
        "items": [line1],
    }
    block1 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.45, 0.42, 0.51),
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
    """Seed the LabelerPageStore with the two-line page — no OCR needed."""
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
class MatchNavServer:
    base_url: str
    project_url: str  # /projects/<id>/pages/pageno/1


@pytest.fixture(scope="module")
def match_nav_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[MatchNavServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("match-nav-data")
    cache_root = tmp_path_factory.mktemp("match-nav-cache")
    config_root = tmp_path_factory.mktemp("match-nav-config")
    source_root = tmp_path_factory.mktemp("match-nav-source")

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

    yield MatchNavServer(base_url=base_url, project_url=project_url)

    server.should_exit = True
    thread.join(timeout=5)


def _goto_project_page(page: Page, project_url: str) -> None:
    page.goto(project_url, timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)


def _line_matches(base_url: str) -> tuple[dict, dict]:
    """Return (lm0, lm1) — the two seeded line_matches, in line_index order."""
    r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=10)
    assert r.status_code == 200, f"page payload GET failed: {r.status_code}"
    lms = sorted(r.json().get("line_matches", []), key=lambda lm: lm["line_index"])
    assert len(lms) == 2, f"expected 2 seeded line_matches, got {len(lms)}"
    return lms[0], lms[1]


def _assert_line_focused(page: Page, lm: dict) -> None:
    """Assert the worklist row, breadcrumb chip, and right panel all agree on `lm`."""
    line_index = lm["line_index"]

    # Worklist row highlight (worklist-store).
    row = page.locator(f'[data-testid="worklist-row-{line_index}"]')
    expect(row).to_have_attribute("aria-selected", "true", timeout=10_000)

    # Breadcrumb line chip (selectionStore — same store the canvas's
    # "selection-lines" overlay layer reads).
    crumb = page.locator('[data-testid="breadcrumb-chip-line"]')
    expect(crumb).to_have_attribute("data-active", "true", timeout=10_000)
    expect(crumb).to_contain_text(f"Line {line_index + 1}")

    # Right panel LineDetail (selectionStore-routed) shows this line's GT text.
    gt_input = page.locator('[data-testid="line-detail-gt-input"]')
    expect(gt_input).to_have_value(lm["ground_truth_line_text"], timeout=10_000)


def test_j_k_keep_worklist_breadcrumb_and_right_panel_in_sync(
    match_nav_server: MatchNavServer,
    page: Page,
) -> None:
    """J/K move the worklist highlight AND the hierarchical selection together.

    Before P1-MATCH-NAV, J/K only moved the worklist row; the breadcrumb and
    right panel stayed on whatever was selected before (or nothing). This
    walks J, J, K across the two seeded lines and asserts all three surfaces
    agree at every step, exactly as a Worklist row click would leave them.
    """
    lm0, lm1 = _line_matches(match_nav_server.base_url)

    _goto_project_page(page, match_nav_server.project_url)
    page.wait_for_selector('[data-testid="worklist-queue"]', timeout=10_000)

    body = page.locator("body")
    body.click()  # ensure document-level hotkeys receive the keydown

    # J from no selection → line 0.
    page.keyboard.press("j")
    _assert_line_focused(page, lm0)

    # J again → line 1. The row that was selected a moment ago must not
    # still show as selected — this is the "does it actually move" check.
    page.keyboard.press("j")
    _assert_line_focused(page, lm1)
    expect(page.locator(f'[data-testid="worklist-row-{lm0["line_index"]}"]')).to_have_attribute(
        "aria-selected", "false"
    )

    # K back → line 0 again, proving both directions stay in sync.
    page.keyboard.press("k")
    _assert_line_focused(page, lm0)


def test_line_card_click_selects_line_for_matches_hotkeys(
    match_nav_server: MatchNavServer,
    page: Page,
) -> None:
    """Clicking a line card selects it, so the matches-scope V hotkey can act on it.

    Regression test for the LineCard click-selection defect found 2026-09-18
    while fixing ``test_keyboard_only.py::test_validate_and_save_keyboard_only``:
    ``LineCard``'s outer element had no click handler at all, so clicking a
    card did nothing — and because the card renders each word's editable GT
    ``<input>`` inline, a click aimed at the card commonly landed inside one
    of those inputs instead, which (a) left V/U/D silently inert
    (``enableOnFormTags`` is ``False`` for the matches scope) and (b) typed a
    stray character into the ground truth.

    This clicks a non-interactive part of line 0's card — its first word's
    OCR text label, not a button and not the GT input — with a real mouse
    click, then presses V and waits for the validate request itself. That is
    the loop the old ``test_validate_and_save_keyboard_only`` appeared to
    cover via a card click but did not: it silently landed in a GT input and
    passed anyway (see that test's current docstring).
    """
    lm0, _lm1 = _line_matches(match_nav_server.base_url)
    assert lm0["is_fully_validated"] is False, "fixture line 0 must start unvalidated"

    _goto_project_page(page, match_nav_server.project_url)
    page.wait_for_selector('[data-testid^="line-card-"]', timeout=10_000, state="attached")

    validate_button = page.locator('[data-testid="line-validate-button-0"]')
    expect(validate_button).to_have_text("Validate")

    # Click a non-interactive part of line 0's card — the first word's OCR
    # text label — to prove selection works from an ordinary click on the
    # card, not just from happening to land on a specific control.
    page.locator('[data-testid="ocr-text-label-0-0"]').click()

    # The click must select line 0 exactly as J does (both call
    # focusWorklistLine) — worklist row, breadcrumb, and right panel agree.
    _assert_line_focused(page, lm0)

    # V validates the now-selected line. Wait for the real response, not a
    # timer — proof this click → hotkey loop reaches the backend, not just
    # a store update that happens to look right.
    with page.expect_response(lambda r: r.url.endswith("/words/validate-batch")) as validate_resp_info:
        page.keyboard.press("v")
    validate_resp = validate_resp_info.value
    assert validate_resp.status == 200, (
        f"Validate request failed: {validate_resp.status} {validate_resp.text()}"
    )
    expect(validate_button).to_have_text("Unvalidate", timeout=5_000)

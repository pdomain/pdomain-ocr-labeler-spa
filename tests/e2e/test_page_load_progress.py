"""E2E: a cold page open shows a named stage, then the page (driver-contract).

Spec: docs/specs/2026-08-08-page-load-progress-design.md
Issue: docs/issues/2026-08-08-page-load-progress-unbuilt.md

A genuine store miss on ``GET .../pages/{idx}`` now submits a ``load_page``
job and returns immediately with ``page_load_job_id`` set, instead of
blocking the request for the OCR pass. This test drives that path in a real
browser against a real (non-mocked) backend and proves the coarse,
end-to-end shape of the fix: the page region names a real OCR stage instead
of a bare spinner, the project shell stays interactive throughout, and the
page itself renders — with the words the job produced — once it completes.
The finer-grained acceptance criteria (the exact first-frame stage text, and
the stage-to-stage transition) are covered where the timing is controlled
instead of raced against a real server — see the docstring on the test
function below for exactly which other tests cover those.

Real cold OCR needs a GPU-backed doctr predictor (docs/specs/2026-08-08-
page-load-progress-design.md's measured 13-30s per page) — unavailable in
this environment and not what this test is checking. Instead, this test
injects a fake ``page_loader`` onto ``runner.context`` (the same test-seam
``core.jobs.handlers.reload_ocr._get_page_loader`` already documents and
``tests/integration/test_load_page_job.py`` already exercises at the
integration level) whose lanes always miss and whose ``run_ocr`` fabricates
a real ``pdomain_book_tools.ocr.page.Page`` after a short sleep — long
enough for this test to observe the stage-2 message on screen, short enough
to keep the test fast. No GPU, no doctr model weights.

Follows the self-contained fixture-server pattern in
``test_review_queue_panel.py`` (read first), duplicated here per that file's
own established convention.

Plan: docs/specs/2026-08-08-page-load-progress-design.md.
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
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready

_PROJECT_ID = "page-load-progress-fixture"
_IMAGE_W = 800
_IMAGE_H = 600

# Long enough that this test can reliably observe the stage-2 message
# ("Preparing the OCR engine and running OCR — ...") on screen before the
# job completes; short enough to keep the test fast. Real per-page OCR on
# this repo's measured hardware ranged 3-30s (design doc) — this fake
# loader stands in for that wait without needing a GPU or doctr weights.
_FAKE_OCR_DELAY_S = 0.6

_WORD_TEXT = "Colophon"


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


def _build_page_dict(page_index: int) -> dict:
    """One-line, one-word page dict — enough to prove real OCR text landed
    (as opposed to an empty page that never distinguishes "loaded" from
    "still pending"). Shape mirrors `test_match_nav_selection_sync.py`."""
    line0 = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.5, 0.2),
        "items": [_word_node(_WORD_TEXT, 0.1, 0.12, 0.5, 0.2)],
    }
    para0 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.5, 0.2),
        "items": [line0],
    }
    block0 = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": _nb(0.1, 0.12, 0.5, 0.2),
        "items": [para0],
    }
    return {
        "type": "Page",
        "page_index": page_index,
        "width": _IMAGE_W,
        "height": _IMAGE_H,
        "items": [block0],
    }


class _FakeColdOcrPageLoader:
    """A ``PageLoader`` whose lanes always miss, and whose ``run_ocr``
    fabricates a real ``Page`` after a short sleep.

    Standing in for ``LocalDoctrPageLoader`` — this test drives the
    frontend's SSE-consuming job-progress UI end to end without needing a
    GPU-backed doctr predictor (see module docstring). Mirrors
    ``tests/integration/test_load_page_job.py``'s ``_StoreMissPageLoader``,
    except ``run_ocr`` returns a genuine ``pdomain_book_tools.ocr.page.Page``
    (not a placeholder dict) so ``GET .../pages/{idx}`` can build a real
    ``PagePayload`` with actual OCR text once the job completes — this test
    asserts on that text to prove "then the page" (not just "then the job
    said complete").
    """

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def run_ocr(
        self,
        page_index: int,
        *,
        edited_image_bytes: bytes | None = None,
        page_kind: object | None = None,
    ) -> PageLoadOutcome:
        time.sleep(_FAKE_OCR_DELAY_S)
        page_obj = BookPage.from_dict(_build_page_dict(page_index))
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=page_obj)


@dataclass
class PageLoadProgressServer:
    base_url: str
    project_root: Path


@pytest.fixture(scope="module")
def page_load_progress_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[PageLoadProgressServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("page-load-progress-data")
    cache_root = tmp_path_factory.mktemp("page-load-progress-cache")
    config_root = tmp_path_factory.mktemp("page-load-progress-config")
    source_root = tmp_path_factory.mktemp("page-load-progress-source")

    dest = source_root / _PROJECT_ID
    dest.mkdir(parents=True)
    image_bytes = _make_png(_IMAGE_W, _IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)
    (dest / "pages.json").write_text(json.dumps({"001.png": ""}))
    # Deliberately NO store seeding — page 0 is a genuine store miss on
    # first fetch, the case this whole design is about.

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
    # Test-seam injection (documented in
    # core/jobs/handlers/reload_ocr.py::_get_page_loader and exercised at
    # the integration level by test_load_page_job.py): set BEFORE the
    # server thread starts serving, so the very first page fetch's
    # load_page job already sees it — no real doctr/GPU OCR runs.
    app.state.job_runner.context["page_loader"] = _FakeColdOcrPageLoader()  # type: ignore[attr-defined]

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

    yield PageLoadProgressServer(base_url=base_url, project_root=dest)

    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.e2e
def test_cold_open_shows_a_named_stage_then_the_page(
    page_load_progress_server: PageLoadProgressServer,
    page: Page,
) -> None:
    """A cold page open names its stage, updates it, then shows the page.

    1. Navigate to a page that is a genuine store miss.
    2. The page region names a real OCR stage — not a bare spinner.
    3. That stage is specifically the engine/OCR stage ("Preparing the OCR
       engine and running OCR — ..."), reliably observable because the fake
       loader's sleep holds the job there.
    4. Once the job completes, the status clears and the real OCR'd word
       text appears — the SPA re-fetched the page.

    This test does not try to catch the store-miss stage's own transient
    text ("Stored page not found — running OCR.") on screen: the handler
    fires it and the engine-stage message back to back with no delay
    between them (see `core/jobs/handlers/load_page.py`), and a sync route
    handler + `asyncio.create_task` scheduling means the job routinely
    reaches the engine stage before the browser's `EventSource` even
    finishes connecting — a race no realistic delay budget here can widen.
    That stage's own text is covered where the timing is controlled instead:
    `tests/integration/test_load_page_job.py` asserts on it directly from
    the SSE event list, and
    `frontend/src/pages/ProjectPage.pageLoadProgress.test.tsx` asserts the
    frontend renders it given a scripted first frame.
    """
    base_url = page_load_progress_server.base_url

    page.goto(f"{base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=20_000)
    page.wait_for_selector('[data-testid="project-page"]', timeout=20_000)

    # Project open itself is not what's slow here (defect 3) — the
    # "Loading project" overlay must not still be covering the screen once
    # the project-page shell has rendered and the page-load job is showing
    # its own status in the page region.
    wait_for_project_ready(page)

    status = page.locator('[data-testid="page-load-status"]')
    expect(status).to_be_visible(timeout=5_000)
    # A named stage, not a bare spinner — true of every stage this job
    # reports (design "Opening a page that needs OCR shows a named stage").
    expect(status).to_contain_text(re.compile(r"running ocr", re.IGNORECASE))
    # The specific engine/OCR stage, held open by the fake loader's sleep —
    # proves the message is the real, device-naming text, not a placeholder.
    expect(status).to_contain_text(re.compile(r"preparing the ocr engine", re.IGNORECASE), timeout=5_000)

    # The rest of the shell stayed interactive throughout — the page-nav
    # control was never covered by a full-viewport overlay.
    expect(page.locator('[data-testid="nav-prev-button"]')).to_be_visible()

    # Terminal: the status clears and the OCR'd word text is on screen —
    # "then the page", not just "then the job said complete".
    expect(status).to_be_hidden(timeout=10_000)
    expect(page.locator('[data-testid="page-load-error"]')).to_have_count(0)
    expect(page.locator('[data-testid="plaintext-editor-ocr"]')).to_have_value(_WORD_TEXT, timeout=10_000)

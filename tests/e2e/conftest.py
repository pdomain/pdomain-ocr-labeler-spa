"""Session-scoped fixtures for Playwright E2E tests.

Mirrors ``pdomain-prep-for-pgdp/tests/e2e/conftest.py``:

- ``live_server`` builds + serves the SPA and FastAPI together on a free
  port, yields the base URL and settings, and tears the server down at
  session end.
- Pre-built SPA is assumed (``make e2e`` runs ``make frontend-build`` first).

Per-test isolation comes from ``data_root`` being a tmp directory unique
to the session; we do not reset between tests in a single session.

``exercise_server`` is re-exported here so that any test module that runs
alone (e.g. ``pytest tests/e2e/test_ui_coverage.py``) can discover it
without needing ``exercise_real_project.py`` to be collected first.

Spec: docs/specs/2026-05-12-testing-design.md §E2E conftest
Issue #247
"""

from __future__ import annotations

import os
import shutil
import socket
import struct
import threading
import time
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from pdomain_book_tools.ocr.page import Page as BookPage

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    _ingest_ocr_result,
    _register_page_in_project,
)
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings

# Path to the bundled fixtures for the tiny-fixture project.
_TINY_FIXTURE_SRC = Path(__file__).parent / "fixtures" / "projects" / "tiny-fixture"

# Page 0 ("pageno/1") is seeded with a single real line of word content so
# driver-contract tests that need at least one word (per-line/per-word
# testids, word-edit affordances) don't depend on cold OCR ever detecting
# text on the fixture's placeholder image. See docs/issues/
# 2026-07-21-e2e-non-blocking-soft-skips.md (P0-CI-SOFT): before this, the
# fixture PNGs were 1x1-pixel placeholders, so OCR always found zero words
# and three test_driver_contract.py tests soft-skipped in every environment.
# Text matches pages.json's page-1 ground truth ("The quick brown fox").
_TINY_FIXTURE_PAGE0_WORDS = ["The", "quick", "brown", "fox"]
_TINY_FIXTURE_IMAGE_W = 1200
_TINY_FIXTURE_IMAGE_H = 1600


def _make_solid_png(width: int, height: int) -> bytes:
    """Build a minimal solid-white grayscale PNG (no external image libs)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(bytes([0]) + bytes([255] * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def _seed_tiny_fixture_page0_words(dest: Path) -> None:
    """Give tiny-fixture page 0 real word content via the event-store path.

    Replaces ``001.png`` with a real (non-1×1) image and seeds a
    ``LabelerPageStore`` with one line of ``_TINY_FIXTURE_PAGE0_WORDS`` via
    ``_ingest_ocr_result`` — the same seeding path
    ``test_selection_operations_parity.py`` and
    ``test_review_queue_panel.py`` use — so ``load_labeled`` reconstructs the
    page without running cold OCR. Only page 0 is seeded; pages 1 and 2 keep
    their placeholder images and fall through to cold OCR (unused by any
    test that asserts on their content).
    """
    image_bytes = _make_solid_png(_TINY_FIXTURE_IMAGE_W, _TINY_FIXTURE_IMAGE_H)
    (dest / "001.png").write_bytes(image_bytes)

    n = len(_TINY_FIXTURE_PAGE0_WORDS)
    word_w = 0.8 / n
    words: list[dict[str, Any]] = []
    for i, text in enumerate(_TINY_FIXTURE_PAGE0_WORDS):
        x1 = 0.1 + i * word_w
        x2 = x1 + word_w * 0.85
        words.append(
            {
                "type": "Word",
                "text": text,
                "bounding_box": {
                    "top_left": {"x": x1, "y": 0.1},
                    "bottom_right": {"x": x2, "y": 0.16},
                },
                "ocr_confidence": 0.95,
                "word_labels": [],
                "ground_truth_text": text,
                "ground_truth_bounding_box": None,
                "ground_truth_match_keys": {"match_score": 100},
            }
        )
    line = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.9, "y": 0.16}},
        "items": words,
    }
    para = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": line["bounding_box"],
        "items": [line],
    }
    block = {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": line["bounding_box"],
        "items": [para],
    }
    page_dict = {
        "type": "Page",
        "page_index": 0,
        "width": _TINY_FIXTURE_IMAGE_W,
        "height": _TINY_FIXTURE_IMAGE_H,
        "items": [block],
    }
    book_page = BookPage.from_dict(page_dict)

    store = LabelerPageStore(dest)
    try:
        _ingest_ocr_result(page=book_page, image_bytes=image_bytes, page_index=0, store=store)
        _register_page_in_project(
            store=store,
            project_id="tiny-fixture",
            page_id=book_page.page_id,
            page_index=0,
        )
    finally:
        store.close()


def pytest_configure(config: pytest.Config) -> None:
    """Make the headless browser environment hermetic: drop ``DISPLAY``.

    A stale ``DISPLAY`` — e.g. a devcontainer X-forwarding socket left over
    from a previous editor session — wedges headless chromium's frame
    production: ``requestAnimationFrame`` never fires even though the page
    reports ``visibilityState === "visible"``, so every Playwright
    actionability check (click, drag, the "stable" wait) burns its full
    timeout.  The tier then melts down into dozens of unrelated-looking
    click-timeout failures plus an apparent hang (2026-06-10 incident in
    pdomain-ocr-simple-gui, reproduced in this workspace; see
    ``test_environment_sanity.py``).

    Headless chromium needs no X server at all, so drop ``DISPLAY`` entirely
    unless the developer explicitly asked for a headed browser (e.g.
    ``make exercise-real HEADED=1``).  Runs in each xdist worker too (workers
    re-import conftest and re-run configure), so the browser subprocess can
    never inherit the variable.
    """
    if not config.getoption("--headed", default=False):
        os.environ.pop("DISPLAY", None)


# ---------------------------------------------------------------------------
# P0-CI-SOFT skip-budget gate
# ---------------------------------------------------------------------------
#
# docs/issues/2026-07-21-e2e-non-blocking-soft-skips.md: `make e2e` must not
# report success while a test soft-skips past a condition it should have
# exercised. Every remaining ``pytest.skip`` reason in tests/e2e/ is listed
# here, each with why it is a legitimate environment- or fixture-state
# dependency rather than a hidden gap (see the P0-CI-SOFT follow-up report
# for the full skip inventory and classification). A SKIPPED e2e test whose
# reason does not start with one of these prefixes fails the session below —
# a new soft-skip must either be fixed at the source (preferred, as this
# issue did for tiny-fixture's word content) or added here with a reason.
#
# This is a session-wide allowlist rather than a per-test pytest marker: the
# skip reasons already carry the justification inline at their call sites,
# so duplicating that as a marker on ~20 call sites across a dozen files
# would be pure repetition. The allowlist is the single place that answers
# "is this skip still expected" for the whole tier.
_ALLOWED_SKIP_PREFIXES = (
    # SPA build is a precondition `make e2e` always satisfies (frontend-build
    # runs first); this only fires for a bare `pytest tests/e2e` without it.
    "SPA not built",
    # axe-core is not yet an installed frontend devDependency (separate,
    # pre-existing gap — see the P0-CI-SOFT follow-up report).
    "axe-core bundle not found",
    "tiny-fixture project not available",
    "Failed to load tiny-fixture",
    # test_ocr_reload_words.py intentionally targets a manually-run dev
    # server on :8080, never the isolated server `make e2e` starts.
    "Dev server not reachable",
    "Server at http://localhost:8080",
    "Could not enumerate projects",
    # UI-layout-state dependent (drawer/rail collapsed, single-project
    # auto-redirect) rather than fixture-content dependent.
    "worklist-sort-select not visible",
    "Root page redirected to project",
    "root-search-input not rendered",
    "nav-page-input (non-stub) not visible",
    # Documented headless-interaction limitations (drag hit-testing, a
    # dialog-store call with no headless equivalent); covered by other
    # tests in the suite or by vitest.
    "MultiLineDetail did not appear",
    "MultiLineDetail did not reappear",
    "No gt-text-input found inside multi-line-detail",
    "word-edit-dialog could not be opened headlessly",
    "export-dialog could not be opened",
    # Negative-condition check: skips when the trainer app IS installed.
    "trainer app is installed",
    # exercise-fixture page 1 deterministically has exactly one paragraph in
    # every environment, so this precondition never holds — paragraph-merge
    # is never exercised by e2e. Tracked as a real gap in the P0-CI-SOFT
    # follow-up report, not fixed here (needs a multi-paragraph fixture).
    "page 1 has 1 paragraph(s); need >= 2 to merge",
)


def _skip_reason(report: pytest.TestReport) -> str:
    """Extract the human-readable reason from a SKIPPED test report.

    ``report.longrepr`` for a skip is ``(path, lineno, reason)`` where
    ``reason`` is typically prefixed with ``"Skipped: "`` — strip that so
    callers can match against the message each ``pytest.skip(...)`` call
    site actually wrote.
    """
    longrepr = report.longrepr
    reason = str(longrepr[2]) if isinstance(longrepr, tuple) and len(longrepr) == 3 else str(longrepr)
    prefix = "Skipped: "
    return reason.removeprefix(prefix)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the session if any e2e test skipped for an unrecognised reason.

    Runs after xdist workers (if any) report back to the controller, so
    ``terminalreporter.stats`` already reflects the whole run. Only tightens
    an otherwise-green session — if something else already failed, that
    exit status is left alone.
    """
    if exitstatus != 0:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    skipped: list[pytest.TestReport] = reporter.stats.get("skipped", [])
    unexpected = [rep for rep in skipped if not _skip_reason(rep).startswith(_ALLOWED_SKIP_PREFIXES)]
    if unexpected:
        session.exitstatus = 1
        reporter.write_line("")
        reporter.write_line(
            f"P0-CI-SOFT: {len(unexpected)} e2e test(s) skipped for a reason not in "
            "conftest._ALLOWED_SKIP_PREFIXES — this is now a hard failure so `make e2e` "
            "cannot report success while masking a gap. Either fix the underlying "
            "precondition or add the reason to _ALLOWED_SKIP_PREFIXES with justification.",
            red=True,
        )
        for rep in unexpected:
            reporter.write_line(f"  {rep.nodeid}: {_skip_reason(rep)}", red=True)


@dataclass
class LiveServer:
    """Holds the running server's base URL and its settings."""

    base_url: str
    settings: Settings
    source_root: Path


def _pick_free_port() -> int:
    """Return an unbound TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spa_built() -> bool:
    """Return True if the SPA static bundle exists.

    ``make e2e`` runs ``frontend-build`` first; this is the safety net
    that prints a clear skip message instead of a cryptic 404.
    """
    static = Path(__file__).resolve().parents[2] / "src" / "pdomain_ocr_labeler_spa" / "static"
    return static.is_dir() and any(static.iterdir())


def _wait_until(url: str, timeout: float = 10.0) -> None:
    """Poll ``url`` until it returns HTTP 200 or ``timeout`` seconds elapse.

    Raises ``RuntimeError`` on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready at {url!r} within {timeout}s")


def _install_tiny_fixture(source_root: Path) -> None:
    """Copy the tiny-fixture project into ``source_root``.

    Creates ``<source_root>/tiny-fixture/`` with the PNG pages, pages.json,
    and ``page-images/`` envelope files so load_project can open it. Page 0
    is then seeded with real word content (see
    :func:`_seed_tiny_fixture_page0_words`) so tests that need at least one
    word don't depend on cold OCR finding text on a placeholder image.
    """
    dest = source_root / "tiny-fixture"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(_TINY_FIXTURE_SRC, dest)
    _seed_tiny_fixture_page0_words(dest)


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveServer]:
    """Start a live uvicorn + FastAPI server for the session.

    Skips the test session when the SPA bundle is not present; run
    ``make frontend-build`` (or ``make e2e``) first.
    """
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) before E2E tests")

    data_root = tmp_path_factory.mktemp("e2e-data")
    cache_root = tmp_path_factory.mktemp("e2e-cache")
    config_root = tmp_path_factory.mktemp("e2e-config")
    source_root = tmp_path_factory.mktemp("e2e-source")

    # Populate the tiny-fixture source project so load_project works.
    _install_tiny_fixture(source_root)

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

    yield LiveServer(base_url=base_url, settings=settings, source_root=source_root)

    server.should_exit = True
    thread.join(timeout=5)


# Re-export so that test modules collected alone (e.g. test_ui_coverage.py)
# can discover this module-scoped fixture without requiring
# exercise_real_project.py to be collected in the same run.
from tests.e2e.exercise_real_project import exercise_server as exercise_server

# Re-export sel_server so test_multi_line_detail.py can reference it without
# also importing from test_selection_operations_parity (which triggers F811).
from tests.e2e.test_selection_operations_parity import sel_server as sel_server

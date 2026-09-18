"""Browser verification — U-M7 history panel + jump-to-version.

Spec authority: ``docs/specs/2026-06-12-event-store-undo.md`` "U-M7 — history
panel + jump-to-version", capability matrix U-14/U-15/U-16:

- U-14: opening the History drawer tab lists one row per version (plus the
  OCR root), each with an op label and a relative time, current highlighted.
- U-15: jump restores an older (or, after an undo, a newer) listed version.
- U-16: jump obeys the linear model — a version truncated by a real edit
  after a backward jump leaves the list; redo becomes unavailable.

Server fixture: module-scoped, event-store-seeded synthetic project — the
same ``_ingest_ocr_result`` seeding path ``test_undo_redo.py`` uses, kept in
its own project/data root so nothing here shares (or can disturb) the
shared ``tiny-fixture`` session state other driver-contract tests rely on.

Locator note: like ``undo-button``/``redo-button``, ``drawer-tab-history``
and the panel's testids only exist once in the DOM (the Drawer, unlike the
page-actions bar, has no hidden duplicate), so no ``.first`` is needed here.
"""

from __future__ import annotations

import io
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.conftest import LiveServer, _pick_free_port
from tests.e2e.helpers import SEED_TIMEOUT, wait_for_page_loaded

_PROJECT_ID = "history-panel-fixture"
_PAGE_W, _PAGE_H = 400, 300


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _word(text: str, x0: int, y0: int) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(x0, y0, x0 + 60, y0 + 20),
    }


def _make_page(page_index: int) -> BookPage:
    words = [_word("alpha", 20, 40), _word("beta", 100, 40)]
    line = {
        "type": "Block",
        "child_type": "WORDS",
        "items": words,
        "bounding_box": _bbox(20, 40, 200, 60),
    }
    para = {
        "type": "Block",
        "child_type": "BLOCKS",
        "items": [line],
        "bounding_box": _bbox(20, 40, 200, 60),
    }
    return BookPage.from_dict(
        {
            "width": _PAGE_W,
            "height": _PAGE_H,
            "page_index": page_index,
            "bounding_box": _bbox(0, 0, _PAGE_W, _PAGE_H),
            "items": [para],
        }
    )


def _png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (_PAGE_W, _PAGE_H), color=(250, 250, 250)).save(buf, format="PNG")
    return buf.getvalue()


def _spa_built() -> bool:
    static = Path(__file__).resolve().parents[2] / "src" / "pdomain_ocr_labeler_spa" / "static"
    return (static / "index.html").is_file()


@pytest.fixture(scope="module")
def history_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("history-data")
    cache_root = tmp_path_factory.mktemp("history-cache")
    config_root = tmp_path_factory.mktemp("history-config")
    source_root = tmp_path_factory.mktemp("history-source")

    project_dir = source_root / _PROJECT_ID
    project_dir.mkdir()
    image_path = project_dir / "001.png"
    image_path.write_bytes(_png_bytes())
    project = Project(
        project_id=_PROJECT_ID,
        project_root=project_dir,
        image_paths=[image_path],
        ground_truth_map={},
        total_pages=1,
    )
    store = LabelerPageStore(project_dir)
    try:
        _ingest_ocr_result(
            page=_make_page(0),
            image_bytes=_png_bytes(),
            page_index=0,
            store=store,
            project=project,
        )
    finally:
        store.close()

    settings = Settings(
        host="127.0.0.1",
        port=_pick_free_port(),
        data_root=data_root,
        cache_root=cache_root,
        config_root=config_root,
        source_projects_root=source_root,
        mode="normal",
        no_prefetch=True,
    )
    app = build_app(settings)

    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{settings.host}:{settings.port}"
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/healthz", timeout=0.5)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("history_server did not become ready")

    r = httpx.post(
        f"{base_url}/api/projects/load",
        json={"project_root": str(project_dir)},
        timeout=SEED_TIMEOUT,
    )
    assert r.status_code == 200, f"load project failed: {r.status_code} {r.text}"

    # Prime page 0 into memory (a GT edit 400s with "no in-memory page
    # record" until something has GET'd the page at least once — the same
    # priming `test_undo_redo.py` and `test_history_undo_redo.py` do).
    r = httpx.get(f"{base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=SEED_TIMEOUT)
    assert r.status_code == 200, f"priming GET failed: {r.status_code} {r.text}"

    yield LiveServer(base_url=base_url, settings=settings, source_root=source_root)

    server.should_exit = True
    thread.join(timeout=10)


# ── Shared helpers ───────────────────────────────────────────────────────────


def _goto_page(page: Page, server: LiveServer) -> None:
    page.goto(f"{server.base_url}/projects/{_PROJECT_ID}/pages/pageno/1", timeout=30_000)
    wait_for_page_loaded(page, server.base_url, timeout=30_000)


def _edit_gt(server: LiveServer, text: str) -> None:
    r = httpx.post(
        f"{server.base_url}/api/projects/{_PROJECT_ID}/pages/0/words/0/0/gt",
        json={"text": text},
        timeout=SEED_TIMEOUT,
    )
    assert r.status_code == 200, r.text


def _api_versions(server: LiveServer) -> list[dict]:
    r = httpx.get(
        f"{server.base_url}/api/projects/{_PROJECT_ID}/pages/0/history/versions", timeout=SEED_TIMEOUT
    )
    assert r.status_code == 200, r.text
    return r.json()


def _api_history(server: LiveServer) -> dict:
    r = httpx.get(f"{server.base_url}/api/projects/{_PROJECT_ID}/pages/0", timeout=SEED_TIMEOUT)
    assert r.status_code == 200, r.text
    return r.json()["history"]


def _open_history_tab(page: Page) -> None:
    page.locator('[data-testid="drawer-tab-history"]').click()
    page.locator('[data-testid="history-panel"]').wait_for(state="visible", timeout=10_000)


def _row(page: Page, node_id: str):
    return page.locator(f'[data-testid="history-version-row"][data-node-id="{node_id}"]')


# ── Tests (ordered: they share one server; each starts from a known cursor) ──


@pytest.mark.e2e
def test_history_tab_lists_one_row_per_version(history_server: LiveServer, page: Page) -> None:
    """U-14: >=3 real edits -> one row per version plus the OCR root, labels
    + relative time, current row highlighted."""
    _edit_gt(history_server, "one")
    _edit_gt(history_server, "two")
    _edit_gt(history_server, "three")

    _goto_page(page, history_server)
    _open_history_tab(page)

    rows = page.locator('[data-testid="history-version-row"]')
    expect(rows).to_have_count(4)  # OCR root + 3 edits

    versions = _api_versions(history_server)
    assert len(versions) == 4
    assert versions[0]["label"] == "OCR"
    current = versions[-1]
    expect(_row(page, current["node_id"])).to_have_attribute("data-current", "true")
    for v in versions[1:]:
        assert v["timestamp"] is not None, "edit rows must carry a real timestamp"


@pytest.mark.e2e
def test_jump_restores_an_older_version_and_moves_the_highlight(
    history_server: LiveServer, page: Page
) -> None:
    """U-15: clicking jump on an older row restores it; highlight moves;
    undo/redo buttons reflect the new cursor."""
    _goto_page(page, history_server)
    _open_history_tab(page)

    versions = _api_versions(history_server)
    root_id = versions[0]["node_id"]
    assert versions[0]["label"] == "OCR"

    _row(page, root_id).locator('[data-testid="history-jump-button"]').click()

    expect(_row(page, root_id)).to_have_attribute("data-current", "true", timeout=10_000)
    payload = _api_history(history_server)
    assert payload["undo_available"] is False
    assert payload["redo_available"] is True

    undo_btn = page.locator('[data-testid="undo-button"]').first
    redo_btn = page.locator('[data-testid="redo-button"]').first
    expect(undo_btn).to_be_disabled(timeout=10_000)
    expect(redo_btn).to_be_enabled()


@pytest.mark.e2e
def test_jump_forward_after_jump_back(history_server: LiveServer, page: Page) -> None:
    """U-15 symmetry: jump also restores a version forward of the cursor."""
    _goto_page(page, history_server)
    _open_history_tab(page)

    versions = _api_versions(history_server)
    newest_id = versions[-1]["node_id"]

    _row(page, newest_id).locator('[data-testid="history-jump-button"]').click()
    expect(_row(page, newest_id)).to_have_attribute("data-current", "true", timeout=10_000)
    payload = _api_history(history_server)
    assert payload["redo_available"] is False


@pytest.mark.e2e
def test_jump_obeys_the_linear_model(history_server: LiveServer, page: Page) -> None:
    """U-16: jump back two versions, make a real edit, the two newer rows
    leave the active list (truncated); redo becomes unavailable."""
    _goto_page(page, history_server)
    _open_history_tab(page)

    versions_before = _api_versions(history_server)
    assert len(versions_before) >= 3
    target = versions_before[-3]["node_id"]  # jump back two steps from the newest

    _row(page, target).locator('[data-testid="history-jump-button"]').click()
    expect(_row(page, target)).to_have_attribute("data-current", "true", timeout=10_000)

    truncated_ids = {v["node_id"] for v in versions_before[-2:]}

    # A real edit through the UI truncates the redo branch.
    _edit_gt(history_server, "truncator")
    page.reload()
    wait_for_page_loaded(page, history_server.base_url, timeout=30_000)
    _open_history_tab(page)

    versions_after = _api_versions(history_server)
    after_ids = {v["node_id"] for v in versions_after}
    assert truncated_ids.isdisjoint(after_ids), "truncated versions must leave the active list"

    payload = _api_history(history_server)
    assert payload["redo_available"] is False

    redo_btn = page.locator('[data-testid="redo-button"]').first
    expect(redo_btn).to_be_disabled()

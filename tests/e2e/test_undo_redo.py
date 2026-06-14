"""Browser verification (BV slice) — per-page undo/redo from the event store.

Spec authority: ``docs/specs/2026-06-12-event-store-undo.md`` slice BV:

- validate words → undo → pre-edit state (canvas/worklist/API) → redo →
  post-edit state (U-1, U-2).
- undo → make a different edit → redo disabled (U-5).
- edit → restart the app server → undo available and works (U-4).
- fresh page: undo disabled (U-3).
- focus a text input, type, Mod+Z → text-field undo only, page state
  unchanged (U-10).
- "Reload" button present under ``load-page-button``; confirm dialog shows
  the new copy; click refreshes without error (U-7).

Server fixture: module-scoped, event-store-seeded synthetic project (the
proven ``_ingest_ocr_result`` seeding path), restartable in place for U-4 —
the data dirs and event store survive a stop/start cycle.

Locator note: ``undo-button`` / ``redo-button`` exist twice in the DOM (the
visible PageActionsCompact header controls AND the hidden full PageActions
driver bar), so locators use ``.first`` — the header bar precedes the page
body in DOM order.
"""

from __future__ import annotations

import io
import socket
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
from tests.e2e.helpers import SEED_TIMEOUT, open_page_actions_overflow, wait_for_page_loaded

_PROJECT_ID = "undo-fixture"
_PAGE_W, _PAGE_H = 400, 300


# ── Synthetic page content (deterministic, no OCR model involved) ────────────


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


# ── Restartable live server ──────────────────────────────────────────────────


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spa_built() -> bool:
    static = Path(__file__).resolve().parents[2] / "src" / "pdomain_ocr_labeler_spa" / "static"
    return (static / "index.html").is_file()


def _wait_until(url: str, timeout: float = 20.0) -> None:
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


class UndoServer:
    """Live uvicorn server that can be stopped and restarted in place (U-4)."""

    def __init__(self, settings: Settings, project_dir: Path) -> None:
        self.settings = settings
        self.project_dir = project_dir
        self.base_url = f"http://{settings.host}:{settings.port}"
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        app = build_app(self.settings)
        config = uvicorn.Config(app, host=self.settings.host, port=self.settings.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        _wait_until(f"{self.base_url}/healthz")
        # (Re)load the project into the fresh process.
        r = httpx.post(
            f"{self.base_url}/api/projects/load",
            json={"project_root": str(self.project_dir)},
            timeout=SEED_TIMEOUT,
        )
        assert r.status_code == 200, f"load project failed: {r.status_code} {r.text}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._server = None
        self._thread = None

    def restart(self) -> None:
        """Full process-state restart: tear down the app (closing the page
        store) and boot a fresh one on the same port + data dirs."""
        self.stop()
        # Give the OS a moment to release the port.
        time.sleep(0.2)
        self.start()


@pytest.fixture(scope="module")
def undo_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[UndoServer]:
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) first")

    data_root = tmp_path_factory.mktemp("undo-data")
    cache_root = tmp_path_factory.mktemp("undo-cache")
    config_root = tmp_path_factory.mktemp("undo-config")
    source_root = tmp_path_factory.mktemp("undo-source")

    # Build the project dir: 3 PNG pages + event-store seed for each.
    # (3 pages so prefetch of idx+1/+2 resolves from the store, never OCR.)
    project_dir = source_root / _PROJECT_ID
    project_dir.mkdir()
    n_pages = 3
    image_paths = []
    for i in range(n_pages):
        p = project_dir / f"{i + 1:03d}.png"
        p.write_bytes(_png_bytes())
        image_paths.append(p)
    project = Project(
        project_id=_PROJECT_ID,
        project_root=project_dir,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=n_pages,
    )
    store = LabelerPageStore(project_dir)
    try:
        for i in range(n_pages):
            _ingest_ocr_result(
                page=_make_page(i),
                image_bytes=_png_bytes(),
                page_index=i,
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
    server = UndoServer(settings, project_dir)
    server.start()
    yield server
    server.stop()


# ── Shared helpers ───────────────────────────────────────────────────────────


def _goto_page(page: Page, server: UndoServer, page_no: int = 1) -> None:
    page.goto(f"{server.base_url}/projects/{_PROJECT_ID}/pages/pageno/{page_no}", timeout=30_000)
    wait_for_page_loaded(page, server.base_url, timeout=30_000)


def _api_page(server: UndoServer, idx: int = 0) -> dict:
    r = httpx.get(f"{server.base_url}/api/projects/{_PROJECT_ID}/pages/{idx}", timeout=SEED_TIMEOUT)
    assert r.status_code == 200, r.text
    return r.json()


def _validated_count(payload: dict) -> int:
    return sum(lm.get("validated_word_count", 0) for lm in payload.get("line_matches", []))


def _undo_btn(page: Page):
    # .first: visible compact-header control (the hidden driver bar duplicates
    # the testid later in the DOM).
    return page.locator('[data-testid="undo-button"]').first


def _redo_btn(page: Page):
    return page.locator('[data-testid="redo-button"]').first


def _confirm(page: Page) -> None:
    btn = page.locator('[data-testid="confirm-dialog-confirm"]')
    btn.wait_for(state="visible", timeout=5_000)
    btn.click()


def _wait_validated_count(server: UndoServer, idx: int, expected: int, timeout: float = 15.0) -> dict:
    """Poll the API until the page's validated-word count equals *expected*."""
    deadline = time.monotonic() + timeout
    payload = _api_page(server, idx)
    while time.monotonic() < deadline:
        payload = _api_page(server, idx)
        if _validated_count(payload) == expected:
            return payload
        time.sleep(0.25)
    raise AssertionError(f"validated count never reached {expected}; last={_validated_count(payload)}")


# ── Tests (ordered: they share one server; each starts from a known state) ───


@pytest.mark.e2e
def test_fresh_page_undo_redo_disabled(undo_server: UndoServer, page: Page) -> None:
    """U-3: fresh OCR page — nothing to undo or redo, both buttons disabled."""
    _goto_page(page, undo_server, page_no=3)  # page 3 stays pristine
    expect(_undo_btn(page)).to_be_visible()
    expect(_undo_btn(page)).to_be_disabled()
    expect(_redo_btn(page)).to_be_disabled()


@pytest.mark.e2e
def test_undo_redo_roundtrip_on_canvas_and_api(undo_server: UndoServer, page: Page) -> None:
    """U-1/U-2: validate-all → undo reverts (API + UI) → redo restores."""
    _goto_page(page, undo_server, page_no=1)
    base = _api_page(undo_server, 0)
    assert _validated_count(base) == 0

    # Mutate: validate every word on the page.
    page.locator('[data-testid="page-validate-all"]').click()
    _wait_validated_count(undo_server, 0, 2)

    # Undo button becomes enabled once the invalidated page query refetches.
    expect(_undo_btn(page)).to_be_enabled(timeout=10_000)

    # Undo → pre-mutation state (API re-fetch shows zero validated words).
    _undo_btn(page).click()
    _wait_validated_count(undo_server, 0, 0)
    expect(_redo_btn(page)).to_be_enabled(timeout=10_000)
    expect(_undo_btn(page)).to_be_disabled()

    # Redo → post-mutation state again.
    _redo_btn(page).click()
    _wait_validated_count(undo_server, 0, 2)
    expect(_undo_btn(page)).to_be_enabled(timeout=10_000)
    expect(_redo_btn(page)).to_be_disabled()

    # Reset for the next test: undo back to the pristine state.
    _undo_btn(page).click()
    _wait_validated_count(undo_server, 0, 0)


@pytest.mark.e2e
def test_new_edit_after_undo_truncates_redo(undo_server: UndoServer, page: Page) -> None:
    """U-5: edit A → undo → edit B: redo becomes unavailable."""
    _goto_page(page, undo_server, page_no=1)

    # Edit A: validate-all.
    page.locator('[data-testid="page-validate-all"]').click()
    _wait_validated_count(undo_server, 0, 2)
    expect(_undo_btn(page)).to_be_enabled(timeout=10_000)

    # Undo → redo available.
    _undo_btn(page).click()
    _wait_validated_count(undo_server, 0, 0)
    expect(_redo_btn(page)).to_be_enabled(timeout=10_000)

    # Edit B (different mutation): edit a word's GT via the API — same
    # store-persisting mutation path the UI uses; the page query refetch
    # keeps the buttons honest.
    r = httpx.post(
        f"{undo_server.base_url}/api/projects/{_PROJECT_ID}/pages/0/words/0/0/gt",
        json={"text": "gamma"},
        timeout=SEED_TIMEOUT,
    )
    assert r.status_code == 200, r.text

    # Redo must now be unavailable (the redo branch was truncated).
    page.reload()
    wait_for_page_loaded(page, undo_server.base_url, timeout=30_000)
    expect(_redo_btn(page)).to_be_disabled()
    expect(_undo_btn(page)).to_be_enabled()

    # Cleanup: undo edit B so later tests start from the pristine page.
    _undo_btn(page).click()
    expect(_undo_btn(page)).to_be_disabled(timeout=10_000)


@pytest.mark.e2e
def test_undo_survives_server_restart(undo_server: UndoServer, page: Page) -> None:
    """U-4: edit → restart backend → undo still available and works."""
    _goto_page(page, undo_server, page_no=1)
    page.locator('[data-testid="page-validate-all"]').click()
    _wait_validated_count(undo_server, 0, 2)

    undo_server.restart()

    _goto_page(page, undo_server, page_no=1)
    payload = _api_page(undo_server, 0)
    assert _validated_count(payload) == 2, "edit lost across restart"
    assert payload["history"]["undo_available"] is True

    expect(_undo_btn(page)).to_be_enabled(timeout=10_000)
    _undo_btn(page).click()
    _wait_validated_count(undo_server, 0, 0)

    # After an undo + restart the page must load in the RESTORED state.
    undo_server.restart()
    payload = _api_page(undo_server, 0)
    assert _validated_count(payload) == 0, "undo lost across restart (head not moved)"


@pytest.mark.e2e
def test_textfield_mod_z_does_not_fire_page_undo(undo_server: UndoServer, page: Page) -> None:
    """U-10: Mod+Z inside a text input performs the native text undo only."""
    _goto_page(page, undo_server, page_no=1)

    # Create one undo step so page undo WOULD be possible.
    page.locator('[data-testid="page-validate-all"]').click()
    payload = _wait_validated_count(undo_server, 0, 2)
    assert payload["history"]["undo_available"] is True

    # Focus a text input (quick-search lives in the Drawer worklist header
    # after D-047), type, then press Control+Z — the page state must NOT change.
    search = page.locator('[data-testid="quick-search-input"]')
    search.click()
    search.type("hello")
    page.keyboard.press("Control+z")
    time.sleep(0.5)  # give a (wrongly fired) mutation time to land

    payload = _api_page(undo_server, 0)
    assert _validated_count(payload) == 2, "page undo fired while a text input had focus — U-10 violated"
    assert payload["history"]["undo_available"] is True

    # Outside the text field the same hotkey DOES fire page undo.
    page.locator('[data-testid="project-page"]').click(position={"x": 5, "y": 5})
    page.keyboard.press("Control+z")
    _wait_validated_count(undo_server, 0, 0)


@pytest.mark.e2e
def test_reload_button_renamed_with_new_confirm_copy(undo_server: UndoServer, page: Page) -> None:
    """U-7: load-page-button says "Reload"; confirm copy honest; click works."""
    _goto_page(page, undo_server, page_no=2)

    # The visible control lives in the compact overflow menu (mounts on open).
    open_page_actions_overflow(page)
    btn = page.locator('[data-testid="load-page-button"]').first
    btn.wait_for(state="visible", timeout=5_000)
    assert "Reload" in (btn.text_content() or "")

    btn.click()
    dialog = page.locator('[data-testid="confirm-dialog"]')
    dialog.wait_for(state="visible", timeout=5_000)
    dialog_text = dialog.text_content() or ""
    assert "unsaved" not in dialog_text.lower()
    assert "discard" not in dialog_text.lower()
    assert "reload" in dialog_text.lower()

    _confirm(page)
    # The page refreshes without error — payload still served.
    wait_for_page_loaded(page, undo_server.base_url, timeout=30_000)
    payload = _api_page(undo_server, 1)
    assert payload["page_index"] == 1


@pytest.mark.e2e
@pytest.mark.slow
def test_reload_ocr_resets_history(undo_server: UndoServer, page: Page) -> None:
    """U-6: re-OCR creates a new aggregate — afterwards both buttons disabled.

    The confirm dialog warns that edit history resets before the job runs.
    Runs real (cold) OCR on the blank fixture image; first model load can
    take tens of seconds, hence the generous waits and the ``slow`` marker.
    """
    _goto_page(page, undo_server, page_no=2)

    # Create one undo step on page 2 so the reset is observable.
    page.locator('[data-testid="page-validate-all"]').click()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _validated_count(_api_page(undo_server, 1)) == 2:
            break
        time.sleep(0.25)
    expect(_undo_btn(page)).to_be_enabled(timeout=10_000)

    # Reload OCR → confirm dialog mentions the history reset (U-6 copy).
    page.locator('[data-testid="reload-ocr-button"]').click()
    dialog = page.locator('[data-testid="confirm-dialog"]')
    dialog.wait_for(state="visible", timeout=5_000)
    assert "history" in (dialog.text_content() or "").lower()
    _confirm(page)

    # Wait until the page payload reports a FRESH history (new aggregate):
    # undo and redo both unavailable. Cold OCR can take a while.
    deadline = time.monotonic() + 180
    history = None
    while time.monotonic() < deadline:
        history = _api_page(undo_server, 1).get("history")
        if history is not None and history["undo_available"] is False:
            break
        time.sleep(1.0)
    assert history is not None
    assert history["undo_available"] is False, "history did not reset after re-OCR"
    assert history["redo_available"] is False

    # And the buttons reflect it (no crash, no stale-aggregate writes).
    page.reload()
    wait_for_page_loaded(page, undo_server.base_url, timeout=60_000)
    expect(_undo_btn(page)).to_be_disabled(timeout=10_000)
    expect(_redo_btn(page)).to_be_disabled()

"""Regression guard for the 2026-09-18 empty-page-payload race.

Root cause (see ``docs/context/decisions.md`` and the fix commit): every read
of ``pdomain_book_tools.ocr.page.Page.items`` (and the ``.lines``/``.words``
properties built on top of it) sorts the page's shared ``_items`` list as a
side effect (``Page._sort_items`` -> ``list.sort()``). CPython's
``list.sort()`` briefly empties the list's backing array while it runs — a
defense against a hostile comparator that mutates the list mid-sort. Two
*readers* of the same live ``Page`` racing from two threads (two concurrent
``GET /pages/{idx}``, or a ``GET`` racing a mutation route's own read) can
interleave on that emptied window and permanently stomp the list back to
empty. Before the fix this showed up as ``GET /pages/{idx}`` returning
``200`` with ``line_matches: []`` for a page that genuinely has words,
immediately after (or racing) a mutation such as ``POST .../validated`` or
``POST .../save`` — reproduced over plain back-to-back ``httpx`` calls
against a real threaded server, no browser involved.

The fix holds the existing per-page lock (``ProjectState.get_page_lock``,
already used by every mutation route) around the *entire* live-``Page``-
touching section of ``_page_payload`` (the read choke point) and around
``save_page``'s call into ``save_page_content_to_store`` (the content-save
choke point that was the one write path skipping it) — so a reader always
observes either the fully-pre-mutation or fully-post-mutation page, never one
mid-sort.

Without real concurrent traffic this race is intermittent (observed roughly
1 in 5-8 requests against production timing). To make this test reliable
rather than probabilistic, it patches ``Page._sort_items`` to insert a short
sleep before the sort actually runs — widening the window during which a
second thread's read can observe (and, pre-fix, corrupt) the shared list.
This does not change what is being tested: it only makes the same real
race land inside the handful of requests a test can afford, instead of
needing hundreds of them.
"""

from __future__ import annotations

import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
import pytest
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
    from pdomain_ocr_labeler_spa.core.project_state import ProjectState

_N_LINES = 8
_N_WORDS = 5
_N_WORKERS = 6
_N_ITERS_PER_WORKER = 8
# Widens the concurrency window inside Page._sort_items (see module
# docstring) so genuinely concurrent readers reliably overlap.
_SORT_DELAY_S = 0.01


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"top_left": {"x": x0, "y": y0}, "bottom_right": {"x": x1, "y": y1}, "is_normalized": False}


def _word(text: str) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(0, 0, 10, 10),
        "word_labels": [],
    }


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": _bbox(0, 0, 100, 20),
    }


def _para(lines: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "items": lines,
        "bounding_box": _bbox(0, 0, 100, 400),
    }


def _make_page() -> Page:
    """A page with ``_N_LINES`` lines of ``_N_WORDS`` words each."""
    lines = [_line([_word(f"w{li}_{wi}") for wi in range(_N_WORDS)]) for li in range(_N_LINES)]
    page_dict = {
        "width": 800,
        "height": 1000,
        "page_index": 0,
        "bounding_box": _bbox(0, 0, 800, 1000),
        "items": [_para(lines)],
    }
    return Page.from_dict(page_dict)


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_healthy(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(f"server did not become healthy at {url!r}") from last_error


@pytest.fixture
def _slow_sort_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """Widen the ``Page._sort_items`` window — see module docstring."""
    orig = Page._sort_items

    def _delayed(self: Page) -> None:
        time.sleep(_SORT_DELAY_S)
        orig(self)

    monkeypatch.setattr(Page, "_sort_items", _delayed)


@dataclass(frozen=True)
class _LiveServer:
    base_url: str
    project_state: ProjectState
    page_store: LabelerPageStore


@contextmanager
def _running_server(tmp_path: Path) -> Iterator[_LiveServer]:
    """Build the app, seed an empty ``book1`` project, and serve it over real HTTP."""
    import uvicorn

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    proj_dir = projects_root / "book1"
    proj_dir.mkdir()
    (proj_dir / "001.png").write_bytes(b"\x89PNG\r\n")

    settings = Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=_pick_free_port(),
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=projects_root,
    )
    app = build_app(settings)
    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://{settings.host}:{settings.port}"
    try:
        _wait_until_healthy(f"{base_url}/healthz")
        resp = httpx.post(f"{base_url}/api/projects/load", json={"project_root": str(proj_dir)}, timeout=20)
        assert resp.status_code == 200, resp.text
        yield _LiveServer(
            base_url=base_url,
            project_state=app.state.project_state,
            page_store=app.state.page_store,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _seed_page(server: _LiveServer) -> None:
    """Register page 0's aggregate and drop a populated ``Page`` into memory."""
    page_id = uuid4()
    server.page_store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=_make_page())
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 1
    pstate.last_saved_generation = 0
    pstate.page_id = page_id
    server.project_state._page_states[0] = pstate

    sanity = httpx.get(f"{server.base_url}/api/projects/book1/pages/0", timeout=20)
    assert sanity.status_code == 200
    assert len(sanity.json()["line_matches"]) == _N_LINES, "fixture page is not what the test expects"


def _hammer_validate_and_save(server: _LiveServer, worker_id: int) -> list[tuple[int, int]]:
    """Alternate validate/GET/save/GET on page 0; return every GET that came back empty."""
    empty_hits: list[tuple[int, int]] = []
    for i in range(_N_ITERS_PER_WORKER):
        li, wi = i % _N_LINES, i % _N_WORDS
        validate_resp = httpx.post(
            f"{server.base_url}/api/projects/book1/pages/0/words/{li}/{wi}/validated",
            json={"validated": True},
            timeout=20,
        )
        assert validate_resp.status_code == 200, validate_resp.text

        get_resp = httpx.get(f"{server.base_url}/api/projects/book1/pages/0", timeout=20)
        assert get_resp.status_code == 200, get_resp.text
        if not get_resp.json().get("line_matches"):
            empty_hits.append((worker_id, i))

        save_resp = httpx.post(f"{server.base_url}/api/projects/book1/pages/0/save", json={}, timeout=20)
        assert save_resp.status_code == 200, save_resp.text

        get_resp2 = httpx.get(f"{server.base_url}/api/projects/book1/pages/0", timeout=20)
        assert get_resp2.status_code == 200, get_resp2.text
        if not get_resp2.json().get("line_matches"):
            empty_hits.append((worker_id, i))
    return empty_hits


@pytest.mark.integration
@pytest.mark.usefixtures("_slow_sort_items")
def test_concurrent_validate_and_get_never_see_empty_page(tmp_path: Path) -> None:
    """Hammer POST .../validated + GET .../pages/0 concurrently.

    Every 200 GET response must carry every line this page actually has —
    never a transiently (or permanently) empty ``line_matches`` for a page
    that was never emptied by any mutation in this test.
    """
    all_empty_hits: list[tuple[int, int]] = []
    hits_lock = threading.Lock()

    def worker(worker_id: int) -> None:
        hits = _hammer_validate_and_save(server, worker_id)
        if hits:
            with hits_lock:
                all_empty_hits.extend(hits)

    with _running_server(tmp_path) as server:
        _seed_page(server)
        threads = [threading.Thread(target=worker, args=(w,)) for w in range(_N_WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert all_empty_hits == [], (
        f"{len(all_empty_hits)} GET(s) returned an empty page for a page that has "
        f"{_N_LINES} lines — the empty-page-payload race regressed: {all_empty_hits[:5]}"
    )

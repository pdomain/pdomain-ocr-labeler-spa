"""Regression guard for the 2026-09-18 page-history consistency race.

Root cause: ``GET /pages/{idx}`` used to build ``PagePayload`` in two steps.
``_page_payload`` reads ``line_matches`` (and so every word count derived
from it) under the per-page lock and returns. Only *after* that lock was
released did ``get_page`` call ``_build_history_info`` — a second, unlocked
read of the same page's event-store aggregate. A mutation such as
``POST .../words/{li}/{wi}/validated`` (which mutates the in-memory page
*and* appends to the event store, both under that same per-page lock) could
land in the gap between the two reads. The single JSON response could then
show an updated ``validated_word_count`` next to a stale
``history.undo_available`` — or the reverse.

``tests/e2e/test_undo_redo.py``'s ``_wait_undo_available`` helper documents
this exact race and polls around it instead of asserting it away.

The fix reads both pieces under one lock acquisition — ``_page_payload``
now stamps ``PagePayload.history`` itself (mirroring what the 2026-09-18
empty-payload fix already did for ``line_matches``), so every response is
one atomic snapshot: either fully pre-mutation or fully post-mutation,
never a mix.

Without real concurrent traffic this race is intermittent (few requests
in a hundred). To make the test reliable rather than probabilistic, it
patches ``api.pages._build_history_info`` to sleep briefly before it reads
the store — pre-fix, that sleep runs in the unlocked gap between the two
reads and reliably lets a concurrent mutation land there; post-fix, that
same sleep runs *inside* the shared lock, so it only slows the test down,
never break consistency. This does not change what is being tested, only
how often the same real race lands inside the handful of requests a test
can afford.
"""

from __future__ import annotations

import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
import pytest
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.api import pages as pages_module
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
_N_ITERS_PER_WORKER = 6
# Widens the window between the word-count read and the history read (see
# module docstring) so genuinely concurrent requests reliably overlap.
_HISTORY_DELAY_S = 0.02


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
def _slow_history_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Widen the gap the pre-fix code left between the two reads.

    Pre-fix, ``get_page`` called ``_page_payload`` (word counts, under the
    per-page lock) and then ``_build_history_info`` (unlocked) as two
    separate steps. A sleep inserted right before ``_build_history_info``
    touches the store reliably lands a concurrent mutation in that gap.
    Post-fix, this same call runs inside ``_page_payload``'s lock, so the
    sleep only slows the request down — it can no longer widen a gap that
    no longer exists.
    """
    orig = pages_module._build_history_info

    def _delayed(store: object, page_id: object, *, depth: int) -> object:
        time.sleep(_HISTORY_DELAY_S)
        return orig(store, page_id, depth=depth)  # type: ignore[arg-type]

    monkeypatch.setattr(pages_module, "_build_history_info", _delayed)


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
        no_prefetch=True,
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
    """Ingest a real OCR result (real provenance) and drop it into memory.

    Unlike a bare aggregate, ``_ingest_ocr_result`` gives page 0 a real
    provenance root, so ``history.undo_available`` starts ``False`` and
    flips ``True`` — and stays ``True`` — the moment the first
    ``.../validated`` mutation's ``save_page_content_to_store`` call appends
    a second content version.
    """
    page = _make_page()
    agg = _ingest_ocr_result(page=page, image_bytes=b"\x89PNG\r\n", page_index=0, store=server.page_store)
    page_id: UUID = agg.record.page_id

    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.generation = 1
    pstate.last_saved_generation = 0
    pstate.page_id = page_id
    server.project_state._page_states[0] = pstate

    sanity = httpx.get(f"{server.base_url}/api/projects/book1/pages/0", timeout=20)
    assert sanity.status_code == 200, sanity.text
    body = sanity.json()
    assert len(body["line_matches"]) == _N_LINES, "fixture page is not what the test expects"
    assert body["history"]["undo_available"] is False, "fresh OCR root must start with undo unavailable"


def _validated_count(payload: dict[str, object]) -> int:
    line_matches = payload.get("line_matches")
    assert isinstance(line_matches, list)
    return sum(int(lm.get("validated_word_count", 0)) for lm in line_matches)  # type: ignore[union-attr]


def _hammer_validate_and_get(server: _LiveServer, worker_id: int) -> list[tuple[int, int, str]]:
    """Alternate a validate mutation with a GET on page 0.

    Every worker targets a distinct, previously-unvalidated word each
    iteration, so each successful mutation advances both signals by exactly
    one: the page-wide ``validated_word_count`` (one more validated word)
    and the aggregate's ``history.cursor`` (one more provenance version).
    Starting from ``count == cursor == 0``, a self-consistent response
    always has ``count == cursor`` — checkable on *every* iteration, not
    just the first mutation (``undo_available`` alone would only prove the
    race once, since it never flips back to ``False`` in this test).

    Returns every GET response where the two diverge.
    """
    violations: list[tuple[int, int, str]] = []
    for i in range(_N_ITERS_PER_WORKER):
        li = (worker_id * _N_ITERS_PER_WORKER + i) % _N_LINES
        wi = (worker_id * _N_ITERS_PER_WORKER + i) % _N_WORDS
        validate_resp = httpx.post(
            f"{server.base_url}/api/projects/book1/pages/0/words/{li}/{wi}/validated",
            json={"validated": True},
            timeout=20,
        )
        assert validate_resp.status_code == 200, validate_resp.text

        get_resp = httpx.get(f"{server.base_url}/api/projects/book1/pages/0", timeout=20)
        assert get_resp.status_code == 200, get_resp.text
        payload = get_resp.json()
        count = _validated_count(payload)
        cursor = (payload.get("history") or {}).get("cursor")
        if count != cursor:
            violations.append((worker_id, i, f"validated_word_count={count} history.cursor={cursor!r}"))
    return violations


@pytest.mark.integration
@pytest.mark.usefixtures("_slow_history_read")
def test_concurrent_validate_and_get_page_response_is_self_consistent(tmp_path: Path) -> None:
    """Hammer POST .../validated + GET .../pages/0 concurrently.

    Every 200 GET response must agree with itself: ``validated_word_count``
    (summed over ``line_matches``) must equal ``history.cursor`` — each
    validate mutation in this test advances both by exactly one, under the
    same per-page lock. Before the fix, a mutation landing between
    ``_page_payload``'s locked word-count read and the unlocked history
    read could produce a response where the two disagree.
    """
    all_violations: list[tuple[int, int, str]] = []
    violations_lock = threading.Lock()

    def worker(worker_id: int) -> None:
        hits = _hammer_validate_and_get(server, worker_id)
        if hits:
            with violations_lock:
                all_violations.extend(hits)

    with _running_server(tmp_path) as server:
        _seed_page(server)
        threads = [threading.Thread(target=worker, args=(w,)) for w in range(_N_WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert all_violations == [], (
        f"{len(all_violations)} GET(s) returned a self-inconsistent page payload — the "
        f"page-history consistency race regressed: {all_violations[:5]}"
    )

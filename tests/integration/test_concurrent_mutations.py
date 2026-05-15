"""Spec-23-G — concurrent-mutation integration test (issue #321).

Spec authority:
- ``specs/23-page-payload-backend.md §13`` — per-page locking via
  ``ProjectState.page_locks[idx]``; serializes concurrent edits on the
  same page so cached-envelope writes don't tear.
- ``specs/23-page-payload-backend.md §15`` — bullet "two concurrent GT
  edits on different words; assert both apply, single cached envelope
  written".

Why this test exists
--------------------

Spec-23-C1 (#315) introduced ``ProjectState.get_page_lock(idx) ->
threading.Lock``, taken inside every word/line/paragraph mutation
handler. The route handlers in this codebase are sync FastAPI
threadpool workers, so the lock is ``threading.Lock`` rather than the
``asyncio.Lock`` the spec text mentions (documented inline on
``get_page_lock``).

The lock guards:

1. The resolve → mutate → ``pstate.generation += 1`` window
   (prevents lost updates).
2. The cached-envelope write that follows the mutation. ``write_cached``
   ultimately calls ``write_json_atomic``, which writes to
   ``<path>.tmp`` and ``os.replace``s into place. If two threads
   raced this for the same target file the loser could observe a
   half-written ``.tmp`` or be clobbered by a stale write.

This test drives two real concurrent POSTs against the FastAPI app via
``ThreadPoolExecutor`` (TestClient is sync; FastAPI dispatches each
request on its own threadpool worker, so a real lock contention can
happen). We assert all four post-conditions named by the spec:

- Both responses are 200.
- Both mutations are reflected in the in-memory Page.
- ``pstate.generation`` ended at exactly ``start + 2`` (no lost bump).
- Exactly one cached envelope file on disk; no leftover ``.tmp`` files
  anywhere under ``cache_root``.

If a real race surfaces that ``ProjectState.page_locks`` does not
cover, the test should fail visibly here — *do not* paper over with
an unrelated fix; escalate (per #321 contract).
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    cached_envelope_path,
)
from pd_ocr_labeler_spa.core.project_state import PageState
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    (proj / "002.png").write_bytes(b"\x89PNG\r\n")
    return root


# ── Stub Page / Line / Word ──────────────────────────────────────────
#
# Mirrors the stubs in ``tests/unit/api/test_words_mutate_gt.py``;
# kept private to this module rather than shared to avoid coupling
# unit / integration test surfaces (the unit-test stubs may grow
# additional surface as spec-23-C2/etc. land).


@dataclass
class _StubWord:
    text: str = "ocr"
    ground_truth_text: str = ""
    text_style_labels: list[str] = field(default_factory=list)
    word_components: list[str] = field(default_factory=list)
    is_validated: bool = False

    def apply_style_scope(self, style: str, scope: str) -> bool:
        self.text_style_labels.append(style)
        return True

    def apply_component(self, component: str, *, enabled: bool) -> bool:
        if enabled and component not in self.word_components:
            self.word_components.append(component)
        elif (not enabled) and component in self.word_components:
            self.word_components.remove(component)
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Word",
            "text": self.text,
            "ground_truth_text": self.ground_truth_text,
            "text_style_labels": list(self.text_style_labels),
            "word_components": list(self.word_components),
            "is_validated": self.is_validated,
        }


@dataclass
class _StubLine:
    words: list[_StubWord] = field(default_factory=list)


@dataclass
class _StubPage:
    lines_: list[_StubLine] = field(default_factory=list)
    label: str = "concurrent"

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubLine]:
        return self.lines_

    @property
    def words(self) -> list[_StubWord]:
        return [w for ln in self.lines_ for w in ln.words]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [{"words": [w.to_dict() for w in ln.words]} for ln in self.lines_],
            "paragraphs": [],
            "words": [w.to_dict() for w in self.words],
            "source_identifier": f"{self.label}.png",
        }


def _make_seeded_page() -> _StubPage:
    return _StubPage(
        lines_=[
            _StubLine(words=[_StubWord(text="hello"), _StubWord(text="world")]),
        ],
        label="concurrent",
    )


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


def _seed_page_state(client: TestClient, *, page_index: int, page: _StubPage) -> PageState:
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(
        page_index=page_index,
        source=PageSource.OCR,
        payload=page,
    )
    pstate = PageState(page_index=page_index, page_record=outcome)
    pstate.generation = 1
    pstate.last_saved_generation = 0
    project_state._page_states[page_index] = pstate
    return pstate


# ── The test ──────────────────────────────────────────────────────────


def test_concurrent_gt_mutations_serialize_and_both_apply(
    loaded_client: TestClient,
) -> None:
    """Two concurrent GT edits on different words of the same page apply
    cleanly under the per-page lock.

    Acceptance gates (spec §13/§15 + issue #321 contract):

    1. Both POSTs return 200.
    2. Both ``Word.ground_truth_text`` mutations are visible in the
       in-memory Page (no lost update).
    3. ``pstate.generation`` ended at ``start + 2`` (the lock ensures
       neither bump was clobbered by the other).
    4. Exactly one cached envelope file on disk at the spec'd path.
    5. No ``.tmp`` files remain under ``cache_root`` — atomic-write
       cleanup completed for both racing writers.
    """
    page = _make_seeded_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    edits = [
        ("/api/projects/book1/pages/0/words/0/0/gt", {"text": "hello-A"}),
        ("/api/projects/book1/pages/0/words/0/1/gt", {"text": "world-B"}),
    ]

    def _post(args: tuple[str, dict[str, str]]) -> int:
        url, body = args
        # Each request gets its own TestClient wrapping the same app —
        # not strictly required (the underlying httpx client is
        # thread-safe-ish for simple use), but using a single shared
        # ``loaded_client`` from two threads is the more honest
        # reproduction of two browser tabs hitting one FastAPI app.
        resp = loaded_client.post(url, json=body)
        return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(_post, edits))

    # Gate 1 — both succeeded.
    assert statuses == [200, 200], f"non-200 statuses: {statuses}"

    # Gate 2 — both mutations visible in-memory.
    assert page.lines[0].words[0].ground_truth_text == "hello-A"
    assert page.lines[0].words[1].ground_truth_text == "world-B"

    # Gate 3 — generation advanced by exactly 2 (no clobber).
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    pstate_after = project_state.page_states[0]
    assert pstate_after.generation == gen_before + 2, (
        f"expected generation={gen_before + 2}, got {pstate_after.generation}"
    )

    # Gate 4 — exactly one cached envelope file on disk.
    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]
    expected_cache = cached_envelope_path(settings.cache_root, "book1", 0)
    assert expected_cache.exists(), f"cached envelope missing: {expected_cache}"

    # The cached lane writes to ``<cache_root>/page-images/`` — count
    # ``*.json`` files at that exact level (not recursive — there are
    # no nested project subdirs in the cached lane).
    cache_dir = expected_cache.parent
    json_files = sorted(p.name for p in cache_dir.glob("*.json"))
    assert json_files == [expected_cache.name], f"expected exactly one cached envelope; got {json_files}"

    # Gate 5 — no ``.tmp`` artefacts anywhere under ``cache_root``.
    # ``write_json_atomic`` writes to ``<target>.tmp`` and ``os.replace``s
    # into place; a torn write would leave one of these behind.
    leftover_tmp = sorted(p.relative_to(settings.cache_root) for p in settings.cache_root.rglob("*.tmp"))
    assert leftover_tmp == [], f"leftover .tmp files: {leftover_tmp}"


# ── Spec §13 lock-discipline test ────────────────────────────────────────
#
# Verifies that ``LaneResolver.write_cached`` is called INSIDE the per-page
# lock, not after releasing it (spec 23 §13: every mutation handler acquires
# the lock for the duration of the call, including the cache write).
#
# Strategy: patch ``LaneResolver.write_cached`` to inspect ``lock.locked()``
# at call time.  If the implementation releases the lock before calling
# ``write_cached``, ``lock.locked()`` will be ``False`` and the assertion
# fails.  If the lock is still held, ``lock.locked()`` is ``True``.
#
# We use a single-threaded POST (no ThreadPoolExecutor) to keep the assertion
# deterministic — the property being checked is "lock held during write_cached
# call", not "two threads race each other".


def test_write_cached_runs_inside_page_lock(
    loaded_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``write_cached`` is called while the per-page lock is held (spec §13).

    The test patches ``LaneResolver.write_cached`` to check
    ``project_state.get_page_lock(page_index).locked()`` at call time.
    If the implementation releases the lock before the cache write the
    patch records ``False`` and the final assertion fails.
    """
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]

    lock_held_during_write: list[bool] = []

    original_write_cached = None

    from pd_ocr_labeler_spa.core.persistence import lanes as lanes_mod

    original_write_cached = lanes_mod.LaneResolver.write_cached

    def _spy_write_cached(self: Any, page_index: int, envelope: Any) -> None:  # type: ignore[misc]
        lock = project_state.get_page_lock(page_index)
        lock_held_during_write.append(lock.locked())
        # Still perform the real write so disk-based gates remain valid.
        original_write_cached(self, page_index, envelope)

    monkeypatch.setattr(lanes_mod.LaneResolver, "write_cached", _spy_write_cached)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "lock-check"},
    )
    assert resp.status_code == 200, resp.text

    # The patch must have been called at least once.
    assert lock_held_during_write, "write_cached spy was never invoked"

    # Every invocation must have seen the lock held.
    assert all(lock_held_during_write), (
        f"write_cached was called outside the page lock on "
        f"{lock_held_during_write.count(False)} of {len(lock_held_during_write)} call(s) "
        f"(spec 23 §13 violation)"
    )

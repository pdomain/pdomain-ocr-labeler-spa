"""Slice 8b — ``core/page_state.ensure_page_model`` contract tests.

Pins the contract surface for the M3 lazy-page-loader. The actual
DocTR run, ``PageRecord`` construction (per
``docs/architecture/01-data-models.md §1`` lines 49–80) and persistence/OCR
adapter wiring slip to a later slice — this slice ships *the
contract*: idempotency, cache-key shape, lock discipline, exception
types, and the load-precedence order spec'd in
``docs/architecture/09-persistence.md`` lines 32–40 (``labeled → cached → ocr
→ fallback``).

Why test-first with stubbed loaders: the rich loader pulls in
``pdomain_book_tools.ocr.page.Page``, ``IStorage``, and the persistence
layer. None of those are M3-ready yet. The ``PageLoader`` protocol
defined here (and mirrored in ``core/page_state.py``) lets us pin
the dispatch contract independently of the heavy machinery, so
when M3-proper lands the real ``LocalDoctrPageLoader`` it just has
to implement the protocol and ``ensure_page_model`` is already
correct.

Spec authority:

- ``specs/16-milestones.md`` line 235 — "``core/page_state.py`` —
  minimal version: ``ensure_page_model`` (load cache > load saved
  > run OCR), ``_resolve_save_directory``, ``persist_page_to_file``."
- ``docs/architecture/09-persistence.md`` lines 32–40 — load precedence:
  labeled-lane → cached-lane → run OCR → fallback.
- Legacy reference: ``pd-ocr-labeler/pd_ocr_labeler/state/
  project_state.py:420`` (``ensure_page_model``).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.page_state import (
    PageImageNotFoundError,
    PageIndexOutOfRangeError,
    PageLoader,
    PageLoadOutcome,
    PageSource,
    ensure_page_model,
)
from pdomain_ocr_labeler_spa.core.project_state import ProjectState


def _make_project(total_pages: int = 3) -> Project:
    """Build a minimal valid Project with ``total_pages`` pages.

    The ``image_paths`` are absolute placeholder paths — they're only
    consulted by the *real* loader, never by the contract tests, which
    inject ``StubLoader`` instances that don't touch disk.
    """
    from pathlib import Path

    return Project(
        project_id="test-project",
        project_root=Path("/tmp/test-project"),
        image_paths=[Path(f"/tmp/test-project/{i:03d}.png") for i in range(total_pages)],
        ground_truth_map={},
        total_pages=total_pages,
        current_page_index=0,
    )


@dataclass
class StubLoader:
    """In-memory ``PageLoader`` for contract tests.

    Records every method call (per page index) so tests can assert
    "ran OCR exactly once" / "did not re-run after first call".
    """

    labeled_hits: dict[int, PageLoadOutcome] = field(default_factory=dict)
    cached_hits: dict[int, PageLoadOutcome] = field(default_factory=dict)
    ocr_results: dict[int, PageLoadOutcome] = field(default_factory=dict)
    image_missing: set[int] = field(default_factory=set)
    ocr_should_raise: set[int] = field(default_factory=set)

    load_labeled_calls: list[int] = field(default_factory=list)
    load_cached_calls: list[int] = field(default_factory=list)
    run_ocr_calls: list[int] = field(default_factory=list)

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        self.load_labeled_calls.append(page_index)
        return self.labeled_hits.get(page_index)

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        self.load_cached_calls.append(page_index)
        return self.cached_hits.get(page_index)

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        self.run_ocr_calls.append(page_index)
        if page_index in self.image_missing:
            raise PageImageNotFoundError(f"image for page_index={page_index} not found")
        if page_index in self.ocr_should_raise:
            raise RuntimeError(f"simulated OCR engine failure on {page_index}")
        if page_index in self.ocr_results:
            return self.ocr_results[page_index]
        # Default fallback OCR result so a test doesn't need to set one
        # explicitly when it just wants "OCR ran and produced a record".
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=object())


# ─── 1. Index validation ──────────────────────────────────────────────────


def test_no_project_loaded_returns_none() -> None:
    """Mirrors legacy ``ensure_page_model:451-453`` — empty project → ``None``."""
    state = ProjectState()
    loader = StubLoader()
    result = ensure_page_model(state, 0, loader=loader)
    assert result is None
    assert loader.run_ocr_calls == []  # didn't run OCR with no project


def test_negative_page_index_raises() -> None:
    state = ProjectState()
    state.set_loaded_project(_make_project(total_pages=3))
    with pytest.raises(PageIndexOutOfRangeError):
        ensure_page_model(state, -1, loader=StubLoader())


def test_page_index_above_total_raises() -> None:
    state = ProjectState()
    state.set_loaded_project(_make_project(total_pages=3))
    with pytest.raises(PageIndexOutOfRangeError):
        ensure_page_model(state, 3, loader=StubLoader())


# ─── 2. Load precedence (docs/architecture/09-persistence.md §1) ──────────────────────


def test_labeled_lane_wins_over_cached_and_ocr() -> None:
    state = ProjectState()
    state.set_loaded_project(_make_project())
    labeled = PageLoadOutcome(page_index=0, source=PageSource.FILESYSTEM, payload="labeled")
    cached = PageLoadOutcome(page_index=0, source=PageSource.CACHED_OCR, payload="cached")
    loader = StubLoader(labeled_hits={0: labeled}, cached_hits={0: cached})
    result = ensure_page_model(state, 0, loader=loader)
    assert result is labeled
    # Cached and OCR not consulted when labeled hit.
    assert loader.load_cached_calls == []
    assert loader.run_ocr_calls == []


def test_cached_lane_wins_when_no_labeled() -> None:
    state = ProjectState()
    state.set_loaded_project(_make_project())
    cached = PageLoadOutcome(page_index=0, source=PageSource.CACHED_OCR, payload="cached")
    loader = StubLoader(cached_hits={0: cached})
    result = ensure_page_model(state, 0, loader=loader)
    assert result is cached
    assert loader.run_ocr_calls == []  # didn't fall through to OCR


def test_ocr_runs_when_no_labeled_or_cached() -> None:
    state = ProjectState()
    state.set_loaded_project(_make_project())
    loader = StubLoader()
    result = ensure_page_model(state, 0, loader=loader)
    assert result is not None
    assert result.source == PageSource.OCR
    assert loader.run_ocr_calls == [0]


# ─── 3. Idempotency / cache (the big one) ─────────────────────────────────


def test_repeated_calls_do_not_rerun_ocr() -> None:
    """Second call for same page_index must hit the in-memory cache."""
    state = ProjectState()
    state.set_loaded_project(_make_project())
    loader = StubLoader()
    first = ensure_page_model(state, 0, loader=loader)
    second = ensure_page_model(state, 0, loader=loader)
    assert first is second  # exact same object (memoised)
    assert loader.run_ocr_calls == [0]  # OCR ran exactly once
    # Lane lookups also only happen once — once the page is cached on
    # ``ProjectState`` we skip both the labeled and cached lane probes.
    assert loader.load_labeled_calls == [0]
    assert loader.load_cached_calls == [0]


def test_different_page_indices_run_independently() -> None:
    state = ProjectState()
    state.set_loaded_project(_make_project(total_pages=3))
    loader = StubLoader()
    r0 = ensure_page_model(state, 0, loader=loader)
    r1 = ensure_page_model(state, 1, loader=loader)
    assert r0 is not r1
    assert sorted(loader.run_ocr_calls) == [0, 1]


def test_force_ocr_bypasses_cache() -> None:
    """``force_ocr=True`` re-runs OCR even if a record is cached."""
    state = ProjectState()
    state.set_loaded_project(_make_project())
    loader = StubLoader()
    first = ensure_page_model(state, 0, loader=loader)
    second = ensure_page_model(state, 0, loader=loader, force_ocr=True)
    assert first is not second
    assert loader.run_ocr_calls == [0, 0]


def test_force_ocr_bypasses_labeled_and_cached_lanes() -> None:
    """``force_ocr`` skips lane probes entirely (legacy parity)."""
    state = ProjectState()
    state.set_loaded_project(_make_project())
    labeled = PageLoadOutcome(page_index=0, source=PageSource.FILESYSTEM, payload="labeled")
    loader = StubLoader(labeled_hits={0: labeled})
    result = ensure_page_model(state, 0, loader=loader, force_ocr=True)
    assert result is not None
    assert result.source == PageSource.OCR
    # The labeled hit was NOT probed because force_ocr short-circuits.
    assert loader.load_labeled_calls == []
    assert loader.run_ocr_calls == [0]


# ─── 4. Lock discipline / concurrency ─────────────────────────────────────


def test_concurrent_callers_do_not_double_run_ocr() -> None:
    """Two threads calling for the same page must produce one OCR run.

    Per ``docs/architecture/00-overview.md`` line 187-189 / legacy
    ``project_state.py:702-723``, OCR is run under the project lock so
    two near-simultaneous page-loads can't both spend the OCR cost.
    """
    state = ProjectState()
    state.set_loaded_project(_make_project())

    barrier = threading.Barrier(2)
    slow_outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload="slow")

    @dataclass
    class SlowLoader:
        run_ocr_calls: list[int] = field(default_factory=list)
        load_labeled_calls: list[int] = field(default_factory=list)
        load_cached_calls: list[int] = field(default_factory=list)

        def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
            self.load_labeled_calls.append(page_index)
            return None

        def load_cached(self, page_index: int) -> PageLoadOutcome | None:
            self.load_cached_calls.append(page_index)
            return None

        def run_ocr(self, page_index: int) -> PageLoadOutcome:
            # Wait for both threads to be inside run_ocr's caller before
            # returning — simulates two contending OCR runs.
            barrier.wait(timeout=2.0)
            self.run_ocr_calls.append(page_index)
            return slow_outcome

    loader = SlowLoader()
    results: list[Any] = [None, None]

    def call(idx: int) -> None:
        results[idx] = ensure_page_model(state, 0, loader=loader)

    t0 = threading.Thread(target=call, args=(0,))
    t1 = threading.Thread(target=call, args=(1,))
    t0.start()
    t1.start()
    # Release the barrier ourselves — the two callers can't both reach
    # ``run_ocr`` because the second is gated by the project lock.
    # So we trip the barrier from the test thread to avoid deadlock if
    # only one thread enters ``run_ocr``.
    try:  # noqa: SIM105  # BrokenBarrierError after wait(timeout=) is a normal control path; suppress(…) hides the timeout semantic
        barrier.wait(timeout=2.0)
    except threading.BrokenBarrierError:
        pass
    t0.join(timeout=3.0)
    t1.join(timeout=3.0)

    assert not t0.is_alive() and not t1.is_alive()
    assert results[0] is results[1]  # both got the same cached outcome
    # The lock guarantees only one OCR ran. (If both ran, this list
    # would have two entries.)
    assert len(loader.run_ocr_calls) == 1


# ─── 5. Error paths ───────────────────────────────────────────────────────


def test_image_missing_raises_typed_error() -> None:
    """Loader signaling ``PageImageNotFoundError`` propagates verbatim."""
    state = ProjectState()
    state.set_loaded_project(_make_project())
    loader = StubLoader(image_missing={0})
    with pytest.raises(PageImageNotFoundError):
        ensure_page_model(state, 0, loader=loader)


def test_ocr_failure_does_not_cache_record() -> None:
    """If OCR raises, the next call must retry (not return a stale ``None``)."""
    state = ProjectState()
    state.set_loaded_project(_make_project())
    loader = StubLoader(ocr_should_raise={0})
    with pytest.raises(RuntimeError):
        ensure_page_model(state, 0, loader=loader)
    # Clear the failure flag and try again — should retry, not be wedged.
    loader.ocr_should_raise.clear()
    result = ensure_page_model(state, 0, loader=loader)
    assert result is not None
    assert loader.run_ocr_calls == [0, 0]


# ─── 6. Protocol shape ────────────────────────────────────────────────────


def test_page_loader_protocol_is_runtime_checkable() -> None:
    """``PageLoader`` is a ``Protocol`` — stubs duck-type without inheritance."""
    loader = StubLoader()
    # Static type checkers should accept this; this assertion is the
    # runtime sanity check that the Protocol-shaped contract is at least
    # callable in the documented way.
    assert callable(loader.load_labeled)
    assert callable(loader.load_cached)
    assert callable(loader.run_ocr)
    # Exists in the module's public surface:
    assert PageLoader is not None


# ─── 7. persist_page_to_file + _resolve_save_directory ───────────────────────
# Spec authority:
#  - specs/16-milestones.md line 240 ("_resolve_save_directory, persist_page_to_file")
#  - docs/architecture/09-persistence.md §1 line 29 ("labeled-lane" path shape)
#  - Legacy: pd-ocr-labeler/pd_ocr_labeler/state/project_state.py:save_current_page


def test_resolve_save_directory_returns_project_subdir(tmp_path: Path) -> None:
    """_resolve_save_directory(data_root, project_id) returns <data>/labeled-projects/<pid>."""
    from pdomain_ocr_labeler_spa.core.page_state import _resolve_save_directory

    result = _resolve_save_directory(tmp_path, "mybook")
    assert result == tmp_path / "labeled-projects" / "mybook"


def test_resolve_save_directory_does_not_create_dirs(tmp_path: Path) -> None:
    """_resolve_save_directory is a pure path derivation — no mkdir."""
    from pdomain_ocr_labeler_spa.core.page_state import _resolve_save_directory

    result = _resolve_save_directory(tmp_path / "nonexistent", "book")
    assert not result.exists()


@pytest.mark.skip(reason="persist_page_to_file retired in M5b; use save_page_to_store")
def test_persist_page_to_file_writes_labeled_envelope(tmp_path: Path) -> None:
    """persist_page_to_file writes a readable envelope to the labeled lane."""
    import json

    from pdomain_ocr_labeler_spa.core.persistence.user_page_envelope import (
        is_user_page_envelope,
        labeled_envelope_path,
    )

    from pdomain_ocr_labeler_spa.core.page_state import persist_page_to_file

    # Build a minimal Page-stub that has to_dict().
    @dataclass
    class _StubPage:
        words: list = field(default_factory=list)

        def to_dict(self) -> dict:
            return {"words": [], "paragraphs": [], "lines": [], "source_identifier": "001.png"}

    project = _make_project(total_pages=3)
    page = _StubPage()
    data_root = tmp_path / "data"

    persist_page_to_file(
        page=page,
        project=project,
        page_index=0,
        data_root=data_root,
    )

    expected_path = labeled_envelope_path(data_root, project.project_id, 0)
    assert expected_path.exists(), f"Labeled envelope not written to {expected_path}"
    raw = json.loads(expected_path.read_text())
    assert is_user_page_envelope(raw), "Written file is not a valid UserPageEnvelope"


@pytest.mark.skip(reason="persist_page_to_file retired in M5b; use save_page_to_store")
def test_persist_page_to_file_creates_parent_dirs(tmp_path: Path) -> None:
    """persist_page_to_file creates the labeled-projects/<pid>/ directory tree."""

    @dataclass
    class _MinimalPage:
        def to_dict(self) -> dict:
            return {"words": [], "paragraphs": [], "lines": [], "source_identifier": "001.png"}

    from pdomain_ocr_labeler_spa.core.page_state import persist_page_to_file

    project = _make_project(total_pages=1)
    data_root = tmp_path / "data"
    # Parent does not exist yet.
    assert not data_root.exists()
    persist_page_to_file(page=_MinimalPage(), project=project, page_index=0, data_root=data_root)
    from pdomain_ocr_labeler_spa.core.persistence.user_page_envelope import labeled_envelope_path

    assert labeled_envelope_path(data_root, project.project_id, 0).exists()


@pytest.mark.skip(reason="persist_page_to_file retired in M5b; use save_page_to_store")
def test_persist_page_to_file_index_out_of_range_raises(tmp_path: Path) -> None:
    """persist_page_to_file raises IndexError for out-of-range page_index."""

    @dataclass
    class _MinimalPage:
        def to_dict(self) -> dict:
            return {}

    from pdomain_ocr_labeler_spa.core.page_state import persist_page_to_file

    project = _make_project(total_pages=2)
    with pytest.raises(IndexError):
        persist_page_to_file(page=_MinimalPage(), project=project, page_index=5, data_root=tmp_path)

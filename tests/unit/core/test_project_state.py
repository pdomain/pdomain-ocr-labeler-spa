"""Unit tests for ``core.project_state`` — the M2-proper container.

This is the spec-canonical ``ProjectState`` named in
``specs/16-milestones.md`` line 158 (M2 backend bullet 1) and described
in ``specs/00-overview.md`` lines 185-187:

> ``ProjectState`` (per project) — knows the loaded ``Project``, the
> current page index, the per-page-index ``PageState`` map, the GT map.

Slice 4-router (iter 3) shipped a ``LoadProjectResponseStub`` that just
echoes the active-project pointer; that pointer lives on
``core/active_project.py``. THIS module is a different shape: it's the
per-project graph that ``LoadProjectResponse.project: Project`` needs
to be derived from once persistence I/O lands (slice 5).

What this iter-4 skeleton ships:

- A frozen ``Project`` model with the minimal fields ``ProjectState``
  needs to carry (full spec §1 lines 28-44 model — ``project_id``,
  ``project_root``, ``image_paths``, ``ground_truth_map``,
  ``total_pages``, ``current_page_index``, etc.). Validation contract
  matches spec §1; persistence (``from_dict`` / ``to_dict``) is iter-5.
- A frozen ``PageState`` placeholder (the rich version with the
  ``pd_book_tools.ocr.page.Page`` object + dirty flags + selection sets
  is M3 — see spec §0 lines 187-189).
- A mutable ``ProjectState`` carrier holding:
   - ``loaded_project: Project | None``
   - ``page_states: dict[int, PageState]``
   - ``current_page_index: int``
   - ``generation: int`` — monotonically-increasing counter for SSE /
     cache-invalidation, same discipline as ``ActiveProjectCarrier``.
   - ``threading.Lock`` for safe sync+async access.
   - ``set_loaded_project(project)`` / ``clear()`` /
     ``get_page_state(idx)`` / ``set_page_state(idx, state)``.

What this iter-4 skeleton deliberately does NOT do:

- Persist anything. No ``from_disk`` / ``save`` methods on
  ``ProjectState``. The slice-5 persistence I/O (``pages.json`` /
  ``pages_manifest.json`` / ground-truth scan) lives in
  ``core/persistence/`` per ``specs/16-milestones.md`` line 159.
- Wire into ``POST /api/projects/load``. The route can't construct a
  real ``Project`` until slice 5 ships persistence; until then it
  keeps emitting ``LoadProjectResponseStub`` (see route docstring +
  the explicit deviation in ``specs/16-milestones.md`` M2 bullet 3).
- Expose ground-truth lookup. ``ProjectState.find_ground_truth_text``
  (spec §1 line 630) lands when the GT map exists — slice 5.

Spec authority:
- ``specs/00-overview.md`` lines 179-201 — state model.
- ``specs/01-data-models.md §1`` lines 21-44 — ``Project`` model.
- ``specs/16-milestones.md`` M2 backend bullet 1 — file + scope.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.models import Project
from pd_ocr_labeler_spa.core.project_state import PageState, ProjectState

# ── Project model basics ──────────────────────────────────────────────────


def test_project_minimal_construction(tmp_path: Path) -> None:
    """Per spec §1 lines 28-44: ``Project`` carries id + root + image_paths."""
    proj = Project(
        project_id="MyProj_001",
        project_root=tmp_path,
        image_paths=[],
        ground_truth_map={},
        total_pages=0,
    )
    assert proj.project_id == "MyProj_001"
    assert proj.project_root == tmp_path
    assert proj.image_paths == []
    assert proj.ground_truth_map == {}
    assert proj.total_pages == 0
    assert proj.current_page_index == 0  # spec default
    assert proj.version == "1.0"  # spec default
    assert proj.source_lib == "doctr-pd-labeled"  # spec default
    assert proj.saved_pages == 0  # spec default
    assert proj.include_images is True  # spec default
    assert proj.copied_images is False  # spec default


def test_project_page_count_property_matches_image_paths(tmp_path: Path) -> None:
    """``page_count`` is ``len(image_paths)`` per spec §1 line 43."""
    paths = [tmp_path / f"p_{i}.jpg" for i in range(5)]
    proj = Project(
        project_id="P",
        project_root=tmp_path,
        image_paths=paths,
        ground_truth_map={},
        total_pages=5,
    )
    assert proj.page_count == 5


# ── ProjectState defaults ─────────────────────────────────────────────────


def test_empty_project_state_has_no_loaded_project() -> None:
    """Fresh ``ProjectState`` has nothing loaded."""
    state = ProjectState()
    assert state.loaded_project is None
    assert state.page_states == {}
    assert state.current_page_index == 0
    assert state.generation == 0


# ── set_loaded_project ────────────────────────────────────────────────────


def test_set_loaded_project_stores_and_bumps_generation(tmp_path: Path) -> None:
    """A successful load swaps ``loaded_project`` and bumps ``generation``."""
    state = ProjectState()
    proj = Project(
        project_id="P",
        project_root=tmp_path,
        image_paths=[],
        ground_truth_map={},
        total_pages=0,
    )
    state.set_loaded_project(proj)
    assert state.loaded_project is proj
    assert state.generation == 1


def test_set_loaded_project_resets_per_page_state(tmp_path: Path) -> None:
    """Loading a new project clears the prior per-page state map.

    Per-page state belongs to ONE project; loading a different project
    must not carry stale ``PageState`` entries across.
    """
    state = ProjectState()
    proj_a = Project(
        project_id="A",
        project_root=tmp_path / "a",
        image_paths=[],
        ground_truth_map={},
        total_pages=1,
    )
    state.set_loaded_project(proj_a)
    state.set_page_state(0, PageState(page_index=0))
    assert 0 in state.page_states

    proj_b = Project(
        project_id="B",
        project_root=tmp_path / "b",
        image_paths=[],
        ground_truth_map={},
        total_pages=1,
    )
    state.set_loaded_project(proj_b)
    assert state.page_states == {}
    assert state.loaded_project is proj_b


def test_set_loaded_project_seeds_current_page_index(tmp_path: Path) -> None:
    """``current_page_index`` is taken from the loaded ``Project``.

    The spec's ``Project.current_page_index`` (§1 line 38) is the
    persisted "where the user was last looking" — the carrier honors it
    so resume-from-disk behavior matches the legacy labeler.
    """
    state = ProjectState()
    proj = Project(
        project_id="P",
        project_root=tmp_path,
        image_paths=[],
        ground_truth_map={},
        total_pages=10,
        current_page_index=4,
    )
    state.set_loaded_project(proj)
    assert state.current_page_index == 4


# ── clear ─────────────────────────────────────────────────────────────────


def test_clear_resets_to_empty(tmp_path: Path) -> None:
    """``clear()`` resets to no-project + bumps generation."""
    state = ProjectState()
    proj = Project(
        project_id="P",
        project_root=tmp_path,
        image_paths=[],
        ground_truth_map={},
        total_pages=0,
    )
    state.set_loaded_project(proj)
    state.set_page_state(0, PageState(page_index=0))
    assert state.generation == 2  # 1 set_loaded_project + 1 set_page_state

    state.clear()
    assert state.loaded_project is None
    assert state.page_states == {}
    assert state.current_page_index == 0
    assert state.generation == 3  # every state change bumps


# ── get / set page state ──────────────────────────────────────────────────


def test_get_page_state_returns_none_when_absent() -> None:
    """Unknown page index → ``None`` (not KeyError)."""
    state = ProjectState()
    assert state.get_page_state(0) is None
    assert state.get_page_state(99) is None


def test_set_page_state_round_trips() -> None:
    """``set_page_state(idx, state)`` then ``get_page_state(idx)`` returns it."""
    state = ProjectState()
    page = PageState(page_index=3)
    state.set_page_state(3, page)
    assert state.get_page_state(3) is page


def test_set_page_state_bumps_generation() -> None:
    """Per-page-state changes are observable via the generation counter."""
    state = ProjectState()
    assert state.generation == 0
    state.set_page_state(0, PageState(page_index=0))
    assert state.generation == 1
    state.set_page_state(1, PageState(page_index=1))
    assert state.generation == 2


def test_set_page_state_rejects_negative_index() -> None:
    """Page indices are 0-based per ``specs/00-overview.md``; negatives invalid."""
    state = ProjectState()
    with pytest.raises(ValueError, match="page_index must be non-negative"):
        state.set_page_state(-1, PageState(page_index=-1))


def test_set_page_state_rejects_index_state_mismatch() -> None:
    """``state.page_index`` must match the dict key — sanity-check.

    Prevents the trivial bug where a caller indexes by 5 but stores a
    ``PageState`` whose ``page_index`` is 3; later code that pulls from
    the dict and trusts ``state.page_index`` would silently misbehave.
    """
    state = ProjectState()
    with pytest.raises(ValueError, match="page_index mismatch"):
        state.set_page_state(5, PageState(page_index=3))


# ── current_page_index manipulation ───────────────────────────────────────


def test_set_current_page_index_within_bounds(tmp_path: Path) -> None:
    """Updating the cursor within ``total_pages`` works + bumps generation."""
    state = ProjectState()
    proj = Project(
        project_id="P",
        project_root=tmp_path,
        image_paths=[],
        ground_truth_map={},
        total_pages=5,
    )
    state.set_loaded_project(proj)
    gen_before = state.generation
    state.set_current_page_index(3)
    assert state.current_page_index == 3
    assert state.generation == gen_before + 1


def test_set_current_page_index_rejects_negative() -> None:
    """Negative page index is invalid even with no project loaded."""
    state = ProjectState()
    with pytest.raises(ValueError, match="must be non-negative"):
        state.set_current_page_index(-1)


def test_set_current_page_index_rejects_out_of_range_when_loaded(tmp_path: Path) -> None:
    """``idx >= total_pages`` rejected when a project IS loaded.

    With no project loaded we can't validate range, so only the
    non-negative check fires; once loaded, the upper bound is the
    ``total_pages`` from the loaded project.
    """
    state = ProjectState()
    proj = Project(
        project_id="P",
        project_root=tmp_path,
        image_paths=[],
        ground_truth_map={},
        total_pages=3,
    )
    state.set_loaded_project(proj)
    with pytest.raises(ValueError, match="out of range"):
        state.set_current_page_index(3)
    with pytest.raises(ValueError, match="out of range"):
        state.set_current_page_index(99)


# ── thread safety ────────────────────────────────────────────────────────


def test_concurrent_set_page_state_serializes_under_lock() -> None:
    """Concurrent ``set_page_state`` calls all succeed; generation == N.

    Mirrors ``ActiveProjectCarrier``'s lock contract — every successful
    mutation bumps the generation counter, so ``N`` concurrent writes
    must produce ``generation == N`` (not less, which would mean a lost
    update due to a racy read-modify-write).
    """
    n_threads = 16
    state = ProjectState()
    barrier = threading.Barrier(n_threads)
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            barrier.wait()
            state.set_page_state(i, PageState(page_index=i))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert state.generation == n_threads
    assert len(state.page_states) == n_threads


# ── separation of concerns ───────────────────────────────────────────────


def test_project_state_does_not_validate_filesystem(tmp_path: Path) -> None:
    """``ProjectState`` is pure in-memory — never stats the disk.

    Filesystem validation belongs to ``ActiveProjectCarrier`` (project
    *root*) and to slice-5 persistence (project *contents*). A
    ``Project`` whose ``project_root`` is a non-existent path is still
    a valid ``Project`` to *hold* — what matters is whether the upstream
    loader was happy to construct it.
    """
    state = ProjectState()
    bogus = tmp_path / "definitely-does-not-exist"
    proj = Project(
        project_id="Ghost",
        project_root=bogus,
        image_paths=[],
        ground_truth_map={},
        total_pages=0,
    )
    state.set_loaded_project(proj)  # must not raise
    assert state.loaded_project is proj

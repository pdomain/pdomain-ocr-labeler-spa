"""Unit tests for adjacent-page prefetch — GAP-2.

Spec authority: GAP-2 design (``_prefetch_adjacent_pages`` in
``api/pages.py``).  Settings gate: ``no_prefetch: bool = False``.

These tests directly call ``_prefetch_adjacent_pages`` with a spy
``PageLoader`` injected on ``runner.context``.  This avoids spinning
up a real HTTP round-trip while still exercising the full prefetch
logic (bounds check, already-cached fast-exit, exception swallowing).

The integration-level test (``test_get_page_schedules_prefetch``) verifies
that ``GET /pages/{idx}`` correctly schedules the background task when
``no_prefetch=False``, and suppresses it when ``no_prefetch=True``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.api.pages import _prefetch_adjacent_pages
from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pd_ocr_labeler_spa.core.project_state import PageState, ProjectState
from pd_ocr_labeler_spa.settings import Settings

# ── Shared helpers ────────────────────────────────────────────────────


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


# ── Stubs ─────────────────────────────────────────────────────────────


class _SpyLoader:
    """``PageLoader`` that records ``ensure_page_model`` calls via run_ocr."""

    def __init__(self) -> None:
        self.run_ocr_calls: list[int] = []
        self.load_labeled_calls: list[int] = []
        self.load_cached_calls: list[int] = []

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        self.run_ocr_calls.append(page_index)
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload=object(),
        )

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        self.load_labeled_calls.append(page_index)
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        self.load_cached_calls.append(page_index)
        return None


# ── _prefetch_adjacent_pages unit tests ───────────────────────────────


def test_prefetch_loads_next_two_pages(tmp_path: Path) -> None:
    """Prefetch triggers ensure_page_model for idx+1 and idx+2."""
    settings = _make_settings(tmp_path)

    # Build a minimal app so build_app wires app.state correctly.
    app = build_app(settings)

    spy = _SpyLoader()
    project_state: ProjectState = app.state.project_state
    runner = app.state.job_runner
    runner.context["page_loader"] = spy

    # Seed a 4-page project directly onto ProjectState.
    from pd_ocr_labeler_spa.core.models import Project

    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=[tmp_path / f"page{i}.png" for i in range(4)],
        total_pages=4,
        ground_truth_map={},
    )
    project_state.set_loaded_project(project)

    _prefetch_adjacent_pages(project_state, runner, settings, current_index=0)

    # Should have attempted pages 1 and 2 (not 3, not 0).
    all_attempted = spy.run_ocr_calls + spy.load_labeled_calls + spy.load_cached_calls
    # load_labeled and load_cached are called per-lane; run_ocr only if both miss.
    # What matters: pages 1 and 2 were touched, page 0 and 3 were not.
    assert 1 in all_attempted, "page 1 should have been prefetched"
    assert 2 in all_attempted, "page 2 should have been prefetched"
    assert 0 not in all_attempted, "page 0 (current) must not be re-prefetched"
    assert 3 not in all_attempted, "page 3 is beyond offset+2 from index 0"


def test_prefetch_respects_page_bounds(tmp_path: Path) -> None:
    """Prefetch on the last page does not attempt out-of-range indices."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)

    spy = _SpyLoader()
    project_state: ProjectState = app.state.project_state
    runner = app.state.job_runner
    runner.context["page_loader"] = spy

    from pd_ocr_labeler_spa.core.models import Project

    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=[tmp_path / "p0.png", tmp_path / "p1.png"],
        total_pages=2,
        ground_truth_map={},
    )
    project_state.set_loaded_project(project)

    # Current index is 1 (last page) — no adjacent pages to load.
    _prefetch_adjacent_pages(project_state, runner, settings, current_index=1)

    all_attempted = spy.run_ocr_calls + spy.load_labeled_calls + spy.load_cached_calls
    assert all_attempted == [], "no pages beyond the last should be attempted"


def test_prefetch_skips_already_cached_pages(tmp_path: Path) -> None:
    """Prefetch skips pages whose PageState already has a page_record."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)

    spy = _SpyLoader()
    project_state: ProjectState = app.state.project_state
    runner = app.state.job_runner
    runner.context["page_loader"] = spy

    from pd_ocr_labeler_spa.core.models import Project

    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=[tmp_path / f"p{i}.png" for i in range(3)],
        total_pages=3,
        ground_truth_map={},
    )
    project_state.set_loaded_project(project)

    # Pre-seed page 1 as already loaded.
    cached_state = PageState(page_index=1)
    cached_state.page_record = PageLoadOutcome(
        page_index=1,
        source=PageSource.CACHED_OCR,
        payload=object(),
    )
    project_state.set_page_state(1, cached_state)

    _prefetch_adjacent_pages(project_state, runner, settings, current_index=0)

    # Page 1 is already cached — loader should NOT have been called for it.
    all_attempted = spy.run_ocr_calls + spy.load_labeled_calls + spy.load_cached_calls
    assert 1 not in all_attempted, "already-cached page 1 must not re-trigger the loader"
    # Page 2 is NOT cached — should have been prefetched.
    assert 2 in all_attempted, "page 2 (not cached) should have been prefetched"


def test_prefetch_swallows_loader_errors(tmp_path: Path) -> None:
    """Prefetch errors must not propagate — must return silently."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)

    project_state: ProjectState = app.state.project_state
    runner = app.state.job_runner

    class _BoomLoader:
        def run_ocr(self, page_index: int) -> PageLoadOutcome:
            raise RuntimeError("boom")

        def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
            raise RuntimeError("boom")

        def load_cached(self, page_index: int) -> PageLoadOutcome | None:
            raise RuntimeError("boom")

    runner.context["page_loader"] = _BoomLoader()

    from pd_ocr_labeler_spa.core.models import Project

    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=[tmp_path / f"p{i}.png" for i in range(3)],
        total_pages=3,
        ground_truth_map={},
    )
    project_state.set_loaded_project(project)

    # Must not raise.
    _prefetch_adjacent_pages(project_state, runner, settings, current_index=0)


def test_prefetch_silently_exits_when_no_project(tmp_path: Path) -> None:
    """Prefetch exits silently when no project is loaded."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)

    project_state: ProjectState = app.state.project_state
    runner = app.state.job_runner
    # No project loaded — project_state.loaded_project is None.
    assert project_state.loaded_project is None

    # Should not raise.
    _prefetch_adjacent_pages(project_state, runner, settings, current_index=0)


# ── Integration: GET /pages/{idx} schedules prefetch ─────────────────


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    # 4 pages so we can test idx+1 and idx+2.
    for i in range(1, 5):
        (proj / f"{i:03d}.png").write_bytes(b"\x89PNG\r\n")
    return root


def test_get_page_schedules_prefetch_by_default(tmp_path: Path, projects_root: Path) -> None:
    """GET /pages/0 schedules _prefetch_adjacent_pages when no_prefetch=False."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root, no_prefetch=False)
    app = build_app(settings)

    with patch("pd_ocr_labeler_spa.api.pages._prefetch_adjacent_pages") as mock_prefetch:
        with TestClient(app) as c:
            c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
            resp = c.get("/api/projects/book1/pages/0")
        assert resp.status_code == 200, resp.text

    # TestClient runs BackgroundTasks synchronously before the response
    # is returned to the caller, so mock_prefetch must have been called.
    assert mock_prefetch.called, "_prefetch_adjacent_pages was not scheduled"
    call_kwargs = mock_prefetch.call_args
    # current_index is the 4th positional arg (project_state, runner, settings, current_index).
    assert call_kwargs.args[3] == 0, "current_index should be 0"


def test_get_page_suppresses_prefetch_when_no_prefetch_true(tmp_path: Path, projects_root: Path) -> None:
    """GET /pages/0 does NOT schedule prefetch when no_prefetch=True."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root, no_prefetch=True)
    app = build_app(settings)

    with patch("pd_ocr_labeler_spa.api.pages._prefetch_adjacent_pages") as mock_prefetch:
        with TestClient(app) as c:
            c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
            resp = c.get("/api/projects/book1/pages/0")
        assert resp.status_code == 200, resp.text

    assert not mock_prefetch.called, "_prefetch_adjacent_pages must not be called when no_prefetch=True"

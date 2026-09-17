"""Shared fixtures for ``core/jobs/handlers`` unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from pdomain_pgdp_measure.profile_models import PageMeasurement, ProfileDiagnostic

from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner, JobStatus
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState

if TYPE_CHECKING:
    from pathlib import Path

    from pdomain_book_contracts.annotation import PageKind
    from pdomain_book_tools.ocr.page import Page
    from pdomain_pgdp_measure.profile_input import ProfileInputPage


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _blank_page(page_index: int) -> Page:
    """A page with no items — Task 2's handler tests exercise the measurement
    and detector-input wiring, not word geometry, which is Task 3's concern.
    """
    from pdomain_book_tools.ocr.page import Page

    return Page.from_dict(
        {
            "width": 200,
            "height": 300,
            "page_index": page_index,
            "bounding_box": _bbox(0, 0, 200, 300),
            "items": [],
        }
    )


def _stub_measure_fn(project_id: str, page: ProfileInputPage) -> PageMeasurement:
    """A valid but unavailable ``PageMeasurement`` — no image is ever decoded."""
    del project_id
    return PageMeasurement(
        page_name=page.name,
        source_path=page.source_path or f"book1/{page.name}",
        sha256=None,
        source_frame=None,
        image_mode=None,
        grayscale_threshold=None,
        foreground_pixels=None,
        foreground_bounds=None,
        margins=None,
        ink_bands=None,
        diagnostics=(ProfileDiagnostic(code="image_missing", message="test fixture"),),
    )


def _build_two_page_run(
    tmp_path: Path, *, reviewed_page_indices: tuple[int, ...]
) -> tuple[JobRunner, Job, ProjectState]:
    """Two loaded pages, a stub measure function, and a job ready to run.

    Only the pages listed in ``reviewed_page_indices`` are marked reviewed
    (page-kind confirmed); the rest carry no page-kind state at all, the same
    as a page nobody has run "Propose page kinds" over yet.
    """
    image_paths = [tmp_path / "000.png", tmp_path / "001.png"]
    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=len(image_paths),
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    reviewed = PageKindReviewedStore(project.project_root)
    for page_index in (0, 1):
        page = _blank_page(page_index)
        outcome = PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=page_index, page_record=outcome)
        pstate.page_id = uuid4()
        project_state._page_states[page_index] = pstate
        if page_index in reviewed_page_indices:
            reviewed.mark_reviewed(page_index, datetime.now(UTC).isoformat())

    context: dict[str, Any] = {
        "project_state": project_state,
        "propose_regions_measure_fn": _stub_measure_fn,
    }
    runner = JobRunner(JobEventBroker(), context=context)
    job = Job(
        job_id="proposal-run-ready-job",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job

    return runner, job, project_state


@pytest.fixture
def proposal_run_ready(tmp_path: Path) -> tuple[JobRunner, Job, ProjectState]:
    """A ``propose_regions`` run ready to execute: two loaded pages, both with a
    confirmed page kind, and a stub measure function wired into
    ``runner.context``.

    Yields ``(runner, job, project_state)``. The ``Job`` is registered in
    ``runner._jobs`` the way the existing tests at the bottom of
    ``tests/integration/test_region_proposals_router.py`` do it, mirroring
    ``runner._run_one``'s own bookkeeping.
    """
    return _build_two_page_run(tmp_path, reviewed_page_indices=(0, 1))


@pytest.fixture
def proposal_run_one_page_missing_kind(tmp_path: Path) -> tuple[JobRunner, Job, ProjectState]:
    """Like ``proposal_run_ready``, but only page 0 has page-kind state.

    Page 1 has no confirmed page kind and no page-kind proposal — the case
    the summary's "Skipped ... run Propose page kinds first" clause exists
    for.
    """
    return _build_two_page_run(tmp_path, reviewed_page_indices=(0,))


@pytest.fixture
def proposal_run_no_kind_state(tmp_path: Path) -> tuple[JobRunner, Job, ProjectState]:
    """Like ``proposal_run_ready``, but neither page has page-kind state.

    The handler's early-return path: no page has a proposed or confirmed
    page kind, so there is nothing to propose regions for.
    """
    return _build_two_page_run(tmp_path, reviewed_page_indices=())


class _LazyLoadPageLoader:
    """Fake ``PageLoader``: a fixed set of pages hit the labeled lane; every
    other page misses every lane. ``run_ocr`` always raises.

    Mirrors ``tests/integration/test_page_kinds_router.py``'s
    ``_FakePageLoader`` — an ``allow_ocr=False`` caller (here: the
    ``propose_regions`` handler's lazy-load pass over pages not yet in
    memory) must never reach ``run_ocr``.
    """

    def __init__(self, labeled_hits: dict[int, PageLoadOutcome]) -> None:
        self._labeled_hits = labeled_hits
        self.run_ocr_calls: list[int] = []
        self.load_labeled_calls: list[int] = []
        self.load_cached_calls: list[int] = []

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        self.load_labeled_calls.append(page_index)
        return self._labeled_hits.get(page_index)

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        self.load_cached_calls.append(page_index)
        return None

    def run_ocr(
        self,
        page_index: int,
        *,
        edited_image_bytes: bytes | None = None,
        page_kind: PageKind | None = None,
    ) -> PageLoadOutcome:
        self.run_ocr_calls.append(page_index)
        raise RuntimeError("run_ocr must never be called by propose_regions (allow_ocr=False)")


@pytest.fixture
def proposal_run_lazy_load(
    tmp_path: Path,
) -> tuple[JobRunner, Job, ProjectState, _LazyLoadPageLoader]:
    """A three-page book with no page in memory; two pages have stored OCR content.

    Mirrors a real book after a server restart, or one nobody has paged
    through yet: ``project_state.page_states`` starts empty. Pages 0 and 2
    are marked reviewed (page-kind confirmed) so they're eligible once
    loaded, and both hit the loader's labeled lane. Page 1 has neither
    stored content nor page-kind state — the "skipped, no OCR output yet"
    case.

    Yields ``(runner, job, project_state, loader)`` so a test can assert on
    ``loader.run_ocr_calls``.
    """
    image_paths = [tmp_path / f"{i:03d}.png" for i in range(3)]
    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=len(image_paths),
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    reviewed = PageKindReviewedStore(project.project_root)
    for page_index in (0, 2):
        reviewed.mark_reviewed(page_index, datetime.now(UTC).isoformat())

    labeled_hits = {
        page_index: PageLoadOutcome(
            page_index=page_index, source=PageSource.FILESYSTEM, payload=_blank_page(page_index)
        )
        for page_index in (0, 2)
    }
    loader = _LazyLoadPageLoader(labeled_hits)

    context: dict[str, Any] = {
        "project_state": project_state,
        "propose_regions_measure_fn": _stub_measure_fn,
        "page_loader": loader,
    }
    runner = JobRunner(JobEventBroker(), context=context)
    job = Job(
        job_id="proposal-run-lazy-load-job",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job

    return runner, job, project_state, loader


@pytest.fixture
def proposal_run_no_loader_with_unloaded_page(
    tmp_path: Path,
) -> tuple[JobRunner, Job, ProjectState]:
    """One page loaded and reviewed; a second page exists but is not in memory.

    No ``page_loader`` (nor the production context keys a loader would be
    built from) is wired — the fallback path that considers only pages
    already in memory, exactly as the handler behaved before it grew the
    lazy-load pass.
    """
    image_paths = [tmp_path / f"{i:03d}.png" for i in range(2)]
    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=len(image_paths),
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    reviewed = PageKindReviewedStore(project.project_root)
    reviewed.mark_reviewed(0, datetime.now(UTC).isoformat())

    page = _blank_page(0)
    outcome = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=0, page_record=outcome)
    pstate.page_id = uuid4()
    project_state._page_states[0] = pstate

    context: dict[str, Any] = {
        "project_state": project_state,
        "propose_regions_measure_fn": _stub_measure_fn,
    }
    runner = JobRunner(JobEventBroker(), context=context)
    job = Job(
        job_id="proposal-run-no-loader-job",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job

    return runner, job, project_state

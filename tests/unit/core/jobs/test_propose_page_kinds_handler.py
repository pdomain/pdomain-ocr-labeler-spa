"""Unit tests for the propose_page_kinds job handler."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pdomain_pgdp_measure.profile_models import CoordinateFrame, InkBand, PageMeasurement

from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.notifications import NotificationQueue
from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog
from pdomain_ocr_labeler_spa.core.project_state import ProjectState

_WIDTH = 1000
_HEIGHT = 1600


def _measured(page_name: str, *, first_band_top: int, bands: int = 24) -> PageMeasurement:
    """A minimal measured page, evenly banded from a given top.

    Mirrors pdomain-pgdp-measure's own ``tests/test_pgdp_page_templates.py::_page``.
    """
    ink_bands = tuple(
        InkBand(y_start=first_band_top + i * 40, y_end=first_band_top + i * 40 + 26) for i in range(bands)
    )
    bottom = ink_bands[-1].y_end
    return PageMeasurement(
        page_name=page_name,
        source_path=f"bookA/{page_name}",
        sha256="a" * 64,
        source_frame=CoordinateFrame(width=_WIDTH, height=_HEIGHT),
        image_mode="L",
        grayscale_threshold=127,
        foreground_pixels=1000,
        foreground_bounds=(80, first_band_top, 920, bottom),
        margins=(80, first_band_top, 80, _HEIGHT - bottom),
        ink_bands=ink_bands,
    )


def _project(tmp_path: Path, page_count: int) -> Project:
    image_paths = [tmp_path / f"{i:03d}.png" for i in range(page_count)]
    for path in image_paths:
        path.write_bytes(b"")
    return Project(
        project_id="bookA",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=page_count,
    )


def _runner_and_job(project: Project, tops: list[int]) -> tuple[JobRunner, Job]:
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    def _measure_fn(project_id: str, page: object) -> PageMeasurement:
        name = page.name
        index = int(name.split(".")[0])
        return _measured(name, first_band_top=tops[index])

    runner = JobRunner(
        JobEventBroker(),
        context={
            "project_state": project_state,
            "notification_queue": NotificationQueue(),
            "propose_page_kinds_measure_fn": _measure_fn,
        },
    )
    job = Job(job_id="j1", job_type="propose_page_kinds", created_at=datetime.now(UTC))
    return runner, job


async def test_a_steady_book_proposes_body_for_every_page(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds import (
        handle_propose_page_kinds,
    )

    # Deviation from the task-6 brief: the brief's tops were [300, 302, 298, 301].
    # pdomain-pgdp-measure's own template fit anchors each class on
    # median(tops) (page_templates._fit_template), so any jitter across pages
    # leaves a nonzero template_residual_px and confidence < 1.0 for most
    # pages — confirmed against the installed 0.1.0 library and mirrored by
    # its own test_normal_pages_score_full_confidence_on_an_exact_match,
    # which uses identical tops within a class to get confidence == 1.0.
    # Using identical tops here keeps the "a steady book proposes body with
    # full confidence" intent while matching real library behavior.
    project = _project(tmp_path, 4)
    runner, job = _runner_and_job(project, tops=[300, 300, 300, 300])

    await handle_propose_page_kinds(runner, job)

    proposal_log = PageKindProposalLog(project.project_root)
    runs = proposal_log.runs()
    assert len(runs) == 1
    proposals = proposal_log.proposals_for_run(runs[0].run_id)
    assert len(proposals) == 4
    assert all(p.kind.value == "body" for p in proposals)
    assert all(p.confidence == 1.0 for p in proposals)


async def test_a_sunk_page_proposes_chapter_opening(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds import (
        handle_propose_page_kinds,
    )

    project = _project(tmp_path, 5)
    runner, job = _runner_and_job(project, tops=[300, 302, 298, 301, 470])

    await handle_propose_page_kinds(runner, job)

    proposal = PageKindProposalLog(project.project_root).latest_proposal_for_page(4)
    assert proposal is not None
    assert proposal.kind.value == "chapter opening"


async def test_the_job_never_touches_the_page_blob(tmp_path: Path) -> None:
    """The page blob is only ever written by a human action — a classifier run is not one."""
    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds import (
        handle_propose_page_kinds,
    )

    project = _project(tmp_path, 3)
    runner, job = _runner_and_job(project, tops=[300, 302, 298])
    blobs_dir = project.project_root / ".pd-pages" / "blobs"

    await handle_propose_page_kinds(runner, job)

    assert not blobs_dir.exists()

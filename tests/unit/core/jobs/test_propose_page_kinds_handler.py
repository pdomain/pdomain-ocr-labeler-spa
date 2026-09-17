"""Unit tests for the propose_page_kinds job handler."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pdomain_pgdp_measure.page_templates import (
    BookTemplates,
    PageClassification,
    fit_book_templates,
)
from pdomain_pgdp_measure.page_templates import classify_pages as _real_classify_pages
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


def _runner_and_job(
    project: Project, tops: list[int], *, payload_project_id: str | None = None
) -> tuple[JobRunner, Job]:
    """A runner with *project* loaded, plus a job queued against it.

    ``payload_project_id`` defaults to the loaded project's own id, matching
    what the start route submits; pass a different one to simulate a book
    swapped in after the job was queued.
    """
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
    job = Job(
        job_id="j1",
        job_type="propose_page_kinds",
        created_at=datetime.now(UTC),
        payload={"project_id": payload_project_id or project.project_id},
    )
    # Register the job the way ``submit`` would, so ``update_progress`` finds
    # it and the handler's progress reports are observable via ``get_job``.
    runner._jobs[job.job_id] = job
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


async def test_a_jittered_book_threads_fractional_confidence_through_the_journal(
    tmp_path: Path,
) -> None:
    """The brief's original tops ([300, 302, 298, 301]) don't hit confidence
    1.0 (see the steady-book test above) — they hit a fraction strictly
    between 0 and 1, which still has to pass ``PageKindProposal.__post_init__``'s
    bound check and round-trip through the journal unchanged. Asserts the
    bound and the round-trip against an independently computed classification,
    not a pinned fractional number (that would tie the test to one library
    version's arithmetic).
    """
    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds import (
        handle_propose_page_kinds,
    )

    tops = [300, 302, 298, 301]
    project = _project(tmp_path, len(tops))
    runner, job = _runner_and_job(project, tops=tops)

    measured = [_measured(f"{i:03d}.png", first_band_top=top) for i, top in enumerate(tops)]
    expected = _real_classify_pages(measured, fit_book_templates(measured))

    await handle_propose_page_kinds(runner, job)

    proposal_log = PageKindProposalLog(project.project_root)
    proposals = {p.page_index: p for p in proposal_log.proposals_for_run(proposal_log.runs()[0].run_id)}
    assert len(proposals) == len(tops)
    assert all(p.kind.value == "body" for p in proposals.values())
    assert any(p.confidence is not None and 0.0 < p.confidence < 1.0 for p in proposals.values())
    for page_index, classification in enumerate(expected):
        assert proposals[page_index].confidence == classification.confidence


async def test_a_classify_pages_length_mismatch_raises_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``classify_pages`` preserving input order isn't a type-checked contract —
    if a future release ever filters or reorders results, ``page_index``
    recovery by position must fail loudly rather than silently mis-attribute
    proposals to the wrong page.

    ``classify_pages`` isn't currently an injectable seam on the runner
    context, so this monkeypatches the handler module's imported name rather
    than adding a second production seam just for this test.
    """
    import pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds as handler_module

    project = _project(tmp_path, 3)
    runner, job = _runner_and_job(project, tops=[300, 302, 298])

    def _classify_pages_dropping_one(
        pages: Sequence[PageMeasurement], templates: BookTemplates
    ) -> tuple[PageClassification, ...]:
        return _real_classify_pages(pages, templates)[:-1]

    monkeypatch.setattr(handler_module, "classify_pages", _classify_pages_dropping_one)

    with pytest.raises(RuntimeError) as exc_info:
        await handler_module.handle_propose_page_kinds(runner, job)
    assert "2" in str(exc_info.value)
    assert "3" in str(exc_info.value)


async def test_a_run_queued_for_another_book_refuses_to_classify_the_loaded_one(
    tmp_path: Path,
) -> None:
    """Jobs dequeue later than they are submitted, and a load in between swaps
    ``loaded_project``. Proposals are durable and book-scoped, so classifying
    whatever is loaded now would write one book's run into another book's
    journal. The handler must refuse rather than proceed.
    """
    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds import (
        handle_propose_page_kinds,
    )

    project = _project(tmp_path, 3)
    runner, job = _runner_and_job(project, tops=[300, 302, 298], payload_project_id="bookB")

    await handle_propose_page_kinds(runner, job)

    proposal_log = PageKindProposalLog(project.project_root)
    assert proposal_log.runs() == []
    assert not proposal_log.path.exists()

    reported = runner.get_job("j1")
    assert reported is not None
    assert "bookB" in reported.message
    assert "bookA" in reported.message


async def test_a_job_carrying_project_id_but_an_empty_payload_still_refuses_the_wrong_book(
    tmp_path: Path,
) -> None:
    """``Job.project_id`` is the typed field every submitter sets; the
    ``payload["project_id"]`` fallback must not be the only guard. A job
    whose payload omits the key entirely — the case with no guard at all
    before this fix — has to refuse just as surely as one that sets it.
    """
    from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds import (
        handle_propose_page_kinds,
    )
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner
    from pdomain_ocr_labeler_spa.core.notifications import NotificationQueue

    project = _project(tmp_path, 3)
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    def _measure_fn(project_id: str, page: object) -> PageMeasurement:
        name = page.name
        index = int(name.split(".")[0])
        return _measured(name, first_band_top=[300, 302, 298][index])

    runner = JobRunner(
        JobEventBroker(),
        context={
            "project_state": project_state,
            "notification_queue": NotificationQueue(),
            "propose_page_kinds_measure_fn": _measure_fn,
        },
    )
    job = Job(
        job_id="j1",
        job_type="propose_page_kinds",
        project_id="bookB",
        created_at=datetime.now(UTC),
        payload={},
    )
    runner._jobs[job.job_id] = job

    await handle_propose_page_kinds(runner, job)

    proposal_log = PageKindProposalLog(project.project_root)
    assert proposal_log.runs() == []
    assert not proposal_log.path.exists()

    reported = runner.get_job("j1")
    assert reported is not None
    assert "bookB" in reported.message
    assert "bookA" in reported.message


async def test_an_unmappable_page_class_proposes_unknown_without_a_confidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``PageKind.UNKNOWN`` is the classifier declining to answer, and
    ``PageKindProposal`` documents that a refusal carries no confidence. A
    ``page_class`` this handler has no mapping for — a future library value —
    must therefore drop the score rather than persist it against an answer
    that was never given.
    """
    import pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds as handler_module

    project = _project(tmp_path, 3)
    runner, job = _runner_and_job(project, tops=[300, 302, 298])

    def _classify_pages_with_a_future_class(
        pages: Sequence[PageMeasurement], templates: BookTemplates
    ) -> tuple[PageClassification, ...]:
        classified = _real_classify_pages(pages, templates)
        return (
            replace(classified[0], page_class="illustration_plate", confidence=0.87),
            *classified[1:],
        )

    monkeypatch.setattr(handler_module, "classify_pages", _classify_pages_with_a_future_class)

    await handler_module.handle_propose_page_kinds(runner, job)

    proposal = PageKindProposalLog(project.project_root).latest_proposal_for_page(0)
    assert proposal is not None
    assert proposal.kind.value == "unknown"
    assert proposal.confidence is None
    assert proposal.evidence["page_class"] == "illustration_plate"


async def test_the_runs_page_count_is_the_number_of_proposals_it_wrote(tmp_path: Path) -> None:
    """A persisted run whose ``page_count`` disagrees with how many proposals
    it wrote contradicts itself. ``total_pages`` is a separate field from the
    ``image_paths`` the run actually walks, so the count comes from the
    classifications.
    """
    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_page_kinds import (
        handle_propose_page_kinds,
    )

    project = _project(tmp_path, 3)
    # A project whose declared total disagrees with its own image list — the
    # run must report what it classified, not what the project claims.
    project.total_pages = 99
    runner, job = _runner_and_job(project, tops=[300, 302, 298])

    await handle_propose_page_kinds(runner, job)

    proposal_log = PageKindProposalLog(project.project_root)
    run = proposal_log.runs()[0]
    assert run.page_count == len(proposal_log.proposals_for_run(run.run_id)) == 3

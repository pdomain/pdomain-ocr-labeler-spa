"""propose_page_kinds job handler.

Spec authority: pdomain-ocr-synth's docs/specs/2026-09-07-region-provenance-and-persistence-
design.md "Page kind is classified per book, and it runs before regions".

The pass needs every page before it can classify any — ``fit_book_templates``
measures the whole book's first-band geometry before classifying a single
page against it — so it cannot run at page fetch; it is a book-scoped job.
Job rows live in memory and are lost on restart, so the run's durable record
is the ``PageKindProposalLog`` journal, not the job row: once the whole book
is classified, the handler appends the run and every page's proposal to that
journal in one pass, and treats the job row purely as progress reporting.
Nothing is journalled before classification finishes — a run that dies
part-way leaves no proposals behind.

This handler never touches ``Page.page_kind`` and never calls
``save_page_content_to_store`` — the page blob is only ever written by a
human action, and a classifier run is not one. Only the page-kind confirm
route does either.

Handler entry-point: ``handle_propose_page_kinds(runner, job)`` — registered
in ``core/jobs/runner._HANDLERS["propose_page_kinds"]``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from pdomain_book_contracts.annotation import PageKind
from pdomain_pgdp_measure.page_templates import (
    PAGE_TEMPLATE_METHOD,
    PageClassification,
    classify_pages,
    fit_book_templates,
)
from pdomain_pgdp_measure.profile_input import ProfileInputPage
from pdomain_pgdp_measure.profile_models import PageMeasurement
from pdomain_pgdp_measure.profiling import profile_page

from ...notifications import NotificationKind, NotificationQueue
from ...page_kind.models import PageKindProposal, PageKindProposalRun
from ...page_kind.proposal_log import PageKindProposalLog
from ...project_state import ProjectState

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)


class _MeasurePageFn(Protocol):
    def __call__(self, project_id: str, page: ProfileInputPage) -> PageMeasurement: ...


# pdomain-pgdp-measure.page_templates.PageClass values -> PageKind. Not a
# vocabulary merge: PageClass is a measured signal that only ever proposes,
# never decides, what a page is. See the spec's "Three page vocabularies
# already exist, and they are different axes".
_PAGE_CLASS_TO_KIND: dict[str, PageKind] = {
    "normal_recto": PageKind.BODY,
    "normal_verso": PageKind.BODY,
    "chapter_opening": PageKind.CHAPTER_OPENING,
    "unknown": PageKind.UNKNOWN,
}


def _get_required_context(
    runner: JobRunner,
) -> tuple[ProjectState, NotificationQueue, _MeasurePageFn]:
    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    notification_queue = ctx.get("notification_queue")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("propose_page_kinds: runner.context['project_state'] is not wired")
    if not isinstance(notification_queue, NotificationQueue):
        raise RuntimeError("propose_page_kinds: runner.context['notification_queue'] is not wired")
    # Test injection point, mirroring auto_rotate_all's "auto_rotate_ocr_fn" —
    # production always measures the real image on disk via profile_page.
    measure_fn: _MeasurePageFn = ctx.get("propose_page_kinds_measure_fn") or profile_page
    return project_state, notification_queue, measure_fn


def _to_kind_and_confidence(classification: PageClassification) -> tuple[PageKind, float | None]:
    """Map one measured classification onto a proposal's ``kind`` + ``confidence``.

    ``PageKind.UNKNOWN`` is the classifier declining to say — either because it
    said so itself (``page_class == "unknown"``) or because it returned a class
    this mapping does not know. ``PageKindProposal`` documents that a refusal
    carries no confidence at all, so a refusal's confidence is dropped rather
    than persisted as a real score for an answer that was never given.
    """
    kind = _PAGE_CLASS_TO_KIND.get(classification.page_class, PageKind.UNKNOWN)
    if kind is PageKind.UNKNOWN:
        return kind, None
    return kind, classification.confidence


async def handle_propose_page_kinds(runner: JobRunner, job: Job) -> None:
    """Classify every page of the active project's book and record proposals."""
    project_state, notification_queue, measure_fn = _get_required_context(runner)
    project = project_state.loaded_project
    if project is None:
        await runner.update_progress(job.job_id, current=0, total=0, message="No project loaded")
        return

    # The run was queued against one book; whoever dequeues it may find a
    # different one loaded (the start route sets both ``Job.project_id`` and
    # ``payload["project_id"]``, and a load in between swaps
    # ``loaded_project``). Proposals are durable and book-scoped, so
    # classifying whatever happens to be loaded now would write book A's run
    # into book B's journal. Refuse instead, reported the same way as the
    # no-project-loaded case. ``Job.project_id`` is the typed field every
    # submitter sets; the untyped payload key is only a fallback for a
    # submitter that omitted it.
    submitted_project_id = job.project_id
    if submitted_project_id is None:
        payload_project_id = job.payload.get("project_id")
        submitted_project_id = payload_project_id if isinstance(payload_project_id, str) else None
    if submitted_project_id is not None and submitted_project_id != project.project_id:
        log.warning(
            "propose_page_kinds: job=%s was queued for project=%s but project=%s is loaded — refusing",
            job.job_id,
            submitted_project_id,
            project.project_id,
        )
        await runner.update_progress(
            job.job_id,
            current=0,
            total=0,
            message=(
                f"Project changed since this run was queued: "
                f"expected {submitted_project_id}, found {project.project_id}"
            ),
        )
        return

    total = project.total_pages
    log.info("propose_page_kinds: project=%s pages=%d job=%s", project.project_id, total, job.job_id)
    await runner.update_progress(job.job_id, current=0, total=total, message=f"Measuring {total} page(s)")

    measured: list[PageMeasurement] = []
    for page_index, image_path in enumerate(project.image_paths):
        input_page = ProfileInputPage(
            name=image_path.name,
            image_path=image_path,
            source_path=f"{project.project_id}/{image_path.name}",
        )
        # ``profile_page`` decodes the image and scans it with numpy — CPU-bound
        # work that would block the one event loop for the whole book. Offload
        # it the way every other image-touching handler does (``reload_ocr``,
        # ``rotate``, ``auto_rotate_all``) so the confirm route and this job's
        # own SSE progress stream keep being served while the run proceeds.
        measured.append(await asyncio.to_thread(measure_fn, project.project_id, input_page))
        await runner.update_progress(
            job.job_id,
            current=page_index + 1,
            total=total,
            message=f"Measured page {page_index + 1}/{total}",
        )

    templates = fit_book_templates(measured)
    # classify_pages preserves input order, so enumerate() recovers page_index
    # without depending on page_name uniqueness. That order-preservation is
    # documented behavior, not a type-checked contract, so the length check
    # below is what makes relying on it safe: a future release that filters
    # or reorders results fails loudly here instead of silently attributing
    # every proposal after the first divergence to the wrong page.
    classifications = classify_pages(measured, templates)
    if len(classifications) != len(measured):  # explicit to survive -O
        raise RuntimeError(
            "propose_page_kinds: classify_pages returned "
            f"{len(classifications)} classification(s) for {len(measured)} measured "
            "page(s) — page_index recovery by position is no longer safe"
        )

    run = PageKindProposalRun(
        run_id=uuid.uuid4().hex,
        model_id="pgdp-measure/page-templates",
        model_version=PAGE_TEMPLATE_METHOD,
        created_at=datetime.now(UTC).isoformat(),
        # The pages this run actually classified, not the project's page total.
        # They are the same number today, but the proposals come from walking
        # ``image_paths`` while ``total_pages`` is a separate field — a run
        # whose page_count disagrees with how many proposals it wrote is a
        # record that contradicts itself.
        page_count=len(classifications),
    )
    proposals: list[PageKindProposal] = []
    for page_index, classification in enumerate(classifications):
        kind, confidence = _to_kind_and_confidence(classification)
        proposals.append(
            PageKindProposal(
                proposal_id=uuid.uuid4().hex,
                run_id=run.run_id,
                page_index=page_index,
                kind=kind,
                confidence=confidence,
                evidence={
                    "page_class": classification.page_class,
                    "template_residual_px": classification.template_residual_px,
                },
            )
        )

    proposal_log = PageKindProposalLog(project.project_root)
    proposal_log.append_run(run)
    proposal_log.append_proposals(proposals)

    job.payload["run_id"] = run.run_id
    job.payload["proposal_count"] = len(proposals)
    notification_queue.queue(
        NotificationKind.POSITIVE,
        f"Proposed page kinds for {len(proposals)} page(s) in project {project.project_id}.",
    )


__all__ = ["handle_propose_page_kinds"]

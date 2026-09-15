"""propose_page_kinds job handler.

Spec authority: pdomain-ocr-synth's docs/specs/2026-09-07-region-provenance-and-persistence-
design.md "Page kind is classified per book, and it runs before regions".

The pass needs every page before it can classify any — ``fit_book_templates``
measures the whole book's first-band geometry before classifying a single
page against it — so it cannot run at page fetch; it is a book-scoped job.
Job rows live in memory and are lost on restart, so this handler writes each
page's proposal durably via ``PageKindProposalLog`` as it goes, and treats
the job row purely as progress reporting.

This handler never touches ``Page.page_kind`` and never calls
``save_page_content_to_store`` — the page blob is only ever written by a
human action, and a classifier run is not one. Only the page-kind confirm
route does either.

Handler entry-point: ``handle_propose_page_kinds(runner, job)`` — registered
in ``core/jobs/runner._HANDLERS["propose_page_kinds"]``.
"""

from __future__ import annotations

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


def _to_kind(classification: PageClassification) -> PageKind:
    return _PAGE_CLASS_TO_KIND.get(classification.page_class, PageKind.UNKNOWN)


async def handle_propose_page_kinds(runner: JobRunner, job: Job) -> None:
    """Classify every page of the active project's book and record proposals."""
    project_state, notification_queue, measure_fn = _get_required_context(runner)
    project = project_state.loaded_project
    if project is None:
        await runner.update_progress(job.job_id, current=0, total=0, message="No project loaded")
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
        measured.append(measure_fn(project.project_id, input_page))
        await runner.update_progress(
            job.job_id,
            current=page_index + 1,
            total=total,
            message=f"Measured page {page_index + 1}/{total}",
        )

    templates = fit_book_templates(measured)
    # classify_pages preserves input order, so zipping with range(total)
    # recovers page_index without depending on page_name uniqueness.
    classifications = classify_pages(measured, templates)

    run = PageKindProposalRun(
        run_id=uuid.uuid4().hex,
        model_id="pgdp-measure/page-templates",
        model_version=PAGE_TEMPLATE_METHOD,
        created_at=datetime.now(UTC).isoformat(),
        page_count=total,
    )
    proposals = [
        PageKindProposal(
            proposal_id=uuid.uuid4().hex,
            run_id=run.run_id,
            page_index=page_index,
            kind=_to_kind(classification),
            confidence=classification.confidence,
            evidence={
                "page_class": classification.page_class,
                "template_residual_px": classification.template_residual_px,
            },
        )
        for page_index, classification in enumerate(classifications)
    ]

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

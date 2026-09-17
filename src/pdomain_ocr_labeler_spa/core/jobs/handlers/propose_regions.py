"""``propose_regions`` job handler — book-scoped region proposal run.

Iterates every currently-loaded page whose page kind has been proposed or
confirmed — reading that state itself from the page-kind stores, never
trusting a caller's say-so — snapshots each such page's facet digests so the
run can be traced to the exact facets it read, calls the injected (or default
no-op) detector, and appends whatever it returns to the proposal journal.
Never calls ``save_page_content_to_store`` or ``save_page_to_store`` — a
proposal run is a machine's claim, and the page blob is only ever written by
a human action.

Three invariants mirror ``propose_page_kinds`` (its own handler fixed the
same defects in commit ``8cb5a58``, plus the lease below in the same change
that added it here):

- **Pinned to its book.** The run was queued against one project; whoever
  dequeues it may find a different one loaded (a load in between swaps
  ``ProjectState.loaded_project``). Proposals are durable and book-scoped, so
  running against whatever happens to be loaded now would write one book's
  run into another book's journal. The handler refuses instead, the same way
  ``propose_page_kinds`` does.
- **Off the event loop.** The book measurement pass (``core/page_measurement.
  measure_book``, shared with ``propose_page_kinds``) decodes every page's
  image and scans it with numpy, and a detector reads word boxes and line
  structure over a whole page — CPU-bound work that would stall every
  request, including this job's own SSE progress stream, if run inline for a
  400-page book. ``detector(detector_input)`` and the per-page facet-digest
  snapshot (which does page-store I/O to read the image digest) are both
  offloaded via ``asyncio.to_thread``, the same pattern ``propose_page_kinds``
  uses for ``profile_page``.
- **Read through a verified lease.** ``detector(detector_input)`` is called
  with a per-page lease held (``core/jobs/handlers/_labeling_page_lease.
  leased_labeling_page``) — on a book-labeling project this is what makes
  ``ProjectState.labeling_image_path`` resolve to the sealed
  ``/proc/self/fd/N`` descriptor instead of raising, and what a real detector
  that reads the page image must see rather than the raw manifest path.
  Held unconditionally, even for the default no-op detector: the seam exists
  to be swapped by slice 4's real detector, and a conditional lease would be
  wrong the moment it is. A page whose lease fails to verify is logged and
  skipped, the same as ``propose_page_kinds`` — both during the book
  measurement pass and, separately, around the detector call itself.

The page-kind journals are each read in full, once, up front — not once per
page. ``PageKindReviewedStore.reviewed_page_indices`` returns every reviewed
page index from one read, so the eligibility loop and
``page_kind_was_confirmed``'s second pass both consult that one set rather
than re-parsing the journal per page. ``PageKindProposalLog`` is read the
same way, via ``runs()`` plus ``proposals_for_run(run_id)`` — one read per
run, not one per page — so the proposed-page-index set is built from that,
rather than the plan's per-page ``latest_proposal_for_page`` calls.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from eventsourcing.application import AggregateNotFoundError
from pdomain_book_tools.ocr.page import Page
from pdomain_pgdp_measure.profiling import profile_page

from ...page_kind.proposal_log import PageKindProposalLog
from ...page_kind.reviewed_store import PageKindReviewedStore
from ...page_measurement import measure_book
from ...project_state import PageState, ProjectState
from ...regions.block_adapter import compute_page_facet_digests
from ...regions.detector import BookFittedDetector, DetectorInput, null_region_detector
from ...regions.models import ProposalRun, RegionProposal
from ...regions.proposal_log import RegionProposalLog
from ._labeling_page_lease import leased_labeling_page

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from ...page_kind.models import PageKindProposalRun
    from ...page_measurement import MeasuredBook, MeasurePageFn
    from ...persistence.page_store import LabelerPageStore
    from ...regions.detector import DetectedRegion, RegionDetector
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)

#: A geometry detector reads word boxes, line/paragraph structure, and the
#: page image — never OCR/ground-truth text — so a text-only edit never
#: invalidates its proposals (spec §"A proposal goes stale per facet, not per
#: page"). Slice 4's real detector may narrow this; this scaffolding detector
#: proposes nothing, so a conservative default is safe here.
_GEOMETRY_FACETS = frozenset({"word_boxes", "line_structure", "page_image"})


def _get_required_context(runner: JobRunner) -> tuple[ProjectState, LabelerPageStore | None]:
    """Pull ``project_state`` and the optional ``page_store`` off ``runner.context``."""
    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("propose_regions: runner.context['project_state'] is not wired")
    page_store = ctx.get("page_store")
    return project_state, page_store


def _resolve_live_page(pstate: PageState) -> Page | None:
    """Narrow ``PageState.page_record.payload`` (typed ``object``) to a real ``Page``.

    Mirrors ``api.words._resolve_page_object``'s ``isinstance`` narrowing,
    duplicated locally rather than imported — a core job handler importing
    from an ``api`` route module would be a layering violation.
    """
    if pstate.page_record is None:
        return None
    payload = pstate.page_record.payload
    return payload if isinstance(payload, Page) else None


def _image_digest(page_store: LabelerPageStore | None, page_id: UUID | None) -> str | None:
    """Best-effort image-facet digest, read off the page's provenance chain."""
    if page_store is None or page_id is None:
        return None
    try:
        agg = page_store.get_page(page_id)
    except AggregateNotFoundError:
        log.warning("propose_regions: no page aggregate for page_id=%s; omitting page_image facet", page_id)
        return None
    head = agg.record.provenance.head if agg.record.provenance else None
    if head is None or not head.blob_refs:
        return None
    return head.blob_refs[1] if len(head.blob_refs) > 1 else head.blob_refs[0]


def _compute_page_facets(
    page_store: LabelerPageStore | None, page: Page, page_id: UUID | None
) -> dict[str, str]:
    """Image digest plus facet digests for one page — the unit offloaded to a thread."""
    image_digest = _image_digest(page_store, page_id)
    return compute_page_facet_digests(page, image_digest=image_digest)


def _proposed_page_indices(
    proposal_log: PageKindProposalLog, kind_runs: Sequence[PageKindProposalRun]
) -> set[int]:
    """Every page index any page-kind run has proposed a kind for.

    Takes the already-read ``runs()`` result rather than reading it again, and
    calls ``proposals_for_run`` once per run — bounded by the number of
    proposal runs, which is book-scoped and small, not by page count.
    """
    indices: set[int] = set()
    for run in kind_runs:
        indices.update(p.page_index for p in proposal_log.proposals_for_run(run.run_id))
    return indices


def _positions_by_page_index(page_indices: Sequence[int]) -> dict[int, int]:
    """Map each measured page's index to its position in the measured sequence.

    A page skipped for a failed lease is absent from the measurements, so
    position and page index diverge. Joining by value rather than by position
    is what keeps one page's geometry off another page. Built once per run
    rather than scanned per page: a linear search inside the detector loop
    makes the join quadratic in the book's page count.
    """
    return {page_index: position for position, page_index in enumerate(page_indices)}


def _book_fit_inputs(
    eligible_indices: Sequence[int],
    project_state: ProjectState,
    measured: MeasuredBook,
    measured_positions: Mapping[int, int],
) -> list[DetectorInput]:
    """One ``DetectorInput`` per eligible page that has both a live page and a measurement.

    Needs no image read and no lease — a ``DetectorInput`` is just the page
    object already held in memory plus the measurement data ``measure_book``
    already produced. A page with no live page object, or whose lease failed
    during the measurement pass (so it has no entry in ``measured_positions``),
    is left out of the book a ``BookFittedDetector.fit`` sees, the same as it
    is left out of the per-page detection loop below.
    """
    inputs: list[DetectorInput] = []
    for idx in eligible_indices:
        pstate = project_state.page_states[idx]
        page = _resolve_live_page(pstate)
        if page is None:
            continue
        measured_at = measured_positions.get(idx)
        if measured_at is None:
            continue
        inputs.append(
            DetectorInput(
                page=page,
                page_index=idx,
                measurement=measured.measurements[measured_at],
                classification=measured.classifications[measured_at],
                templates=measured.templates,
            )
        )
    return inputs


async def handle_propose_regions(runner: JobRunner, job: Job) -> None:
    project_state, page_store = _get_required_context(runner)
    project = project_state.loaded_project
    if project is None:
        await runner.update_progress(job.job_id, current=0, total=0, message="No project loaded")
        return

    # The run was queued against one book; whoever dequeues it may find a
    # different one loaded (the start route sets ``payload["project_id"]``,
    # and a load in between swaps ``loaded_project``). Proposals are durable
    # and book-scoped, so proposing regions for whatever happens to be loaded
    # now would write book A's run into book B's journal. Refuse instead —
    # the same defect ``propose_page_kinds`` was fixed for in 8cb5a58.
    submitted_project_id = job.payload.get("project_id")
    if isinstance(submitted_project_id, str) and submitted_project_id != project.project_id:
        log.warning(
            "propose_regions: job=%s was queued for project=%s but project=%s is loaded — refusing",
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

    page_indices = sorted(
        idx for idx, pstate in project_state.page_states.items() if pstate.page_record is not None
    )
    if not page_indices:
        await runner.update_progress(job.job_id, current=0, total=0, message="No pages loaded")
        return

    # The job reads page-kind state itself rather than trusting a caller's
    # say-so — a request field the handler never checked would let a caller
    # propose regions for a book whose page kinds were never proposed or
    # confirmed, silently breaking the ordering the design depends on. Both
    # journals are read in full up front, not once per page — see the module
    # docstring.
    page_kind_proposals = PageKindProposalLog(project.project_root)
    page_kind_reviewed = PageKindReviewedStore(project.project_root)
    kind_runs = page_kind_proposals.runs()
    proposed_page_indices = _proposed_page_indices(page_kind_proposals, kind_runs)
    reviewed_page_indices = page_kind_reviewed.reviewed_page_indices()

    def _is_kind_confirmed(idx: int) -> bool:
        """A page's kind is confirmed when the live page carries one, or a person reviewed it.

        ``reviewed_page_indices`` is the whole journal's reviewed-page set,
        read once up front (see the module docstring), so this is a set
        lookup rather than a second full-file read of the reviewed-store
        journal.
        """
        pstate = project_state.page_states[idx]
        page = _resolve_live_page(pstate)
        return (page is not None and page.page_kind is not None) or idx in reviewed_page_indices

    eligible_indices: list[int] = []
    skipped_indices: list[int] = []
    for idx in page_indices:
        has_kind_state = _is_kind_confirmed(idx) or idx in proposed_page_indices
        (eligible_indices if has_kind_state else skipped_indices).append(idx)

    total = len(eligible_indices)
    if total == 0:
        await runner.update_progress(
            job.job_id,
            current=0,
            total=0,
            message="No page has a proposed or confirmed page kind; nothing to propose regions for",
        )
        return

    # ``.get(...)`` returns ``Any`` here (``runner.context: dict[str, Any]``), same
    # as ``propose_page_kinds``'s ``measure_fn`` injection seam — assigned straight
    # into the annotated variable rather than narrowed via ``callable()``, which
    # would synthesize a mismatched call signature against ``RegionDetector``.
    #
    # This is the raw injected object, not yet the per-page callable the loop
    # below calls. A ``BookFittedDetector`` (isinstance-checked once the book
    # is measured, below) needs the whole book before it can judge any one
    # page; a plain ``RegionDetector`` callable is used exactly as it always
    # was.
    ctx: dict[str, Any] = runner.context
    raw_detector: RegionDetector | BookFittedDetector = ctx.get("region_detector") or null_region_detector

    # The detector needs the book, not just one page: where the head band
    # belongs and how wide the text block is are book-level facts. Measure the
    # whole volume the way propose_page_kinds does, through the same shared
    # pass — see core/page_measurement.py.
    measure_fn: MeasurePageFn = ctx.get("propose_regions_measure_fn") or profile_page

    # A run has two phases: measure every page of the book, then detect over the
    # eligible ones. They have different page counts, so reporting each against
    # its own denominator makes ``progress_total`` change mid-run and
    # ``progress_current`` reset to zero — a progress bar that goes backwards.
    # Both phases report against one combined total instead, so progress only
    # ever moves forward.
    measure_total = len(project.image_paths)
    combined_total = measure_total + total

    async def _report_measured(current: int, total_pages: int) -> None:
        await runner.update_progress(
            job.job_id,
            current=current,
            total=combined_total,
            message=f"Measuring page {current}/{total_pages}",
        )

    measured = await measure_book(
        project,
        project_state=project_state,
        measure_fn=measure_fn,
        on_page_measured=_report_measured,
    )

    page_facet_digests: dict[int, dict[str, str]] = {}
    for idx in eligible_indices:
        pstate = project_state.page_states[idx]
        page = _resolve_live_page(pstate)
        if page is None:
            continue
        # Reads the page-store's provenance graph (page-store I/O) plus walks
        # the page's word/line tree — offloaded so a book-scoped run of many
        # pages doesn't stall the event loop for the duration of the pass.
        page_facet_digests[idx] = await asyncio.to_thread(
            _compute_page_facets, page_store, page, pstate.page_id
        )

    run_id = uuid.uuid4().hex
    run = ProposalRun(
        run_id=run_id,
        model_id=str(job.payload.get("model_id", "null-detector")),
        model_version=str(job.payload.get("model_version", "0.0.0")),
        created_at=datetime.now(UTC).isoformat(),
        page_facet_digests=page_facet_digests,
        depends_on=_GEOMETRY_FACETS,
        page_kind_decision_ref=kind_runs[-1].run_id if kind_runs else None,
        page_kind_was_confirmed=all(_is_kind_confirmed(idx) for idx in eligible_indices),
    )

    proposal_log = RegionProposalLog(project.project_root)
    proposal_log.append_run(run)

    if skipped_indices:
        log.info(
            "propose_regions: run=%s project=%s skipped %d page(s) with no page-kind state: %s",
            run_id,
            project.project_id,
            len(skipped_indices),
            skipped_indices,
        )

    measured_positions = _positions_by_page_index(measured.page_indices)

    # A ``BookFittedDetector`` needs the whole book before it can judge any
    # one page — the same "fit the whole book once" shape ``measure_book``
    # already applies for templates. Building the per-page inputs needs no
    # image read and no lease (see ``_book_fit_inputs``); only ``fit`` itself
    # is CPU-bound (it walks every word box in the book), so only that call
    # is offloaded. A plain callable skips this branch entirely and is used
    # exactly as it always was.
    detector: RegionDetector
    if isinstance(raw_detector, BookFittedDetector):
        fit_inputs = _book_fit_inputs(eligible_indices, project_state, measured, measured_positions)
        try:
            detector = await asyncio.to_thread(raw_detector.fit, fit_inputs)
        except Exception:
            # A whole-book fit failure is not one page's problem to isolate —
            # unlike a per-page detector call, there is no single bad page to
            # skip. Falling back to the no-op detector keeps the run from
            # crashing and keeps its log loud, rather than guessing at a
            # detector-specific fixed-share fallback the handler has no
            # business knowing about (the seam is deliberately
            # detector-agnostic — see DetectorInput's own docstring).
            log.exception(
                "propose_regions: run=%s project=%s detector.fit raised on %d page(s) of "
                "book-fit input; proposing nothing for the rest of this run",
                run_id,
                project.project_id,
                len(fit_inputs),
            )
            detector = null_region_detector
    else:
        detector = raw_detector

    await runner.update_progress(
        job.job_id,
        current=measure_total,
        total=combined_total,
        message=f"Proposing regions for {total} page(s)",
    )
    proposal_count = 0
    lease_failed_indices: list[int] = []
    detector_failed_indices: list[int] = []
    for i, idx in enumerate(eligible_indices, start=1):
        pstate = project_state.page_states[idx]
        page = _resolve_live_page(pstate)
        if page is not None:
            # A detector reads the page image on a book-labeling project only
            # through a verified per-page lease — reading
            # ``project.image_paths`` directly would bypass the manifest hash
            # pin the same way the defect this fixes did for
            # ``propose_page_kinds``. Held unconditionally, even for the
            # default no-op detector: the seam exists to be swapped by slice
            # 4's real detector, and a conditional lease would be wrong the
            # moment it is.
            #
            # The lease is entered through an ``ExitStack`` rather than a
            # ``with`` inside a ``try``, so only ``open_labeling_page``'s own
            # ``ValueError`` is attributed to the lease. A detector is
            # entitled to raise ``ValueError`` of its own — slice 4's reads
            # ``Page.is_content_normalized``, which raises on a page mixing
            # normalized and pixel word boxes — and reporting that as a
            # failed lease would send the next reader looking at the manifest
            # instead of the page.
            stack = ExitStack()
            detected: Sequence[DetectedRegion] | None
            try:
                stack.enter_context(leased_labeling_page(project_state, idx))
            except ValueError as exc:
                lease_failed_indices.append(idx)
                log.warning(
                    "propose_regions: skipping page=%d — could not open a verified page lease: %s",
                    idx,
                    exc,
                )
                detected = None
            else:
                with stack:
                    # Map the page index to its measurement through
                    # page_indices, never by position: a page skipped for a
                    # failed lease during the measurement pass opens a gap,
                    # and taking measurements[idx] would hand page 7's
                    # geometry to page 3.
                    measured_at = measured_positions.get(idx)
                    if measured_at is None:
                        log.warning(
                            "propose_regions: page=%d has no book measurement (its "
                            "lease failed during the measurement pass); skipping the "
                            "detector for it",
                            idx,
                        )
                        detected = None
                    else:
                        detector_input = DetectorInput(
                            page=page,
                            page_index=idx,
                            measurement=measured.measurements[measured_at],
                            classification=measured.classifications[measured_at],
                            templates=measured.templates,
                        )
                        try:
                            # CPU-bound in the general case — slice 4's
                            # furniture detector walks every word box on the
                            # page. Offloaded for the same reason the
                            # facet-digest snapshot is; the lease stays bound
                            # for the duration of the offloaded call, since
                            # ``asyncio.to_thread`` propagates the contextvar
                            # the binding uses.
                            detected = await asyncio.to_thread(detector, detector_input)
                        except Exception:
                            # The detector is a swap-in callable from
                            # ``runner.context``, so its failures are not this
                            # handler's bugs to distinguish. One bad page must
                            # not kill a 400-page run, and the traceback is
                            # logged rather than swallowed, so a broken
                            # detector is still loud.
                            detector_failed_indices.append(idx)
                            log.exception("propose_regions: detector raised on page=%d; skipping it", idx)
                            detected = None
            if detected:
                proposals = [
                    RegionProposal(
                        proposal_id=uuid.uuid4().hex,
                        run_id=run_id,
                        page_index=idx,
                        role=d.role,
                        box=d.box,
                        confidence=d.confidence,
                        evidence=d.evidence,
                    )
                    for d in detected
                ]
                proposal_log.append_proposals(proposals)
                proposal_count += len(proposals)
        await runner.update_progress(
            job.job_id, current=measure_total + i, total=combined_total, message=f"page {idx}"
        )

    if lease_failed_indices:
        log.warning(
            "propose_regions: run=%s project=%s skipped %d page(s) with no verified lease: %s",
            run_id,
            project.project_id,
            len(lease_failed_indices),
            lease_failed_indices,
        )

    if detector_failed_indices:
        log.warning(
            "propose_regions: run=%s project=%s detector raised on %d page(s): %s",
            run_id,
            project.project_id,
            len(detector_failed_indices),
            detector_failed_indices,
        )

    log.info(
        "propose_regions: run=%s project=%s pages=%d proposals=%d",
        run_id,
        project.project_id,
        total,
        proposal_count,
    )


__all__ = ["handle_propose_regions"]

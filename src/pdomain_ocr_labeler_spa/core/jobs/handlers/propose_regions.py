"""``propose_regions`` job handler — book-scoped region proposal run.

Considers every page of the book, whether or not it is already in memory —
reading page-kind state itself from the page-kind stores, never trusting a
caller's say-so — snapshots each eligible page's facet digests so the run can
be traced to the exact facets it read, calls the injected (or default no-op)
detector, and appends whatever it returns to the proposal journal. Never
calls ``save_page_content_to_store`` or ``save_page_to_store`` — a proposal
run is a machine's claim, and the page blob is only ever written by a human
action.

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

**Pages load lazily.** A page only enters ``project_state.page_states`` once
someone opens it — after a server restart, or on a book nobody has paged
through yet, that dict can be empty even though every page has stored OCR
content. Before eligibility is computed, every page index of the book not
already carrying a ``page_record`` is loaded through ``core.page_state.
ensure_page_model`` with ``allow_ocr=False``: labeled → cached precedence
only, never OCR — a proposal run is read-only over what OCR has already
produced, the same restriction the bulk page-kind confirm route
(``api/page_kinds.py``'s ``_bulk_page_loader`` / ``_NullPageLoader``) applies
for the same reason. A page with no stored or cached content yet is skipped
and counted in the run's summary. ``ensure_page_model`` takes the project
lock and may read the store, so each call is offloaded via
``asyncio.to_thread``, run before the measurement pass so it never competes
with ``combined_total`` for a progress slot of its own — see
``_get_page_loader``'s docstring for where the loader comes from. A core job
handler must not import from the ``api`` package (a layering rule the tests
enforce), so this cannot call ``api.pages._build_page_loader_from_context``
directly; ``_get_page_loader`` duplicates that function's production-path
construction instead, mirroring ``core/jobs/handlers/reload_ocr.py``'s own
``_get_page_loader``. When no loader is available at all (no project
context wired), the run falls back to considering only pages already in
memory — today's behavior — and logs it.

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

from ....settings import Settings
from ...labeler_sidecars import LegacyTypographyPayloadError
from ...page_kind.proposal_log import PageKindProposalLog
from ...page_kind.reviewed_store import PageKindReviewedStore
from ...page_measurement import measure_book
from ...page_state import ensure_page_model
from ...project_state import PageState, ProjectState
from ...regions.block_adapter import compute_page_facet_digests, confirmed_regions_from_page
from ...regions.decision_log import RegionDecisionLog
from ...regions.detector import BookFittedDetector, DetectorInput, null_region_detector
from ...regions.models import Disposition, ProposalRun, RegionDecision, RegionProposal
from ...regions.proposal_log import RegionProposalLog
from ._labeling_page_lease import leased_labeling_page

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from ...models import Project
    from ...ocr.predictor import PredictorCache
    from ...ocr_config_state import OCRConfigCarrier
    from ...page_kind.models import PageKindProposalRun
    from ...page_measurement import MeasuredBook, MeasurePageFn
    from ...page_state import PageLoader
    from ...persistence.page_store import LabelerPageStore
    from ...regions.detector import DetectedRegion, RegionDetector
    from ...regions.models import ResolvedRegion
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)

#: A geometry detector reads word boxes, line/paragraph structure, and the
#: page image — never OCR/ground-truth text — so a text-only edit never
#: invalidates its proposals (spec §"A proposal goes stale per facet, not per
#: page"). Slice 4's real detector may narrow this; this scaffolding detector
#: proposes nothing, so a conservative default is safe here.
_GEOMETRY_FACETS = frozenset({"word_boxes", "line_structure", "page_image"})

#: Minimum box intersection-over-union for a new proposal to carry a person's
#: earlier confirmation forward (spec §"Decisions must carry across runs
#: first, or the queue fills with work already done"). Uncalibrated starting
#: value, per the owner ruling this implements — not derived from data.
_CARRY_IOU_THRESHOLD = 0.7


def _get_required_context(runner: JobRunner) -> tuple[ProjectState, LabelerPageStore | None]:
    """Pull ``project_state`` and the optional ``page_store`` off ``runner.context``."""
    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("propose_regions: runner.context['project_state'] is not wired")
    page_store = ctx.get("page_store")
    return project_state, page_store


def _get_page_loader(
    runner: JobRunner,
    project_state: ProjectState,
    page_store: LabelerPageStore | None,
) -> PageLoader | None:
    """The ``PageLoader`` used to lazily load a page not yet in memory, or ``None``.

    Mirrors ``core/jobs/handlers/reload_ocr.py``'s ``_get_page_loader`` (see
    that module's docstring, ~lines 27-51): a core job handler must not
    import from the ``api`` package, so this cannot call
    ``api.pages._build_page_loader_from_context`` and instead duplicates its
    production-path construction, the same way ``reload_ocr.py`` does.

    1. ``runner.context["page_loader"]`` — test injection or explicit
       route-layer wiring. Returned directly.
    2. Otherwise, an on-demand ``LocalDoctrPageLoader`` built from the
       production context keys ``predictor_cache`` / ``ocr_config_carrier`` /
       ``settings`` that ``bootstrap.py`` wires at startup.

    Every call site below passes ``allow_ocr=False``, so unlike reload_ocr's
    production path (which drives OCR through a per-page lease), this
    loader's ``run_ocr`` is never reached — no image-path resolver is wired.

    Returns ``None`` when neither is available: no project loaded, or the
    production context keys aren't wired. The caller falls back to
    considering only pages already in memory — the behavior before this
    function existed — and logs it.
    """
    loader = runner.context.get("page_loader")
    if loader is not None:
        return loader  # type: ignore[return-value]

    if project_state.loaded_project is None:
        return None

    ctx: dict[str, Any] = runner.context
    predictor_cache: PredictorCache | None = ctx.get("predictor_cache")
    ocr_carrier: OCRConfigCarrier | None = ctx.get("ocr_config_carrier")
    settings = ctx.get("settings")
    if predictor_cache is None or ocr_carrier is None or not isinstance(settings, Settings):
        return None

    from ....adapters.ocr.local_doctr import LocalDoctrPageLoader

    detection_key, recognition_key, hf_revision = ocr_carrier.snapshot()
    return LocalDoctrPageLoader(
        project=project_state.loaded_project,
        predictor_cache=predictor_cache,
        detection_key=detection_key,
        recognition_key=recognition_key,
        hf_revision=hf_revision,
        data_root=settings.data_root,
        cache_root=settings.cache_root,
        store=page_store,
    )


def _loaded_project_id(project_state: ProjectState) -> str | None:
    """The currently loaded project's id, or ``None`` if none is loaded."""
    current = project_state.loaded_project
    return current.project_id if current is not None else None


def _project_still_pinned(project_state: ProjectState, project: Project) -> bool:
    """Whether ``project`` — captured at the top of this run — is still loaded.

    A concurrent ``POST .../load`` can swap ``ProjectState.loaded_project``
    to a different book at any point during the lazy-load loop below:
    ``ensure_page_model`` takes the project lock only for its own page, not
    once for the whole loop, so a swap can land between two of the loop's
    calls. Re-checked before every page load and once after the loop, so a
    swap is caught before ``ensure_page_model`` can go on stamping the old
    book's content into the new book's ``page_states``, and before any
    journal write below uses the now-stale ``project``.
    """
    current = project_state.loaded_project
    return current is not None and current.project_id == project.project_id


async def _refuse_project_changed(
    runner: JobRunner,
    job: Job,
    *,
    expected_project_id: str,
    found_project_id: str | None,
) -> None:
    """Abort the run: report that the loaded project no longer matches.

    Shared by the book-pinning check at the top of the run and by the
    lazy-load loop's per-page and post-loop re-checks — one wording, so a
    person reading the SSE message sees the same sentence regardless of
    when the mismatch was caught.
    """
    log.warning(
        "propose_regions: job=%s expected project=%s but project=%s is loaded — refusing",
        job.job_id,
        expected_project_id,
        found_project_id,
    )
    await runner.update_progress(
        job.job_id,
        current=0,
        total=0,
        message=(
            f"Project changed since this run was queued: "
            f"expected {expected_project_id}, found {found_project_id}"
        ),
    )


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


def _box_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Intersection-over-union of two ``(left, top, right, bottom)`` pixel boxes."""
    a_left, a_top, a_right, a_bottom = a
    b_left, b_top, b_right, b_bottom = b
    inter_width = max(0, min(a_right, b_right) - max(a_left, b_left))
    inter_height = max(0, min(a_bottom, b_bottom) - max(a_top, b_top))
    intersection = inter_width * inter_height
    if intersection <= 0:
        return 0.0
    a_area = (a_right - a_left) * (a_bottom - a_top)
    b_area = (b_right - b_left) * (b_bottom - b_top)
    union = a_area + b_area - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _best_carry_match(proposal: RegionProposal, confirmed: Sequence[ResolvedRegion]) -> ResolvedRegion | None:
    """The confirmed region this proposal carries from, or ``None``.

    A match needs the same role and a box IoU at or above
    ``_CARRY_IOU_THRESHOLD``. When more than one confirmed region qualifies,
    the highest IoU wins; on an exact tie the earlier region in page order
    keeps the match.
    """
    best: ResolvedRegion | None = None
    best_iou = _CARRY_IOU_THRESHOLD
    for region in confirmed:
        if region.role != proposal.role:
            continue
        iou = _box_iou(proposal.box, region.box)
        if iou > best_iou or (best is None and iou == best_iou):
            best = region
            best_iou = iou
    return best


def _origin_decisions_by_region_id(
    decisions: Sequence[RegionDecision],
) -> dict[str, RegionDecision]:
    """Map each confirmed region to the decision that originally confirmed it.

    The origin is the ``accepted`` or ``edited`` decision naming a region's
    id — never a ``carried`` one, or a second re-run would name a previous
    carry as the origin instead of the person's own confirmation. Read once
    per run over the whole decision journal, not once per proposal.
    """
    origin_by_region_id: dict[str, RegionDecision] = {}
    for decision in decisions:
        if decision.disposition not in (Disposition.ACCEPTED, Disposition.EDITED):
            continue
        if decision.region_id is None:
            continue
        if decision.region_id not in origin_by_region_id:
            origin_by_region_id[decision.region_id] = decision
    return origin_by_region_id


def _carry_decisions_for_page(
    *,
    page: Page,
    proposals: Sequence[RegionProposal],
    origin_by_region_id: Mapping[str, RegionDecision],
    decided_at: str,
) -> tuple[list[RegionDecision], int]:
    """Carried decisions for one page's newly proposed regions.

    Returns the decisions to append, plus the count of distinct confirmed
    regions that matched a new proposal but had no origin decision to carry
    from — a hand-drawn region, or one whose confirming decision is missing.
    """
    confirmed = confirmed_regions_from_page(page)
    decisions: list[RegionDecision] = []
    regions_with_no_origin: set[str] = set()
    for proposal in proposals:
        match = _best_carry_match(proposal, confirmed)
        if match is None or match.region_id is None:
            continue
        origin = origin_by_region_id.get(match.region_id)
        if origin is None:
            regions_with_no_origin.add(match.region_id)
            continue
        decisions.append(
            RegionDecision(
                decision_id=uuid.uuid4().hex,
                run_id=proposal.run_id,
                proposal_id=proposal.proposal_id,
                disposition=Disposition.CARRIED,
                region_id=match.region_id,
                actor="propose_regions",
                decided_at=decided_at,
                carried_from_run_id=origin.run_id,
                carried_from_proposal_id=origin.proposal_id,
            )
        )
    return decisions, len(regions_with_no_origin)


def _carry_page(
    *,
    project_state: ProjectState,
    decision_log: RegionDecisionLog,
    page_index: int,
    proposals: Sequence[RegionProposal],
    origin_by_region_id: Mapping[str, RegionDecision],
    decided_at: str,
) -> tuple[int, int]:
    """Match and append one page's carried decisions under that page's lock.

    Returns the count of carried decisions appended and the count of matched
    regions with no origin decision. The lock is the one every region route
    takes, and ``delete_region`` holds it until its rejections are recorded,
    so a carry can neither read a half-mutated block tree nor append a carry
    naming a region a concurrent delete has already rejected. A carried
    decision is append-only and permanent, which a transient digest read is not.
    Blocking: call it through ``asyncio.to_thread``.
    """
    pstate = project_state.page_states[page_index]
    appended = 0
    with project_state.get_page_lock(page_index):
        page = _resolve_live_page(pstate)
        if page is None:
            return 0, 0
        carried, skipped = _carry_decisions_for_page(
            page=page,
            proposals=proposals,
            origin_by_region_id=origin_by_region_id,
            decided_at=decided_at,
        )
        for decision in carried:
            try:
                decision_log.append(decision)
            except OSError:
                log.warning(
                    "propose_regions: failed to persist a carried decision for proposal_id=%s page=%d",
                    decision.proposal_id,
                    page_index,
                    exc_info=True,
                )
                continue
            appended += 1
    return appended, skipped


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
        await _refuse_project_changed(
            runner, job, expected_project_id=submitted_project_id, found_project_id=project.project_id
        )
        return

    # Pages load lazily — a page only enters ``project_state.page_states``
    # once someone opens it, so after a server restart, or on a book nobody
    # has paged through yet, that dict can be empty even though every page
    # has stored OCR content. Load every page not already carrying a
    # ``page_record`` before eligibility is computed below, through the same
    # labeled/cached-only precedence the bulk page-kind confirm route uses
    # (``allow_ocr=False`` — never runs OCR from this job). No progress is
    # reported for this pass: it runs entirely before the measurement pass's
    # first ``update_progress`` call, so it cannot make ``combined_total``'s
    # progress go backwards or claim a slot of its own. See the module
    # docstring's "Pages load lazily" section and ``_get_page_loader``.
    #
    # Deliberately no message-only "loading N page(s) from storage" update
    # before this loop, tempting as that looks: every ``update_progress``
    # call this handler makes, from its very first to its very last, is
    # required to report the same ``total`` (``test_progress_never_goes_
    # backwards_across_the_two_phases`` asserts ``len({t for _, t in seen})
    # == 1`` over the *whole* run). ``combined_total`` isn't known until
    # ``total = len(eligible_indices)`` is computed below, which itself
    # depends on this very loop having already run (eligibility reads each
    # loaded page's kind) plus the page-kind journal reads that follow it —
    # so an update here would have to either report ``total=0`` (a
    # different value from every later call) or already know
    # ``combined_total`` (impossible this early). Neither fits; there is no
    # total this update could report that both means something and holds
    # for the rest of the run.
    loader = _get_page_loader(runner, project_state, page_store)
    no_ocr_yet_indices: list[int] = []
    legacy_payload_indices: list[int] = []
    if loader is not None:
        for idx in range(project.total_pages):
            # A concurrent ``POST .../load`` can swap ``loaded_project`` to a
            # different book between two of this loop's iterations — see
            # ``_project_still_pinned``. Re-checked before every page load,
            # not just once at the top of the run.
            if not _project_still_pinned(project_state, project):
                await _refuse_project_changed(
                    runner,
                    job,
                    expected_project_id=project.project_id,
                    found_project_id=_loaded_project_id(project_state),
                )
                return
            pstate = project_state.page_states.get(idx)
            if pstate is not None and pstate.page_record is not None:
                continue
            # Blocking: ``ensure_page_model`` takes the project lock and may
            # read the store's provenance graph — offloaded so a book with
            # many unloaded pages doesn't stall the event loop for the
            # duration of the pass.
            try:
                outcome = await asyncio.to_thread(
                    ensure_page_model, project_state, idx, loader=loader, allow_ocr=False
                )
            except LegacyTypographyPayloadError:
                # ``LocalDoctrPageLoader.load_labeled`` (and
                # ``ensure_page_model`` in turn) re-raises this rather than
                # treating it as an ordinary cache miss — "Removed review
                # data must never be mistaken for a cache miss" (see its own
                # docstring). Right for a single-page route to stop outright
                # over, but a book-scoped run must not let one un-migrated
                # page cost every other page its proposals — skip it,
                # counted in its own summary clause below.
                legacy_payload_indices.append(idx)
                continue
            if outcome is None:
                no_ocr_yet_indices.append(idx)
    else:
        log.info(
            "propose_regions: run for project=%s — no page loader available; "
            "considering only pages already in memory",
            project.project_id,
        )

    # One more re-check after the loop: a swap during the *last* iteration's
    # ``ensure_page_model`` call has no further iteration to catch it via
    # the per-page check above.
    if not _project_still_pinned(project_state, project):
        await _refuse_project_changed(
            runner,
            job,
            expected_project_id=project.project_id,
            found_project_id=_loaded_project_id(project_state),
        )
        return

    if no_ocr_yet_indices:
        log.info(
            "propose_regions: project=%s skipped %d page(s) with no stored or cached OCR output yet: %s",
            project.project_id,
            len(no_ocr_yet_indices),
            no_ocr_yet_indices,
        )

    if legacy_payload_indices:
        log.warning(
            "propose_regions: project=%s skipped %d page(s) with legacy review data that must be "
            "migrated first: %s",
            project.project_id,
            len(legacy_payload_indices),
            legacy_payload_indices,
        )

    page_indices = sorted(
        idx for idx, pstate in project_state.page_states.items() if pstate.page_record is not None
    )
    if not page_indices:
        await runner.update_progress(job.job_id, current=0, total=0, message="No page has OCR output yet")
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
            message=(
                "No page has a proposed or confirmed page kind; nothing to propose regions for. "
                "Run Propose page kinds first."
            ),
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
    detected_page_indices: set[int] = set()
    lease_failed_indices: list[int] = []
    no_measurement_indices: list[int] = []
    detector_failed_indices: list[int] = []
    # Proposals this run wrote, by page — read back afterward for the carry
    # pass rather than re-reading the journal, since this run already holds
    # them in memory.
    new_proposals_by_page: dict[int, list[RegionProposal]] = {}
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
                        no_measurement_indices.append(idx)
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
                detected_page_indices.add(idx)
                new_proposals_by_page[idx] = proposals
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

    if no_measurement_indices:
        log.warning(
            "propose_regions: run=%s project=%s skipped %d page(s) with no book measurement: %s",
            run_id,
            project.project_id,
            len(no_measurement_indices),
            no_measurement_indices,
        )

    if detector_failed_indices:
        log.warning(
            "propose_regions: run=%s project=%s detector raised on %d page(s): %s",
            run_id,
            project.project_id,
            len(detector_failed_indices),
            detector_failed_indices,
        )

    # A new proposal that matches a confirmed region — same role, box IoU at
    # or above ``_CARRY_IOU_THRESHOLD`` — carries that region's earlier
    # confirmation forward as its own decision, so a re-run does not re-
    # propose work a person already did (spec §"Decisions must carry across
    # runs first"). The decision journal is read once here, for the whole
    # run, not once per proposal.
    decision_log = RegionDecisionLog(project.project_root)
    carried_count = 0
    carry_skipped_region_count = 0
    if new_proposals_by_page:
        origin_by_region_id = _origin_decisions_by_region_id(decision_log.decisions())
        decided_at = datetime.now(UTC).isoformat()
        for idx, page_proposals in new_proposals_by_page.items():
            appended, skipped = await asyncio.to_thread(
                _carry_page,
                project_state=project_state,
                decision_log=decision_log,
                page_index=idx,
                proposals=page_proposals,
                origin_by_region_id=origin_by_region_id,
                decided_at=decided_at,
            )
            carried_count += appended
            carry_skipped_region_count += skipped

    if carry_skipped_region_count:
        log.info(
            "propose_regions: run=%s project=%s skipped %d confirmed region(s) with no "
            "accepted/edited origin decision (hand-drawn, or a missing decision)",
            run_id,
            project.project_id,
            carry_skipped_region_count,
        )

    log.info(
        "propose_regions: run=%s project=%s pages=%d proposals=%d carried=%d",
        run_id,
        project.project_id,
        total,
        proposal_count,
        carried_count,
    )

    # The runner's completion step copies this call's ``message`` verbatim onto
    # the terminal SSE frame (core/jobs/runner.py, ~334-345) — this is the only
    # message a person who started the run ever sees. A run that skipped every
    # page for a missing page kind otherwise ends in a silent success toast
    # over an unchanged page, with the reason left in a server log nobody but
    # an operator reads.
    #
    # ``pages_detected`` counts pages that actually received a proposal (its
    # detector call returned at least one region), not every eligible page the
    # loop above visited. An eligible page whose detector ran and legitimately
    # found nothing is not itself surprising or actionable; folding it into
    # this count would make "Proposed 3 region(s) on 40 page(s)" read as
    # roughly one region per page when the truth is 3 regions on 2 pages and
    # 38 pages of denser-than-expected but genuine silence. Pairing
    # ``proposal_count`` with the page count that actually produced those
    # proposals keeps the sentence's two halves aligned.
    #
    # The skip clause below names only pages skipped for having no page kind
    # — the one failure mode a person can fix by clicking "Propose page
    # kinds". Failed leases, missing measurements and a raising detector are
    # this run's own bookkeeping rather than something the reader's next click
    # fixes, so they are named in a separate clause, only when non-zero, so a
    # smaller-than-expected result still points at a cause instead of reading
    # as an unexplained gap.
    summary_parts = [f"Proposed {proposal_count} region(s) on {len(detected_page_indices)} page(s)."]
    if skipped_indices:
        summary_parts.append(
            f"Skipped {len(skipped_indices)} page(s) with no page kind; run Propose page kinds first."
        )
    if no_ocr_yet_indices:
        summary_parts.append(f"Skipped {len(no_ocr_yet_indices)} page(s) with no OCR output yet.")
    if legacy_payload_indices:
        summary_parts.append(
            f"Skipped {len(legacy_payload_indices)} page(s) with legacy review data that must be "
            "migrated first."
        )
    if carried_count:
        summary_parts.append(f"Carried {carried_count} decision(s) from earlier runs.")
    unprocessed_parts: list[str] = []
    if lease_failed_indices:
        unprocessed_parts.append(f"{len(lease_failed_indices)} page(s) had a failed lease")
    if no_measurement_indices:
        unprocessed_parts.append(f"{len(no_measurement_indices)} page(s) had no measurement")
    if detector_failed_indices:
        unprocessed_parts.append(f"{len(detector_failed_indices)} page(s) had a detector error")
    if unprocessed_parts:
        summary_parts.append("; ".join(unprocessed_parts) + ".")

    await runner.update_progress(
        job.job_id,
        current=combined_total,
        total=combined_total,
        message=" ".join(summary_parts),
    )


__all__ = ["handle_propose_regions"]

"""``/api/projects/{project_id}/pages/{page_index}/regions`` router.

Spec authority: ``docs/specs/2026-09-07-region-provenance-and-persistence-design.md``
"The routes follow the convention already in place". Every mutating route
resolves the page, holds the per-page lock, mutates, bumps
``PageState.generation``, persists via ``_save_to_store_best_effort``, and
returns the full ``PagePayload`` — the same shape ``api/words.py`` uses.

A region is a ``Block`` carrying an opaque ``region_id`` in
``additional_block_attributes``, and it nests: a leaf region (``child_type=
WORDS``) holds words directly and lives wherever it was created — as a
top-level ``Page.items`` sibling by default, or as a child of a
nesting-capable container region when ``parent_region_id`` is given. A
container region (``child_type=BLOCKS``) holds other regions and nothing
else — a ``WORDS``-typed block raises ``TypeError`` if a ``Block`` is added
to it, so a leaf region can never itself hold a nested child.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_contracts.geometry.bounding_box import BoundingBox
from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
from pdomain_book_tools.ocr.page import Page
from pdomain_book_tools.ocr.reorganize_page_utils import build_recovered_words_block
from pdomain_book_tools.ocr.word import Word
from pydantic import BaseModel

from ..core.jobs import JobRunner
from ..core.models import BBox
from ..core.persistence.config_yaml import AppConfig
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..core.regions.block_adapter import find_region_block
from ..core.regions.coordinates import pixel_box_to_bounding_box
from ..core.regions.decision_log import RegionDecisionLog
from ..core.regions.models import Disposition, RegionDecision, RegionProposal
from ..core.regions.proposal_log import RegionProposalLog
from ..settings import Settings
from .dependencies import (
    bind_page_labeling_lease,
    get_app_config,
    get_job_runner,
    get_page_store_optional,
    get_project_state,
    get_settings,
)
from .middleware.error_handler import ApiError
from .pages import PagePayload
from .words import (
    _check_project_and_page,
    _page_not_loaded,
    _refresh_payload_response,
    _resolve_page_object,
    _save_to_store_best_effort,
    _store_persist_failed_response,
    _word_not_found,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["regions"])

_REGION_ID_KEY = "region_id"
_SOURCE_PROPOSAL_ID_KEY = "source_proposal_id"
_HAND_DRAWN_SENTINEL = "hand-drawn"


# ── Request models ─────────────────────────────────────────────────────


class CreateRegionRequest(BaseModel):
    """``child_type="blocks"`` creates a nesting-capable container region — one that
    can hold other regions but no words of its own. ``parent_region_id`` nests the new
    region as a child of an existing container region instead of adding it as a
    top-level ``Page.items`` sibling; the parent must itself be a container.
    """

    role: RegionRole
    box: BBox
    child_type: Literal["words", "blocks"] = "words"
    parent_region_id: str | None = None


class EditRegionRequest(BaseModel):
    role: RegionRole | None = None
    box: BBox | None = None


class WordRef(BaseModel):
    """A word's position in the *current* live tree — never a stored key.

    See ``_resolve_target_word`` for why line/word ordinals cannot be persisted.
    """

    line_index: int
    word_index: int


class SetRegionWordMembershipRequest(BaseModel):
    word_refs: list[WordRef]


class AcceptRegionProposalRequest(BaseModel):
    """Optional overrides. Present -> disposition is ``edited``; absent -> ``accepted``."""

    role: RegionRole | None = None
    box: BBox | None = None


class RegionProposalListItem(BaseModel):
    proposal_id: str
    run_id: str
    role: RegionRole
    box: BBox
    confidence: float
    # Open-ended: shape varies per detector — mirrors ``RegionProposal.evidence``
    # upstream, which is equally open-ended, so no single TypedDict fits.
    evidence: dict[str, Any]
    disposition: str | None = None


class ListRegionProposalsResponse(BaseModel):
    proposals: list[RegionProposalListItem]


class StartRegionProposalRunRequest(BaseModel):
    """No page-kind fields: the handler reads that state itself from the page-kind
    stores (``PageKindProposalLog``, ``PageKindReviewedStore``) rather than trusting
    a caller's say-so — see the job handler's docstring.
    """

    model_id: str = "null-detector"
    model_version: str = "0.0.0"


class StartRegionProposalRunResponse(BaseModel):
    job_id: str


# ── Shared helpers ───────────────────────────────────────────────────────


def _bbox_to_ltrb(box: BBox) -> tuple[int, int, int, int]:
    return box.x, box.y, box.x + box.width, box.y + box.height


def _build_region_block(
    *,
    bounding_box: BoundingBox,
    child_type: BlockChildType,
    role: RegionRole,
    region_id: str,
    source_proposal_id: str,
) -> Block:
    """Construct a new confirmed region ``Block``.

    Shared by ``create_region`` (a person drew this region unprompted —
    ``source_proposal_id`` is the hand-drawn sentinel) and
    ``accept_region_proposal`` (a person confirmed a machine's proposal —
    ``source_proposal_id`` is the real proposal id). ``bounding_box`` is
    already converted to the page's own storage convention by the caller,
    via ``pixel_box_to_bounding_box`` — that conversion can itself raise
    ``ValueError`` for an out-of-bounds box, which is why it runs before this
    function, not inside its ``try``. Both stamp ``region_id`` and
    ``source_proposal_id`` into ``additional_block_attributes`` and let
    ``Block.__init__`` raise ``ValueError`` for an unsupported role; the
    caller maps *that* ``ValueError`` to the 400 ``invalid_region_role``
    envelope.
    """
    return Block(
        items=[],
        bounding_box=bounding_box,
        child_type=child_type,
        block_category=BlockCategory.BLOCK,
        block_role_labels=[role.value],
        additional_block_attributes={
            _REGION_ID_KEY: region_id,
            _SOURCE_PROPOSAL_ID_KEY: source_proposal_id,
        },
    )


def _resolve_target_word(page: Page, line_index: int, word_index: int) -> Word | None:
    """Resolve the word at ``(line_index, word_index)`` in the *current* live tree.

    Positional and resolved once, at request time, exactly like ``_resolve_word``
    in ``api/words.py`` — never persisted as a stored key. Line numbering is
    renumbered by the band-identification fixes, so nothing here stores this pair.
    """
    lines = page.lines
    if not (0 <= line_index < len(lines)):
        return None
    words = lines[line_index].words
    if not (0 <= word_index < len(words)):
        return None
    return words[word_index]


def _normalized_role_labels(role: RegionRole) -> list[str]:
    """Validate and normalize ``role`` the same way ``Block.__init__`` does.

    ``Block.block_role_labels`` is a plain attribute, not a validating property, so
    assigning to it directly (as ``edit_region`` must, to avoid re-deriving the
    region's box or membership from a full reconstruction) bypasses
    ``Block._normalize_label`` entirely. A throwaway, memberless ``Block`` runs that
    same normalization — including its alias and whitespace/underscore/hyphen
    handling — and raises ``ValueError`` for an unsupported role exactly as
    ``Block(block_role_labels=[...])`` does in ``create_region``. There is no public
    single-label validator on ``Block``; running the real constructor is the only way
    to get its exact normalization without duplicating (and risking drift from)
    ``_normalize_label``.
    """
    probe = Block(
        items=[],
        child_type=BlockChildType.WORDS,
        block_category=BlockCategory.BLOCK,
        block_role_labels=[role.value],
    )
    return probe.block_role_labels


def _remove_word_by_identity(owner: Block, word: Word) -> None:
    """Remove ``word`` from ``owner`` by object identity, never by equality.

    ``Block.remove_item`` tests ``item in self._items``, which runs
    ``Word.__eq__`` — ``Word`` is a plain dataclass, so that is value equality.
    Two words with the same text and the same box are equal and still different
    objects on the page, so ``remove_item`` can drop the wrong one. Assigning
    ``Block.items`` replaces the list wholesale and runs the same ``_sort_items``
    + ``recompute_bounding_box`` that ``remove_item`` runs, without the equality
    test. ``pdomain-book-tools`` is left alone; this is local to the route.
    """
    owner.items = [item for item in owner.items if item is not word]


def _region_not_found(region_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(error="region_not_found", message=f"region not found: {region_id}").model_dump(),
    )


def _invalid_region_role(exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ApiError(error="invalid_region_role", message=str(exc)).model_dump(),
    )


def _invalid_region_box(exc: ValueError) -> JSONResponse:
    """400 when a pixel box cannot be converted to the page's storage convention.

    Raised by ``pixel_box_to_bounding_box`` for a box that reaches past the
    edge of a normalized page — its projection onto ``[0, 1]`` overflows, so
    ``BoundingBox`` itself refuses it — or for a page reporting a zero-sized
    dimension. Reading the conversion outside the role ``try`` (below) is
    what keeps this distinct from ``invalid_region_role``: before this fix,
    the conversion ran inside that same ``try`` and any bad box was reported
    as an unsupported role, which named the wrong cause.
    """
    return JSONResponse(
        status_code=400,
        content=ApiError(error="invalid_region_box", message=str(exc)).model_dump(),
    )


def _mixed_page_coordinates(exc: ValueError) -> JSONResponse:
    """400 when the page mixes normalized and pixel-space word boxes.

    ``Page.is_content_normalized`` raises ``ValueError`` on such a page, and a
    region's box has to be stamped in one convention or the other. Reading it
    inside the ``_build_region_block`` try block reported the real problem as
    ``invalid_region_role``, which names the wrong cause; reading it outside
    any catch turned it into a 500. Both siblings now report what actually
    went wrong.
    """
    return JSONResponse(
        status_code=400,
        content=ApiError(error="mixed_page_coordinates", message=str(exc)).model_dump(),
    )


def _region_owner(page: Page, region: Block) -> Page | Block:
    """Return whatever holds ``region`` — its parent container block, or the page itself.

    Compares by identity, never equality: two regions can carry equal field values and
    still be different objects on the page.
    """
    stack: list[Block] = list(page.items)
    while stack:
        item = stack.pop()
        if any(child is region for child in item.items):
            return item
        stack.extend(child for child in item.items if isinstance(child, Block))
    return page


def _parent_not_nesting_capable(parent_region_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ApiError(
            error="parent_not_nesting_capable",
            message=(
                f"region {parent_region_id} holds words, not regions; create it with child_type=blocks first"
            ),
        ).model_dump(),
    )


def _region_not_word_capable(region_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ApiError(
            error="region_not_word_capable",
            message=f"region {region_id} holds regions, not words; address a leaf region instead",
        ).model_dump(),
    )


def _find_proposal(store: RegionProposalLog, page_index: int, proposal_id: str) -> RegionProposal | None:
    for proposal in store.proposals_for_page(page_index):
        if proposal.proposal_id == proposal_id:
            return proposal
    return None


def _source_proposal_id(region: Block) -> str | None:
    """The real proposal id a confirmed region came from, or ``None``.

    ``None`` covers both a hand-drawn region (the explicit sentinel) and a
    region blob written before the routes stamped an origin at all — neither
    is a proposal anybody can have decided about.
    """
    raw = region.additional_block_attributes.get(_SOURCE_PROPOSAL_ID_KEY)
    if not isinstance(raw, str) or not raw or raw == _HAND_DRAWN_SENTINEL:
        return None
    return raw


def _proposal_already_accepted(proposal_id: str, region_id: str) -> JSONResponse:
    """409 when a proposal a person already accepted is rejected without deleting the region.

    The journal is append-only and the page blob keeps the confirmed ``Block``,
    so appending the rejection anyway would leave the payload showing a
    confirmed region whose proposal the journal says a person refused — two
    stores stating opposite facts about the same proposal.
    """
    return JSONResponse(
        status_code=409,
        content=ApiError(
            error="proposal_already_accepted",
            message=(
                f"proposal {proposal_id} was accepted and region {region_id} still exists; "
                f"delete the region first"
            ),
        ).model_dump(),
    )


def _proposal_not_found(proposal_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="proposal_not_found", message=f"proposal not found: {proposal_id}"
        ).model_dump(),
    )


def _decision_persist_failed_response(*, proposal_id: str) -> JSONResponse:
    """503 when a region decision could not be durably persisted (mirrors
    ``_store_persist_failed_response`` in ``api/words.py``, for the decision log
    rather than the page store).
    """
    return JSONResponse(
        status_code=503,
        content=ApiError(
            error="decision_persist_failed",
            message=f"decision could not be persisted to the decision log (proposal_id={proposal_id})",
        ).model_dump(),
    )


def _append_decision_or_error(
    decision_log: RegionDecisionLog, decision: RegionDecision
) -> JSONResponse | None:
    """Append ``decision``; return ``None`` on success or a 503 envelope on I/O failure.

    A disk-full, permission, or concurrent-write failure on the decision log is a
    reachable I/O failure, same as the page-store writes ``_save_to_store_best_effort``
    guards — no route in this codebase lets a reachable request fall through to the
    catch-all handler's 500.
    """
    try:
        decision_log.append(decision)
    except OSError as exc:
        log.warning(
            "decision log append failed proposal_id=%s run_id=%s: %s",
            decision.proposal_id,
            decision.run_id,
            exc,
        )
        return _decision_persist_failed_response(proposal_id=decision.proposal_id)
    return None


def _record_region_deletion(
    *, project_root: Path, page_index: int, region_id: str, proposal_id: str | None
) -> JSONResponse | None:
    """Record that a person removed a confirmed region, for every proposal that decided it.

    A region can be named by more than one proposal's latest decision once carries
    exist: the proposal that was originally accepted, plus every later run's proposal
    that carried the same confirmation forward. Each gets its own ``rejected``
    decision, under its own run id — the convention every decision already follows —
    so none of them stays hidden behind a decision naming a region that no longer
    exists.

    Returns ``None`` when there is nothing to record at all — a hand-drawn region (no
    proposal ever named it) with no carried proposal either. The source proposal on
    the block is included even if its own decision is somehow not among the ones
    found by region id; if it is not present in the proposal log either, it is
    skipped and logged, exactly as before, without failing the delete. Returns the
    guarded 503 envelope the moment any append fails.
    """
    decision_log = RegionDecisionLog(project_root)
    latest_by_proposal = decision_log.latest_by_proposal()

    # Every proposal whose latest decision names this region — the source
    # accept/edit and every later carry — keyed by proposal id to its own run id.
    to_reject: dict[str, str] = {
        pid: run_id
        for (pid, run_id), decision in latest_by_proposal.items()
        if decision.region_id == region_id
    }

    if proposal_id is not None and proposal_id not in to_reject:
        proposal = _find_proposal(RegionProposalLog(project_root), page_index, proposal_id)
        if proposal is None:
            log.warning(
                "region deleted but its proposal is not in the log; no decision recorded (proposal_id=%s)",
                proposal_id,
            )
        else:
            to_reject[proposal_id] = proposal.run_id

    if not to_reject:
        return None

    for pid, run_id in to_reject.items():
        err = _append_decision_or_error(
            decision_log,
            RegionDecision(
                decision_id=uuid.uuid4().hex,
                run_id=run_id,
                proposal_id=pid,
                disposition=Disposition.REJECTED,
                region_id=None,
                actor="default",
                decided_at=datetime.now(UTC).isoformat(),
            ),
        )
        if err is not None:
            return err
    return None


# ── Routes: create / edit / delete ──────────────────────────────────────


@router.post(
    "/{project_id}/pages/{page_index}/regions",
    response_model=PagePayload,
    dependencies=[Depends(bind_page_labeling_lease)],
    operation_id="create_region",
)
def create_region(
    *,
    project_id: str,
    page_index: int,
    body: CreateRegionRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """Create a new confirmed region, hand-drawn by a person — no members yet.

    ``child_type="words"`` (the default) makes a leaf region that can hold words via
    the membership route. ``child_type="blocks"`` makes a nesting-capable container
    that can hold other regions but never words directly. ``parent_region_id`` nests
    the new region under an existing container instead of adding it as a top-level
    ``Page.items`` sibling.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    left, top, right, bottom = _bbox_to_ltrb(body.box)
    region_id = uuid.uuid4().hex
    child_type = BlockChildType.BLOCKS if body.child_type == "blocks" else BlockChildType.WORDS

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        parent = None
        if body.parent_region_id is not None:
            parent = find_region_block(page, body.parent_region_id)
            if parent is None:
                return _region_not_found(body.parent_region_id)
            if parent.child_type is not BlockChildType.BLOCKS:
                return _parent_not_nesting_capable(body.parent_region_id)

        try:
            is_normalized = page.is_content_normalized
        except ValueError as exc:
            return _mixed_page_coordinates(exc)
        try:
            bounding_box = pixel_box_to_bounding_box(
                (left, top, right, bottom),
                page_width=page.width,
                page_height=page.height,
                is_normalized=is_normalized,
            )
        except ValueError as exc:
            return _invalid_region_box(exc)
        try:
            region = _build_region_block(
                bounding_box=bounding_box,
                child_type=child_type,
                role=body.role,
                region_id=region_id,
                source_proposal_id=_HAND_DRAWN_SENTINEL,
            )
        except ValueError as exc:
            return _invalid_region_role(exc)
        # ``Block.add_item`` recomputes the owner's bounding box from its items. A
        # container region's box is what a person drew on the page, not the union of
        # its children — same rule the membership route follows for a leaf region.
        saved_parent_box = parent.bounding_box if parent is not None else None
        (parent if parent is not None else page).add_item(region)
        if parent is not None:
            parent.bounding_box = saved_parent_box
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[{"type": "region_created", "region_id": region_id, "role": body.role.value}],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.patch(
    "/{project_id}/pages/{page_index}/regions/{region_id}",
    response_model=PagePayload,
    dependencies=[Depends(bind_page_labeling_lease)],
    operation_id="edit_region",
)
def edit_region(
    *,
    project_id: str,
    page_index: int,
    region_id: str,
    body: EditRegionRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """Edit a region's role and/or box. Box is set directly — it is never re-derived from members."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        region = find_region_block(page, region_id)
        if region is None:
            return _region_not_found(region_id)
        if body.role is not None:
            try:
                region.block_role_labels = _normalized_role_labels(body.role)
            except ValueError as exc:
                return _invalid_region_role(exc)
        if body.box is not None:
            try:
                is_normalized = page.is_content_normalized
            except ValueError as exc:
                return _mixed_page_coordinates(exc)
            left, top, right, bottom = _bbox_to_ltrb(body.box)
            try:
                region.bounding_box = pixel_box_to_bounding_box(
                    (left, top, right, bottom),
                    page_width=page.width,
                    page_height=page.height,
                    is_normalized=is_normalized,
                )
            except ValueError as exc:
                return _invalid_region_box(exc)
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[{"type": "region_edited", "region_id": region_id}],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.delete(
    "/{project_id}/pages/{page_index}/regions/{region_id}",
    response_model=PagePayload,
    dependencies=[Depends(bind_page_labeling_lease)],
    operation_id="delete_region",
)
def delete_region(
    *,
    project_id: str,
    page_index: int,
    region_id: str,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """Delete a region. Its member words (if any) are recovered, never dropped.

    Deleting a region a person accepted from a proposal records a ``rejected``
    decision naming that proposal — and, once a region has been carried forward
    into later proposal runs, naming every other proposal whose latest decision
    also names this region. Without it, a decision naming a ``region_id`` that
    no longer exists would keep going through the resolver's "already promoted
    into a confirmed region" branch, and the proposal it belongs to would vanish
    from the payload and the canvas with no record that anybody removed it — a
    rejection expressed as an absence, which is the one thing this design
    refuses to do.

    ``Disposition.REJECTED`` is the only value that says a person declined the
    proposal; the enum is owned upstream and gains no member here. Because the
    journal is append-only, the earlier ``accepted`` record survives beside the
    new one, so "rejected at review" and "accepted, then later deleted" stay
    distinguishable by sequence.

    A region with no proposal origin — hand-drawn, or written before the routes
    stamped one — writes no decision, and the delete still succeeds.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    project = project_state.loaded_project
    assert project is not None  # narrowed by _check_project_and_page

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        region = find_region_block(page, region_id)
        if region is None:
            return _region_not_found(region_id)
        proposal_id = _source_proposal_id(region)
        members = list(region.words)
        # A region created with ``parent_region_id`` lives in its parent's ``items``,
        # not in ``page.items``, so ``page.remove_item`` would not find it.
        owner = _region_owner(page, region)
        saved_owner_box = owner.bounding_box if isinstance(owner, Block) else None
        owner.remove_item(region)
        if isinstance(owner, Block):
            owner.bounding_box = saved_owner_box
        if members:
            recovered = build_recovered_words_block(members)
            if recovered is not None:
                page.add_item(recovered)
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[{"type": "region_deleted", "region_id": region_id}],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

        # The page blob is written first, as in ``accept_region_proposal``: a
        # deleted region with no decision is recoverable (the proposal simply
        # reads as still-accepted until someone looks), a decision naming a
        # deletion that never happened is not.
        decision_err = _record_region_deletion(
            project_root=project.project_root,
            page_index=page_index,
            region_id=region_id,
            proposal_id=proposal_id,
        )
        if decision_err is not None:
            return decision_err

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.put(
    "/{project_id}/pages/{page_index}/regions/{region_id}/words",
    response_model=PagePayload,
    dependencies=[Depends(bind_page_labeling_lease)],
    operation_id="set_region_word_membership",
)
def set_region_word_membership(
    *,
    project_id: str,
    page_index: int,
    region_id: str,
    body: SetRegionWordMembershipRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """Replace a region's word membership exactly with the given set.

    Only a leaf (``child_type=WORDS``) region can hold words directly; a container
    region rejects this route with 400 ``region_not_word_capable``, checked right
    after the region resolves and before any word is resolved or moved, mirroring
    ``create_region``'s ``parent_not_nesting_capable`` check for the opposite shape.

    A word not listed is released back to a ``recovered`` block, never dropped; a
    word newly listed is moved out of wherever it currently sits — another line or
    another region. ``Block.add_item``/``remove_item`` recompute the block's
    bounding box from its items as a side effect, so *every* block this route
    takes a word from or gives a word to — the target region, a source region,
    a source line — has its box saved before the edit and restored after,
    because a region's box is what a person drew, not a function of its
    membership.

    Known interaction, owned elsewhere: moving a word changes its published
    ``word_id``. ``stable_word_id`` hashes a page-wide ``reading_order``
    position, and a region joins ``page.lines``, so one membership write
    renumbers every word on the page and detaches any
    ``TypographyCorrectionLog`` record keyed to the old id — the record stays on
    disk under an id no word carries. The flaw is in the keying, not in this
    route: ``api/lines_paragraphs.py``'s merge, split and delete already
    renumber ``page.lines`` the same way, so this route adds a trigger, not the
    fragility. Re-keying word identity off something stable belongs to its own
    plan; ``tests/integration/test_region_membership_word_identity.py`` pins
    exactly what happens today, so the day it changes, it changes visibly.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        region = find_region_block(page, region_id)
        if region is None:
            return _region_not_found(region_id)
        if region.child_type is not BlockChildType.WORDS:
            return _region_not_word_capable(region_id)

        target_words: list[Word] = []
        for ref in body.word_refs:
            word = _resolve_target_word(page, ref.line_index, ref.word_index)
            if word is None:
                return _word_not_found(ref.line_index, ref.word_index)
            target_words.append(word)

        # Every block a word is about to leave, resolved *before* anything moves,
        # with the box it had at that moment. ``Block.lines`` returns ``[self]``
        # for a ``WORDS``-typed block, so a leaf region is itself one of
        # ``page.lines`` — when the claimed word currently belongs to another
        # region, the block losing it IS that region. ``remove_item`` ends in
        # ``recompute_bounding_box``, so without this the source region's box
        # would be re-derived from whatever words it has left, and to ``None``
        # if the moved word was its last; ``confirmed_regions_from_page`` skips
        # a box-less block, so a person's drawn region would disappear from
        # ``PagePayload.regions`` while still living in the page blob —
        # invisible, undeletable, still serialized.
        #
        # An ordinary OCR line is restored for the same reason ``delete_region``
        # restores its owner: a membership change must not re-derive geometry it
        # did not edit. A line whose box collapsed to ``None`` also sorts to the
        # front of its paragraph (``Block._sort_items`` keys a missing box as 0),
        # silently reordering the page.
        saved_boxes: list[tuple[Block, BoundingBox | None]] = [(region, region.bounding_box)]
        for word in target_words:
            source = next((ln for ln in page.lines if any(w is word for w in ln.words)), None)
            if source is not None and not any(block is source for block, _ in saved_boxes):
                saved_boxes.append((source, source.bounding_box))

        # Identity, not equality: ``Word`` may compare equal by value, and two words
        # with the same text and box are still different objects on the page.
        released = [w for w in region.words if not any(w is t for t in target_words)]
        for word in released:
            _remove_word_by_identity(region, word)
        if released:
            recovered = build_recovered_words_block(released)
            if recovered is not None:
                page.add_item(recovered)

        for word in target_words:
            if any(w is word for w in region.words):
                continue
            owner_line = next((ln for ln in page.lines if any(w is word for w in ln.words)), None)
            if owner_line is not None:
                _remove_word_by_identity(owner_line, word)
            region.add_item(word)

        for block, box in saved_boxes:
            block.bounding_box = box

        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {"type": "region_membership_set", "region_id": region_id, "word_count": len(target_words)}
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


# ── Routes: proposals — list / accept / reject ───────────────────────────


@router.get(
    "/{project_id}/pages/{page_index}/regions/proposals",
    response_model=ListRegionProposalsResponse,
    operation_id="list_region_proposals",
)
def list_region_proposals(
    *,
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """List every proposal for this page, across every run, with confidence and evidence.

    The decision journal is read once and indexed, not re-read per proposal.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    project = project_state.loaded_project
    assert project is not None  # narrowed by _check_project_and_page

    proposal_log = RegionProposalLog(project.project_root)
    latest_decisions = RegionDecisionLog(project.project_root).latest_by_proposal()
    items: list[RegionProposalListItem] = []
    for p in proposal_log.proposals_for_page(page_index):
        decision = latest_decisions.get((p.proposal_id, p.run_id))
        items.append(
            RegionProposalListItem(
                proposal_id=p.proposal_id,
                run_id=p.run_id,
                role=p.role,
                box=BBox(x=p.box[0], y=p.box[1], width=p.box[2] - p.box[0], height=p.box[3] - p.box[1]),
                confidence=p.confidence,
                evidence=p.evidence,
                disposition=decision.disposition.value if decision is not None else None,
            )
        )
    response = ListRegionProposalsResponse(proposals=items)
    return JSONResponse(status_code=200, content=response.model_dump(mode="json"))


@router.post(
    "/{project_id}/pages/{page_index}/regions/proposals/{proposal_id}/accept",
    response_model=PagePayload,
    dependencies=[Depends(bind_page_labeling_lease)],
    operation_id="accept_region_proposal",
)
def accept_region_proposal(
    *,
    project_id: str,
    page_index: int,
    proposal_id: str,
    body: AcceptRegionProposalRequest = AcceptRegionProposalRequest(),
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """Accept a proposal: create the confirmed region it describes and record the decision.

    The proposal record itself is never touched — only a new confirmed ``Block`` and a
    new ``RegionDecision`` are written. An override in the request body records
    ``edited`` instead of ``accepted``, per ``Disposition.knowledge_state`` (both map to
    ``KnowledgeState.POSITIVE``; only ``rejected`` is a refusal).

    Idempotent: if an earlier decision already named a region for this proposal and
    that region still exists on the page, the accept already happened — the current
    payload is returned unchanged rather than creating a second confirmed region. If
    the decision exists but its region was since deleted, this is a legitimate fresh
    accept, not a repeat.

    The page blob is written before the decision, both under the page lock: a
    confirmed region with no decision reads as "nobody has looked yet" (recoverable —
    the block still names its own ``source_proposal_id``), but a decision naming a
    region that was never written is not recoverable.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    project = project_state.loaded_project
    assert project is not None

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    proposal_log = RegionProposalLog(project.project_root)
    proposal = _find_proposal(proposal_log, page_index, proposal_id)
    if proposal is None:
        return _proposal_not_found(proposal_id)

    role = body.role if body.role is not None else proposal.role
    box = _bbox_to_ltrb(body.box) if body.box is not None else proposal.box
    has_override = body.role is not None or body.box is not None
    disposition = Disposition.EDITED if has_override else Disposition.ACCEPTED
    decision_log = RegionDecisionLog(project.project_root)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        existing_decision = decision_log.decision_for(proposal_id, run_id=proposal.run_id)
        existing_region_id = existing_decision.region_id if existing_decision is not None else None
        if existing_region_id is not None and find_region_block(page, existing_region_id) is not None:
            return _refresh_payload_response(
                project_id=project_id,
                page_index=page_index,
                project_state=project_state,
                settings=settings,
                app_config=app_config,
                page_store=store,
            )

        region_id = uuid.uuid4().hex
        try:
            is_normalized = page.is_content_normalized
        except ValueError as exc:
            return _mixed_page_coordinates(exc)
        try:
            bounding_box = pixel_box_to_bounding_box(
                box, page_width=page.width, page_height=page.height, is_normalized=is_normalized
            )
        except ValueError as exc:
            return _invalid_region_box(exc)
        try:
            region = _build_region_block(
                bounding_box=bounding_box,
                child_type=BlockChildType.WORDS,
                role=role,
                region_id=region_id,
                source_proposal_id=proposal_id,
            )
        except ValueError as exc:
            return _invalid_region_role(exc)
        page.add_item(region)
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {"type": "region_proposal_accepted", "proposal_id": proposal_id, "region_id": region_id}
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

        decision_err = _append_decision_or_error(
            decision_log,
            RegionDecision(
                decision_id=uuid.uuid4().hex,
                run_id=proposal.run_id,
                proposal_id=proposal_id,
                disposition=disposition,
                region_id=region_id,
                actor="default",
                decided_at=datetime.now(UTC).isoformat(),
            ),
        )
        if decision_err is not None:
            return decision_err

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/regions/proposals/{proposal_id}/reject",
    response_model=PagePayload,
    operation_id="reject_region_proposal",
)
def reject_region_proposal(
    *,
    project_id: str,
    page_index: int,
    proposal_id: str,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    # Read-only here: the reject path never writes the page blob. The payload
    # helper needs it to read the same image-provenance digest ``GET /pages``
    # reads, so this route's ``stale`` agrees with the GET's for one page state.
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """Reject a proposal. Records ``rejected`` (``KnowledgeState.VERIFIED_NEGATIVE``);
    never touches the page blob — the blob is written only by a human *confirming*
    something, and a rejection confirms nothing new about the page. That is also why
    this route, unlike ``accept_region_proposal``, has no ``bind_page_labeling_lease``
    dependency.

    Returns 409 when the latest decision for this proposal accepted it and the
    region that accept produced is still on the page. Appending the rejection
    would leave the payload showing a confirmed region whose proposal the journal
    says a person refused — the journal and the page blob stating opposite facts.
    Deleting the region first records the rejection itself (see
    ``delete_region``), so the 409 asks for the one action that keeps both stores
    in step.

    The page must be loaded, exactly as every sibling route requires — this one
    resolves it first and returns ``page_not_loaded`` otherwise. That guard is
    not a formality here: with no live page there is nothing to check the
    accepted region against, and proceeding would append the rejection while the
    confirmed region survives in the persisted blob, which is the very
    contradiction the 409 exists to prevent, reached by a request a caller can
    make.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    project = project_state.loaded_project
    assert project is not None

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    proposal_log = RegionProposalLog(project.project_root)
    proposal = _find_proposal(proposal_log, page_index, proposal_id)
    if proposal is None:
        return _proposal_not_found(proposal_id)

    decision_log = RegionDecisionLog(project.project_root)
    latest = decision_log.decision_for(proposal_id, run_id=proposal.run_id)
    accepted_region_id = latest.region_id if latest is not None else None
    if accepted_region_id is not None and find_region_block(page, accepted_region_id) is not None:
        return _proposal_already_accepted(proposal_id, accepted_region_id)

    # A second reject is a no-op, not a second decision. A held or double-tapped
    # reject key sends the request twice, and the decision journal is what
    # confidence gets calibrated against, so a duplicate would count one
    # person's single "no" twice. Answer with the current payload, as a first
    # reject would, and append nothing.
    if latest is not None and latest.disposition is Disposition.REJECTED:
        return _refresh_payload_response(
            project_id=project_id,
            page_index=page_index,
            project_state=project_state,
            settings=settings,
            app_config=app_config,
            page_store=store,
        )

    decision_err = _append_decision_or_error(
        decision_log,
        RegionDecision(
            decision_id=uuid.uuid4().hex,
            run_id=proposal.run_id,
            proposal_id=proposal_id,
            disposition=Disposition.REJECTED,
            region_id=None,
            actor="default",
            decided_at=datetime.now(UTC).isoformat(),
        ),
    )
    if decision_err is not None:
        return decision_err

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/regions/propose",
    status_code=202,
    response_model=StartRegionProposalRunResponse,
    operation_id="start_region_proposal_run",
)
def start_region_proposal_run(
    project_id: str,
    body: StartRegionProposalRunRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """Start a book-scoped proposal run. Progress and completion stream via ``/api/jobs``.

    The queued job must be pinned to the book it was submitted for — its
    handler refuses to run against a different project loaded in the
    meantime — so ``project_id`` is stamped into the job payload alongside
    the request body, following ``post_propose_page_kinds``'s precedent
    (``api/projects.py``).
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return JSONResponse(
            status_code=404,
            content=ApiError(
                error="project_not_found", message=f"project not found: {project_id}"
            ).model_dump(),
        )
    job_id = runner.submit(
        "propose_regions",
        project_id=project_id,
        payload={"project_id": project_id, **body.model_dump()},
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


def install_regions_router(app: FastAPI) -> None:
    """Register the regions router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "AcceptRegionProposalRequest",
    "CreateRegionRequest",
    "EditRegionRequest",
    "ListRegionProposalsResponse",
    "RegionProposalListItem",
    "SetRegionWordMembershipRequest",
    "StartRegionProposalRunRequest",
    "StartRegionProposalRunResponse",
    "WordRef",
    "install_regions_router",
    "router",
]

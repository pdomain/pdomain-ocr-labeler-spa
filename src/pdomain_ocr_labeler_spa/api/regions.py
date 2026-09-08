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

from ..core.models import BBox
from ..core.persistence.config_yaml import AppConfig
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..core.regions.block_adapter import find_region_block
from ..core.regions.decision_log import RegionDecisionLog
from ..core.regions.models import Disposition, RegionDecision, RegionProposal
from ..core.regions.proposal_log import RegionProposalLog
from ..settings import Settings
from .dependencies import (
    bind_page_labeling_lease,
    get_app_config,
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


class RejectRegionProposalRequest(BaseModel):
    pass


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


# ── Shared helpers ───────────────────────────────────────────────────────


def _bbox_to_ltrb(box: BBox) -> tuple[int, int, int, int]:
    return box.x, box.y, box.x + box.width, box.y + box.height


def _build_region_block(
    *,
    box: tuple[int, int, int, int],
    is_content_normalized: bool,
    child_type: BlockChildType,
    role: RegionRole,
    region_id: str,
    source_proposal_id: str,
) -> Block:
    """Construct a new confirmed region ``Block``.

    Shared by ``create_region`` (a person drew this region unprompted —
    ``source_proposal_id`` is the hand-drawn sentinel) and
    ``accept_region_proposal`` (a person confirmed a machine's proposal —
    ``source_proposal_id`` is the real proposal id). Both stamp ``region_id``
    and ``source_proposal_id`` into ``additional_block_attributes`` and let
    ``Block.__init__`` raise ``ValueError`` for an unsupported role; the
    caller maps that to the 400 ``invalid_region_role`` envelope.
    """
    left, top, right, bottom = box
    return Block(
        items=[],
        bounding_box=BoundingBox.from_ltrb(left, top, right, bottom, is_normalized=is_content_normalized),
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
            region = _build_region_block(
                box=(left, top, right, bottom),
                is_content_normalized=page.is_content_normalized,
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
            left, top, right, bottom = _bbox_to_ltrb(body.box)
            region.bounding_box = BoundingBox.from_ltrb(
                left, top, right, bottom, is_normalized=page.is_content_normalized
            )
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
    """Delete a region. Its member words (if any) are recovered, never dropped."""
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

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
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
    bounding box from its items as a side effect — the region's own explicitly-set
    box is saved before the edit and restored after, because a region's box is not
    its membership.
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

        saved_box = region.bounding_box

        # Identity, not equality: ``Word`` may compare equal by value, and two words
        # with the same text and box are still different objects on the page.
        released = [w for w in region.words if not any(w is t for t in target_words)]
        for word in released:
            region.remove_item(word)
        if released:
            recovered = build_recovered_words_block(released)
            if recovered is not None:
                page.add_item(recovered)

        for word in target_words:
            if any(w is word for w in region.words):
                continue
            owner_line = next((ln for ln in page.lines if any(w is word for w in ln.words)), None)
            if owner_line is not None:
                owner_line.remove_item(word)
            region.add_item(word)

        region.bounding_box = saved_box

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
    )


# ── Routes: proposals — list / accept / reject ───────────────────────────


@router.get(
    "/{project_id}/pages/{page_index}/regions/proposals",
    response_model=ListRegionProposalsResponse,
    operation_id="list_region_proposals",
)
def list_region_proposals(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """List every proposal for this page, across every run, with confidence and evidence."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    project = project_state.loaded_project
    assert project is not None  # narrowed by _check_project_and_page

    proposal_log = RegionProposalLog(project.project_root)
    decision_log = RegionDecisionLog(project.project_root)
    items: list[RegionProposalListItem] = []
    for p in proposal_log.proposals_for_page(page_index):
        decision = decision_log.decision_for(p.proposal_id, run_id=p.run_id)
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
            )

        region_id = uuid.uuid4().hex
        try:
            region = _build_region_block(
                box=box,
                is_content_normalized=page.is_content_normalized,
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
    _body: RejectRegionProposalRequest = RejectRegionProposalRequest(),
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
) -> JSONResponse:
    """Reject a proposal. Records ``rejected`` (``KnowledgeState.VERIFIED_NEGATIVE``);
    never touches the page blob — the blob is written only by a human *confirming*
    something, and a rejection confirms nothing new about the page. That is also why
    this route, unlike ``accept_region_proposal``, has no ``bind_page_labeling_lease``
    dependency.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    project = project_state.loaded_project
    assert project is not None

    proposal_log = RegionProposalLog(project.project_root)
    proposal = _find_proposal(proposal_log, page_index, proposal_id)
    if proposal is None:
        return _proposal_not_found(proposal_id)

    decision_log = RegionDecisionLog(project.project_root)
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
    )


def install_regions_router(app: FastAPI) -> None:
    """Register the regions router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "AcceptRegionProposalRequest",
    "CreateRegionRequest",
    "EditRegionRequest",
    "ListRegionProposalsResponse",
    "RegionProposalListItem",
    "RejectRegionProposalRequest",
    "SetRegionWordMembershipRequest",
    "WordRef",
    "install_regions_router",
    "router",
]

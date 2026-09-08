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
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_contracts.geometry.bounding_box import BoundingBox
from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
from pdomain_book_tools.ocr.page import Page
from pdomain_book_tools.ocr.reorganize_page_utils import build_recovered_words_block
from pydantic import BaseModel

from ..core.models import BBox
from ..core.persistence.config_yaml import AppConfig
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..core.regions.block_adapter import find_region_block
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


# ── Shared helpers ───────────────────────────────────────────────────────


def _bbox_to_ltrb(box: BBox) -> tuple[int, int, int, int]:
    return box.x, box.y, box.x + box.width, box.y + box.height


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
            region = Block(
                items=[],
                bounding_box=BoundingBox.from_ltrb(
                    left, top, right, bottom, is_normalized=page.is_content_normalized
                ),
                child_type=child_type,
                block_category=BlockCategory.BLOCK,
                block_role_labels=[body.role.value],
                additional_block_attributes={
                    _REGION_ID_KEY: region_id,
                    _SOURCE_PROPOSAL_ID_KEY: _HAND_DRAWN_SENTINEL,
                },
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


def install_regions_router(app: FastAPI) -> None:
    """Register the regions router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = ["CreateRegionRequest", "EditRegionRequest", "install_regions_router", "router"]

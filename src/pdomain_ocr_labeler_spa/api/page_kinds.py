"""``/api/projects/{project_id}/page-kinds`` routes.

Spec authority: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-
design.md "One route lists every page's kind" / "One route confirms many
pages".

``GET .../page-kinds`` answers a book-wide question — every page's proposed
and confirmed kind — from two journal reads, never one per page. It follows
``get_region_review_queue`` in ``api/regions.py``, tested for the same
one-read-per-journal contract.

``POST .../page-kinds/confirm`` confirms many pages in one request, each
exactly as ``POST .../pages/{index}/page-kind`` confirms it —
``_confirm_page_kind_locked`` in ``api/pages.py`` is the single shared body
both routes call, so the bulk route cannot drift from the single one. A page
not already in memory is loaded through ``ensure_page_model`` with
``allow_ocr=False``: confirming a kind must never start OCR.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pdomain_book_contracts.annotation import PageKind
from pydantic import BaseModel, BeforeValidator, Field

from ..core.jobs import JobRunner
from ..core.page_kind.proposal_log import PageKindProposalLog
from ..core.page_kind.reviewed_store import PageKindReviewedStore, is_marker_reviewed
from ..core.page_state import PageLoader, PageLoadOutcome, ensure_page_model
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..settings import Settings
from .dependencies import get_job_runner, get_page_store_optional, get_project_state, get_settings
from .middleware.error_handler import ApiError
from .pages import (
    _build_page_loader_from_context,
    _confirm_page_kind_locked,
    _normalize_page_kind_input,
    _resolve_page_object_for_pages,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

    from ..core.models import Project

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["page-kinds"])

_BulkStatus = Literal["confirmed", "not_loaded", "store_unavailable", "persist_failed"]


class _NullPageLoader:
    """Stand-in ``PageLoader`` for when no OCR loader can be built.

    Every lane misses, so every not-yet-loaded page reports ``not_loaded``.
    Safe here because the bulk route always calls ``ensure_page_model`` with
    ``allow_ocr=False`` — ``run_ocr`` is never reached.
    """

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def run_ocr(
        self,
        page_index: int,
        *,
        edited_image_bytes: bytes | None = None,
        page_kind: PageKind | None = None,
    ) -> PageLoadOutcome:
        raise RuntimeError("_NullPageLoader.run_ocr should never be called (allow_ocr=False)")


# ── Wire shapes ─────────────────────────────────────────────────────────


class PageKindsListItem(BaseModel):
    """One page's row in the book-wide page-kinds list."""

    page_index: int
    confirmed_kind: PageKind | None
    reviewed: bool
    proposed_kind: PageKind | None
    confidence: float | None
    run_id: str | None


class PageKindsListResponse(BaseModel):
    """``GET .../page-kinds`` response."""

    total_pages: int
    reviewed_count: int
    pages: list[PageKindsListItem]


class ConfirmPageKindsBulkItem(BaseModel):
    """One page's requested kind in a bulk-confirm request."""

    page_index: int
    kind: Annotated[PageKind, BeforeValidator(_normalize_page_kind_input)]


class ConfirmPageKindsBulkRequest(BaseModel):
    """``POST .../page-kinds/confirm`` request body."""

    pages: list[ConfirmPageKindsBulkItem]
    note: str | None = None


class ConfirmPageKindsResultItem(BaseModel):
    """One page's outcome in a bulk-confirm response."""

    page_index: int
    status: _BulkStatus


class ConfirmPageKindsBulkResponse(BaseModel):
    """``POST .../page-kinds/confirm`` response body."""

    results: list[ConfirmPageKindsResultItem] = Field(default_factory=list)
    confirmed_count: int = 0


# ── Helpers ──────────────────────────────────────────────────────────────


def _page_kinds_project_not_found(project_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(error="project_not_found", message=f"project not found: {project_id}").model_dump(),
    )


def _bulk_page_loader(runner: JobRunner, project_state: ProjectState, settings: Settings) -> PageLoader:
    """Build the loader used for every requested page in one bulk-confirm request.

    Falls back to ``_NullPageLoader`` when no OCR loader can be built (e.g. no
    project context wired) — pages already in memory still confirm; pages
    that would need a fresh load report ``not_loaded``.
    """
    try:
        return _build_page_loader_from_context(runner, project_state, settings)
    except Exception:
        log.warning(
            "confirm_page_kinds_bulk: no page loader available; unloaded pages will report not_loaded",
            exc_info=True,
        )
        return _NullPageLoader()


def _confirm_one_bulk_page(
    *,
    project_root: Path,
    project_state: ProjectState,
    page_store: LabelerPageStore | None,
    loader: PageLoader,
    page_index: int,
    kind: PageKind,
    note: str | None,
) -> _BulkStatus:
    """Load (if needed) and confirm one page — one page's worth of the bulk route.

    Mirrors the single-page route's checks in order: not loaded, then store
    unavailable, then the shared locked-confirm body.
    """
    outcome = ensure_page_model(project_state, page_index, loader=loader, allow_ocr=False)
    if outcome is None:
        return "not_loaded"

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object_for_pages(pstate)
    if pstate is None or page is None:
        return "not_loaded"

    page_id = pstate.page_id
    if page_store is None or page_id is None:
        log.warning(
            "confirm_page_kinds_bulk: no durable target for page=%d (store=%s page_id=%s)",
            page_index,
            "wired" if page_store is not None else "missing",
            page_id,
        )
        return "store_unavailable"

    save_error = _confirm_page_kind_locked(
        project_root=project_root,
        project_state=project_state,
        page_index=page_index,
        page_store=page_store,
        kind=kind,
        note=note,
        method="bulk",
    )
    return "persist_failed" if save_error is not None else "confirmed"


# ── Routes ───────────────────────────────────────────────────────────────


def page_kinds_rows(project: Project, project_state: ProjectState) -> tuple[list[PageKindsListItem], int]:
    """Every page's proposed and confirmed kind, plus the book's reviewed count.

    Reads the proposal journal once (``PageKindProposalLog.latest_by_page``)
    and the reviewed journal once (``PageKindReviewedStore.latest_by_page``)
    — a book of any size costs exactly two file reads. ``confirmed_kind``
    comes from the live page when it is loaded; otherwise from the latest
    reviewed marker, which is ``None`` for a marker written before the
    marker carried a kind (reported as "reviewed, kind not recorded").

    Shared by ``list_page_kinds`` and ``api/review_queue.py``'s book-wide
    review queue (pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-
    what-to-review-next.md "Reuse the existing counting paths"), so the two
    routes can never disagree about which pages still need a kind confirmed.
    """
    proposals_by_page = PageKindProposalLog(project.project_root).latest_by_page()
    markers_by_page = PageKindReviewedStore(project.project_root).latest_by_page()

    rows: list[PageKindsListItem] = []
    reviewed_count = 0
    for page_index in range(project.total_pages):
        marker = markers_by_page.get(page_index)
        reviewed = is_marker_reviewed(marker)
        if reviewed:
            reviewed_count += 1

        pstate = project_state.get_page_state(page_index)
        page = _resolve_page_object_for_pages(pstate)
        if page is not None:
            confirmed_kind = page.page_kind
        else:
            confirmed_kind = marker.kind if reviewed and marker is not None else None

        proposal = proposals_by_page.get(page_index)
        rows.append(
            PageKindsListItem(
                page_index=page_index,
                confirmed_kind=confirmed_kind,
                reviewed=reviewed,
                proposed_kind=proposal.kind if proposal is not None else None,
                confidence=proposal.confidence if proposal is not None else None,
                run_id=proposal.run_id if proposal is not None else None,
            )
        )
    return rows, reviewed_count


@router.get(
    "/{project_id}/page-kinds",
    response_model=PageKindsListResponse,
    operation_id="list_page_kinds",
)
def list_page_kinds(
    project_id: str,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """Every page's proposed and confirmed kind, in page order.

    See ``page_kinds_rows`` for how the rows are built — this route just
    wraps them in the book-level response shape.
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _page_kinds_project_not_found(project_id)

    rows, reviewed_count = page_kinds_rows(project, project_state)

    response = PageKindsListResponse(
        total_pages=project.total_pages,
        reviewed_count=reviewed_count,
        pages=rows,
    )
    return JSONResponse(status_code=200, content=response.model_dump(mode="json"))


@router.post(
    "/{project_id}/page-kinds/confirm",
    response_model=ConfirmPageKindsBulkResponse,
    operation_id="confirm_page_kinds_bulk",
)
def confirm_page_kinds_bulk(
    *,
    project_id: str,
    body: ConfirmPageKindsBulkRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
    settings: Settings = Depends(get_settings),
    page_store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """Confirm many pages in one request — each exactly as the single-page
    route confirms it (``_confirm_page_kind_locked``).

    A page index outside the book, or the same index requested twice, fails
    the whole request with ``400`` before any page is written. Those two
    checks also bound ``len(body.pages)`` at the book's page count: every
    index is unique and in range, so more entries than that is impossible
    without tripping one of them first.

    Each page not already in memory is loaded through ``ensure_page_model``
    with ``allow_ocr=False`` — confirming a kind must never start OCR — under
    the project lock, which is released before this function takes that
    page's lock to confirm it (the same order a page fetch followed by an
    edit already uses).
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _page_kinds_project_not_found(project_id)

    total_pages = project.total_pages
    seen: set[int] = set()
    for item in body.pages:
        if item.page_index < 0 or item.page_index >= total_pages:
            return JSONResponse(
                status_code=400,
                content=ApiError(
                    error="page_index_out_of_range",
                    message=f"page_index {item.page_index} is out of range for a book of {total_pages} pages",
                ).model_dump(),
            )
        if item.page_index in seen:
            return JSONResponse(
                status_code=400,
                content=ApiError(
                    error="duplicate_page_index",
                    message=f"page_index {item.page_index} was requested more than once",
                ).model_dump(),
            )
        seen.add(item.page_index)

    loader = _bulk_page_loader(runner, project_state, settings)

    results: list[ConfirmPageKindsResultItem] = []
    confirmed_count = 0
    for item in body.pages:
        status = _confirm_one_bulk_page(
            project_root=project.project_root,
            project_state=project_state,
            page_store=page_store,
            loader=loader,
            page_index=item.page_index,
            kind=item.kind,
            note=body.note,
        )
        results.append(ConfirmPageKindsResultItem(page_index=item.page_index, status=status))
        if status == "confirmed":
            confirmed_count += 1

    response = ConfirmPageKindsBulkResponse(results=results, confirmed_count=confirmed_count)
    return JSONResponse(status_code=200, content=response.model_dump(mode="json"))


def install_page_kinds_router(app: FastAPI) -> None:
    """Register the page-kinds router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "ConfirmPageKindsBulkItem",
    "ConfirmPageKindsBulkRequest",
    "ConfirmPageKindsBulkResponse",
    "ConfirmPageKindsResultItem",
    "PageKindsListItem",
    "PageKindsListResponse",
    "confirm_page_kinds_bulk",
    "install_page_kinds_router",
    "list_page_kinds",
    "page_kinds_rows",
    "router",
]

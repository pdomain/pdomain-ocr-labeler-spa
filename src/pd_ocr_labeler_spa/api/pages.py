"""``/api/projects/{project_id}/pages`` router — spec §5.3."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..core.jobs import JobRunner
from ..core.models import EncodedDims, LineFilter, LineMatch, PageRecord, Selection
from ..core.project_state import ProjectState
from .dependencies import get_job_runner, get_project_state
from .middleware.error_handler import ApiError

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/pages",
    tags=["pages"],
)


# ── Wire shapes — spec §01-data-models.md §2 ─────────────────────────


class PagePayload(BaseModel):
    """Full per-page payload — spec §5.3 / §1 ``PagePayload``.

    ``page_text_ocr`` and ``page_text_gt`` are pre-built plaintext strings
    assembled from the page's OCR / GT words.  When
    ``normalize_plaintext_tabs=True`` in ``AppConfig`` these are normalised
    (long-s → ASCII etc.) before serialisation.  The envelope itself is never
    modified.
    """

    project_id: str
    page_index: int
    page_record: PageRecord | None = None
    line_matches: list[LineMatch] = Field(default_factory=list)
    selection: Selection = Field(default_factory=Selection)
    encoded_dims: EncodedDims | None = None
    line_filter: LineFilter = LineFilter.ALL
    image_url: str | None = None
    generation: int = 0
    # Plaintext representations — spec §1 ``PagePayload``.
    page_text_ocr: str | None = None
    page_text_gt: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SavePageRequest(BaseModel):
    """Body for ``POST .../save`` — spec §5.3."""

    generation: int | None = None


class SavePageResponse(BaseModel):
    """Response for ``POST .../save`` — spec §5.3."""

    project_id: str
    page_index: int
    saved: bool = True


class SaveFailure(BaseModel):
    """Error detail for failed save operations — spec §5.3."""

    page_index: int
    error: str


class SaveProjectResponse(BaseModel):
    """Response for ``POST .../save-all`` → ``202 {job_id}`` — spec §5.3."""

    job_id: str
    failures: list[SaveFailure] = Field(default_factory=list)


class ReloadOCRRequest(BaseModel):
    """Body for ``POST .../reload-ocr`` — spec §5.3."""

    force: bool = False


class ReloadOCRResponse(BaseModel):
    """Response for ``POST .../reload-ocr`` → 202 Accepted — spec §5.3."""

    job_id: str


class RematchGtRequest(BaseModel):
    """Body for ``POST .../rematch-gt`` — spec §5.3."""

    pass


class RotatePageRequest(BaseModel):
    """Body for ``POST .../rotate`` — spec §19 (M9.1).

    ``degrees`` must be one of ``-90``, ``90``, ``180``.
    ``manual`` distinguishes user-initiated (``True``) from
    auto-rotate (``False``) for ``rotation_source`` tracking.
    """

    degrees: int
    manual: bool = True


class RotatePageResponse(BaseModel):
    """Response for ``POST .../rotate`` → ``202 Accepted`` — spec §19 (M9.1)."""

    job_id: str


# ── Helpers ──────────────────────────────────────────────────────────


def _project_not_found(project_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="project_not_found",
            message=f"project not found: {project_id}",
        ).model_dump(),
    )


def _page_not_found(page_index: int) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="page_not_found",
            message=f"page not found: {page_index}",
        ).model_dump(),
    )


def _not_implemented(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=ApiError(
            error="not_implemented",
            message=message,
        ).model_dump(),
    )


def _check_project_and_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState,
) -> JSONResponse | None:
    """Return an error response if the project/page isn't valid, else None."""
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _project_not_found(project_id)
    if page_index < 0 or page_index >= project.total_pages:
        return _page_not_found(page_index)
    return None


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/{page_index}", response_model=PagePayload)
def get_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``GET /api/projects/{pid}/pages/{idx}`` — stub; M3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("GET page payload requires M3 OCR plumbing")


@router.post("/{page_index}/save", response_model=SavePageResponse)
def save_page(
    project_id: str,
    page_index: int,
    body: SavePageRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../save`` — stub; M3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("save page requires M3 persistence plumbing")


@router.post("/{page_index}/load", response_model=PagePayload)
def load_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../load`` — stub; M3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("reload page from disk requires M3 persistence plumbing")


@router.post("/{page_index}/reload-ocr", response_model=ReloadOCRResponse)
def reload_ocr(
    project_id: str,
    page_index: int,
    body: ReloadOCRRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST .../reload-ocr`` → ``202 {job_id}`` — spec §5.3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    job_id = runner.submit(
        "reload_ocr",
        project_id=project_id,
        payload={"page_index": page_index},
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


@router.post("/{page_index}/rematch-gt", response_model=PagePayload)
def rematch_gt(
    project_id: str,
    page_index: int,
    body: RematchGtRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../rematch-gt`` — stub; M3."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("rematch-gt requires M3 plumbing")


@router.post("/{page_index}/rotate", response_model=RotatePageResponse)
def rotate_page(
    project_id: str,
    page_index: int,
    body: RotatePageRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST .../rotate`` → ``202 {job_id}`` — spec §19 (M9.1).

    Enqueues a ``rotate_page`` job that rotates the source image, re-runs
    OCR, updates ``PageRecord.rotation_degrees`` / ``rotation_source``, and
    auto-saves the envelope.

    ``degrees`` must be one of ``-90``, ``90``, ``180``; other values are
    rejected with ``400 invalid_degrees``.  ``manual=True`` (default) sets
    ``rotation_source="manual"``; ``False`` sets ``"auto"`` (used by the
    auto-rotate-all pass in M9.2).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    if body.degrees not in (-90, 90, 180):
        return JSONResponse(
            status_code=400,
            content=ApiError(
                error="invalid_degrees",
                message=f"degrees must be -90, 90, or 180; got {body.degrees}",
            ).model_dump(),
        )

    job_id = runner.submit(
        "rotate_page",
        project_id=project_id,
        payload={
            "project_id": project_id,
            "page_index": page_index,
            "degrees": body.degrees,
            "manual": body.manual,
        },
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


def install_pages_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the pages router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "PagePayload",
    "ReloadOCRRequest",
    "ReloadOCRResponse",
    "RematchGtRequest",
    "RotatePageRequest",
    "RotatePageResponse",
    "SaveFailure",
    "SavePageRequest",
    "SavePageResponse",
    "SaveProjectResponse",
    "install_pages_router",
    "router",
]

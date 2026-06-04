"""``/api/projects/{project_id}/pages/{page_index}/refine`` router (§5.6).

Also exposes ``GET /api/refine/available`` — a capability probe used by
``ErasePixelsSection`` to decide whether to enable the Apply button (FO-9).

Spec authority:
- ``docs/architecture/01-data-models.md §2`` — ``RefineScopeRequest`` shape.
- ``docs/architecture/02-backend.md §5.6`` — endpoint contract: 202 Accepted + job_id.
- ``docs/specs/2026-05-12-backend-design.md`` — long-running operations
  return 202 Accepted with {job_id}; callers open EventSource on the job.
- ``docs/hifi-followons.md #FO-9`` — ErasePixelsSection backendAvailable probe.

``POST .../refine`` is a long-running operation (OCR bounding-box
refinement may take seconds per scope). It follows the same 202+job_id
pattern as ``POST .../reload-ocr`` (spec §5.3). The stub runner immediately
completes — full OCR refinement logic lands in M3-proper when the OCR
adapter is wired.

``GET /api/refine/available`` is a lightweight synchronous probe:
- ``available: true`` — the server has an OCR engine wired that supports
  bbox refinement (currently always ``false`` until M3-proper).
- ``available: false`` — the feature is not wired; clients should disable
  the Apply button and show an explanatory tooltip.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.jobs import JobRunner
from ..core.project_state import ProjectState
from .dependencies import get_job_runner, get_project_state
from .middleware.error_handler import ApiError

# Two routers: the per-project refine route keeps its prefix; the capability
# probe lives at /api/refine/* (no project_id in path) so it can be called
# before any project is loaded.
router = APIRouter(prefix="/api/projects", tags=["refine"])
probe_router = APIRouter(prefix="/api/refine", tags=["refine"])


class RefineAvailableResponse(BaseModel):
    """Response for ``GET /api/refine/available`` — FO-9 capability probe.

    ``available`` is ``True`` when the refine engine is wired. As of Lane A
    Task A1 the ``refine_bboxes`` job handler is registered, so this is
    ``True``. ``reason`` is empty when ``available=True``; otherwise a
    human-readable explanation of why the feature is not available.
    """

    available: bool = True
    reason: str = ""


class RefineScopeRequest(BaseModel):
    """Body for ``POST .../refine`` — spec §2 lines 371-378."""

    scope: Literal["page", "paragraph", "line", "word"]
    mode: Literal["refine", "expand_then_refine", "expand_only"] = "refine"
    padding_px: int = 2
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    word_indices: list[tuple[int, int]] = []


class RefineJobResponse(BaseModel):
    """Response for ``POST .../refine`` → ``202 {job_id}`` — spec §5.6."""

    job_id: str


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


@router.post("/{project_id}/pages/{page_index}/refine", status_code=202, response_model=RefineJobResponse)
def refine_scope(
    project_id: str,
    page_index: int,
    body: RefineScopeRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST .../refine`` → ``202 {job_id}`` — queue a bbox-refinement job.

    Long-running: the handler submits the job and returns immediately with
    202 Accepted. The SPA polls ``GET /api/jobs/{id}/events`` (SSE) until
    the terminal ``complete`` event. Full OCR refinement logic (``IOCREngine``
    + bounding-box adjustment) lands in M3-proper; the stub runner
    immediately emits a terminal complete.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    job_id = runner.submit(
        "refine_bboxes",
        project_id=project_id,
        payload={
            "page_index": page_index,
            "scope": body.scope,
            "mode": body.mode,
            "padding_px": body.padding_px,
            "paragraph_indices": body.paragraph_indices,
            "line_indices": body.line_indices,
            "word_indices": body.word_indices,
        },
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


@probe_router.get("/available", response_model=RefineAvailableResponse)
def refine_available() -> RefineAvailableResponse:
    """``GET /api/refine/available`` — capability probe (FO-9).

    Returns immediately without requiring a project to be loaded. As of
    Lane A Task A1 the ``refine_bboxes`` job handler is registered and the
    DocTR loader attaches the cv2 image, so this returns ``available=True``
    with ``reason=""``.

    The ``ErasePixelsSection`` frontend component calls this on mount
    and uses the result to decide whether to enable the Apply button.
    """
    return RefineAvailableResponse()


def install_refine_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the refine routers. Called from ``bootstrap.build_app``."""
    app.include_router(router)
    app.include_router(probe_router)


__all__ = [
    "RefineAvailableResponse",
    "RefineJobResponse",
    "RefineScopeRequest",
    "install_refine_router",
    "probe_router",
    "router",
]

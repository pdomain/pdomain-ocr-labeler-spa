"""``/api/projects/{project_id}/pages/{page_index}/refine`` router (§5.6).

Spec authority:
- ``specs/01-data-models.md §2`` — ``RefineScopeRequest`` shape.
- ``specs/02-backend.md §5.6`` — endpoint contract: 202 Accepted + job_id.
- ``docs/specs/2026-05-12-backend-design.md`` — long-running operations
  return 202 Accepted with {job_id}; callers open EventSource on the job.

``POST .../refine`` is a long-running operation (OCR bounding-box
refinement may take seconds per scope). It follows the same 202+job_id
pattern as ``POST .../reload-ocr`` (spec §5.3). The stub handler in the
job runner immediately completes — full OCR refinement logic lands in
M3-proper when the OCR adapter is wired.
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

router = APIRouter(prefix="/api/projects", tags=["refine"])


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


@router.post("/{project_id}/pages/{page_index}/refine", response_model=RefineJobResponse)
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


def install_refine_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the refine router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "RefineJobResponse",
    "RefineScopeRequest",
    "install_refine_router",
    "router",
]

"""``/api/projects/{project_id}/pages`` router.

Spec authority: ``specs/02-backend.md §5.3``.

What this slice (issue #185) ships:

- ``GET /{idx}`` — validates project + page-index; returns 501 until M3
  wires ``ensure_page_model`` + ``PagePayload`` construction.
- ``POST /{idx}/save`` — validates project + page-index; returns 501
  until M3 wires the labeled-lane persistence layer.
- ``POST /{idx}/load`` — validates project + page-index; returns 501
  until M3 wires the reload-from-disk lane.
- ``POST /{idx}/reload-ocr`` — 202 Accepted with a ``job_id``; the job
  handler in ``core/jobs/runner.py`` is a stub that immediately
  completes. M3 will replace the stub body with the real doctr pipeline.

``POST /api/projects/{pid}/save-all`` lives here logically (it's a
project-scoped page operation) but is registered on the projects router
prefix to match the spec URL shape.

Validation order for all page endpoints:

1. ``project_id`` matches the currently loaded project in ``ProjectState``
   → ``404 project_not_found`` if not.
2. ``page_index`` is in range ``[0, total_pages)``
   → ``404 page_not_found`` if out of range.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..core.jobs import JobRunner
from ..core.project_state import ProjectState
from .dependencies import get_job_runner, get_project_state
from .middleware.error_handler import ApiError

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/pages",
    tags=["pages"],
)


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


@router.get("/{page_index}")
def get_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``GET /api/projects/{pid}/pages/{idx}`` — load page payload.

    Spec §5.3: lazily loads via labeled → cached → OCR lanes.
    M3 will wire ``ensure_page_model`` + ``PagePayload`` construction.
    Until then returns 501 for in-range pages.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("GET page payload requires M3 OCR plumbing")


@router.post("/{page_index}/save")
def save_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../save`` — write labeled envelope to disk.

    Returns 501 until M3 wires ``persist_page_to_file``.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("save page requires M3 persistence plumbing")


@router.post("/{page_index}/load")
def load_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../load`` — reload page from disk, discard in-memory edits.

    Returns 501 until M3 wires the reload-from-disk lane.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _not_implemented("reload page from disk requires M3 persistence plumbing")


@router.post("/{page_index}/reload-ocr")
def reload_ocr(
    project_id: str,
    page_index: int,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST .../reload-ocr`` → ``202 {job_id}``.

    Spec §5.3: long-running; returns 202 Accepted immediately.
    The job handler is a stub that immediately completes (M3 will wire
    the real doctr pipeline). Callers track progress via
    ``GET /api/jobs/{job_id}/events``.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    job_id = runner.submit(
        "reload_ocr",
        project_id=project_id,
        payload={"page_index": page_index},
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


def install_pages_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the pages router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = ["install_pages_router", "router"]

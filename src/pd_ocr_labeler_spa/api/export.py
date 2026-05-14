"""``/api/projects/{project_id}/export`` router.

Spec authority:
- ``specs/02-backend.md §5.9`` lines 325-328 — endpoint contracts.
- ``specs/01-data-models.md §2`` lines 415-425 — ``ExportScope``,
  ``ExportRequest``, ``ExportResponse`` shapes.
- ``specs/10-export.md`` — export dialog + DocTR export operation.

Routes:
- ``POST /api/projects/{project_id}/export`` → 202 ``ExportResponse{job_id}``.
  Enqueues an ``export`` job via the ``JobRunner`` and returns immediately.
  The caller opens ``EventSource(/api/jobs/{job_id}/events)`` to track
  progress.
- ``GET /api/projects/{project_id}/exports`` → list of past exports
  (best-effort, read from disk — stub returning empty list until the
  export handler writes manifests).
"""

from __future__ import annotations

import enum

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.jobs import JobRunner
from .dependencies import get_job_runner

router = APIRouter(prefix="/api/projects", tags=["export"])


class ExportScope(str, enum.Enum):
    """Export scope discriminant — spec §2 lines 411-412."""

    CURRENT = "current"
    ALL_VALIDATED = "all_validated"


class ExportRequest(BaseModel):
    """Body for ``POST /api/projects/{id}/export`` — spec §2 lines 414-420.

    ``normalize_recognition_labels``: when ``True``, recognition ``labels.json``
    strings are normalised (long-s → ASCII, ligatures → ASCII) before write.
    Image bytes are unchanged.  Requires ``pd_book_tools.text.normalize``;
    silently ignored when the module is absent.  Spec: §18-text-normalization.
    """

    scope: ExportScope
    style_filters: list[str] = []
    component_filter: str | None = None
    include_classification: bool = False
    detection_only: bool = False
    recognition_only: bool = False
    normalize_recognition_labels: bool = False


class ExportResponse(BaseModel):
    """Response for export — spec §2 lines 422-423."""

    job_id: str


@router.post("/{project_id}/export", response_model=ExportResponse, status_code=202)
def start_export(
    project_id: str,
    body: ExportRequest,
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST /api/projects/{id}/export`` — enqueue an export job.

    Spec §5.9 line 325. Returns 202 Accepted with ``{job_id}``; the
    caller opens ``EventSource(/api/jobs/{job_id}/events)`` to receive
    progress and the terminal event. The actual DocTR export pipeline
    is wired in the ``export`` job handler (``core/jobs/runner.py``
    ``_HANDLERS["export"]``); until full M3 wiring the handler completes
    immediately (stub body, no I/O).
    """
    job_id = runner.submit(
        "export",
        project_id=project_id,
        payload={
            "scope": body.scope.value,
            "style_filters": body.style_filters,
            "component_filter": body.component_filter,
            "include_classification": body.include_classification,
            "detection_only": body.detection_only,
            "recognition_only": body.recognition_only,
        },
    )
    return JSONResponse(
        status_code=202,
        content=ExportResponse(job_id=job_id).model_dump(),
    )


@router.get("/{project_id}/exports")
def list_exports(project_id: str) -> JSONResponse:
    """``GET /api/projects/{id}/exports`` — past exports (best-effort).

    Spec §5.9 line 326. Returns a list of past export manifests read
    from disk. Until the export handler writes manifests, always returns
    an empty list (spec says "best-effort").
    """
    return JSONResponse(status_code=200, content=[])


def install_export_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the export router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "ExportRequest",
    "ExportResponse",
    "ExportScope",
    "install_export_router",
    "router",
]

"""``/api/projects/{project_id}/export`` router (M3+).

Spec authority:
- ``specs/01-data-models.md §2`` — ``ExportScope``, ``ExportRequest``,
  ``ExportResponse`` shapes.
- ``specs/02-backend.md §5.7`` — endpoint contract.

Route handler is a stub returning 501 until M3 export plumbing lands.
"""

from __future__ import annotations

import enum

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects", tags=["export"])


class ExportScope(str, enum.Enum):
    """Export scope discriminant — spec §2 lines 411-412."""

    CURRENT = "current"
    ALL_VALIDATED = "all_validated"


class ExportRequest(BaseModel):
    """Body for ``POST /api/projects/{id}/export`` — spec §2 lines 414-420."""

    scope: ExportScope
    style_filters: list[str] = []
    component_filter: str | None = None
    include_classification: bool = False
    detection_only: bool = False
    recognition_only: bool = False


class ExportResponse(BaseModel):
    """Response for export — spec §2 lines 422-423."""

    job_id: str


@router.post("/{project_id}/export", response_model=ExportResponse)
def start_export(project_id: str, body: ExportRequest) -> JSONResponse:
    """``POST /api/projects/{id}/export`` — stub; M3."""
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "message": "export route lands in M3"},
    )


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

"""``POST /api/projects/{project_id}/maintenance/prune`` — U-M6 blob prune.

The route is the only interactive trigger. Project open runs it only when
``PDLABELER_PRUNE_ON_OPEN`` is set. Writes never prune.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.page_prune import prune_store
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..settings import Settings
from .dependencies import get_page_store, get_project_state, get_settings
from .middleware.error_handler import ApiError

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/maintenance",
    tags=["maintenance"],
)


class PruneResponse(BaseModel):
    """How many blob files the maintenance prune deleted."""

    deleted_count: int


def _project_error(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=ApiError(error=error, message=message).model_dump())


@router.post("/prune", response_model=PruneResponse)
def prune_project(
    *,
    project_id: str,
    project_state: ProjectState = Depends(get_project_state),  # pyright: ignore[reportCallInDefaultInitializer]
    settings: Settings = Depends(get_settings),  # pyright: ignore[reportCallInDefaultInitializer]
    store: LabelerPageStore = Depends(get_page_store),  # pyright: ignore[reportCallInDefaultInitializer]
) -> JSONResponse:
    """Delete blobs the undo spec marks dead. Live and lineage-reachable blobs stay."""
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _project_error(404, "project_not_found", f"project {project_id!r} is not loaded")
    deleted = prune_store(
        store,
        project_id,
        retention_days=settings.prune_retention_days,
        undo_depth=settings.undo_depth,
    )
    log.info("prune: project=%s deleted=%d", project_id, len(deleted))
    return JSONResponse(
        status_code=200,
        content=PruneResponse(deleted_count=len(deleted)).model_dump(mode="json"),
    )


def install_maintenance_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the maintenance router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = ["PruneResponse", "install_maintenance_router", "prune_project"]

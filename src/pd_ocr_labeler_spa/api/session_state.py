"""GET /api/session-state — returns last-loaded project path and page index.

Spec authority:
- ``docs/specs/2026-05-12-root-page-design.md §Decision`` — endpoint contract.
- ``docs/architecture/09-persistence.md §6`` — session_state.json schema.

The endpoint reads ``session_state.json`` from ``settings.data_root`` and
returns its contents. If the file is missing or unparsable, returns a
response with ``last_project_path: null`` (same as a cold first-run state).

This is a read-only endpoint: it does not modify session state. The
frontend ``RootPage`` component uses it to decide whether to redirect to
the last-viewed page or show the empty state.

Response (200 always):

    {
      "schema_version": "1.0",
      "last_project_path": "/abs/path/to/project" | null,
      "last_page_index": 0
    }

Issue: #274
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..core.persistence.session_state import (
    SESSION_STATE_SCHEMA_VERSION,
    load_session_state,
)

log = logging.getLogger(__name__)

router = APIRouter()


class SessionStateResponse(BaseModel):
    """Response model for GET /api/session-state.

    Matches the ``session_state.json`` schema (spec §6) for direct
    frontend consumption. ``last_project_path`` is ``null`` on first
    run or when the file is missing/corrupt.
    """

    schema_version: str = SESSION_STATE_SCHEMA_VERSION
    last_project_path: str | None = None
    last_page_index: int = 0


@router.get("/api/session-state", response_model=SessionStateResponse)
def get_session_state(request: Request) -> SessionStateResponse:
    """Read and return the last-loaded session state.

    Always returns 200. Missing or corrupt session_state.json is treated
    as a cold start (``last_project_path: null``) — the frontend falls
    back to the EmptyProjectState in that case.

    Spec: ``docs/specs/2026-05-12-root-page-design.md §Decision``.
    """
    settings = request.app.state.settings
    state = load_session_state(settings.data_root)
    if state is None:
        return SessionStateResponse()
    return SessionStateResponse(
        schema_version=state.schema_version,
        last_project_path=state.last_project_path,
        last_page_index=state.last_page_index,
    )


def install_session_state_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the session-state router on ``app``."""
    app.include_router(router)

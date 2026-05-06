"""GET /healthz — operational liveness probe.

Per ``specs/02-backend.md §5.1``::

    GET /healthz → {"status": "ok", "version": "..."}

Unauthenticated by design: probes don't carry tokens. M0 ships the
minimal shape; later milestones may extend the response (e.g. adapter
state) without breaking existing consumers.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import __version__

router = APIRouter()


class HealthzResponse(BaseModel):
    status: str
    version: str


@router.get("/healthz", include_in_schema=False)
async def healthz() -> HealthzResponse:
    return HealthzResponse(status="ok", version=__version__)


def install_healthz(app) -> None:  # type: ignore[no-untyped-def]
    """Register ``GET /healthz``. Call before the SPA mount so the catch-all
    fallback doesn't shadow it."""
    app.include_router(router)

"""``/api/notifications`` router — SSE stream + dismiss.

Spec authority:
- ``docs/architecture/02-backend.md §5.11`` lines 342-346 — endpoint contracts.
- ``docs/architecture/11-notifications.md §2.3`` — SSE shape (``event: notification``,
  JSON data: ``{id, kind, message, created_at}``).
- ``docs/architecture/01-data-models.md §2 Notifications`` — wire shapes.

Routes:
- ``GET /api/notifications/stream`` — SSE. First events are the ring-buffer
  snapshot; subsequent events are live broadcasts. Stays open until the
  client closes the connection.
- ``POST /api/notifications/{id}/dismiss`` — remove one notification from
  the buffer. Returns 204 on success, 404 if not found. Test-only per spec.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..core.notifications import NotificationQueue
from .dependencies import get_notification_queue
from .middleware.error_handler import ApiError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _sse_event(notif_dict: dict) -> str:
    return f"event: notification\ndata: {json.dumps(notif_dict)}\n\n"


@router.get(
    "/stream",
    response_class=StreamingResponse,
    # SSE: not expressible as a typed Pydantic response — spec §5.11
    # intentional exception (same as job events).
)
async def notifications_stream(
    nq: NotificationQueue = Depends(get_notification_queue),
) -> StreamingResponse:
    """``GET /api/notifications/stream`` — SSE.

    Spec §5.11 line 342. First yields the ring-buffer snapshot (so a
    late subscriber sees recent history), then live events as they
    arrive. The connection stays open until the client closes it.
    """

    async def stream():
        async for notif in nq.subscribe():
            yield _sse_event(notif.model_dump(mode="json"))

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/{notification_id}/dismiss")
def dismiss_notification(
    notification_id: str,
    nq: NotificationQueue = Depends(get_notification_queue),
) -> Response:
    """``POST /api/notifications/{id}/dismiss`` — remove from ring buffer.

    Spec §5.11 line 343: 204 on success, 404 if not found. Test-only.
    """
    found = nq.dismiss(notification_id)
    if not found:
        return JSONResponse(
            status_code=404,
            content=ApiError(
                error="notification_not_found",
                message=f"notification not found: {notification_id}",
            ).model_dump(),
        )
    return Response(status_code=204)


def install_notifications_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the notifications router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = ["install_notifications_router", "router"]

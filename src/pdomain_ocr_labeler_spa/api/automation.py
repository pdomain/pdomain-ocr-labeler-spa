"""Revisioned application events and explicit per-tab viewer commands."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..core.automation.service import AutomationService, AutomationState
from ..core.automation.viewers import ViewerAck, ViewerCommandRequest, ViewerConflictError, ViewerState

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

router = APIRouter(prefix="/api/automation", tags=["automation"])


def request_app(scope: Mapping[str, object]) -> FastAPI:
    app = scope["app"]
    if not isinstance(app, FastAPI):
        raise RuntimeError("request app is not FastAPI")
    return app


def get_automation(request: Request) -> AutomationService:
    app = request_app(request.scope)
    service: object = getattr(app.state, "automation", None)
    if not isinstance(service, AutomationService):
        raise RuntimeError("app.state.automation is not configured")
    return service


def conflict_response(exc: ViewerConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"error": exc.error, "message": str(exc), "details": None}
    )


class ViewerRegistration(BaseModel):
    viewer_id: str | None = None


Service = Annotated[AutomationService, Depends(get_automation)]


@router.get("/state", response_model=AutomationState)
def state(service: Service) -> AutomationState:
    return service.snapshot()


@router.post("/viewers", response_model=ViewerState)
def register(body: ViewerRegistration, service: Service) -> ViewerState | JSONResponse:
    try:
        return service.viewers.register(body.viewer_id)
    except ViewerConflictError as exc:
        return conflict_response(exc)


@router.get("/view", response_model=ViewerState)
def view(viewer_id: str, service: Service) -> ViewerState | JSONResponse:
    try:
        return service.viewers.get(viewer_id)
    except ViewerConflictError as exc:
        return conflict_response(exc)


@router.patch("/view", response_model=ViewerState)
def command(body: ViewerCommandRequest, service: Service) -> ViewerState | JSONResponse:
    try:
        return service.viewers.command(body)
    except ViewerConflictError as exc:
        return conflict_response(exc)


@router.post("/view/ack", response_model=ViewerState)
def acknowledge(body: ViewerAck, service: Service) -> ViewerState | JSONResponse:
    try:
        return service.viewers.ack(body)
    except ViewerConflictError as exc:
        return conflict_response(exc)


# SSE uses a streaming response rather than a JSON response model.
@router.get(
    "/events",
    response_class=StreamingResponse,
    response_model=None,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
def events(
    *,
    service: Service,
    after: Annotated[int | None, Query(ge=0)] = None,
    viewer_id: str | None = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse | JSONResponse:
    if viewer_id is not None:
        try:
            _ = service.viewers.get(viewer_id)
        except ViewerConflictError as exc:
            return conflict_response(exc)
    cursor = after
    if last_event_id is not None:
        try:
            cursor = int(last_event_id)
        except ValueError:
            cursor = None  # Invalid reconnect cursor explicitly resets.

    async def stream() -> AsyncIterator[str]:
        subscription = service.broker.subscribe(after=cursor, viewer_id=viewer_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(subscription.receive(), timeout=15)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                event_json = (
                    event.model_dump_json(exclude={"generation_reset"})
                    if event.generation_reset is None
                    else event.model_dump_json()
                )
                yield f"id: {event.revision}\nevent: {event.kind}\ndata: {event_json}\n\n"
        finally:
            subscription.close()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

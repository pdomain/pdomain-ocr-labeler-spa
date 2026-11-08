"""Publish successful synchronous domain writes before releasing snapshot readers."""

from __future__ import annotations

import inspect
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from fastapi.routing import APIRoute
from starlette.responses import Response

from .route_introspection import iter_leaf_routes

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send

    from pdomain_ocr_labeler_spa.core.automation.events import AutomationBroker
    from pdomain_ocr_labeler_spa.core.project_state import ProjectState


@dataclass(frozen=True)
class PublicationContext:
    broker: AutomationBroker
    project_state: ProjectState


_context: ContextVar[PublicationContext | None] = ContextVar("automation_publication", default=None)


@final
class PublicationContextMiddleware:
    def __init__(self, app: ASGIApp, *, broker: AutomationBroker, project_state: ProjectState) -> None:
        self.app = app
        self.context = PublicationContext(broker, project_state)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = _context.set(self.context)
        try:
            await self.app(scope, receive, send)
        finally:
            _context.reset(token)


@final
class PublishedCall[**P, R]:
    def __init__(self, call: Callable[P, R], *, page_index_name: str | None, mutation: bool) -> None:
        self.call = call
        self.page_index_name = page_index_name
        self.mutation = mutation
        self.__signature__: inspect.Signature = inspect.signature(call, eval_str=True)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        context = _context.get()
        if context is None:
            return self.call(*args, **kwargs)
        broker, project_state = context.broker, context.project_state
        with broker.lock:
            before_generation = project_state.generation
            result = self.call(*args, **kwargs)
            if isinstance(result, Response) and result.status_code >= 400:
                return result
            if self.mutation or project_state.generation != before_generation:
                page_index = kwargs.get(self.page_index_name) if self.page_index_name is not None else None
                project = project_state.loaded_project
                project_id = project.project_id if project is not None else None
                if isinstance(page_index, int):
                    state = project_state.get_page_state(page_index)
                    _ = broker.publish(
                        "page_changed",
                        project_id=project_id,
                        page_index=page_index,
                        generation=state.generation if state is not None else None,
                    )
                else:
                    _ = broker.publish("project_changed", project_id=project_id)
            return result


def install_change_publication(
    app: FastAPI, *, broker: AutomationBroker, project_state: ProjectState
) -> None:
    app.add_middleware(PublicationContextMiddleware, broker=broker, project_state=project_state)
    for route in iter_leaf_routes(app):
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/projects"):
            continue
        call = route.dependant.call
        if call is None or inspect.iscoroutinefunction(call):
            continue
        while isinstance(call, PublishedCall):
            call = call.call
        wrapped = PublishedCall(
            call,
            page_index_name="page_index" if "{page_index}" in route.path else None,
            mutation=bool((route.methods or set()) - {"GET", "HEAD", "OPTIONS"}),
        )
        route.endpoint = wrapped
        route.dependant.call = wrapped

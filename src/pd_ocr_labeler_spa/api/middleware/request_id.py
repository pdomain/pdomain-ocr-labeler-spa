"""Request-ID middleware for log correlation (specs/02-backend.md §9).

Reads the configured header (default ``X-Request-ID``) from the
incoming request — orchestrators / load balancers / Sentry typically
set this so a single user-facing request can be traced through every
service it touches. If the header is absent we mint a fresh
``uuid4().hex`` so log lines are still correlated within this app.

The id is published on a ``ContextVar``
(``logging_config.request_id_var``) for the duration of the request —
every ``logging.getLogger().info(...)`` call below this middleware in
the stack picks it up via ``RequestIdFilter``. The id is also echoed
back on the response header so clients (and end-to-end tests) can
capture it.

Design choice: this is a pure ASGI middleware, not a FastAPI
dependency. A dependency would only stamp routes that explicitly opt
in; we want *every* log line — including ones from ``lifespan``,
exception handlers, and the SPA fallback — to have the id.

Per spec §9 last bullets ("closes pgdp-prep gap"), this middleware
also emits a per-route audit log: a ``request_start`` info record on
entry (with ``path`` + ``method``) and a ``request_end`` info record
on exit (with ``status`` + ``duration_ms``). Both lines are emitted
INSIDE the request-id ContextVar scope, so the ``rid=`` tag from
``RequestIdFilter`` shows up on each — letting an operator grep one
end-to-end timeline per request. ``time.monotonic()`` is used for
duration so wall-clock jumps (NTP, suspend/resume) can't produce
negative spans.

Port shape from ``pd-prep-for-pgdp/src/pd_prep_for_pgdp/api/middleware/request_id.py``;
extended with the audit-log enhancement that spec §9 calls "closes
the pgdp-prep gap."
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ...core.logging_config import request_id_var

log = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Stamp every request with a correlation id + emit an audit log.

    Args:
        header_name: HTTP header to read & echo. Lower-cased on read
            (Starlette's headers are case-insensitive); echoed in the
            canonical case the caller passes in.
    """

    def __init__(self, app, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(self.header_name)
        rid = incoming or uuid.uuid4().hex
        token = request_id_var.set(rid)
        # Capture path + method up-front — Starlette's request can be
        # mutated by downstream middleware / handlers, but ``url.path``
        # and ``method`` are stable once the request is constructed.
        path = request.url.path
        method = request.method
        # ``time.monotonic`` rather than ``time.time``: monotonic is
        # immune to wall-clock jumps (NTP step, suspend/resume), so the
        # measured ``duration_ms`` can never be negative.
        started = time.monotonic()
        log.info(
            "request_start",
            extra={"path": path, "method": method},
        )
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            # Emit ``request_end`` BEFORE resetting the contextvar so
            # the ``rid=`` tag still appears via ``RequestIdFilter``.
            log.info(
                "request_end",
                extra={
                    "path": path,
                    "method": method,
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)
        response.headers[self.header_name] = rid
        return response

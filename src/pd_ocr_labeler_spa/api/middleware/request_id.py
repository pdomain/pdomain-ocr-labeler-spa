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

Design choice: this is a **raw ASGI middleware**, not a
``BaseHTTPMiddleware`` subclass. ``BaseHTTPMiddleware`` plumbs the
inner app through ``anyio`` streams + ``collapse_excgroups`` — when
``call_next`` raises, modern Starlette discards header mutations made
on the response object, so the rid header was silently dropped from
500 responses. Filed as B-50; this rewrite closes it.

Why we also re-implement the ``Exception`` catch-all here
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

FastAPI/Starlette routes the ``Exception``-class handler to
``ServerErrorMiddleware``, which sits **outside** all user middleware
in the framework's ASGI stack (see
``starlette/applications.py:build_middleware_stack``). When a route
raises an unhandled exception, the exception propagates UP through
us first (running our ``finally`` block — good, the audit log fires)
and then ``ServerErrorMiddleware`` builds the 500 response via the
registered handler and sends it directly via the OUTER ``send`` —
bypassing our ``send_wrapper``. The rid header is lost.

So we catch the exception ourselves, dispatch to the
``Exception``-class handler that ``error_handler.py`` registered on
``app.exception_handlers``, and send the resulting response through
our own ``send_wrapper``. Net effect: the rid header is on the 500
response, and the audit-log ``request_end`` line carries
``status=500`` with ``rid=<the actual id>`` (not the empty default
that ``ServerErrorMiddleware``'s separate context would have stamped).

The HTTPException / RequestValidationError / BoundingBoxGeometryError
handlers do NOT need this treatment — those are routed through
``ExceptionMiddleware`` which sits INSIDE us, so responses from those
handlers naturally pass through our ``send_wrapper``.

A pure-ASGI middleware also intercepts the ``send`` callable and
injects the ``X-Request-ID`` header on every ``http.response.start``
message — regardless of whether the inner app generated the response
from a route handler, an exception handler, or our own catch-all
fallback below.

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
the pgdp-prep gap" and the raw-ASGI rewrite that closes B-50.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette._utils import is_async_callable
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ...core.logging_config import request_id_var

log = logging.getLogger(__name__)


class RequestIdMiddleware:
    """Stamp every request with a correlation id + emit an audit log.

    Raw ASGI middleware (NOT ``BaseHTTPMiddleware``). See module
    docstring for why — the ``BaseHTTPMiddleware`` shape silently
    discards header mutations and audit-log finally-blocks when the
    inner app raises (B-50).

    Args:
        app: the wrapped ASGI app (next layer down).
        header_name: HTTP header to read & echo. Lower-cased on read
            (header lookup is case-insensitive); echoed back using the
            caller-supplied case so the response matches an upstream
            proxy's expectation.
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name
        # Bytes form for header injection — ASGI message ``headers``
        # are ``list[tuple[bytes, bytes]]``. Pre-encode once.
        self._header_name_bytes = header_name.encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Lifespan / websocket / unknown scope types pass through
        # untouched — the rid is HTTP-request-scoped only.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Read the incoming header via ``MutableHeaders(scope=...)`` so
        # the lookup is case-insensitive. ``MutableHeaders`` over the
        # request scope is read-only-with-mutate-helpers; we only read.
        request_headers = MutableHeaders(scope=scope)
        incoming = request_headers.get(self.header_name)
        rid = incoming or uuid.uuid4().hex

        token = request_id_var.set(rid)
        # ``time.monotonic`` rather than ``time.time``: monotonic is
        # immune to wall-clock jumps (NTP step, suspend/resume), so the
        # measured ``duration_ms`` can never be negative.
        started = time.monotonic()
        path = scope.get("path", "")
        method = scope.get("method", "")
        # Pre-seed the status holder with 500 — the conventional
        # "server error before any response start" code. If the inner
        # app raises before sending ``http.response.start``, the
        # ``finally`` block emits ``request_end`` with status=500.
        # Otherwise ``send_wrapper`` updates this on the start message.
        status_holder: dict[str, int] = {"status": 500}

        log.info(
            "request_start",
            extra={"path": path, "method": method},
        )

        rid_bytes = rid.encode("latin-1")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                # Inject the rid on the outgoing headers. We mutate the
                # message in place by appending to ``message["headers"]``
                # — Starlette/uvicorn read this list when serialising
                # the response.
                #
                # ``setdefault`` semantics: only inject if the inner
                # app didn't already echo one (defensive — only this
                # middleware should be doing this, but a downstream
                # framework future-version might).
                response_headers = MutableHeaders(scope=message)
                if self.header_name not in response_headers:
                    message.setdefault("headers", [])
                    message["headers"].append((self._header_name_bytes, rid_bytes))
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as exc:
                # B-50: catch the exception ourselves before it
                # escapes to ``ServerErrorMiddleware`` (which would
                # bypass ``send_wrapper`` and lose the rid header).
                # Dispatch to the Exception-class handler registered
                # on the FastAPI app via
                # ``error_handler.install_error_handlers``; if no
                # handler is registered, re-raise so
                # ``ServerErrorMiddleware`` handles it with its
                # default 500 (we're back to the legacy behaviour, but
                # only when there's no app-level handler — which would
                # be a bootstrap bug worth surfacing).
                handler = self._lookup_exception_handler(scope, exc)
                if handler is None:
                    raise
                # Update path/method capture from a Request object so
                # the registered handler sees the full Request API.
                request = Request(scope, receive)
                if is_async_callable(handler):
                    response = await handler(request, exc)
                else:
                    response = await run_in_threadpool(handler, request, exc)
                # Send the response through ``send_wrapper`` so the
                # rid header is injected onto its
                # ``http.response.start`` message.
                await response(scope, receive, send_wrapper)
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            # Emit ``request_end`` BEFORE resetting the contextvar so
            # the ``rid=`` tag still appears via ``RequestIdFilter``.
            log.info(
                "request_end",
                extra={
                    "path": path,
                    "method": method,
                    "status": status_holder["status"],
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)

    @staticmethod
    def _lookup_exception_handler(scope: Scope, exc: Exception):
        """Find a handler for ``exc`` on the FastAPI app's registry.

        FastAPI stores exception handlers on
        ``app.exception_handlers``. Walking ``type(exc).__mro__``
        mirrors Starlette's own dispatch logic
        (``starlette/_exception_handler.py:_lookup_exception_handler``)
        — most-specific subclass wins. Returns ``None`` if no handler
        is registered for any class in the MRO; the caller then
        re-raises so ``ServerErrorMiddleware`` produces its default
        500.
        """
        app = scope.get("app")
        if app is None:
            return None
        handlers = getattr(app, "exception_handlers", None)
        if not handlers:
            return None
        for cls in type(exc).__mro__:
            if cls in handlers:
                return handlers[cls]
        return None

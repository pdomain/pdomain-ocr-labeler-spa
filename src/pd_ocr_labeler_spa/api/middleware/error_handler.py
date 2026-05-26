"""Global error handler — uniform JSON error envelope (spec §8).

Verbatim port of ``pd-prep-for-pgdp``'s
``api/middleware/error_handler.py`` with one labeler-specific addition:
``BoundingBoxGeometryError`` (raised from the OCR / refine paths when
geometry normalization fails) maps to ``422 geometry_error``.

Handler chain (per ``docs/architecture/02-backend.md §8``):

1. ``StarletteHTTPException`` → preserve ``exc.status_code``, error tag
   ``http_<n>``. Covers ``HTTPException(404, ...)`` raised from routes
   AND the framework's own 404/405 etc.
2. ``RequestValidationError`` → ``400 validation_error``,
   ``details = exc.errors()``. Pydantic-shaped errors are JSON-safe.
3. ``BoundingBoxGeometryError`` → ``422 geometry_error``. The labeler-
   specific case from spec §8 — the SPA's toast layer recognises this
   tag and shows "this box is degenerate" rather than a generic toast.
4. ``IncompatibleEnvelopeError`` → ``422 incompatible_envelope`` (spec
   §11 of ``docs/architecture/09-persistence.md``). Raised by ``parse_envelope``
   when a saved page has a schema version this binary cannot read.
5. ``Exception`` (catch-all) → ``500 internal_error``. The full
   traceback is logged via ``logger.exception(...)`` so operators see
   the full stack with the request-id prefixed by ``RequestIdFilter``.
   Whether the last three traceback lines reach the client in
   ``details`` is gated on ``Settings.debug_unhandled_traceback``
   (default ``True`` — single-user laptop UX inherited from pgdp-prep).
   When the flag is ``False`` (D-040, Q-A11 option B), ``details`` is
   ``None`` and operators must correlate the client-side ``error``
   with the server-side log via the ``X-Request-ID`` header.

Response envelope (uniform across all four handlers — the SPA's
``client.ts`` parses one shape):

    { "error": <tag>, "message": <string>, "details": <any> }

The request-id is **not** carried inside the body; it travels on the
``X-Request-ID`` response header (set by ``RequestIdMiddleware``) so
operators can correlate without needing to parse the JSON envelope.
That matches pgdp-prep and avoids the body shape diverging on success
vs. error.

Why exception handlers rather than middleware: FastAPI's
``app.exception_handler(...)`` runs INSIDE the middleware chain, so a
500 here still passes back through ``RequestIdMiddleware`` on the way
out. Pure ASGI middleware would have to swallow the exception itself,
which loses the per-class dispatch.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from ...core.exceptions import BoundingBoxGeometryError, IncompatibleEnvelopeError

log = logging.getLogger(__name__)


class ApiError(BaseModel):
    """The uniform error envelope returned by every handler.

    Kept as a pydantic model (rather than a plain dict literal) so the
    OpenAPI export carries a schema for it — the generated TS types
    then expose ``ApiError`` for the SPA's ``client.ts`` to consume.
    """

    error: str
    message: str
    details: Any = None


def install_error_handlers(app: FastAPI) -> None:
    """Register the spec §8 handler chain on ``app``.

    Idempotent in the sense that re-registering replaces (FastAPI keeps
    one handler per exception class) — calling twice from a misbehaving
    test fixture won't stack handlers.
    """

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Preserve the original status — the framework's own 404 for
        # an unknown route should still come back as 404, not 500.
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiError(
                error=f"http_{exc.status_code}",
                message=str(exc.detail),
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # ``exc.errors()`` is the pydantic-shaped list. Pydantic v2
        # ``field_validator`` errors include ``ctx={'error': <ExcInstance>}``
        # which is not JSON-serializable — convert exception instances to
        # their string repr so the response is always serializable.
        def _safe_ctx(ctx: object) -> object:
            if not isinstance(ctx, dict):
                return ctx
            return {k: str(v) if isinstance(v, BaseException) else v for k, v in ctx.items()}

        raw = exc.errors()
        safe = [{k: (_safe_ctx(v) if k == "ctx" else v) for k, v in err.items()} for err in raw]
        return JSONResponse(
            status_code=400,
            content=ApiError(
                error="validation_error",
                message="request body failed validation",
                details=safe,
            ).model_dump(),
        )

    @app.exception_handler(BoundingBoxGeometryError)
    async def _geometry_exc(_request: Request, exc: BoundingBoxGeometryError) -> JSONResponse:
        # Labeler-specific addition (spec §8). 422 because the input
        # was syntactically valid (passed body validation) but
        # semantically un-normalisable.
        return JSONResponse(
            status_code=422,
            content=ApiError(
                error="geometry_error",
                message=str(exc) or exc.__class__.__name__,
            ).model_dump(),
        )

    @app.exception_handler(IncompatibleEnvelopeError)
    async def _incompatible_envelope(_request: Request, exc: IncompatibleEnvelopeError) -> JSONResponse:
        # spec §11: unknown schema version → 422 incompatible_envelope.
        # The details dict carries both the encountered version and the
        # supported range so the SPA toast can show a meaningful message
        # ("This page was saved by v{version}; upgrade to read it").
        return JSONResponse(
            status_code=422,
            content=ApiError(
                error="incompatible_envelope",
                message=str(exc),
                details={
                    "version": exc.version,
                    "supported": exc.supported,
                },
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # ``logger.exception`` emits the full traceback at ERROR level
        # — combined with ``RequestIdFilter`` the operator gets one log
        # line per request with the correlation id and the full stack.
        # This fires UNCONDITIONALLY: the client-side response is always
        # a generic message (F-003 / #408), but operators correlate via
        # the X-Request-ID header against this log line.
        log.exception("unhandled exception in %s %s", request.method, request.url.path)
        # The ``details`` field is gated on
        # ``Settings.debug_unhandled_traceback`` (D-040, Q-A11). Default
        # False (secure): no exception text or traceback crosses the wire.
        # Read from ``request.app.state.settings`` — set by
        # ``bootstrap.build_app`` step 1; falls back to ``False`` if the
        # app was constructed without going through bootstrap (defensive
        # — the test harness builds bare FastAPI apps in a few places).
        settings = getattr(request.app.state, "settings", None)
        debug_traceback = getattr(settings, "debug_unhandled_traceback", False)
        details = traceback.format_exc().splitlines()[-3:] if debug_traceback else None
        # ``message`` is ALWAYS the generic string regardless of debug mode —
        # ``str(exc)`` can contain internal paths, env-specific values, or
        # other sensitive data (F-003 / #408). The full exception is in the
        # server-side log; the client only needs enough to file a report.
        return JSONResponse(
            status_code=500,
            content=ApiError(
                error="internal_error",
                message="Internal server error",
                details=details,
            ).model_dump(),
        )

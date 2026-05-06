"""Tests for the per-route audit log emitted by ``RequestIdMiddleware``
(spec §9, last bullets — "closes pgdp-prep gap").

Spec §9:

    Per-route audit log (closes pgdp-prep gap):
    - ``request_start`` info log on entry (path, method, request_id).
    - ``request_end`` info log on exit (status, duration_ms).

The middleware emits both lines INSIDE the request-id ContextVar
scope so ``RequestIdFilter`` (when attached to the receiving handler)
tags both records with ``record.request_id``. ``time.monotonic()``
guards against negative durations under wall-clock jumps.

These tests use ``caplog`` against the middleware's own logger
(``pd_ocr_labeler_spa.api.middleware.request_id``) and assert the
structured ``extra`` fields land on the LogRecord.

B-47: the autouse ``_reset_managed_handlers`` cleanup lives in
``tests/unit/core/conftest.py``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.api.middleware.request_id import RequestIdMiddleware
from pd_ocr_labeler_spa.core.logging_config import RequestIdFilter

AUDIT_LOGGER = "pd_ocr_labeler_spa.api.middleware.request_id"


def _make_audit_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/explode")
    def explode() -> dict[str, bool]:
        # Used by the duration-doesn't-go-negative branch — but the
        # middleware default behaviour is sufficient; we don't need to
        # raise to verify duration_ms > 0.
        return {"ok": True}

    @app.get("/boom")
    def boom() -> dict[str, bool]:
        # Used by ``test_request_end_emitted_when_call_next_raises``
        # — verifies the ``finally`` block in the middleware still
        # emits ``request_end`` when the inner app raises.
        raise RuntimeError("kaboom from middleware audit test")

    return app


def test_request_start_emitted_with_path_method(caplog) -> None:
    """``request_start`` info record carries ``path`` and ``method``."""
    app = _make_audit_app()
    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
        with TestClient(app) as client:
            response = client.get("/probe")
    assert response.status_code == 200

    starts = [r for r in caplog.records if r.name == AUDIT_LOGGER and r.message == "request_start"]
    assert starts, "expected at least one request_start record"
    rec = starts[-1]
    assert getattr(rec, "path", None) == "/probe"
    assert getattr(rec, "method", None) == "GET"


def test_request_end_emitted_with_status_duration(caplog) -> None:
    """``request_end`` info record carries ``status`` + non-negative ``duration_ms``."""
    app = _make_audit_app()
    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
        with TestClient(app) as client:
            response = client.get("/probe")
    assert response.status_code == 200

    ends = [r for r in caplog.records if r.name == AUDIT_LOGGER and r.message == "request_end"]
    assert ends, "expected at least one request_end record"
    rec = ends[-1]
    assert getattr(rec, "path", None) == "/probe"
    assert getattr(rec, "method", None) == "GET"
    assert getattr(rec, "status", None) == 200
    duration_ms = getattr(rec, "duration_ms", None)
    assert isinstance(duration_ms, int), (
        f"duration_ms must be an int (rounded ms), got {type(duration_ms).__name__}"
    )
    # Non-negative because we use ``time.monotonic()`` under the hood —
    # wall-clock jumps cannot make this measurement negative.
    assert duration_ms >= 0, f"duration_ms must be non-negative, got {duration_ms}"


def test_audit_log_carries_request_id(caplog) -> None:
    """``request_start`` and ``request_end`` are emitted INSIDE the
    request-id ContextVar scope, so ``RequestIdFilter`` tags both with
    ``record.request_id``."""
    # Wire the filter onto caplog's handler so the ContextVar value
    # gets stamped onto each record. This mirrors how the production
    # ``configure_logging`` handler is set up.
    rid_filter = RequestIdFilter()
    caplog.handler.addFilter(rid_filter)
    try:
        app = _make_audit_app()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            with TestClient(app) as client:
                response = client.get("/probe", headers={"X-Request-ID": "audit-trace-1"})
        assert response.status_code == 200

        audit = [r for r in caplog.records if r.name == AUDIT_LOGGER]
        starts = [r for r in audit if r.message == "request_start"]
        ends = [r for r in audit if r.message == "request_end"]
        assert starts and ends

        for rec in (starts[-1], ends[-1]):
            assert getattr(rec, "request_id", None) == "audit-trace-1", (
                f"{rec.message!r} should carry request_id=audit-trace-1, "
                f"got {getattr(rec, 'request_id', None)!r}"
            )
    finally:
        # Identity-based removal (avoids the B-48 positional pitfall).
        caplog.handler.removeFilter(rid_filter)


def test_request_end_emitted_when_call_next_raises(caplog) -> None:
    """B-50/B-56: ``request_end`` fires even when the inner app raises.

    Pre-fix shape (``BaseHTTPMiddleware`` + ``collapse_excgroups``)
    swallowed the ``finally`` block when ``call_next`` raised — so
    ``request_end`` never fired on unhandled-exception requests, the
    operationally most-important case for an audit timeline. The fix
    rewrites the middleware as raw ASGI; this test pins the new
    contract: ``request_end`` is emitted with ``status=500`` and a
    non-negative ``duration_ms`` regardless of whether the inner app
    returned cleanly or raised.

    Status defaults to 500 (the conventional "server error before any
    response was started") when the inner app raises before sending a
    response start message.
    """
    app = _make_audit_app()
    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
        # ``raise_server_exceptions=False`` so the test client surfaces
        # the resulting 500 response (built by Starlette's
        # ``ServerErrorMiddleware``) rather than re-raising into the test.
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/boom")
    assert response.status_code == 500

    audit = [r for r in caplog.records if r.name == AUDIT_LOGGER]
    starts = [r for r in audit if r.message == "request_start"]
    ends = [r for r in audit if r.message == "request_end"]
    assert starts, "request_start must fire on entry even when inner app raises"
    assert ends, (
        "request_end MUST fire on exit even when call_next raises — "
        "the middleware's finally-block guarantees the audit timeline"
    )
    rec = ends[-1]
    assert getattr(rec, "path", None) == "/boom"
    assert getattr(rec, "method", None) == "GET"
    assert getattr(rec, "status", None) == 500, (
        "status defaults to 500 when the inner app raises before "
        "sending a response.start (server error pre-response)"
    )
    duration_ms = getattr(rec, "duration_ms", None)
    assert isinstance(duration_ms, int)
    assert duration_ms >= 0


def test_request_id_var_resets_after_exception_request() -> None:
    """B-50: the ContextVar token is reset even when the inner app raises.

    The middleware brackets ``request_id_var.set(rid)`` /
    ``request_id_var.reset(token)`` around the entire request lifecycle
    via ``try/finally`` — so a raising inner app must NOT leak the rid
    into the outer ContextVar scope.
    """
    from pd_ocr_labeler_spa.core.logging_config import request_id_var

    sentinel_token = request_id_var.set("")
    try:
        app = _make_audit_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/boom", headers={"X-Request-ID": "should-not-leak"})
        assert response.status_code == 500
        # After the failing request, this thread's ContextVar is back
        # to the empty default.
        assert request_id_var.get() == ""
    finally:
        request_id_var.reset(sentinel_token)

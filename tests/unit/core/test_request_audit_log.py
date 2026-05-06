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

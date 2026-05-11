"""Tests for ``api/middleware/request_id.py`` (spec §9 / §12).

The middleware is a verbatim port from ``pd-prep-for-pgdp``:
- read ``X-Request-ID`` (or whatever header_name resolves to);
- if absent, mint a fresh ``uuid4().hex``;
- set the ContextVar from ``core/logging_config.request_id_var`` so
  log records emitted inside the request carry the same id;
- echo the (possibly newly-minted) id back on the response header.

These tests pin the externally-observable contract — header echo on
both branches, contextvar tagging on log lines, and middleware
ordering so the request-id is wrapped around CORS.
"""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.api.middleware.request_id import RequestIdMiddleware
from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.logging_config import (
    RequestIdFilter,
    configure_logging,
    request_id_var,
)
from pd_ocr_labeler_spa.settings import Settings

UUID_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


def _make_probe_app(settings: Settings | None = None) -> FastAPI:
    """A minimal FastAPI app with the RequestIdMiddleware mounted.

    Bootstrapping the full ``build_app`` here would also pull in
    ``/healthz`` etc. — fine for the integration-shaped tests below,
    but for the dedicated middleware-shape test we want a clean app
    with just the probe route.
    """
    if settings is None:
        settings = Settings(mode="api_only")
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware, header_name=settings.request_id_header)

    @app.get("/probe")
    def probe() -> dict[str, str]:
        # Read inside the handler so we observe the contextvar value
        # the middleware stamped for this request.
        return {"rid": request_id_var.get()}

    return app


def test_request_id_echoed() -> None:
    """Spec §9: incoming X-Request-ID is echoed on the response."""
    app = _make_probe_app()
    with TestClient(app) as client:
        response = client.get("/probe", headers={"X-Request-ID": "abc"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "abc"
    # And the contextvar saw the same value inside the handler.
    assert response.json() == {"rid": "abc"}


def test_request_id_generated_when_absent() -> None:
    """Spec §9: missing header → mint a fresh ``uuid4().hex``."""
    app = _make_probe_app()
    with TestClient(app) as client:
        response = client.get("/probe")
    assert response.status_code == 200
    rid = response.headers.get("X-Request-ID")
    assert rid is not None, "RequestIdMiddleware must always echo the header"
    assert UUID_HEX_RE.match(rid), f"rid={rid!r} is not a uuid4 hex string"
    # Round-trips through ``uuid.UUID`` cleanly.
    uuid.UUID(hex=rid)
    # The handler observed the same minted id.
    assert response.json() == {"rid": rid}


def test_request_id_tagged_on_log_lines(caplog) -> None:
    """A log emitted inside the request carries the id via RequestIdFilter."""
    # Wire the filter explicitly onto caplog's handler — pytest's
    # caplog handler is attached to the root logger but doesn't pick
    # up filters we install via ``configure_logging`` (which targets
    # its own _pdlabeler_managed handler).
    #
    # Capture the filter instance so cleanup can remove THIS exact
    # filter — never the positional last-in-list, which would pick the
    # wrong one if anything else appended a filter mid-test. (B-48.)
    rid_filter = RequestIdFilter()
    caplog.handler.addFilter(rid_filter)

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/log")
    def log_endpoint() -> dict[str, bool]:
        logging.getLogger("test.rid").info("hello from inside")
        return {"ok": True}

    try:
        with caplog.at_level(logging.INFO), TestClient(app) as client:
            response = client.get("/log", headers={"X-Request-ID": "trace-xyz"})
        assert response.status_code == 200
        records = [r for r in caplog.records if r.name == "test.rid"]
        assert records, "expected a log record from the handler"
        rids = [(r.name, getattr(r, "request_id", None)) for r in records]
        assert all(getattr(r, "request_id", None) == "trace-xyz" for r in records), (
            f"records did not carry request_id=trace-xyz: {rids}"
        )
    finally:
        caplog.handler.removeFilter(rid_filter)


def test_contextvar_resets_after_request() -> None:
    """Outside a request the contextvar reverts to its empty default."""
    # Save and explicitly reset the contextvar to a known empty state
    # — pytest may have run earlier tests in the same thread that left
    # the var set if they didn't properly reset their tokens.
    sentinel_token = request_id_var.set("")
    try:
        app = _make_probe_app()
        with TestClient(app) as client:
            client.get("/probe", headers={"X-Request-ID": "should-not-leak"})
        # After the request the contextvar in this test thread is back
        # to the empty default (the middleware ``reset(token)``s it).
        assert request_id_var.get() == ""
    finally:
        request_id_var.reset(sentinel_token)


def test_build_app_registers_request_id_outermost() -> None:
    """Spec §12 ordering: RequestIdMiddleware is the outermost layer.

    Starlette stores user_middleware as a list where index 0 is the
    OUTERMOST. So we pin: index 0 must be RequestIdMiddleware, and
    CORSMiddleware must follow inside it.
    """
    app = build_app(Settings(mode="api_only"))
    classes = [getattr(entry, "cls", None) for entry in app.user_middleware]
    assert RequestIdMiddleware in classes, "RequestIdMiddleware not registered"
    assert CORSMiddleware in classes, "CORSMiddleware not registered"
    rid_idx = classes.index(RequestIdMiddleware)
    cors_idx = classes.index(CORSMiddleware)
    assert rid_idx < cors_idx, (
        f"spec §12: RequestIdMiddleware must be OUTERMOST (lower index in "
        f"user_middleware), got rid_idx={rid_idx} cors_idx={cors_idx}"
    )


def test_build_app_request_id_uses_settings_header() -> None:
    """``Settings.request_id_header`` is honoured by the middleware kwargs."""
    app = build_app(Settings(mode="api_only", request_id_header="X-Trace-ID"))
    for entry in app.user_middleware:
        if getattr(entry, "cls", None) is RequestIdMiddleware:
            kwargs = getattr(entry, "kwargs", None) or getattr(entry, "options", {})
            assert kwargs.get("header_name") == "X-Trace-ID"
            break
    else:
        raise AssertionError("RequestIdMiddleware not registered on built app")


def test_build_app_calls_configure_logging() -> None:
    """Spec §2 step 1: ``configure_logging(settings.log_format)`` runs.

    Pinned by checking the root logger has at least one handler tagged
    with our sentinel after ``build_app``. Idempotent re-builds remove
    and re-add the same managed handler so the count stays exactly 1.
    """
    # First, drop any previously-installed handler so the assertion
    # below checks the freshly-installed one (not the one a prior
    # test left behind).
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_pdlabeler_managed", False):
            root.removeHandler(h)

    build_app(Settings(mode="api_only"))
    managed = [h for h in root.handlers if getattr(h, "_pdlabeler_managed", False)]
    assert len(managed) == 1, (
        f"expected exactly one _pdlabeler_managed handler after build_app, got {len(managed)}"
    )

    # Cleanup so we don't leak into later tests.
    configure_logging("plain")

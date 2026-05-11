"""Tests for ``api/middleware/error_handler.py`` (spec §8).

The handler chain is a verbatim port of pgdp-prep with one addition
(``BoundingBoxGeometryError`` → ``422 geometry_error``). Each test
pins one branch of the chain and asserts the externally-observable
JSON envelope ``{error, message, details}``.

A few harness notes:

* ``TestClient(app, raise_server_exceptions=False)`` is required for
  the catch-all branch — the default re-raises unhandled exceptions
  through the test (helpful for debugging route bugs, fatal for
  exercising the 500 path on purpose).
* The probe app is built via ``build_app(...)`` so we exercise the
  REAL wiring (RequestIdMiddleware → CORS → handlers), not a mocked
  miniature. That way "the handler is wired" and "the handler shape
  is right" are both pinned by these tests.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from pd_ocr_labeler_spa.api.middleware.error_handler import (
    ApiError,
    install_error_handlers,
)
from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.exceptions import BoundingBoxGeometryError
from pd_ocr_labeler_spa.settings import Settings


def _probe_app() -> FastAPI:
    """Build the real app via ``build_app`` and bolt on probe routes.

    Using ``build_app`` (rather than a hand-rolled FastAPI) means each
    test exercises the actual middleware + handler ordering as wired
    by ``bootstrap.build_app`` — so a future refactor that forgets to
    call ``install_error_handlers`` fails these tests, not just a
    bespoke unit test.
    """
    app = build_app(Settings(mode="api_only"))

    @app.get("/_probe/http_404")
    def _raise_404() -> None:
        raise HTTPException(status_code=404, detail="thing not found")

    @app.get("/_probe/http_409")
    def _raise_409() -> None:
        raise HTTPException(status_code=409, detail="conflict text")

    @app.get("/_probe/geometry")
    def _raise_geometry() -> None:
        raise BoundingBoxGeometryError("box has zero height")

    @app.get("/_probe/boom")
    def _raise_runtime() -> None:
        raise RuntimeError("internal secret should not leak")

    class _Body(BaseModel):
        n: int
        s: str

    @app.post("/_probe/validate")
    def _accept_body(body: _Body) -> dict[str, object]:
        return {"ok": True, "n": body.n, "s": body.s}

    return app


def _client() -> TestClient:
    # ``raise_server_exceptions=False`` — without this, the catch-all
    # 500 branch never fires; pytest receives the original exception
    # straight from the route function instead of the handler's
    # JSONResponse. (Spec §8 case 4 is otherwise untestable.)
    return TestClient(_probe_app(), raise_server_exceptions=False)


# ---------- shape-pin: ApiError envelope --------------------------------


def test_api_error_envelope_shape() -> None:
    """Spec §8 envelope: ``{error, message, details}`` only."""
    fields = ApiError.model_fields
    assert set(fields.keys()) == {"error", "message", "details"}, (
        f"ApiError envelope drift: got {set(fields.keys())}"
    )
    # ``details`` is optional / nullable; ``error`` + ``message`` are required.
    assert fields["details"].default is None


# ---------- handler 1: StarletteHTTPException ---------------------------


def test_http_exception_preserves_status_and_tags_with_status() -> None:
    """Spec §8 case 1: 404 stays 404, error tag = ``http_404``."""
    with _client() as client:
        response = client.get("/_probe/http_404")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "http_404"
    assert body["message"] == "thing not found"
    # ``details`` is optional; envelope guarantees the key exists.
    assert "details" in body


def test_http_exception_other_status_codes() -> None:
    """The status code is templated into the tag — not a 404 special-case."""
    with _client() as client:
        response = client.get("/_probe/http_409")
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "http_409"
    assert body["message"] == "conflict text"


def test_unknown_route_returns_404_envelope() -> None:
    """The framework's own 404 (no matching route) still flows through.

    StarletteHTTPException is the base of FastAPI's HTTPException —
    the not-found 404 the router itself raises is a Starlette one,
    so handler 1 catches it.
    """
    with _client() as client:
        response = client.get("/_probe/this-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "http_404"


# ---------- handler 2: RequestValidationError ---------------------------


def test_validation_error_returns_400_with_details() -> None:
    """Spec §8 case 2: bad body → 400 ``validation_error`` + ``details``."""
    with _client() as client:
        # ``n`` is missing; ``s`` is the wrong type (int).
        response = client.post("/_probe/validate", json={"s": 7})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "validation_error"
    assert body["message"] == "request body failed validation"
    # ``details`` is the pydantic ``exc.errors()`` list.
    assert isinstance(body["details"], list)
    assert body["details"], "expected at least one validation error entry"
    # Each entry has the pydantic shape (``loc``, ``msg``, ``type``).
    sample = body["details"][0]
    assert {"loc", "msg", "type"}.issubset(sample.keys())


# ---------- handler 3: BoundingBoxGeometryError -------------------------


def test_geometry_error_maps_to_422_geometry_error() -> None:
    """Spec §8 case 3 (labeler-specific): 422 ``geometry_error``."""
    with _client() as client:
        response = client.get("/_probe/geometry")
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "geometry_error"
    assert body["message"] == "box has zero height"


# ---------- handler 4: catch-all Exception ------------------------------


def test_unhandled_exception_returns_500_envelope() -> None:
    """Spec §8 case 4: any unhandled exception → ``500 internal_error``."""
    with _client() as client:
        response = client.get("/_probe/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal_error"
    # The catch-all DOES surface ``str(exc)`` in ``message`` (spec
    # mirrors pgdp-prep here — the message is human-readable diagnostic
    # text, not a security boundary). Operators rely on this to
    # triage from a browser console.
    assert "internal secret" in body["message"]
    # ``details`` is the LAST 3 traceback lines.
    assert isinstance(body["details"], list)
    assert len(body["details"]) <= 3


def test_unhandled_exception_emits_full_traceback_log(caplog) -> None:
    """The catch-all logs at ERROR with the full traceback server-side.

    Independent of what the response surfaces, the full stack must hit
    the logs so operators can root-cause from `journalctl`. Pinned by
    asserting ``logger.exception`` emitted an ERROR record AND that
    the ``exc_info`` carries the original ``RuntimeError`` traceback
    (which contains the ``"internal secret"`` token from the route).
    """
    error_logger = "pd_ocr_labeler_spa.api.middleware.error_handler"
    with caplog.at_level(logging.ERROR, logger=error_logger), _client() as client:
        client.get("/_probe/boom")
    error_records = [r for r in caplog.records if r.name == error_logger and r.levelno >= logging.ERROR]
    assert error_records, (
        f"expected ERROR-level record from {error_logger}; got "
        f"{[(r.name, r.levelname) for r in caplog.records]}"
    )
    # ``logger.exception`` always sets ``exc_info``; the formatted
    # traceback then contains the original message — confirming the
    # full stack reaches the log handler, not just a one-liner.
    rec = error_records[0]
    assert rec.exc_info is not None, "logger.exception must include exc_info"
    formatted = logging.Formatter().formatException(rec.exc_info)
    assert "internal secret" in formatted, "server-side traceback must carry the original exception message"


def test_handled_error_responses_preserve_request_id_header() -> None:
    """The X-Request-ID header echoes on every error response, including
    the unhandled-Exception 500 path (B-50 fix).

    RequestIdMiddleware wraps the handler chain — when one of the
    *registered* handlers fires (HTTP, validation, geometry), the
    response must carry the request-id so operators can correlate
    the client report with the server-side traceback. The id lives
    on the header (not in the JSON envelope) per the error_handler
    module docstring.

    Handler 4 (catch-all ``Exception``) is now also covered.
    Pre-B-50, ``RequestIdMiddleware`` extended ``BaseHTTPMiddleware``,
    which discarded the response-header mutation when ``call_next``
    raised — so 500s went out without the rid header. The B-50 fix
    rewrites the middleware as a raw ASGI app that wraps the ``send``
    callable and injects ``X-Request-ID`` on every
    ``http.response.start`` message, regardless of whether the inner
    app returned cleanly or raised. ``/_probe/boom`` raises
    ``RuntimeError`` and exercises the catch-all handler; the rid
    must still echo.
    """
    cases = [
        ("/_probe/http_404", 404),
        ("/_probe/geometry", 422),
        ("/_probe/boom", 500),
    ]
    with _client() as client:
        for path, expected_status in cases:
            response = client.get(path, headers={"X-Request-ID": "trace-err"})
            assert response.status_code == expected_status, path
            assert response.headers.get("X-Request-ID") == "trace-err", path


# ---------- wiring shape ------------------------------------------------


def test_build_app_registers_all_four_handlers() -> None:
    """Wiring: ``install_error_handlers`` registers all four classes.

    FastAPI stores handlers in ``app.exception_handlers`` keyed by the
    exception class. Pinning the key set means a future refactor that
    drops one of the handlers (e.g. forgets the geometry case during
    a port) fails this test loudly.
    """
    app = build_app(Settings(mode="api_only"))
    handler_keys = set(app.exception_handlers.keys())
    # Starlette / FastAPI register their own default for
    # StarletteHTTPException; ``install_error_handlers`` overwrites
    # that. RequestValidationError and Exception are ours unconditionally.
    assert StarletteHTTPException in handler_keys
    assert RequestValidationError in handler_keys
    assert BoundingBoxGeometryError in handler_keys
    assert Exception in handler_keys


def test_install_error_handlers_idempotent_under_double_call() -> None:
    """Calling ``install_error_handlers`` twice doesn't stack handlers.

    Stress test for misbehaving fixtures or test setup that might
    re-bootstrap. FastAPI keys handlers by class so the second call
    overwrites the first — pinned here so a refactor doesn't grow
    a list-append shape that would silently double-execute.
    """
    app = build_app(Settings(mode="api_only"))
    install_error_handlers(app)  # second call

    # Same number of distinct class keys; a list-append shape would
    # multiply the count.
    assert len(app.exception_handlers) >= 4
    # Issuing a request still produces exactly one envelope (not two).
    with TestClient(app, raise_server_exceptions=False) as client:

        @app.get("/_probe_idem/boom")
        def _b() -> None:
            raise RuntimeError("xx")

        response = client.get("/_probe_idem/boom")
    assert response.status_code == 500
    # JSON, not double-JSON-on-one-line.
    body = response.text
    # Exactly one decoded object.
    decoded = json.loads(body)
    assert decoded["error"] == "internal_error"


# ---------- defensive: error tag character class ------------------------


_TAG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def test_error_tags_are_machine_readable() -> None:
    """All four error tags are snake_case ascii — no localized text.

    Per spec §8 the tag is the API contract; the SPA's ``client.ts``
    switches on it. Pinning the character class catches a future
    refactor that accidentally puts a human-readable phrase or a
    capitalised class name in there.
    """
    expected = {
        "http_404": 404,
        "http_409": 409,
        "validation_error": 400,
        "geometry_error": 422,
        "internal_error": 500,
    }
    for tag in expected:
        assert _TAG_RE.match(tag), f"tag {tag!r} is not snake_case ascii"

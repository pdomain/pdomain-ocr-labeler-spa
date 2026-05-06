"""Tests for ``core/logging_config.py`` (spec §9).

Verbatim port from pgdp-prep:
- ``request_id_var`` ContextVar with empty-string default.
- ``RequestIdFilter`` injects ``record.request_id`` from the var.
- ``JsonFormatter`` emits one JSON object per record with the stable
  schema (``ts``, ``level``, ``logger``, ``msg``, ``request_id``,
  plus extras and ``exc``).
- ``configure_logging`` is idempotent: repeated calls don't stack.
- The plain formatter includes ``rid=<value>`` in the log line so a
  grep for ``rid=…`` works without parsing JSON.
"""

from __future__ import annotations

import io
import json
import logging

from pd_ocr_labeler_spa.core.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    configure_logging,
    request_id_var,
)


def test_request_id_var_default_is_empty_string() -> None:
    """Spec §9 invariant: empty-string default keeps the JSON field
    type-stable and makes absent-vs-present unambiguous in log greps.

    Reads the *declared* default by running ``.get()`` inside a fresh
    ``contextvars.Context()`` — that context has never seen a ``set()``
    on this var, so ``.get()`` returns whatever ``ContextVar(default=)``
    was passed at construction. A circular ``set("") -> get() == ""``
    test would silently pass on a future ``default=None`` regression;
    this one would not. (B-49.)
    """
    import contextvars

    ctx = contextvars.Context()
    assert ctx.run(lambda: request_id_var.get()) == ""


def test_request_id_filter_injects_attribute() -> None:
    """``RequestIdFilter`` copies the contextvar onto the LogRecord."""
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hi",
        args=(),
        exc_info=None,
    )
    token = request_id_var.set("rid-123")
    try:
        assert RequestIdFilter().filter(record) is True
        assert record.request_id == "rid-123"
    finally:
        request_id_var.reset(token)


def test_request_id_filter_default_when_unset() -> None:
    """When no request is active, the filter sets request_id to ''."""
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hi",
        args=(),
        exc_info=None,
    )
    # Force an empty default.
    token = request_id_var.set("")
    try:
        RequestIdFilter().filter(record)
        assert record.request_id == ""
    finally:
        request_id_var.reset(token)


def test_json_formatter_schema() -> None:
    """JSON shape: ts, level, logger, msg, request_id at minimum."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="my.module",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.request_id = "rid-abc"
    out = formatter.format(record)
    payload = json.loads(out)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "my.module"
    assert payload["msg"] == "hello world"
    assert payload["request_id"] == "rid-abc"
    assert "ts" in payload


def test_json_formatter_folds_extras() -> None:
    """``log.info("x", extra={"k": v})`` should appear in the JSON output."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="t",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    record.request_id = ""
    # Simulate an ``extra={"job_id": "J1", "step": 4}`` call.
    record.job_id = "J1"
    record.step = 4
    payload = json.loads(formatter.format(record))
    assert payload["job_id"] == "J1"
    assert payload["step"] == 4


def test_json_formatter_handles_exc_info() -> None:
    """``exc_info`` becomes a string ``exc`` field, not raw tuple."""
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="t",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed",
        args=(),
        exc_info=exc_info,
    )
    record.request_id = ""
    payload = json.loads(formatter.format(record))
    assert "ValueError: boom" in payload["exc"]


def test_configure_logging_is_idempotent() -> None:
    """Repeated calls don't stack handlers (spec §9: ``--reload`` safety)."""
    root = logging.getLogger()
    # Drop any existing managed handlers first so we count from a known state.
    for h in list(root.handlers):
        if getattr(h, "_pdlabeler_managed", False):
            root.removeHandler(h)

    configure_logging("plain")
    first = [h for h in root.handlers if getattr(h, "_pdlabeler_managed", False)]
    assert len(first) == 1

    configure_logging("plain")
    second = [h for h in root.handlers if getattr(h, "_pdlabeler_managed", False)]
    assert len(second) == 1

    configure_logging("json")
    third = [h for h in root.handlers if getattr(h, "_pdlabeler_managed", False)]
    assert len(third) == 1

    # Cleanup.
    for h in list(root.handlers):
        if getattr(h, "_pdlabeler_managed", False):
            root.removeHandler(h)


def test_configure_logging_does_not_evict_caplog_handler(caplog) -> None:
    """Sentinel-attribute scoping: caplog stays attached after configure_logging."""
    pre_handlers = list(logging.getLogger().handlers)
    configure_logging("plain")
    post_handlers = list(logging.getLogger().handlers)
    # Every pre-existing non-managed handler is still attached.
    for h in pre_handlers:
        if not getattr(h, "_pdlabeler_managed", False):
            assert h in post_handlers, f"configure_logging evicted a non-managed handler: {h!r}"
    # Cleanup.
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_pdlabeler_managed", False):
            root.removeHandler(h)


def test_plain_formatter_includes_rid_token() -> None:
    """The plain log line must include ``rid=<value>`` so log greps work.

    Spec-named acceptance: a log line emitted with the contextvar set
    contains the ``rid=abc`` substring.
    """
    # Build the same formatter wiring ``configure_logging("plain")``
    # uses, but route to an in-memory buffer so we can inspect output
    # without depending on stdout capture.
    buf = io.StringIO()
    handler = logging.StreamHandler(stream=buf)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s [rid=%(request_id)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger = logging.getLogger("test.plain.rid")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    token = request_id_var.set("abc")
    try:
        logger.info("ping")
    finally:
        request_id_var.reset(token)
        logger.removeHandler(handler)

    output = buf.getvalue()
    assert "rid=abc" in output, f"expected 'rid=abc' in log line, got: {output!r}"
    assert "ping" in output


# B-47: the autouse ``_reset_managed_handlers`` cleanup fixture is now
# in ``tests/unit/core/conftest.py`` so both this file and
# ``test_request_id.py`` / ``test_request_audit_log.py`` share it.

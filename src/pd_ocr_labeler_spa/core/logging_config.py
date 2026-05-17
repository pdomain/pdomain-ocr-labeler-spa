"""Structured logging setup — stdlib-only.

Per ``docs/architecture/02-backend.md §9``: JSON or plain logs with request-id
correlation. Default behaviour is ``plain`` (matches pgdp-prep); opt
in to JSON by setting ``PDLABELER_LOG_FORMAT=json`` or by passing
``log_format="json"`` to ``Settings``.

Two pieces:

* ``request_id_var`` — a ``contextvars.ContextVar`` set by
  ``RequestIdMiddleware``. ``RequestIdFilter`` copies its value onto
  every ``LogRecord``, so loggers anywhere in the stack pick up the
  correlation id "for free".
* ``JsonFormatter`` — emits one JSON object per record with a stable
  schema. Pure stdlib (``json.dumps``); no ``python-json-logger``
  dependency needed for what we want here.

``configure_logging(format)`` is idempotent — calling it twice replaces
the root handler rather than stacking. That matters under uvicorn
``--reload`` where ``build_app()`` may run more than once in the same
process. We tag our handler with ``_pdlabeler_managed`` (per spec
§9: "removes previous handlers tagged ``_pdlabeler_managed = True``")
so we don't accidentally evict pytest's caplog or uvicorn's own
handlers.

Verbatim port from
``pd-prep-for-pgdp/src/pd_prep_for_pgdp/core/logging_config.py`` — the
only naming-convention adjustment is the ``_pdlabeler_managed`` sentinel
attribute (was ``_pgdp_managed``).
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Literal

LogFormat = Literal["plain", "json"]

# Set by RequestIdMiddleware for the duration of each HTTP request.
# Default empty string (rather than None) so the JSON field is always
# the same type and absent-vs-present is unambiguous in log greps.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdFilter(logging.Filter):
    """Copy the current request-id contextvar onto every LogRecord.

    Filters run before formatters, so the JSON formatter (and any plain
    formatter that wants ``%(request_id)s``) can read
    ``record.request_id`` without checking for its existence.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


# Standard ``LogRecord`` attributes we don't want to dump twice.
# Anything not in this set is treated as an ``extra=`` field passed by
# the caller and gets folded into the JSON output.
_RESERVED_LOGRECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        # request_id is hoisted to a top-level field by JsonFormatter
        "request_id",
    }
)


class JsonFormatter(logging.Formatter):
    """Format records as one JSON object per line.

    Keys: ``ts`` (ISO-8601 UTC), ``level``, ``logger``, ``msg``,
    ``request_id``, plus any ``extra=`` fields the caller passed.
    ``exc_info`` becomes a string ``exc`` field. We deliberately don't
    include source-file info by default — ``logger`` (the dotted module
    name) is enough for operational triage and keeps lines compact.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Render the message with %-args before serializing so callers
        # can still do ``log.info("hello %s", name)``.
        message = record.getMessage()

        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": message,
            "request_id": getattr(record, "request_id", "") or "",
        }

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Fold extras (anything passed via ``log.info("x", extra={"k": v})``).
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_ATTRS:
                continue
            # ``default=str`` handles Path, datetime, Exception, etc.
            payload[key] = value

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(log_format: LogFormat = "plain", level: int = logging.INFO) -> None:
    """Install one stderr handler on the root logger.

    Idempotent: removes any handlers we previously installed before
    adding the new one, so repeated calls (uvicorn ``--reload``) don't
    stack handlers and double-log.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Drop any handlers we previously installed. We mark our handler
    # with a sentinel attribute so we don't accidentally remove
    # uvicorn's or pytest's caplog handler.
    for handler in list(root.handlers):
        if getattr(handler, "_pdlabeler_managed", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler._pdlabeler_managed = True  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
    handler.addFilter(RequestIdFilter())

    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s [rid=%(request_id)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    root.addHandler(handler)

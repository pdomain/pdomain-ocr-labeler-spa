"""Shared fixtures for ``tests/unit/core/`` (specs/02-backend.md §9).

Tests in this directory routinely call ``configure_logging(...)`` —
either directly (``test_logging_config.py``) or transitively via
``build_app(...)`` (``test_request_id.py``, ``test_request_audit_log.py``).

``configure_logging`` installs a managed handler on the root logger
tagged ``_pdlabeler_managed=True``. Without an autouse cleanup, that
handler leaks across the entire pytest session — fine within a single
file (the second call removes the first), broken across files (a
later test in a sibling file inspecting the root logger sees a stale
handler from whichever test ran last here).

Lifting the cleanup into ``conftest.py`` makes it a directory-wide
invariant. Closes B-47 (was: only ``test_logging_config.py`` had its
own copy of this fixture).
"""

from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def _reset_managed_handlers():
    """After every test, remove any ``_pdlabeler_managed`` handler.

    Other handlers (pytest's caplog, uvicorn's own) are left alone —
    we identify ours by the sentinel attribute, not by class.
    """
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_pdlabeler_managed", False):
            root.removeHandler(handler)

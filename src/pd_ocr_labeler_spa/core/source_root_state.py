"""Mutable holder for the runtime ``source_projects_root`` override.

Spec authority: ``docs/architecture/09-persistence.md §7`` (config.yaml) +
``docs/architecture/02-backend.md §5.2`` (``POST /api/projects/source-root``).

The ``POST /api/projects/source-root`` endpoint persists a new projects
root to ``config.yaml`` AND updates the in-process state so that
subsequent ``GET /api/projects`` + ``POST /api/projects/discover`` calls
use the new root immediately (without a server restart).

Pattern: same ``threading.Lock`` + monotonic ``generation`` counter as
``ActiveProjectCarrier`` and ``OCRConfigCarrier``. One instance per
``build_app`` call, stashed on ``app.state.source_root_carrier``.

Why not mutate ``Settings``? ``Settings`` is frozen (Pydantic
``frozen=True``) and frozen for good reason — it is the authoritative
boot-time snapshot. A separate carrier holds the runtime override so
the two layers stay independent.

Startup seeding: ``bootstrap._make_lifespan`` seeds this carrier from
``Settings.source_projects_root`` (which the CLI + env vars populate at
startup), then from ``config.yaml`` if the settings value is still
``None`` (CLI > config.yaml precedence mirrors legacy
``cli.py`` resolution order).
"""

from __future__ import annotations

import threading
from pathlib import Path


class SourceRootCarrier:
    """Mutable holder for the effective ``source_projects_root``.

    Thread-safe: ``threading.Lock`` guards all mutations.
    ``generation`` bumps on every real change (same pattern as
    ``ActiveProjectCarrier`` + ``OCRConfigCarrier``).
    """

    def __init__(self, initial: Path | None = None) -> None:
        self._root: Path | None = initial
        self._generation: int = 0
        self._lock = threading.Lock()

    @property
    def generation(self) -> int:
        """Monotonically-increasing change counter (snapshot under the lock)."""
        with self._lock:
            return self._generation

    def get(self) -> Path | None:
        """Return the current effective source root (or ``None`` if unset)."""
        with self._lock:
            return self._root

    def set(self, root: Path | None) -> bool:
        """Set the effective root; returns ``True`` iff state actually changed.

        If ``root == self._root`` the call is a no-op and returns ``False``
        (callers can gate disk writes on the return value).
        """
        with self._lock:
            if self._root == root:
                return False
            self._root = root
            self._generation += 1
            return True

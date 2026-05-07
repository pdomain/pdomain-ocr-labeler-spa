"""Mutable carrier for the *currently active* project.

Spec authority:

- ``specs/02-backend.md §13`` — background discovery + restoration.
  ``POST /api/projects/load`` ultimately sets the per-process active
  project (line 217: "Sets ``app_state.current_project_id``"); this
  module ships the carrier that endpoint will mutate.
- ``specs/00-overview.md`` "State model" lines 179-201 — backend keeps
  a single ``AppState`` with a per-project ``ProjectState`` map. The
  *active-pointer* (which project is the current one for THIS server
  process) is its own concern; this module is that pointer.
- ``specs/16-milestones.md`` M2 backend bullet 1 names
  ``core/project_state.py`` for the *spec-proper* ``ProjectState``
  (loaded ``Project`` + per-page state + GT map). This module
  intentionally lands at ``core/active_project.py`` so it doesn't
  collide with that future module — the carrier here is the *seam*
  through which the M2-proper ``ProjectState`` will be plumbed.

What this slice ships (M2 slice 2):

- ``ActiveProject`` — a frozen dataclass snapshot (path, label,
  opened_at). Path is always ``Path.resolve()``-d so equality matches
  slice 1's ``ResolvedInitialProject`` discipline.
- ``ActiveProjectCarrier`` — a small mutable holder with:
   - ``snapshot()`` returning ``ActiveProject | None`` (the current
     active or "nothing open").
   - ``set_active_project(path, *, label=None)`` that validates via
     slice 1's ``validate_project_dir``, swaps under a lock, bumps
     a ``generation`` counter, and emits a structured INFO log line.
   - ``clear()`` returning the carrier to "nothing open" (and bumping
     the generation — every state change is observable).
   - ``generation`` — monotonically-increasing counter so future SSE /
     cache-invalidation code can detect "the active project changed
     under me" without diffing path strings.

What this slice deliberately does NOT do (deferred):

- **Lifespan wiring.** Slice 3 will add the FastAPI lifespan startup
  hook that calls ``resolve_initial_project()`` (slice 1) and feeds
  the result into ``set_active_project()`` here.
- **HTTP routes.** Slice 4 wires ``POST /api/projects/load`` /
  ``DELETE /api/projects/{id}`` to call into this carrier.
- **The richer ``ProjectState``.** Loaded ``Project`` model, per-page
  state map, GT map — all live in M2-proper's
  ``core/project_state.py``. This carrier holds a *path*, not a
  ``Project``; it's the pointer, not the page graph.
- **File-system watching.** Out of scope for M2 entirely.
- **Project enumeration.** ``GET /api/projects`` reads
  ``Settings.source_projects_root`` — a separate concern from this
  pointer carrier.

Concurrency contract:

The carrier uses a ``threading.Lock``. Three justifications:

1. ``threading`` (not ``asyncio``) because FastAPI route handlers may
   be either sync (run on a threadpool worker) or async (run on the
   event loop). A ``threading.Lock`` is safe to hold from both — it
   blocks the caller's thread, which for an async caller means the
   event loop, which for the *brief* swap (~microseconds) is
   acceptable. An ``asyncio.Lock`` would be unsafe to hold from a
   sync handler.
2. The critical section is constant-time (a couple of struct
   assignments + a generation bump + one log call). No I/O happens
   inside the lock — ``validate_project_dir`` runs OUTSIDE the lock
   so a slow stat doesn't serialize all swaps.
3. Failure-atomic: validation runs before the lock is acquired; if
   it fails, ``InvalidProjectDirError`` propagates and the carrier's
   internal state is provably untouched (we never wrote anything).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .startup_discovery import validate_project_dir

logger = logging.getLogger(__name__)


class InvalidProjectDirError(ValueError):
    """Raised when ``set_active_project`` is given a non-directory / unreadable path.

    Subclasses ``ValueError`` so generic except-clauses still catch it,
    but greppable by name. The eventual ``POST /api/projects/load``
    endpoint will catch this and surface it as a ``404 project_not_found``
    or ``400 invalid_project_dir`` per spec §8 — the mapping lives at
    the endpoint, not here.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"path is not a readable directory: {path!s}",
        )
        self.path = path


@dataclass(frozen=True)
class ActiveProject:
    """Frozen snapshot of "which project is currently active."

    Three fields, deliberately minimal:

    - ``path``: absolute, ``Path.resolve()``-d project root. Same
      canonicalization as ``ResolvedInitialProject.path`` so
      cross-module equality just works.
    - ``label``: human-readable name. Defaults to ``path.name`` (the
      directory's basename, which matches the legacy "project ID =
      dir name" convention used by the NiceGUI labeler) but can be
      overridden by the caller — the future
      ``POST /api/projects/load`` may carry a pretty label.
    - ``opened_at``: UTC timestamp of when the swap completed. Used
      by future telemetry / "recently opened" UI — not load-bearing
      for any current logic.

    No ``generation`` field on the snapshot itself — generation lives
    on the *carrier* because it describes the carrier's history, not
    a property of any one project.
    """

    path: Path
    label: str
    opened_at: datetime


class ActiveProjectCarrier:
    """Mutable holder for the active ``ActiveProject``, with a swap lock.

    Lives on ``app.state.active_project_carrier`` (wired in
    ``bootstrap.build_app`` per spec §2 step 9). DI provider
    ``api.dependencies.get_active_project_carrier`` surfaces it to
    handlers; ``get_active_project`` returns just the snapshot, which
    is what most read-side callers want.

    Identity contract: there is exactly one carrier per ``FastAPI``
    app, constructed at ``build_app`` time and never replaced. The
    carrier itself is mutable; the ``ActiveProject`` snapshots it
    holds are frozen.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: ActiveProject | None = None
        self._generation: int = 0

    @property
    def generation(self) -> int:
        """Monotonically-increasing swap counter.

        Increments on every successful ``set_active_project`` AND on
        every ``clear()`` (including clear-on-empty — see test
        ``test_clear_on_empty_carrier_is_noop_but_increments_generation``).
        Read-only by design; written only inside the lock-guarded
        mutation paths.
        """
        return self._generation

    def snapshot(self) -> ActiveProject | None:
        """Return the current ``ActiveProject`` or ``None``.

        No copy needed: ``ActiveProject`` is a frozen dataclass, so
        consumers can't mutate the carrier through the returned ref.
        Reading without the lock is safe because Python's GIL
        guarantees attribute reads are atomic and the caller is OK
        with "either pre-swap or post-swap, not in-between" — which
        is what they always get since swaps are constant-time.
        """
        return self._active

    def set_active_project(self, path: Path, *, label: str | None = None) -> ActiveProject:
        """Swap the active project to ``path``; return the new snapshot.

        Pre-validates via slice 1's ``validate_project_dir`` BEFORE
        acquiring the lock. If validation fails, raises
        ``InvalidProjectDirError`` and the carrier is provably
        untouched (no internal state was written).

        Inside the lock:

        1. Build the ``ActiveProject`` snapshot (path resolved, label
           defaulted, ``opened_at`` set to ``datetime.now(UTC)``).
        2. Bump ``generation``.
        3. Swap ``self._active``.
        4. Log INFO with stable structured keys
           (``active_project_path``, ``active_project_label``,
           ``active_project_generation``) so the lifecycle is testable
           without parsing message strings.

        Args:
            path: The project directory. Will be ``Path.resolve()``-d
                in the snapshot.
            label: Optional human-readable name. Defaults to
                ``path.name`` (the directory's basename).

        Returns:
            The new ``ActiveProject`` snapshot.

        Raises:
            InvalidProjectDirError: ``path`` is missing / not a
                directory / unreadable.
        """
        if not validate_project_dir(path):
            raise InvalidProjectDirError(path)

        resolved = path.resolve()
        snap = ActiveProject(
            path=resolved,
            label=label if label is not None else resolved.name,
            opened_at=datetime.now(UTC),
        )
        with self._lock:
            self._generation += 1
            self._active = snap
            generation = self._generation
        logger.info(
            "Active project swapped",
            extra={
                "active_project_path": str(snap.path),
                "active_project_label": snap.label,
                "active_project_generation": generation,
            },
        )
        return snap

    def clear(self) -> None:
        """Reset to "no project active"; bump the generation counter.

        Mirrors ``DELETE /api/projects/{id}`` semantics (spec §5.2
        line 222: "Closes (forgets) the project state in memory;
        doesn't touch disk."). Always bumps ``generation`` — every
        state change is observable, even clearing-an-already-empty
        carrier.
        """
        with self._lock:
            self._generation += 1
            self._active = None
            generation = self._generation
        logger.info(
            "Active project cleared",
            extra={"active_project_generation": generation},
        )


__all__ = [
    "ActiveProject",
    "ActiveProjectCarrier",
    "InvalidProjectDirError",
]

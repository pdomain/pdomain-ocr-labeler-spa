"""Resolve which project (if any) the labeler should open at startup.

Spec authority: ``docs/architecture/02-backend.md §13`` (background discovery +
restoration), step 4 ("If ``Settings.cli_project_dir`` is set, override
the restore — load the CLI dir.") and step 3 (session_state restore).

This module is **slice 1** of the M2 startup-discovery work
(milestones doc M2). It ships:

- ``validate_project_dir(path)`` — exists / is_dir / readable check.
- ``resolve_initial_project(settings, session_state)`` — pure function
  that picks ``cli`` over ``session_restore`` per the spec precedence,
  emits structured log events, and returns ``None`` if neither input
  resolves to a usable directory.

What slice 1 deliberately does NOT do (deferred to M2 proper):

- **Project enumeration** of ``Settings.source_projects_root``. Spec
  §13 step 2 ("scan for project subdirectories") requires a
  ``Project`` model + GT loading; that's a bigger chunk and lives in
  ``core/project_state.py`` (M2 file list per ``specs/16-milestones.md``
  M2 backend bullet 1).
- **Mutating ``AppState``.** ``core/app_state.py`` is a
  ``frozen=True`` dataclass by design (its docstring spells out the
  immutability contract). Slice 1 returns a value; the consumer
  (``app_state.startup()``, M2) will plumb it into a mutable
  ``ProjectState`` container that doesn't exist yet.
- **Lifespan wiring.** Bootstrap's lifespan is still empty (M3 adds
  the JobRunner background task). When M2's ``ProjectState`` lands,
  the lifespan will gain its first real ``await app_state.startup()``
  hook that calls into this module.

The function is pure (no FS writes, no side effects beyond logging),
side-effect-free at module scope, and unit-testable with stdlib's
``caplog`` — no integration test needed for slice 1.

Legacy parity reference:
``pd-ocr-labeler/pd_ocr_labeler/app.py:_try_restore_session:437`` does
the equivalent restore on the NiceGUI side; we keep the same
"silently fall through to None on stale path" semantics so a user who
moves their project dir doesn't get a startup crash.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..settings import Settings
from .persistence.session_state import SessionState, last_project_path_exists

logger = logging.getLogger(__name__)

InitialProjectSource = Literal["cli", "session_restore"]


@dataclass(frozen=True)
class ResolvedInitialProject:
    """The resolved startup-time project handle.

    ``path`` is always ``Path.resolve()``-d so downstream comparisons /
    log lines agree on a canonical absolute form regardless of
    user-supplied relative path or trailing-slash trivia.

    ``source`` distinguishes the two restore paths so observability
    (and future test assertions in ``app_state.startup()``) can tell
    "user typed --project-dir X" from "we restored X from
    session_state.json". Future restore sources (e.g. URL deep-link)
    should extend the Literal additively.
    """

    path: Path
    source: InitialProjectSource


def validate_project_dir(path: Path) -> bool:
    """Return True iff ``path`` exists, is a directory, and is readable.

    Three layered checks:

    1. ``is_dir()`` — covers both "missing" and "regular file" cases in
       a single syscall (``stat()`` returns ``ENOENT`` for missing,
       ``S_ISDIR(st_mode)`` is False for regular files / symlinks to
       files).
    2. ``os.access(path, os.R_OK)`` — process can actually read the
       directory entry. Saved-projects are dir-shaped (per spec §1)
       and the labeler reads ``pages.json`` / per-page envelopes from
       inside; without read perms the M2 enumeration would later fail
       loudly.
    3. ``os.access`` is effective-uid / euid-aware on POSIX, so the
       check matches the perms the running process *actually has* —
       not a static mode bit. Matters in container scenarios where
       the labeler runs as a non-root uid that may differ from the
       user who created the dir.

    The function is **pure** beyond the three ``stat()``-level reads
    above — no writes, no logging (the caller decides the log level).

    Symlinks are followed (default ``Path`` / ``os`` behaviour);
    intentional, since both legacy and the SPA accept symlinks to
    project dirs as legitimate inputs.
    """
    if not path.is_dir():
        return False
    return os.access(path, os.R_OK)


def resolve_initial_project(
    settings: Settings,
    *,
    session_state: SessionState | None,
) -> ResolvedInitialProject | None:
    """Resolve which project to open on startup.

    Precedence (per ``docs/architecture/02-backend.md §13``):

    1. ``settings.cli_project_dir`` if set AND valid → ``cli``.
    2. ``session_state.last_project_path`` if set AND valid →
       ``session_restore``.
    3. Otherwise → ``None`` (the labeler boots to "no project loaded";
       the user will pick from the dropdown after M2's frontend
       discovery UI ships).

    Failure modes (per branch):

    - **CLI set but invalid** (path missing / not a dir / unreadable):
      log a WARNING with structured ``cli_project_dir`` extra; fall
      through to session-restore. NOT a fatal error — legacy parity
      (``cli.py:18-23`` doesn't pre-validate either; the user gets a
      runnable app and a visible warning, not a refusal-to-boot).
    - **Session restore but stale path**: logged at DEBUG via
      ``last_project_path_exists`` + this module; return ``None``.
      Stale-path is the *expected* state when projects move; not a
      warning.

    Args:
        settings: Process-wide ``Settings``. We only read
            ``cli_project_dir`` here; ``source_projects_root`` is M2's
            project-enumeration concern, not slice 1.
        session_state: Pre-loaded ``SessionState`` from
            ``load_session_state(settings.data_root)``, or ``None`` for
            cold-start. Passing it in (rather than re-reading the file
            here) keeps this function pure and lets the future
            ``app_state.startup()`` orchestrate the file read once.

    Returns:
        ``ResolvedInitialProject`` with the chosen path + source, or
        ``None`` if no startup project should be loaded.
    """
    # ── CLI override branch ────────────────────────────────────────────
    cli_dir = settings.cli_project_dir
    if cli_dir is not None:
        if validate_project_dir(cli_dir):
            resolved_path = cli_dir.resolve()
            logger.info(
                "Initial project resolved from CLI",
                extra={
                    "initial_project_source": "cli",
                    "initial_project_path": str(resolved_path),
                },
            )
            return ResolvedInitialProject(path=resolved_path, source="cli")
        logger.warning(
            "CLI --project-dir is invalid (missing / not a directory / unreadable); "
            "falling through to session restore",
            extra={"cli_project_dir": str(cli_dir)},
        )

    # ── Session restore branch ─────────────────────────────────────────
    if session_state is not None and last_project_path_exists(session_state):
        # ``last_project_path_exists`` is True → ``last_project_path``
        # is a non-None string AND resolves to an existing directory.
        # Type-checkers don't know the implication, so the cast is
        # explicit.
        assert session_state.last_project_path is not None
        path = Path(session_state.last_project_path).resolve()
        logger.info(
            "Initial project resolved from session_state.json",
            extra={
                "initial_project_source": "session_restore",
                "initial_project_path": str(path),
                "initial_page_index": session_state.last_page_index,
            },
        )
        return ResolvedInitialProject(path=path, source="session_restore")

    # ── No-input cold start ────────────────────────────────────────────
    if session_state is not None and session_state.last_project_path is not None:
        # SessionState had a path but it didn't pass the existence check
        # — log at DEBUG so an operator running -v can see "we tried to
        # restore but the dir is gone." Stays out of normal logs since
        # this is the expected state when a user moves their project.
        logger.debug(
            "session_state.last_project_path is stale; ignoring",
            extra={"stale_last_project_path": session_state.last_project_path},
        )
    logger.debug("No initial project to resolve (no CLI override, no valid session restore).")
    return None


__all__ = [
    "InitialProjectSource",
    "ResolvedInitialProject",
    "resolve_initial_project",
    "validate_project_dir",
]

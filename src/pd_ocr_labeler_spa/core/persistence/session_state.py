"""Read/write of ``<data_root>/session_state.json``.

Spec: ``specs/09-persistence.md §6`` + ``specs/01-data-models.md §3``
("session_state.json"). Tiny single-file persistence: where was the
user when they last closed the app? Re-applied on next startup
(``app_state.startup()`` step 3 per ``specs/02-backend.md §13``).

Schema (verbatim from spec §6, **byte-compatible with legacy
pd_ocr_labeler under D-003** — both binaries share the file)::

    {"schema_version": "1.0",
     "last_project_path": "/abs/path/to/project_dir",
     "last_page_index": 5}

Field-name compatibility is **mandatory**: ``last_project_path`` is
singular (legacy spelling), not ``_paths``; ``last_page_index`` is
0-based; ``schema_version`` is a string ``"1.0"`` (NOT an int — legacy
serialises it as a string and we must read+write the same shape).

Failure modes (load):
- File missing                   → ``None`` (cold start; no restore).
- File present but unparsable    → ``None`` (logged at debug; don't crash startup).
- File present, dict, wrong keys → ``None`` (best-effort; don't crash).
- File present, valid            → ``SessionState(...)``.

Failure modes (save):
- ``data_root`` missing          → mkdir parent then write (atomic).
- write fails                    → re-raise (caller decides; legacy
                                   swallowed silently which made
                                   "session never saved" a silent bug).

Atomicity: save-side uses ``tmp + replace`` so a crash mid-write
leaves either the old file or the new file — never a half-written one.
The general ``write_json_atomic`` helper in spec §8 is a sibling
``atomic.py`` module (lands separately when ``user_page_envelope``
needs it); for now we inline the same pattern here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pd_ocr_labeler_spa.core.persistence.paths import session_state_path

logger = logging.getLogger(__name__)

SESSION_STATE_FILENAME = "session_state.json"
"""Re-exported from ``paths`` for callers that only import this module."""

SESSION_STATE_SCHEMA_VERSION = "1.0"
"""Spec §6: schema_version is the **string** ``"1.0"``, not an int."""


class SessionState(BaseModel):
    """Last-loaded project + page — restored on next startup.

    The legacy binary uses a ``dataclass`` with the same field names
    (``pd_ocr_labeler/operations/persistence/session_state_operations.py``).
    We use Pydantic for validation but keep the wire shape identical
    (``model_dump()`` → ``json.dumps`` produces the same JSON the legacy
    writes).
    """

    # Top-level envelope: forbid extra keys so a malformed save (e.g.
    # someone shipping a v1.1 field we don't know about) is detected
    # at parse time rather than silently dropped. The version-bump
    # rule is documented in ``specs/09-persistence.md §11``.
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default=SESSION_STATE_SCHEMA_VERSION,
        description="Schema version string. Spec §6 fixes this at '1.0'.",
    )
    last_project_path: str | None = Field(
        default=None,
        description=(
            "Absolute path to the project directory most recently loaded. "
            "Stored as a string (NOT a Path) for legacy interop — the legacy "
            "binary writes a string and we must round-trip identically."
        ),
    )
    last_page_index: int = Field(
        default=0,
        ge=0,
        description="0-based page index. Negative values rejected (page 0 means 'first page').",
    )


def load_session_state(data_root: Path) -> SessionState | None:
    """Read ``<data_root>/session_state.json`` if present and valid.

    Returns ``None`` (not an exception) on:
    - file missing
    - file unparsable as JSON
    - JSON not an object
    - object fails Pydantic validation

    All four are normal cold-start / drift conditions; the caller
    should treat ``None`` as "no prior session" and present the
    project picker. Legacy parity: ``SessionStateOperations.load_session_state``
    returns ``None`` on every failure path (legacy lines 95-120). We
    preserve that contract here.

    Logged at ``debug`` level (not ``warning`` / ``error``): a missing
    or stale file is the **expected** state on first run.
    """
    path = session_state_path(data_root)
    if not path.exists():
        logger.debug("No session state file at %s (cold start).", path)
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.debug("Failed to read %s.", path, exc_info=True)
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("Session state at %s is not valid JSON; ignoring.", path, exc_info=True)
        return None
    if not isinstance(data, dict):
        logger.debug("Session state at %s is not a JSON object; ignoring.", path)
        return None
    try:
        return SessionState.model_validate(data)
    except Exception:  # pragma: no cover - pydantic ValidationError covered below
        # Catch-all so a future Pydantic version change in error class
        # hierarchy doesn't crash startup. The branch is covered by
        # the malformed-input test in tests/.
        logger.debug("Session state at %s failed validation; ignoring.", path, exc_info=True)
        return None


def save_session_state(data_root: Path, state: SessionState) -> None:
    """Write ``state`` atomically to ``<data_root>/session_state.json``.

    Atomicity: writes ``<path>.tmp`` then ``Path.replace`` — POSIX
    rename is atomic so readers see either the old file or the new
    file (never a half-written one). On Windows ``Path.replace``
    delegates to ``MoveFileExW(MOVEFILE_REPLACE_EXISTING)`` which is
    also atomic.

    Creates ``data_root`` (and any parent dirs) if missing — the
    ``mkdir`` is the only filesystem mutation other than the write
    itself, so the function is safe to call before the data root
    has ever been touched. Any I/O error is **re-raised** (legacy
    swallowed it; that turned save-failures into silent data loss).

    Args:
        data_root: The OS-aware data root from ``Settings.data_root``.
            The session-state file lives directly under it (per spec §6).
        state: The state to persist. ``model_dump`` produces the
            legacy-compatible JSON shape (see ``SessionState`` docstring).
    """
    path = session_state_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.model_dump(), indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    logger.debug(
        "Saved session state to %s (project=%s page_index=%s).",
        path,
        state.last_project_path,
        state.last_page_index,
    )

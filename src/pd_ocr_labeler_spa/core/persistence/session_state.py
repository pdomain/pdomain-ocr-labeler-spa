"""Read/write of ``<data_root>/session_state.json``.

Spec: ``docs/architecture/09-persistence.md §6`` + ``docs/architecture/01-data-models.md §3``
("session_state.json"). Tiny single-file persistence: where was the
user when they last closed the app? Re-applied on next startup
(``app_state.startup()`` step 3 per ``docs/architecture/02-backend.md §13``).

Extras-tolerance policy (D-041, 2026-05-07): the SPA and legacy
share this file and either may add additive fields without a
coordinated release, so the reader uses ``extra="ignore"`` (legacy
parity — `from_dict` semantics). When unknown keys ARE seen, they
are logged at **WARNING** with the stable grep-able substring
``session_state_extras_dropped`` so a release-time CI step or
operator can detect uncoordinated drift. The ``UserPageEnvelope``
keeps ``extra="forbid"`` — that asymmetry is the deliberate
forward-compat circuit-breaker for the versioned schema (spec §11).

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

    # Top-level envelope: ``extra="ignore"`` per D-041 — the SPA and
    # legacy share this file and either may add additive fields
    # without a coordinated release. ``load_session_state`` separately
    # logs dropped keys at WARNING (stable substring
    # ``session_state_extras_dropped``) so an operator / CI gate can
    # spot uncoordinated drift. ``UserPageEnvelope`` keeps
    # ``extra="forbid"`` (the versioned schema's forward-compat
    # circuit-breaker; spec §11). Don't conflate the two.
    model_config = ConfigDict(extra="ignore")

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
        parsed = SessionState.model_validate(data)
    except Exception:  # pragma: no cover - pydantic ValidationError covered below
        # Catch-all so a future Pydantic version change in error class
        # hierarchy doesn't crash startup. The branch is covered by
        # the malformed-input test in tests/.
        logger.debug("Session state at %s failed validation; ignoring.", path, exc_info=True)
        return None

    # D-041: detect dropped (unknown) keys and emit a WARNING with the
    # stable substring ``session_state_extras_dropped`` so an operator
    # or CI grep can spot uncoordinated SPA/legacy drift. Compare the
    # raw JSON keys to the model's declared field names — anything in
    # the JSON but not in the model was silently dropped by
    # ``extra="ignore"``.
    declared = set(SessionState.model_fields.keys())
    raw_keys = set(data.keys())
    dropped = sorted(raw_keys - declared)
    if dropped:
        logger.warning(
            "session_state_extras_dropped — unknown key(s) %s in %s ignored "
            "(possible SPA/legacy drift; stable substring for grep / CI gates).",
            dropped,
            path,
            extra={
                "session_state_dropped_keys": dropped,
                "session_state_path": str(path),
            },
        )
    return parsed


def last_project_path_exists(state: SessionState) -> bool:
    """Stage-2 validation seam for spec §6's "ignore stale path" rule.

    Spec §6 reads "Read on app start; if the path no longer exists or
    doesn't contain images, ignore." That's a **two-stage validation**:

    1. ``load_session_state`` parses the JSON envelope (this module).
    2. The caller (``app_state.startup()``) verifies ``last_project_path``
       still resolves to a project directory (this helper).

    Splitting the seams keeps ``load_session_state`` a pure read — no
    filesystem checks beyond the file the function is named for — and
    gives callers an explicit single-call validator they can either
    use or bypass with intent. B-60 motivated this seam: without an
    explicit helper a future caller author may reasonably read
    "load_session_state returned a state ⇒ I can trust the path" and
    skip the existence check, then blow up on the first file read.

    Returns ``True`` iff ``state.last_project_path`` is non-None AND
    resolves to an existing directory (NOT a regular file — saved
    projects are always dirs containing per-page JSONs per spec §1).
    Otherwise returns ``False`` — the caller should treat that as "no
    prior session" and present the project picker.
    """
    if state.last_project_path is None:
        return False
    return Path(state.last_project_path).is_dir()


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

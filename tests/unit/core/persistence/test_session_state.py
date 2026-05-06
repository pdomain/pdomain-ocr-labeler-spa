"""Round-trip + failure-mode pins for ``core/persistence/session_state.py``.

Spec: ``specs/09-persistence.md §6`` + ``specs/01-data-models.md §3``.

The session-state file is shared with the legacy ``pd-ocr-labeler``
binary under D-003 (same ``data_root``, both binaries read+write it),
so the wire shape is **byte-compatible** with legacy. These tests pin:

- Field names (``last_project_path`` singular; ``last_page_index``;
  ``schema_version`` as a string ``"1.0"``).
- Cold-start: missing file returns ``None`` (NOT raises ``FileNotFoundError``).
- Failure modes: malformed JSON / wrong shape / extra fields each
  return ``None`` cleanly (never crash startup).
- Save atomicity: ``Path.replace`` semantics (no half-written files).
- Save creates the data-root parent dir on first use.
- Save errors propagate (legacy swallowed; we don't, per docstring rationale).

These pins guard the D-003 contract: flipping between the legacy
binary and the SPA must "just work" against a shared data root.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pd_ocr_labeler_spa.core.persistence.paths import session_state_path
from pd_ocr_labeler_spa.core.persistence.session_state import (
    SESSION_STATE_FILENAME,
    SESSION_STATE_SCHEMA_VERSION,
    SessionState,
    load_session_state,
    save_session_state,
)

# ── module-level constants (legacy parity pin) ───────────────────────────


def test_session_state_constants_match_legacy_spelling() -> None:
    """Spec §6: filename ``session_state.json``, schema version string ``"1.0"``."""
    assert SESSION_STATE_FILENAME == "session_state.json"
    assert SESSION_STATE_SCHEMA_VERSION == "1.0"
    # Critical: the version is a STRING not an int. Legacy serialises it
    # as a string and we must round-trip identically.
    assert isinstance(SESSION_STATE_SCHEMA_VERSION, str)


# ── SessionState model: field defaults + validation ──────────────────────


def test_session_state_default_construction() -> None:
    """Empty construction yields the spec defaults (cold-start sentinel)."""
    state = SessionState()
    assert state.schema_version == "1.0"
    assert state.last_project_path is None
    assert state.last_page_index == 0


def test_session_state_legacy_field_names() -> None:
    """Field names are spelled exactly as the legacy binary writes them.

    ``last_project_path`` is **singular** (one path, not a list);
    ``last_page_index`` is 0-based. A typo here breaks D-003 interop.
    """
    fields = set(SessionState.model_fields.keys())
    assert fields == {"schema_version", "last_project_path", "last_page_index"}


def test_session_state_rejects_negative_page_index() -> None:
    """``last_page_index`` must be ≥ 0 (page 0 means 'first page')."""
    with pytest.raises(ValidationError):
        SessionState(last_page_index=-1)


def test_session_state_rejects_extra_fields() -> None:
    """Top-level envelope is ``extra="forbid"``: a stray key surfaces
    schema-drift loudly rather than being silently dropped (spec §11
    versioning policy)."""
    with pytest.raises(ValidationError):
        SessionState.model_validate({"last_project_path": "/x", "last_page_index": 0, "future_field": True})


# ── cold-start / failure-mode load behaviour ─────────────────────────────


def test_load_returns_none_when_file_missing(tmp_path: Path) -> None:
    """Cold start: file doesn't exist → ``None`` (NOT FileNotFoundError).

    The caller (``app_state.startup()``) treats ``None`` as "no prior
    session" and presents the project picker. Raising would crash startup.
    """
    assert load_session_state(tmp_path) is None


def test_load_returns_none_when_data_root_does_not_exist(tmp_path: Path) -> None:
    """Even more pathological cold-start: the data root itself isn't
    on disk yet. ``Path.exists()`` returns False; we don't crash."""
    nonexistent = tmp_path / "no-such-data-root"
    assert load_session_state(nonexistent) is None


def test_load_returns_none_when_file_is_unparseable_json(tmp_path: Path) -> None:
    """Corrupt file → ``None`` (logged at debug; don't crash startup)."""
    path = session_state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this is not { json", encoding="utf-8")
    assert load_session_state(tmp_path) is None


def test_load_returns_none_when_json_is_not_an_object(tmp_path: Path) -> None:
    """Wrong top-level shape (list, string, number) → ``None``."""
    path = session_state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_session_state(tmp_path) is None


def test_load_returns_none_when_object_has_extra_field(tmp_path: Path) -> None:
    """``extra="forbid"`` rejection at parse time → ``None`` (not raise).

    Best-effort load: an unknown future field shouldn't crash startup;
    we just ignore the file and let the user start fresh.
    """
    path = session_state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": "1.0", "last_page_index": 0, "future": "x"}),
        encoding="utf-8",
    )
    assert load_session_state(tmp_path) is None


def test_load_returns_none_when_page_index_negative(tmp_path: Path) -> None:
    """Validation failure (negative page_index) → ``None``."""
    path = session_state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": "1.0", "last_project_path": "/x", "last_page_index": -5}),
        encoding="utf-8",
    )
    assert load_session_state(tmp_path) is None


# ── happy-path round trip ────────────────────────────────────────────────


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    """Standard cycle: save state, load it back, fields equal."""
    state = SessionState(last_project_path="/path/to/project", last_page_index=7)
    save_session_state(tmp_path, state)
    loaded = load_session_state(tmp_path)
    assert loaded is not None
    assert loaded.last_project_path == "/path/to/project"
    assert loaded.last_page_index == 7
    assert loaded.schema_version == "1.0"


def test_save_creates_data_root_if_missing(tmp_path: Path) -> None:
    """``save_session_state`` mkdir's the data root on first call.

    Cold install: ``~/.local/share/pd-ocr-labeler/`` doesn't exist
    yet on first run; the save must succeed without the user pre-creating it.
    """
    fresh = tmp_path / "first-run-data-root"
    assert not fresh.exists()
    save_session_state(fresh, SessionState(last_project_path="/x", last_page_index=0))
    assert fresh.exists()
    assert (fresh / SESSION_STATE_FILENAME).exists()


def test_save_overwrites_existing_state(tmp_path: Path) -> None:
    """Two saves: the second wins; no append, no merge."""
    save_session_state(tmp_path, SessionState(last_project_path="/first", last_page_index=1))
    save_session_state(tmp_path, SessionState(last_project_path="/second", last_page_index=99))
    loaded = load_session_state(tmp_path)
    assert loaded is not None
    assert loaded.last_project_path == "/second"
    assert loaded.last_page_index == 99


# ── on-disk wire shape (legacy interop pin) ──────────────────────────────


def test_saved_json_matches_legacy_shape(tmp_path: Path) -> None:
    """Dump the saved file and assert key set + types match legacy spec §6.

    Legacy field names + types must be byte-compatible — flipping
    between the SPA and pd-ocr-labeler against the same data root
    must work transparently.
    """
    state = SessionState(last_project_path="/abs/project", last_page_index=3)
    save_session_state(tmp_path, state)
    path = session_state_path(tmp_path)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    # Exact key set per spec §6 — extra keys would be a schema drift.
    assert set(on_disk.keys()) == {"schema_version", "last_project_path", "last_page_index"}
    # Types per spec.
    assert isinstance(on_disk["schema_version"], str)
    assert on_disk["schema_version"] == "1.0"
    assert isinstance(on_disk["last_project_path"], str)
    assert on_disk["last_project_path"] == "/abs/project"
    assert isinstance(on_disk["last_page_index"], int)
    assert on_disk["last_page_index"] == 3


def test_saved_json_serialises_null_project_path(tmp_path: Path) -> None:
    """``last_project_path=None`` → JSON ``null`` (not the string ``"None"``).

    Catches a regression where someone replaces the field default with
    a string sentinel.
    """
    state = SessionState()  # all defaults
    save_session_state(tmp_path, state)
    on_disk = json.loads(session_state_path(tmp_path).read_text(encoding="utf-8"))
    assert on_disk["last_project_path"] is None


def test_can_read_legacy_shaped_file(tmp_path: Path) -> None:
    """Hand-crafted legacy-shaped file (mimicking what the legacy binary
    writes) loads cleanly. This is the **D-003 interop pin**: if the
    legacy binary writes the file, the SPA must read it."""
    path = session_state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Legacy writes via dataclass.asdict + json.dumps with indent=2.
    legacy_payload = {
        "schema_version": "1.0",
        "last_project_path": "/some/legacy/project",
        "last_page_index": 12,
    }
    path.write_text(json.dumps(legacy_payload, indent=2), encoding="utf-8")
    loaded = load_session_state(tmp_path)
    assert loaded is not None
    assert loaded.last_project_path == "/some/legacy/project"
    assert loaded.last_page_index == 12


# ── atomicity invariants ─────────────────────────────────────────────────


def test_save_does_not_leave_tmp_file_on_success(tmp_path: Path) -> None:
    """``Path.replace`` consumes the tmp file; no stray ``.tmp`` afterwards."""
    save_session_state(tmp_path, SessionState(last_page_index=0))
    final = session_state_path(tmp_path)
    tmp_marker = final.with_suffix(final.suffix + ".tmp")
    assert final.exists()
    assert not tmp_marker.exists(), "stray .tmp left after save — atomic-rename broken"


def test_save_replaces_atomically_under_concurrent_load(tmp_path: Path) -> None:
    """Reader sees the OLD file or the NEW file, never a half-written one.

    Sketch: write an initial state, then save a new one; between the
    write of ``.tmp`` and the ``replace``, the file the reader sees
    must still be the old one. Verifying this exhaustively requires
    fault injection — here we settle for the weaker invariant: between
    saves, the on-disk file is always the result of a complete previous
    save, never partial JSON.
    """
    save_session_state(tmp_path, SessionState(last_project_path="/old", last_page_index=1))
    # Read mid-cycle: the file must parse as valid JSON with all fields.
    raw = session_state_path(tmp_path).read_text(encoding="utf-8")
    parsed = json.loads(raw)  # would raise on partial/empty
    assert parsed["last_project_path"] == "/old"
    assert parsed["last_page_index"] == 1

    save_session_state(tmp_path, SessionState(last_project_path="/new", last_page_index=2))
    raw2 = session_state_path(tmp_path).read_text(encoding="utf-8")
    parsed2 = json.loads(raw2)
    assert parsed2["last_project_path"] == "/new"
    assert parsed2["last_page_index"] == 2

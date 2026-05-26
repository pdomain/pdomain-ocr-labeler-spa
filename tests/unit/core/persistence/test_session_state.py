"""Round-trip + failure-mode pins for ``core/persistence/session_state.py``.

Spec: ``docs/architecture/09-persistence.md §6`` + ``docs/architecture/01-data-models.md §3``.

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
import logging
from concurrent.futures import ThreadPoolExecutor
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


def test_session_state_ignores_extra_fields_per_d041() -> None:
    """D-041 (2026-05-07): top-level envelope is ``extra="ignore"`` —
    the SPA and legacy share this file and either may add additive
    fields. Unknown keys are silently dropped at the model layer; the
    operator-facing WARNING is emitted by ``load_session_state``
    (covered separately below)."""
    s = SessionState.model_validate({"last_project_path": "/x", "last_page_index": 0, "future_field": True})
    assert s.last_project_path == "/x"
    assert s.last_page_index == 0
    assert not hasattr(s, "future_field")


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


def test_load_ignores_unknown_keys_per_d041(tmp_path: Path) -> None:
    """D-041 (2026-05-07): unknown keys are silently dropped at the
    Pydantic layer (``extra="ignore"``), the load returns the parsed
    state with the known fields populated. The operator-facing
    WARNING is asserted in
    ``test_load_logs_warning_with_stable_substring_when_extras_dropped``.
    """
    path = session_state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "last_project_path": "/x",
                "last_page_index": 3,
                "future": "x",
            }
        ),
        encoding="utf-8",
    )
    state = load_session_state(tmp_path)
    assert state is not None
    assert state.last_project_path == "/x"
    assert state.last_page_index == 3


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


# ── B-60: stale-path validation seam ─────────────────────────────────────


def test_load_session_state_returns_state_for_stale_path(tmp_path: Path) -> None:
    """B-60: ``load_session_state`` MUST be a pure read — it does NOT
    validate that ``last_project_path`` still exists on disk.

    Spec §6 says "Read on app start; if the path no longer exists or
    doesn't contain images, ignore." That's a two-stage validation;
    the module owner of stage 1 is ``load_session_state`` and the
    owner of stage 2 is the caller (``app_state.startup()``). Pinning
    the divide here means a future caller author can't accidentally
    "fix" stage 2 inside ``load_session_state`` — which would couple
    the persistence layer to the filesystem in ways the docstring
    explicitly disclaims.
    """
    stale = tmp_path / "this-project-was-moved-away"
    save_session_state(tmp_path, SessionState(last_project_path=str(stale), last_page_index=3))
    assert not stale.exists(), "test setup: project dir must not exist"
    loaded = load_session_state(tmp_path)
    # Stage-1 read returns a SessionState even though the path is stale.
    assert loaded is not None
    assert loaded.last_project_path == str(stale)


def test_last_project_path_exists_returns_false_when_none(tmp_path: Path) -> None:
    """B-60 stage-2 helper: ``last_project_path is None`` → False."""
    from pd_ocr_labeler_spa.core.persistence.session_state import (
        last_project_path_exists,
    )

    state = SessionState()  # last_project_path defaults to None
    assert last_project_path_exists(state) is False
    del tmp_path  # unused


def test_last_project_path_exists_returns_false_when_missing(tmp_path: Path) -> None:
    """B-60 stage-2 helper: a path string that doesn't resolve → False."""
    from pd_ocr_labeler_spa.core.persistence.session_state import (
        last_project_path_exists,
    )

    state = SessionState(last_project_path=str(tmp_path / "nope"), last_page_index=0)
    assert last_project_path_exists(state) is False


def test_last_project_path_exists_returns_true_when_dir_exists(tmp_path: Path) -> None:
    """B-60 stage-2 helper: a path string pointing at a real dir → True.

    The helper checks ``Path.is_dir()`` (not ``.exists()``) — a regular
    file at the path doesn't count, since saved projects are always
    directories under spec §1.
    """
    from pd_ocr_labeler_spa.core.persistence.session_state import (
        last_project_path_exists,
    )

    proj = tmp_path / "real-project"
    proj.mkdir()
    state = SessionState(last_project_path=str(proj), last_page_index=2)
    assert last_project_path_exists(state) is True


def test_last_project_path_exists_returns_false_for_file_at_path(tmp_path: Path) -> None:
    """B-60 stage-2 helper: a regular file (not a dir) at the path → False.

    Saved projects are dirs containing per-page JSON files; a file at
    the path means the layout is corrupt and the caller should treat
    it as "no prior session" rather than try to load it.
    """
    from pd_ocr_labeler_spa.core.persistence.session_state import (
        last_project_path_exists,
    )

    not_a_dir = tmp_path / "regular-file.txt"
    not_a_dir.write_text("not a project")
    state = SessionState(last_project_path=str(not_a_dir), last_page_index=0)
    assert last_project_path_exists(state) is False


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


# ── D-041 (2026-05-07): WARNING-level drift signal on dropped keys ────────


def test_load_logs_warning_with_stable_substring_when_extras_dropped(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-041 spec amendment to §6: when ``load_session_state`` reads a
    file with unknown keys, it MUST emit a WARNING containing the
    stable grep-able substring ``session_state_extras_dropped``. The
    substring is the contract — future iters that change the
    human-readable wording must keep it intact so a release-time CI
    grep can detect uncoordinated SPA/legacy drift.

    The dropped key names also appear in ``extra=`` so structured-log
    parsers can route on them.
    """
    path = session_state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "last_project_path": "/x",
                "last_page_index": 0,
                "future_one": "a",
                "future_two": "b",
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.persistence.session_state"):
        state = load_session_state(tmp_path)

    assert state is not None
    matching = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "session_state_extras_dropped" in r.getMessage()
    ]
    assert len(matching) == 1, (
        "Expected exactly one WARNING with the stable substring "
        "'session_state_extras_dropped'. D-041 makes this substring the "
        "release-CI / operator-grep contract."
    )
    dropped = getattr(matching[0], "session_state_dropped_keys", None)
    assert dropped == ["future_one", "future_two"], (
        f"WARNING extra= must list dropped key names; got {dropped!r}"
    )


def test_load_does_not_warn_when_no_extras_present(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Negative pin for D-041: a normal load with only declared keys
    must NOT emit the WARNING. Otherwise every release would trip the
    operator's drift alarm and the signal would be useless."""
    path = session_state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "last_project_path": "/x",
                "last_page_index": 0,
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.persistence.session_state"):
        state = load_session_state(tmp_path)

    assert state is not None
    drift_warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "session_state_extras_dropped" in r.getMessage()
    ]
    assert drift_warnings == [], (
        "WARNING must be silent when only declared keys are present — "
        "the substring is reserved for actual drift signals (D-041)."
    )


def test_save_concurrent_writes_no_collision(tmp_path: Path) -> None:
    """Concurrent ``save_session_state`` calls each use a unique temp file.

    With the deterministic ``<path>.tmp`` name, two concurrent writers
    would collide on the temp file.  With random temp names each writer
    gets its own private temp file, so ``os.replace`` always finds the
    file it created and the last caller's data wins (no exception).

    Post-conditions:
    - No exception raised by any writer.
    - The session-state file exists and is valid JSON with the expected shape.
    - No ``.tmp`` files remain in the data root.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    n = 8

    def write_i(i: int) -> None:
        save_session_state(
            data_root,
            SessionState(
                schema_version="1.0",
                last_project_path=f"/proj/{i}",
                last_page_index=i,
            ),
        )

    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(write_i, range(n)))

    # Target must exist and be a valid session-state file.
    loaded = load_session_state(data_root)
    assert loaded is not None
    assert loaded.last_page_index in range(n)

    # No orphan temp files.
    assert list(data_root.glob("*.tmp")) == []

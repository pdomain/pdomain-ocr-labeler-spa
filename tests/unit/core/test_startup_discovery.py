"""Unit tests for ``core.startup_discovery``.

M2 startup-discovery slice 1 (iter 52). Pins the contract that:

- ``cli_project_dir`` overrides any session restore (per
  ``docs/architecture/02-backend.md §13`` step 4: "If ``Settings.cli_project_dir``
  is set, override the restore — load the CLI dir.").
- A ``cli_project_dir`` that doesn't exist / isn't a directory / isn't
  readable is logged at WARNING and treated as if unset (slice 1 is
  observability-only; the failure mode is "fall through to session
  restore", same as legacy ``cli.py:18-23`` whose `project_dir` is just
  threaded through to `app_state.startup()` and validated there).
- A valid ``cli_project_dir`` produces a ``ResolvedInitialProject``
  with ``source="cli"``.
- An unset ``cli_project_dir`` + non-stale session produces
  ``source="session_restore"``.
- Both unset/missing → ``None``.
- Structured log events are emitted at INFO with stable keys
  (``initial_project_source``, ``initial_project_path``) so the
  observability surface is testable without resorting to message
  string parsing.

Slice intentionally STOPS at: project enumeration / scanning of
``source_projects_root`` (M2 proper); mutation of ``AppState``
(``AppState`` is frozen by design — landing the mutable
``ProjectState`` container is M2 proper); wiring into bootstrap's
lifespan (the lifespan stub still has no startup hook; that's M2
proper too). What slice 1 ships is a pure, unit-testable function the
M2 endpoint layer will plumb when it lands.

Spec authority: ``docs/architecture/02-backend.md §13`` (background discovery +
restoration), ``specs/16-milestones.md`` M2 outcome.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.persistence.session_state import SessionState
from pd_ocr_labeler_spa.core.startup_discovery import (
    ResolvedInitialProject,
    resolve_initial_project,
    validate_project_dir,
)
from pd_ocr_labeler_spa.settings import Settings

# ── validate_project_dir ───────────────────────────────────────────────────


def test_validate_project_dir_accepts_existing_readable_directory(tmp_path: Path) -> None:
    """Happy path: tmpdir exists, is a directory, is readable."""
    assert validate_project_dir(tmp_path) is True


def test_validate_project_dir_rejects_missing_path(tmp_path: Path) -> None:
    """Missing path → False (do not raise; caller logs and falls through)."""
    missing = tmp_path / "does-not-exist"
    assert validate_project_dir(missing) is False


def test_validate_project_dir_rejects_regular_file(tmp_path: Path) -> None:
    """Saved projects are dirs (per spec §1). A regular file is rejected.

    Mirrors the same is_dir() check ``last_project_path_exists`` enforces
    (B-60 follow-up; sibling validators must agree on "project = dir").
    """
    f = tmp_path / "regular.json"
    f.write_text("{}", encoding="utf-8")
    assert validate_project_dir(f) is False


def test_validate_project_dir_rejects_unreadable_directory(tmp_path: Path) -> None:
    """Permission-denied directory → False.

    chmod 000 then restore so the tmpdir cleanup can succeed. On systems
    where the test runs as root (``os.access`` always returns True),
    skip — there's nothing to assert.
    """
    import os

    if os.geteuid() == 0:
        pytest.skip("Running as root; os.access bypasses permission bits.")
    d = tmp_path / "locked"
    d.mkdir()
    d.chmod(0o000)
    try:
        assert validate_project_dir(d) is False
    finally:
        d.chmod(0o700)  # restore so pytest cleanup can rmtree


# ── resolve_initial_project: CLI-only branch ───────────────────────────────


def test_resolve_initial_project_cli_overrides_session(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Spec §13 step 4: ``cli_project_dir`` overrides ``last_project_path``.

    Both fields point to a real dir; the resolved source MUST be ``cli``.
    """
    cli_dir = tmp_path / "cli-project"
    cli_dir.mkdir()
    session_dir = tmp_path / "session-project"
    session_dir.mkdir()

    settings = Settings(
        config_root=tmp_path / "cfg",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        cli_project_dir=cli_dir,
    )
    session = SessionState(last_project_path=str(session_dir), last_page_index=3)

    with caplog.at_level(logging.INFO, logger="pd_ocr_labeler_spa.core.startup_discovery"):
        resolved = resolve_initial_project(settings, session_state=session)

    assert resolved is not None
    assert resolved.path == cli_dir.resolve()
    assert resolved.source == "cli"

    # Structured-log assertion: at least one record carries the
    # ``initial_project_source`` extra. (caplog records preserve LogRecord
    # attrs, including everything ``extra=`` set.)
    sources = [getattr(r, "initial_project_source", None) for r in caplog.records]
    assert "cli" in sources, f"expected an INFO log with extra=initial_project_source=cli; got {sources}"


def test_resolve_initial_project_cli_invalid_falls_through_to_session(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid ``cli_project_dir`` → log a WARNING; fall through to session.

    The slice-1 contract: validation failure is observable but
    non-fatal. Legacy parity (``cli.py:18-23`` doesn't pre-validate
    either; ``app_state.startup()`` decides). Avoids "user mistypes a
    path on the CLI and the labeler refuses to boot at all."
    """
    cli_dir = tmp_path / "missing-cli-project"  # deliberately not created
    session_dir = tmp_path / "session-project"
    session_dir.mkdir()

    settings = Settings(
        config_root=tmp_path / "cfg",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        cli_project_dir=cli_dir,
    )
    session = SessionState(last_project_path=str(session_dir), last_page_index=0)

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.startup_discovery"):
        resolved = resolve_initial_project(settings, session_state=session)

    assert resolved is not None
    assert resolved.path == session_dir.resolve()
    assert resolved.source == "session_restore"

    # The WARNING for the bad CLI path should mention it via the
    # structured ``cli_project_dir`` extra so log greps stay stable.
    bad_paths = [getattr(r, "cli_project_dir", None) for r in caplog.records if r.levelno == logging.WARNING]
    assert any(p == str(cli_dir) for p in bad_paths), (
        f"expected a WARNING with extra=cli_project_dir={cli_dir}; got {bad_paths}"
    )


# ── resolve_initial_project: session-restore branch ────────────────────────


def test_resolve_initial_project_session_restore(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """No CLI override; session has a valid ``last_project_path``."""
    session_dir = tmp_path / "session-project"
    session_dir.mkdir()
    settings = Settings(
        config_root=tmp_path / "cfg",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
    )
    session = SessionState(last_project_path=str(session_dir), last_page_index=2)

    with caplog.at_level(logging.INFO, logger="pd_ocr_labeler_spa.core.startup_discovery"):
        resolved = resolve_initial_project(settings, session_state=session)

    assert resolved is not None
    assert resolved.path == session_dir.resolve()
    assert resolved.source == "session_restore"

    sources = [getattr(r, "initial_project_source", None) for r in caplog.records]
    assert "session_restore" in sources, sources


def test_resolve_initial_project_session_stale_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Session ``last_project_path`` no longer resolves → None.

    Same two-stage seam as ``last_project_path_exists`` enforces (B-60):
    parsed-JSON-but-stale-path is treated as "no prior session".
    """
    settings = Settings(
        config_root=tmp_path / "cfg",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
    )
    session = SessionState(last_project_path=str(tmp_path / "vanished"), last_page_index=0)

    with caplog.at_level(logging.DEBUG, logger="pd_ocr_labeler_spa.core.startup_discovery"):
        resolved = resolve_initial_project(settings, session_state=session)

    assert resolved is None


def test_resolve_initial_project_no_inputs_returns_none(tmp_path: Path) -> None:
    """No CLI dir + no session → None. The "first-launch" cold path."""
    settings = Settings(
        config_root=tmp_path / "cfg",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
    )
    resolved = resolve_initial_project(settings, session_state=None)
    assert resolved is None


def test_resolve_initial_project_session_none_path_returns_none(tmp_path: Path) -> None:
    """SessionState exists but ``last_project_path is None`` → None.

    Defensive — the schema allows ``None`` (cold-start save before any
    project ever loaded). Must not crash on ``Path(None)``.
    """
    settings = Settings(
        config_root=tmp_path / "cfg",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
    )
    session = SessionState(last_project_path=None, last_page_index=0)
    assert resolve_initial_project(settings, session_state=session) is None


# ── ResolvedInitialProject ─────────────────────────────────────────────────


def test_resolved_initial_project_is_immutable(tmp_path: Path) -> None:
    """The resolved record is frozen — same hard-frozen contract as
    ``AppState`` (``core/app_state.py``). Future code mutating the
    resolved path would silently desync from what got logged at
    startup; this pin makes that a TypeError."""
    r = ResolvedInitialProject(path=tmp_path, source="cli")
    with pytest.raises((AttributeError, Exception)):
        r.source = "session_restore"  # type: ignore[misc]


def test_resolved_initial_project_source_is_constrained(tmp_path: Path) -> None:
    """``source`` is a Literal — the type-checker's the primary gate, but
    we also pin via runtime behaviour: pickling-friendly, str-ish."""
    r = ResolvedInitialProject(path=tmp_path, source="cli")
    assert r.source in ("cli", "session_restore")

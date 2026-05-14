"""M2 slice 3 acceptance: lifespan calls ``resolve_initial_project`` and
feeds the result into ``app.state.active_project_carrier``.

Spec authority:

- ``docs/architecture/02-backend.md §13`` — background discovery + restoration.
  Step 4 ("If ``Settings.cli_project_dir`` is set, override the
  restore — load the CLI dir") + step 3 (session_state restore)
  together describe the precedence already implemented as a pure
  function in ``core/startup_discovery.resolve_initial_project``.
  Slice 1 (iter 52) shipped that function.
- ``docs/architecture/02-backend.md §2`` step 5 names ``lifespan`` as a discrete
  build_app step. Slice 2 (iter 53) wired
  ``app.state.active_project_carrier`` but did not yet add the
  startup hook. **This slice (slice 3) is the missing connector.**
- ``core/active_project.ActiveProjectCarrier.set_active_project``
  takes a ``Path`` and pre-validates via
  ``startup_discovery.validate_project_dir``. The lifespan hook just
  routes the resolver's output into the carrier; both halves were
  unit-tested in iter 52/53.

Slice 3 deliberately does NOT:

- Enumerate ``Settings.source_projects_root`` (that's M2-proper
  ``core/project_state.py``).
- Add a ``GET /api/projects/discover`` route or
  ``POST /api/projects/load``  (slice 4).
- Persist a *new* ``session_state.json`` from the CLI source path
  (the writer half lives in iter 44's ``save_session_state`` and is
  invoked by the load route, not by the startup hook).

What this test pins:

1. Happy path — CLI project dir set + valid → after lifespan startup,
   ``app.state.active_project_carrier.snapshot()`` is a non-None
   ``ActiveProject`` whose ``path`` equals the resolved CLI dir.
2. No-inputs path — neither CLI nor session state set → after
   lifespan startup, snapshot stays ``None`` (no spurious project).
3. Session-restore path — no CLI, but a valid
   ``<data_root>/session_state.json`` pointing at an existing dir →
   snapshot reflects it with ``source="session_restore"`` semantics
   (we observe that via the ``ActiveProject.label`` defaulting to
   the dir basename and the path equality).
4. Stale-session path — session_state points at a missing dir →
   snapshot stays ``None`` (graceful fallthrough; legacy parity).

Acceptance test name (per ``specs/16-milestones.md`` M2 entry's
testing philosophy): each test is a one-line assertion of one
spec-mandated behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.persistence.paths import session_state_path
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Build a Settings instance rooted at ``tmp_path`` for isolation.

    api_only mode keeps the SPA-fallback off so the test sandbox
    doesn't need a populated ``static/`` bundle. The startup hook
    we're testing runs in every mode (it's not gated on mode).
    """
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _write_session_state(data_root: Path, last_project_path: str | None) -> None:
    """Write a minimal session_state.json under ``data_root``."""
    data_root.mkdir(parents=True, exist_ok=True)
    session_state_path(data_root).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "last_project_path": last_project_path,
                "last_page_index": 0,
            }
        ),
        encoding="utf-8",
    )


def test_lifespan_loads_cli_project_dir_into_carrier(tmp_path: Path) -> None:
    """Happy path: ``--project-dir DIR`` (valid) → carrier holds DIR."""
    project = tmp_path / "my-project"
    project.mkdir()

    settings = _make_settings(tmp_path, cli_project_dir=project)
    app = build_app(settings)

    # Carrier starts empty before lifespan runs (slice 2 invariant).
    assert app.state.active_project_carrier.snapshot() is None

    with TestClient(app):
        snap = app.state.active_project_carrier.snapshot()
        assert snap is not None, (
            "lifespan startup hook should have populated the carrier from settings.cli_project_dir"
        )
        assert snap.path == project.resolve(), (
            f"carrier path {snap.path!r} does not match resolved cli_project_dir {project.resolve()!r}"
        )
        # Default label = dir basename per slice-2 contract.
        assert snap.label == project.name


def test_lifespan_with_no_inputs_leaves_carrier_empty(tmp_path: Path) -> None:
    """No CLI, no session_state → carrier stays None after startup."""
    settings = _make_settings(tmp_path)  # no cli_project_dir, no session_state file
    app = build_app(settings)

    with TestClient(app):
        assert app.state.active_project_carrier.snapshot() is None


def test_lifespan_restores_session_state_when_no_cli(tmp_path: Path) -> None:
    """Session-restore path: valid session_state.json, no CLI override."""
    project = tmp_path / "restored-project"
    project.mkdir()
    data_root = tmp_path / "data"
    _write_session_state(data_root, last_project_path=str(project))

    settings = _make_settings(tmp_path)  # cli_project_dir not set
    app = build_app(settings)

    with TestClient(app):
        snap = app.state.active_project_carrier.snapshot()
        assert snap is not None, (
            "lifespan startup hook should have restored the project from session_state.json"
        )
        assert snap.path == project.resolve()
        assert snap.label == project.name


def test_lifespan_with_stale_session_state_leaves_carrier_empty(tmp_path: Path) -> None:
    """Stale session path → carrier stays None (legacy parity, no crash)."""
    data_root = tmp_path / "data"
    _write_session_state(data_root, last_project_path=str(tmp_path / "no-such-project"))

    settings = _make_settings(tmp_path)
    app = build_app(settings)

    with TestClient(app):
        assert app.state.active_project_carrier.snapshot() is None


def test_lifespan_cli_overrides_session_state(tmp_path: Path) -> None:
    """CLI takes precedence over session_state per spec §13 step 4."""
    cli_project = tmp_path / "cli-project"
    cli_project.mkdir()
    session_project = tmp_path / "session-project"
    session_project.mkdir()
    data_root = tmp_path / "data"
    _write_session_state(data_root, last_project_path=str(session_project))

    settings = _make_settings(tmp_path, cli_project_dir=cli_project)
    app = build_app(settings)

    with TestClient(app):
        snap = app.state.active_project_carrier.snapshot()
        assert snap is not None
        assert snap.path == cli_project.resolve(), (
            "CLI override must win over session_state per spec §13 step 4"
        )


def test_lifespan_with_invalid_cli_falls_through_to_session(tmp_path: Path) -> None:
    """Invalid CLI dir → WARNING + fall-through to session restore.

    Pinned by ``startup_discovery.resolve_initial_project``'s "invalid
    CLI falls through" contract. The lifespan hook MUST keep that
    fallthrough — i.e. it can't independently raise on an invalid CLI
    path; the resolver does its own logging and returns the next
    valid candidate.
    """
    bogus_cli = tmp_path / "does-not-exist"  # never created
    session_project = tmp_path / "session-project"
    session_project.mkdir()
    data_root = tmp_path / "data"
    _write_session_state(data_root, last_project_path=str(session_project))

    settings = _make_settings(tmp_path, cli_project_dir=bogus_cli)
    app = build_app(settings)

    with TestClient(app):
        snap = app.state.active_project_carrier.snapshot()
        assert snap is not None, "invalid CLI should fall through to session restore, not refuse to boot"
        assert snap.path == session_project.resolve()


def test_lifespan_startup_hook_is_idempotent_across_app_builds(tmp_path: Path) -> None:
    """Two ``build_app`` calls produce independent carriers — pinning
    the per-app singleton-not-module-global identity contract.

    Without this, a future "module-level lifespan helper" refactor
    that keys off a global ``_initial_project_resolved`` flag would
    silently break per-test isolation.
    """
    project = tmp_path / "p"
    project.mkdir()
    settings = _make_settings(tmp_path, cli_project_dir=project)

    app1 = build_app(settings)
    app2 = build_app(settings)

    # Different carrier instances per app.
    assert app1.state.active_project_carrier is not app2.state.active_project_carrier

    with TestClient(app1):
        snap1 = app1.state.active_project_carrier.snapshot()
        assert snap1 is not None and snap1.path == project.resolve()

    # app2 starts fresh; its carrier wasn't touched by app1's lifespan.
    assert app2.state.active_project_carrier.snapshot() is None
    with TestClient(app2):
        snap2 = app2.state.active_project_carrier.snapshot()
        assert snap2 is not None and snap2.path == project.resolve()

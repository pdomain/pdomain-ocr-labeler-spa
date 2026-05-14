"""Integration tests for lifespan session-restore wiring: HTTP surface.

Spec authority:
- ``docs/architecture/02-backend.md §13`` — startup discovery + session restoration.
  Steps 3–5: session_state.json → resolve_initial_project → carrier.set_active_project.
- ``docs/architecture/02-backend.md §5.2`` — ``GET /api/projects`` returns ``selected``
  equal to the carrier's current project_id (or null when carrier is empty).

What these tests guard (HTTP-level, not just carrier-level):

1. Seed ``session_state.json`` → start app → ``GET /api/projects`` returns
   ``selected`` matching the seeded project. This is the end-to-end proof
   that the lifespan hook correctly wires the session-restore path through
   to the public API surface.

2. Cold start (no ``session_state.json``) → ``GET /api/projects`` returns
   ``selected: null``.

3. Stale session (project dir missing) → ``GET /api/projects`` returns
   ``selected: null`` (no crash, no 500).

Carrier-level tests (no HTTP) live in
``tests/integration/test_startup_discovery_wiring.py``.

Issue: #188
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _settings(tmp_path: Path, **kwargs) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=tmp_path / "projects",
        **kwargs,
    )


def _write_session_state(data_root: Path, last_project_path: str | None) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "last_project_path": last_project_path,
        "last_page_index": 0,
    }
    (data_root / "session_state.json").write_text(json.dumps(payload), encoding="utf-8")


def test_session_restore_visible_in_get_projects(tmp_path: Path) -> None:
    """Seed session_state.json → GET /api/projects returns selected=project_id.

    This is the HTTP-surface proof that the lifespan hook's session-restore
    path wires through correctly: the carrier is populated at startup, and
    GET /api/projects reads the carrier to fill ``selected``.
    """
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    project_dir = projects_root / "my-project"
    project_dir.mkdir()

    data_root = tmp_path / "data"
    _write_session_state(data_root, last_project_path=str(project_dir))

    settings = _settings(tmp_path)
    app = build_app(settings)

    with TestClient(app) as c:
        resp = c.get("/api/projects")
        assert resp.status_code == 200
        body = resp.json()
        # The carrier was populated at startup from session_state — it should
        # now appear as the selected project.
        assert body["selected"] == "my-project", (
            f"Expected selected='my-project' but got {body['selected']!r}. "
            "Check that the lifespan startup hook feeds the session-restore "
            "path through to ActiveProjectCarrier."
        )


def test_cold_start_selected_is_null(tmp_path: Path) -> None:
    """Cold start (no session_state.json) → GET /api/projects returns selected=null."""
    settings = _settings(tmp_path)
    app = build_app(settings)

    with TestClient(app) as c:
        resp = c.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json()["selected"] is None


def test_stale_session_selected_is_null(tmp_path: Path) -> None:
    """Stale session (project dir missing) → GET /api/projects returns selected=null.

    Tests that a missing project dir doesn't cause a 500 at startup or at
    GET /api/projects time — the carrier stays empty and selected=null.
    """
    data_root = tmp_path / "data"
    # Point at a dir that was never created.
    _write_session_state(data_root, last_project_path=str(tmp_path / "ghost-project"))

    settings = _settings(tmp_path)
    app = build_app(settings)

    with TestClient(app) as c:
        resp = c.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json()["selected"] is None


def test_graceful_shutdown_no_asyncio_warnings(tmp_path: Path) -> None:
    """App exits cleanly without asyncio task warnings.

    Verifies that runner.stop() is awaited and no
    ``asyncio.exceptions.CancelledError`` is surfaced at shutdown —
    i.e. the JobRunner task teardown is clean.
    """
    import warnings

    settings = _settings(tmp_path)
    app = build_app(settings)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        with TestClient(app):
            pass
        import gc

        gc.collect()

    asyncio_warns = [
        w
        for w in captured
        if issubclass(w.category, RuntimeWarning) and "coroutine" in str(w.message).lower()
    ]
    assert asyncio_warns == [], (
        f"Asyncio coroutine warnings at shutdown: {[str(w.message) for w in asyncio_warns]}"
    )

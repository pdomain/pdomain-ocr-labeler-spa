"""Integration tests for GET /api/session-state endpoint.

Spec authority:
- ``docs/specs/2026-05-12-root-page-design.md §Decision`` — endpoint contract.
- ``specs/09-persistence.md §6`` — session_state.json schema.

Contract:
- GET /api/session-state returns 200 with ``last_project_path: null``
  when no session_state.json exists (cold start / first run).
- Returns 200 with ``last_project_path`` populated when session file exists.
- Returns 200 with ``schema_version: "1.0"`` and ``last_page_index: int``.

Issue: #274
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_session_state_no_prior_session(client: TestClient) -> None:
    """Cold start: no session_state.json → 200, last_project_path=null."""
    resp = client.get("/api/session-state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_project_path"] is None
    assert body["last_page_index"] == 0
    assert body["schema_version"] == "1.0"


def test_session_state_with_saved_session(
    client: TestClient,
    settings,
    tmp_path: Path,
) -> None:
    """When session_state.json exists and is valid, returns its contents."""
    data_root = settings.data_root
    data_root.mkdir(parents=True, exist_ok=True)
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    session = {
        "schema_version": "1.0",
        "last_project_path": str(project_dir),
        "last_page_index": 3,
    }
    (data_root / "session_state.json").write_text(json.dumps(session), encoding="utf-8")

    resp = client.get("/api/session-state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_project_path"] == str(project_dir)
    assert body["last_page_index"] == 3
    assert body["schema_version"] == "1.0"


def test_session_state_missing_file_returns_null(
    client: TestClient,
) -> None:
    """Missing session_state.json treated same as first run — null path."""
    resp = client.get("/api/session-state")
    assert resp.status_code == 200
    assert resp.json()["last_project_path"] is None


def test_session_state_corrupt_file_returns_null(
    client: TestClient,
    settings,
) -> None:
    """Corrupt session_state.json → graceful 200 with null path (no 500)."""
    data_root = settings.data_root
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "session_state.json").write_text("NOT JSON", encoding="utf-8")

    resp = client.get("/api/session-state")
    assert resp.status_code == 200
    assert resp.json()["last_project_path"] is None

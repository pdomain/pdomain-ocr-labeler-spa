"""Integration tests for ``api/jobs.py`` — list, get, SSE stream, cancel.

Spec authority:
- ``specs/02-backend.md §5.10`` — endpoint contracts.

Acceptance (issue #187):
- job cancel: POST /api/jobs/{id}/cancel terminates the running task.
- SSE stream: correct snapshot + terminal event.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


def _parse_sse_events(raw: bytes) -> list[dict]:
    """Parse ``event: <type>\ndata: {...}\n\n`` SSE frames."""
    events = []
    for block in raw.decode().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        event_type = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_type = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_type and data is not None:
            events.append({"event": event_type, "data": data})
    return events


def _submit_export(client: TestClient, project_id: str = "test-proj") -> str:
    """Helper: submit an export job and return its job_id."""
    resp = client.post(
        f"/api/projects/{project_id}/export",
        json={"scope": "current"},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["job_id"]


# ── GET /api/jobs ─────────────────────────────────────────────────────────────


def test_list_jobs_returns_empty_list_initially(client: TestClient) -> None:
    """No jobs submitted yet → empty list."""
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_jobs_after_submit(client: TestClient) -> None:
    """After submitting a job, it appears in the list."""
    job_id = _submit_export(client)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    ids = [j["job_id"] for j in resp.json()]
    assert job_id in ids


# ── GET /api/jobs/{job_id} ────────────────────────────────────────────────────


def test_get_job_returns_job(client: TestClient) -> None:
    """``GET /api/jobs/{job_id}`` returns the job record."""
    job_id = _submit_export(client)
    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == job_id


def test_get_job_unknown_id_returns_404(client: TestClient) -> None:
    """Unknown job id → 404."""
    resp = client.get("/api/jobs/no-such-job")
    assert resp.status_code == 404
    assert resp.json()["error"] == "job_not_found"


# ── GET /api/jobs/{job_id}/events (SSE) ───────────────────────────────────────


def test_job_events_route_returns_sse(client: TestClient) -> None:
    """The SSE endpoint sets Content-Type text/event-stream."""
    job_id = _submit_export(client)
    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


def test_job_events_first_frame_is_snapshot(client: TestClient) -> None:
    """The first SSE frame is a status snapshot (per spec §5.10)."""
    job_id = _submit_export(client)
    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        raw = b""
        for chunk in resp.iter_raw():
            raw += chunk
            if b"\n\n" in raw:
                break
    events = _parse_sse_events(raw)
    assert events, "Expected at least one SSE frame"
    first = events[0]
    assert "status" in first["data"]
    assert first["data"]["status"] in ("queued", "running", "complete", "error", "cancelled")


def test_job_events_sse_ends_on_terminal(client: TestClient) -> None:
    """SSE stream ends after the terminal event (complete/error/cancelled)."""
    job_id = _submit_export(client)
    terminal_events = {"complete", "error", "cancelled"}
    events: list[dict] = []

    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        raw = b""
        for chunk in resp.iter_raw():
            raw += chunk
            parsed = _parse_sse_events(raw)
            if any(e["event"] in terminal_events for e in parsed):
                events = parsed
                break

    terminal = [e for e in events if e["event"] in terminal_events]
    assert terminal, f"No terminal event; events={events}"


def test_job_events_unknown_job_returns_404(client: TestClient) -> None:
    """SSE endpoint on an unknown job_id returns 404."""
    resp = client.get("/api/jobs/no-such-job/events")
    assert resp.status_code == 404


# ── POST /api/jobs/{job_id}/cancel ────────────────────────────────────────────


def test_cancel_queued_job_returns_200(tmp_path: Path) -> None:
    """Cancelling a queued job returns 200 with cancelled status.

    Issue #187 acceptance: "job cancel: POST /api/jobs/{id}/cancel
    terminates the running task."

    We use a separate app (NOT the lifespan context) so the job stays
    QUEUED — the runner background task hasn't started yet.
    """
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    # Build the TestClient WITHOUT entering the lifespan context manager:
    # the runner's run_forever task is NOT started, so submitted jobs stay QUEUED.
    c = TestClient(app, raise_server_exceptions=True)

    # Submit a job (stays QUEUED — runner not running).
    resp = c.post(
        "/api/projects/test-proj/export",
        json={"scope": "current"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Verify it's queued (runner not started).
    job_before = c.get(f"/api/jobs/{job_id}").json()
    assert job_before["status"] == "queued"

    # Cancel it.
    resp_cancel = c.post(f"/api/jobs/{job_id}/cancel")
    assert resp_cancel.status_code == 200, resp_cancel.text
    body = resp_cancel.json()
    assert body["status"] == "cancelled"
    assert body["job_id"] == job_id


def test_cancel_updates_job_status_to_cancelled(tmp_path: Path) -> None:
    """After cancel, ``GET /api/jobs/{id}`` reflects CANCELLED status."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    c = TestClient(app, raise_server_exceptions=True)

    resp = c.post(
        "/api/projects/test-proj/export",
        json={"scope": "current"},
    )
    job_id = resp.json()["job_id"]

    c.post(f"/api/jobs/{job_id}/cancel")
    job = c.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "cancelled"


def test_cancel_unknown_job_returns_404(client: TestClient) -> None:
    """Cancel on unknown job_id → 404."""
    resp = client.post("/api/jobs/no-such-job/cancel")
    assert resp.status_code == 404
    assert resp.json()["error"] == "job_not_found"


def test_cancel_terminal_job_returns_409(client: TestClient) -> None:
    """Cancel on a completed job → 409 (already terminal).

    The lifespan context runs the runner, so the stub export job
    completes quickly. We wait until it's terminal via the SSE stream.
    """
    job_id = _submit_export(client)

    # Wait for terminal via SSE so the job is definitely complete.
    terminal_events = {"complete", "error", "cancelled"}
    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        raw = b""
        for chunk in resp.iter_raw():
            raw += chunk
            parsed = _parse_sse_events(raw)
            if any(e["event"] in terminal_events for e in parsed):
                break

    # Now cancel the completed job.
    resp_cancel = client.post(f"/api/jobs/{job_id}/cancel")
    assert resp_cancel.status_code == 409, resp_cancel.text
    assert resp_cancel.json()["error"] == "job_already_terminal"

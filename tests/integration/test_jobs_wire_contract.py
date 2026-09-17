"""Contract tests: REST job responses and SSE frames validate against the
declared public ``Job`` model, for every reachable status.

``docs/issues/2026-07-21-jobs-api-openapi-mismatch.md`` (P1-JOBS-API) and
``docs/issues/2026-07-21-job-sse-fe-be-shape-mismatch.md`` (P1-JOB-SSE):
routes declared ``response_model=Job`` but serialized a different shape via
a raw ``JSONResponse``, which FastAPI never validates; the SSE stream used a
third, flat shape. These tests drive the real ``JobRunner`` end to end and
assert every wire frame — REST and SSE, for ``running``/``complete``/
``error``/``cancelled`` — parses as the one declared ``Job`` model.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.jobs import JobEventBroker
from pdomain_ocr_labeler_spa.core.models import Job as PublicJob
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
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


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    return root


class _FakePageLoader:
    """Stand-in ``PageLoader``; optionally raises so the job reaches ``error``."""

    def __init__(self, *, raise_on_run: Exception | None = None) -> None:
        self.calls: list[int] = []
        self._raise = raise_on_run

    def run_ocr(
        self,
        page_index: int,
        *,
        edited_image_bytes: bytes | None = None,
        page_kind: object | None = None,
    ) -> PageLoadOutcome:
        self.calls.append(page_index)
        if self._raise is not None:
            raise self._raise
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload={"fake": "page"})

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None


def _wrap_broker_publish(broker: JobEventBroker, sink: list[dict[str, Any]]) -> None:
    original = broker.publish

    async def recording_publish(job_id: str, event: dict[str, Any]) -> None:
        sink.append(dict(event))
        await original(job_id, event)

    broker.publish = recording_publish  # type: ignore[method-assign]


def _wait_for_terminal(events: list[dict[str, Any]], *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(e.get("event") in ("complete", "error", "cancelled") for e in events):
            return
        time.sleep(0.01)
    raise AssertionError(f"no terminal event after {timeout}s; events={events}")


def _assert_frame_is_a_valid_job(frame: dict[str, Any], *, expected_event: str) -> None:
    assert frame["event"] == expected_event, frame
    # Job.model_config does not set extra="forbid", so the "event" wire
    # discriminator (not a Job field) is silently ignored by validation —
    # exactly what lets one payload double as "the Job model" + "which SSE
    # event this is".
    validated = PublicJob.model_validate(frame)
    assert validated.status.value in {"queued", "running", "complete", "error", "cancelled"}


# ── REST: GET /api/jobs, GET /api/jobs/{id}, POST /api/jobs/{id}/cancel ───────


def test_get_job_response_validates_against_the_declared_model(tmp_path: Path, projects_root: Path) -> None:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202
        job_id = ocr_resp.json()["job_id"]

        get_resp = c.get(f"/api/jobs/{job_id}")
        assert get_resp.status_code == 200, get_resp.text
        validated = PublicJob.model_validate(get_resp.json())
        assert validated.id == job_id
        assert validated.type.value == "reload_ocr"


def test_list_jobs_response_validates_against_the_declared_model(tmp_path: Path, projects_root: Path) -> None:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        job_id = ocr_resp.json()["job_id"]

        list_resp = c.get("/api/jobs")
        assert list_resp.status_code == 200
        jobs = [PublicJob.model_validate(item) for item in list_resp.json()]
        assert any(j.id == job_id for j in jobs)


def test_cancel_response_validates_against_the_declared_model(tmp_path: Path) -> None:
    """Cancelling a queued job returns a body the ``Job`` model accepts."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    # No lifespan context: the runner's run_forever task never starts, so the
    # submitted job stays QUEUED and cancel exercises the queued→cancelled path.
    c = TestClient(app, raise_server_exceptions=True)

    resp = c.post("/api/projects/test-proj/export", json={"scope": "all_validated"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    cancel_resp = c.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200, cancel_resp.text
    validated = PublicJob.model_validate(cancel_resp.json())
    assert validated.status.value == "cancelled"
    assert validated.id == job_id


# ── SSE: one frame per reachable status validates against the same model ──────


def test_sse_frames_for_running_and_complete_validate_against_the_declared_model(
    tmp_path: Path, projects_root: Path
) -> None:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202

        _wait_for_terminal(recorded)

        running_frames = [e for e in recorded if e.get("event") == "progress"]
        assert running_frames, f"no running/progress frame recorded: {recorded}"
        _assert_frame_is_a_valid_job(running_frames[0], expected_event="progress")

        _assert_frame_is_a_valid_job(recorded[-1], expected_event="complete")


def test_sse_frame_for_error_validates_against_the_declared_model(
    tmp_path: Path, projects_root: Path
) -> None:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader(raise_on_run=RuntimeError("doctr exploded"))
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202

        _wait_for_terminal(recorded)

        _assert_frame_is_a_valid_job(recorded[-1], expected_event="error")
        validated = PublicJob.model_validate(recorded[-1])
        assert validated.error_message is not None
        assert "doctr exploded" in validated.error_message


def test_sse_frame_for_cancelled_validates_against_the_declared_model(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    c = TestClient(app, raise_server_exceptions=True)
    recorded: list[dict[str, Any]] = []
    _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]

    resp = c.post("/api/projects/test-proj/export", json={"scope": "all_validated"})
    job_id = resp.json()["job_id"]

    cancel_resp = c.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200, cancel_resp.text

    _assert_frame_is_a_valid_job(recorded[-1], expected_event="cancelled")


# ── SSE stream endpoint itself: the frame it sends is the model shape ─────────


def _parse_sse_frames(raw: bytes) -> list[dict[str, Any]]:
    """Parse ``event: <name>\\ndata: {...}\\n\\n`` blocks into ``{event, data}``."""
    import json

    frames: list[dict[str, Any]] = []
    for block in raw.decode().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_name is not None and data is not None:
            frames.append({"event": event_name, "data": data})
    return frames


def test_sse_stream_terminal_frame_validates_against_the_declared_model(
    tmp_path: Path, projects_root: Path
) -> None:
    """A real ``GET /api/jobs/{id}/events`` terminal frame parses as ``Job``."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        job_id = ocr_resp.json()["job_id"]

        terminal_events = {"complete", "error", "cancelled"}
        terminal_frame: dict[str, Any] | None = None
        with c.stream("GET", f"/api/jobs/{job_id}/events") as resp:
            raw = b""
            for chunk in resp.iter_raw():
                raw += chunk
                parsed = _parse_sse_frames(raw)
                terminal = [f for f in parsed if f["event"] in terminal_events]
                if terminal:
                    terminal_frame = terminal[-1]
                    break

    assert terminal_frame is not None, "SSE stream never delivered a terminal frame"
    _assert_frame_is_a_valid_job(terminal_frame["data"], expected_event="complete")

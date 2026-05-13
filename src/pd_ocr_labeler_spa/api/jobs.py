"""``/api/jobs`` router — job list + SSE stream.

Spec authority: ``specs/02-backend.md §5.10``.

Endpoints:

- ``GET /api/jobs`` → ``list[Job]`` (in-memory snapshot).
- ``GET /api/jobs/{job_id}`` → ``Job``.
- ``GET /api/jobs/{job_id}/events`` → ``text/event-stream``.
  SSE: first frame = current job snapshot; subsequent = broker events;
  ends on terminal state (``complete`` | ``error`` | ``cancelled``).
- ``POST /api/jobs/{job_id}/cancel`` → ``Job`` (cooperative; honours
  only ``queued``/``running`` jobs — deferred to M3-proper).

SSE pattern: always emit the current job state first (snapshot frame),
then subscribe to the broker for live events. This handles two races:

1. The job completed BEFORE the SSE client connected — the snapshot
   shows terminal state; the generator returns immediately without
   subscribing.
2. The job is still running — the snapshot shows current progress;
   subsequent broker events carry the rest.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from ..core.jobs import Job, JobEventBroker, JobRunner, JobStatus
from .dependencies import get_job_events, get_job_runner
from .middleware.error_handler import ApiError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_TERMINAL = {JobStatus.COMPLETE, JobStatus.ERROR, JobStatus.CANCELLED}


def _job_not_found(job_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="job_not_found",
            message=f"job not found: {job_id}",
        ).model_dump(),
    )


def _job_snapshot(job: Job) -> dict:
    ev_type = job.status.value if job.status in _TERMINAL else "progress"
    return {
        "type": ev_type,
        "status": job.status.value,
        "current": job.progress_current,
        "total": job.progress_total,
        "message": job.message,
        "error": job.error_message,
    }


def _sse_line(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Routes ───────────────────────────────────────────────────────────


@router.get("")
def list_jobs(
    runner: JobRunner = Depends(get_job_runner),
) -> list[dict]:
    """``GET /api/jobs`` — in-memory job list."""
    return [j.model_dump(mode="json") for j in runner.list_jobs()]


@router.get("/{job_id}")
def get_job(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``GET /api/jobs/{job_id}`` — single job by id."""
    job = runner.get_job(job_id)
    if job is None:
        return _job_not_found(job_id)
    return JSONResponse(status_code=200, content=job.model_dump(mode="json"))


@router.get("/{job_id}/events")
async def job_events(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
    broker: JobEventBroker = Depends(get_job_events),
) -> StreamingResponse:
    """``GET /api/jobs/{job_id}/events`` — SSE stream.

    Per spec §5.10: first frame = current snapshot; subsequent = broker
    events; terminates on terminal state.
    """
    job = runner.get_job(job_id)
    if job is None:
        return JSONResponse(  # type: ignore[return-value]
            status_code=404,
            content=ApiError(
                error="job_not_found",
                message=f"job not found: {job_id}",
            ).model_dump(),
        )

    async def stream():
        snapshot = _job_snapshot(job)
        ev_name = snapshot["type"] if snapshot["type"] in ("complete", "error", "cancelled") else "snapshot"
        yield _sse_line(ev_name, snapshot)

        if job.status in _TERMINAL:
            return

        async for event in broker.subscribe(job_id):
            ev_type = event.get("type", "progress")
            yield _sse_line(ev_type, event)
            if ev_type in ("complete", "error", "cancelled"):
                return

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST /api/jobs/{job_id}/cancel`` — cooperative cancel stub."""
    job = runner.get_job(job_id)
    if job is None:
        return _job_not_found(job_id)
    return JSONResponse(status_code=200, content=job.model_dump(mode="json"))


def install_jobs_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the jobs router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = ["install_jobs_router", "router"]

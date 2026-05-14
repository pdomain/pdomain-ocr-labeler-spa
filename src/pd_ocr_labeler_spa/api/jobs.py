"""``/api/jobs`` router — list, get, SSE stream, cancel. Spec §5.10."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from ..core.jobs import Job as RunnerJob
from ..core.jobs import JobEventBroker, JobRunner, JobStatus
from ..core.models import Job, JobProgress, JobType  # noqa: F401
from .dependencies import get_job_events, get_job_runner
from .middleware.error_handler import ApiError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_TERMINAL = {JobStatus.COMPLETE, JobStatus.ERROR, JobStatus.CANCELLED}


def _runner_job_to_dict(job: RunnerJob) -> dict:
    return job.model_dump(mode="json")


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


@router.get("", response_model=list[Job])
def list_jobs(
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``GET /api/jobs`` — in-memory job list."""
    return JSONResponse(status_code=200, content=[_runner_job_to_dict(j) for j in runner.list_jobs()])


@router.get("/{job_id}", response_model=Job)
def get_job(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``GET /api/jobs/{job_id}`` — single job by id."""
    job = runner.get_job(job_id)
    if job is None:
        return _job_not_found(job_id)
    return JSONResponse(status_code=200, content=_runner_job_to_dict(job))


@router.get(
    "/{job_id}/events",
    response_class=StreamingResponse,
    # SSE: no Pydantic response_model; text/event-stream cannot be
    # declared as a typed schema — spec §5.10 intentional exception.
)
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


@router.post("/{job_id}/cancel", response_model=Job)
async def cancel_job(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST /api/jobs/{job_id}/cancel`` — cooperative cancel.

    Spec §5.10 line 337: cooperative cancel; only valid for queued /
    running. Returns the updated ``Job`` in ``cancelled`` state, or 404
    if not found, or 409 if already in a terminal state (spec "only
    valid for queued / running").
    """
    job = runner.get_job(job_id)
    if job is None:
        return _job_not_found(job_id)
    if job.status in _TERMINAL:
        return JSONResponse(
            status_code=409,
            content=ApiError(
                error="job_already_terminal",
                message=f"job {job_id} is already in terminal state {job.status}",
            ).model_dump(),
        )
    updated = await runner.request_cancel(job_id)
    if updated is None:
        return _job_not_found(job_id)
    return JSONResponse(status_code=200, content=_runner_job_to_dict(updated))


def install_jobs_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the jobs router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = ["install_jobs_router", "router"]

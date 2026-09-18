"""``/api/jobs`` router — list, get, SSE stream, cancel. Spec §5.10."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from ..core.jobs import Job as RunnerJob
from ..core.jobs import JobEventBroker, JobRunner, JobStatus, to_public_job
from ..core.models import Job
from .dependencies import get_job_events, get_job_runner
from .middleware.error_handler import ApiError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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


def _job_snapshot(job: RunnerJob) -> dict[str, object]:
    """Build the first SSE frame: the public ``Job`` model + an ``event`` field.

    Same shape as every other SSE frame (``JobRunner._emit``) and every REST
    ``Job`` response — see ``to_public_job`` for the field mapping.
    """
    ev_type = job.status.value if job.status in _TERMINAL else "progress"
    snapshot: dict[str, object] = dict(to_public_job(job).model_dump(mode="json"))
    snapshot["event"] = ev_type
    # Merge any structured result (e.g. export stats) so a late subscriber
    # that arrives after the job completed still sees the breakdown.
    if job.result:
        snapshot.update(job.result)
    return snapshot


def _sse_line(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Routes ───────────────────────────────────────────────────────────


@router.get("", response_model=list[Job])
def list_jobs(
    runner: JobRunner = Depends(get_job_runner),
) -> list[Job]:
    """``GET /api/jobs`` — in-memory job list.

    Returns the public ``Job`` model directly so FastAPI's ``response_model``
    actually validates/serializes the body — a raw ``JSONResponse`` here
    bypassed that check and let the wire shape drift from the declared
    OpenAPI ``Job`` (docs/issues/2026-07-21-jobs-api-openapi-mismatch.md,
    P1-JOBS-API).
    """
    return [to_public_job(j) for j in runner.list_jobs()]


@router.get("/{job_id}", response_model=Job)
def get_job(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
) -> Job | JSONResponse:
    """``GET /api/jobs/{job_id}`` — single job by id."""
    job = runner.get_job(job_id)
    if job is None:
        return _job_not_found(job_id)
    return to_public_job(job)


@router.get(
    "/{job_id}/events",
    response_class=StreamingResponse,
    # SSE: no Pydantic response_model; text/event-stream cannot be
    # declared as a typed schema — spec §5.10 intentional exception.
    # response_model=None also stops FastAPI trying (and failing) to build
    # a response field from the `StreamingResponse | JSONResponse` return
    # annotation — both are raw Starlette Response types, not model data.
    response_model=None,
)
async def job_events(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
    broker: JobEventBroker = Depends(get_job_events),
) -> StreamingResponse | JSONResponse:
    """``GET /api/jobs/{job_id}/events`` — SSE stream.

    Per spec §5.10: first frame = current snapshot; subsequent = broker
    events; terminates on terminal state. Every frame's JSON payload is the
    public ``Job`` model plus an ``event`` field naming the SSE event kind
    (``snapshot`` / ``progress`` / ``complete`` / ``error`` / ``cancelled``)
    — see ``JobRunner._emit`` and ``_job_snapshot`` for the shared shape.

    Registers the broker listener (``broker.listen``) *before* reading the
    job's current status for the initial snapshot — not after, the way an
    earlier version did by capturing ``job`` once and re-checking that same
    stale reference post-yield. That let a job racing to a terminal state
    between the initial fetch and the (only then made) ``subscribe`` call
    both report a stale non-terminal snapshot *and* subscribe to an
    already-closed, already-drained broker channel: the terminal event was
    gone for good and the stream hung forever. Listening first closes the
    race — see ``JobEventBroker.listen``'s docstring for the guarantee.
    """
    job = runner.get_job(job_id)
    if job is None:
        return _job_not_found(job_id)

    async def stream() -> AsyncIterator[str]:
        queue = await broker.listen(job_id)
        try:
            current = runner.get_job(job_id) or job
            snapshot = _job_snapshot(current)
            ev_name = (
                snapshot["event"] if snapshot["event"] in ("complete", "error", "cancelled") else "snapshot"
            )
            yield _sse_line(str(ev_name), snapshot)

            if current.status in _TERMINAL:
                return

            async for event in broker.drain(queue):
                ev_type = event.get("event", "progress")
                yield _sse_line(str(ev_type), event)
                if ev_type in ("complete", "error", "cancelled"):
                    return
        finally:
            await broker.unlisten(job_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/{job_id}/cancel", response_model=Job)
async def cancel_job(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
) -> Job | JSONResponse:
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
    return to_public_job(updated)


def install_jobs_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the jobs router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = ["install_jobs_router", "router"]

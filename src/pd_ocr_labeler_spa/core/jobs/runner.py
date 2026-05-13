"""In-process asyncio job runner.

Spec: ``specs/02-backend.md §11``. Simpler than pgdp-prep's
``InProcessJobRunner`` because this labeler needs no database backend,
no multi-user enumeration, and no distributed queue. Every job row lives
in ``self._jobs`` (lost on restart — the on-disk labeled envelopes are
the durable record).

Job lifecycle: QUEUED → RUNNING → COMPLETE | ERROR | CANCELLED.

``run_forever()`` is a background coroutine launched in the lifespan
hook (M3 slice spec §2 step 5). Each queued job runs inside an
``asyncio.create_task`` so the runner loop doesn't block while a job is
executing.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .events import JobEventBroker

log = logging.getLogger(__name__)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


class Job(BaseModel):
    """In-memory job record. Spec §5.10 ``Job`` shape."""

    job_id: str
    job_type: str
    status: JobStatus = JobStatus.QUEUED
    project_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    progress_current: int = 0
    progress_total: int = 0
    message: str = ""
    error_message: str = ""
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


Handler = Callable[["JobRunner", Job], Coroutine[Any, Any, None]]


class JobRunner:
    """Single-process asyncio job runner.

    ``submit`` enqueues a job and returns its ``job_id`` immediately.
    ``run_forever`` processes jobs from the internal queue until
    ``stop()`` is called.
    """

    def __init__(self, broker: JobEventBroker) -> None:
        self._broker = broker
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._stop = asyncio.Event()
        self._running_tasks: set[asyncio.Task] = set()

    # ── Public API ──────────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def submit(
        self,
        job_type: str,
        *,
        project_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Enqueue a new job and return its ``job_id``."""
        job_id = uuid.uuid4().hex
        job = Job(
            job_id=job_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            project_id=project_id,
            payload=payload or {},
            created_at=datetime.now(UTC),
        )
        self._jobs[job_id] = job
        self._queue.put_nowait(job)
        return job_id

    async def run_forever(self) -> None:
        """Consume jobs from the queue until ``stop()`` is called."""
        while not self._stop.is_set():
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=0.25)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            task = asyncio.create_task(self._run_one(job))
            self._running_tasks.add(task)
            task.add_done_callback(self._running_tasks.discard)

    async def stop(self) -> None:
        """Signal ``run_forever`` to exit at the next iteration boundary."""
        self._stop.set()

    async def update_progress(
        self,
        job_id: str,
        *,
        current: int,
        total: int,
        message: str = "",
    ) -> None:
        """Update progress counters and broadcast a progress event."""
        job = self._jobs.get(job_id)
        if job is None:
            return
        updated = job.model_copy(
            update={
                "progress_current": current,
                "progress_total": total,
                "message": message or job.message,
            }
        )
        self._jobs[job_id] = updated
        await self._emit(updated)

    # ── Internal ────────────────────────────────────────────────────────

    async def _emit(self, job: Job) -> None:
        terminal = {JobStatus.COMPLETE, JobStatus.ERROR, JobStatus.CANCELLED}
        ev_type = job.status.value if job.status in terminal else "progress"
        await self._broker.publish(
            job.job_id,
            {
                "type": ev_type,
                "status": job.status.value,
                "current": job.progress_current,
                "total": job.progress_total,
                "message": job.message,
                "error": job.error_message,
            },
        )
        if job.status in terminal:
            await self._broker.close(job.job_id)

    async def _run_one(self, job: Job) -> None:
        log.info("running job %s (%s)", job.job_id, job.job_type)
        running = job.model_copy(
            update={
                "status": JobStatus.RUNNING,
                "started_at": datetime.now(UTC),
            }
        )
        self._jobs[running.job_id] = running
        await self._emit(running)

        try:
            handler = _HANDLERS.get(job.job_type)
            if handler is None:
                raise NotImplementedError(f"no handler for job type {job.job_type!r}")
            await handler(self, running)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("job %s failed", job.job_id)
            failed = self._jobs[job.job_id].model_copy(
                update={
                    "status": JobStatus.ERROR,
                    "completed_at": datetime.now(UTC),
                    "error_message": str(exc),
                }
            )
            self._jobs[failed.job_id] = failed
            await self._emit(failed)
            return

        completed = self._jobs[job.job_id].model_copy(
            update={
                "status": JobStatus.COMPLETE,
                "completed_at": datetime.now(UTC),
            }
        )
        self._jobs[completed.job_id] = completed
        await self._emit(completed)


# ── Job handlers ─────────────────────────────────────────────────────


async def _handle_reload_ocr(runner: JobRunner, job: Job) -> None:
    """Stub reload-OCR handler. M3 will wire the real doctr pipeline."""
    await asyncio.sleep(0)


async def _handle_save_project(runner: JobRunner, job: Job) -> None:
    """Stub save-all handler. M3 will persist labeled envelopes to disk."""
    await asyncio.sleep(0)


_HANDLERS: dict[str, Handler] = {
    "reload_ocr": _handle_reload_ocr,
    "save_project": _handle_save_project,
}


__all__ = ["Job", "JobRunner", "JobStatus"]

"""In-process asyncio job runner.

Spec: ``docs/architecture/02-backend.md §11``. Simpler than pgdp-prep's
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
import json
import logging
import threading
import uuid
from collections.abc import Callable, Coroutine, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol

from pydantic import BaseModel, Field, JsonValue, TypeAdapter

from ..automation.events import AutomationBroker
from ..models import Job as PublicJob
from ..models import JobProgress as PublicJobProgress
from ..models import JobResult as PublicJobResult
from ..models import JobStatus as PublicJobStatus
from ..models import JobType as PublicJobType
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
    # Optional structured result payload merged into the terminal SSE event
    # (e.g. export stats breakdown). Empty for non-terminal / statless jobs.
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


_TERMINAL = {JobStatus.COMPLETE, JobStatus.ERROR, JobStatus.CANCELLED}


class RequestIdConflictError(ValueError):
    """A logical request key was already admitted with different inputs."""


Handler = Callable[["JobRunner", Job], Coroutine[Any, Any, None]]

# Keys individual handlers write into ``job.payload`` as OUTPUT (not the
# caller-submitted input echoed in that same dict) — the allowlist
# ``to_public_job`` uses to surface them through the public model's
# ``result`` field. ``tests/unit/core/jobs/test_job_type_contract.py``
# statically greps every handler module for ``job.payload["<key>"] = ``
# writes and fails if one is missing here, so a new output key can't
# silently go missing from the wire the way ``skipped_pages`` did
# (docs/issues/2026-07-21-jobs-api-openapi-mismatch.md, P1-JOBS-API).
_PAYLOAD_RESULT_KEYS: frozenset[str] = frozenset(
    {
        "failures",  # save_project
        "skipped_pages",  # save_project
        "skipped_indices",  # save_project
        "refined",  # refine_bboxes
        "run_id",  # propose_page_kinds
        "proposal_count",  # propose_page_kinds
    }
)


def payload_result_keys() -> frozenset[str]:
    """Return the ``job.payload`` output keys ``to_public_job`` surfaces.

    Public accessor mirroring ``registered_job_types()`` so tests can check
    the allowlist without reaching into the private ``_PAYLOAD_RESULT_KEYS``.
    """
    return _PAYLOAD_RESULT_KEYS


def _build_public_result(job: Job) -> PublicJobResult:
    """Merge ``job.payload``'s allowlisted output keys with ``job.result``
    into the typed public ``JobResult`` shape.

    Written key-by-key (not a loop over ``_PAYLOAD_RESULT_KEYS``) because
    ``JobResult`` is a ``TypedDict``: static key-by-key assignment lets
    basedpyright check every key/value type here with no ``cast`` or
    ``# type: ignore``, at the cost of listing each key twice (once in
    ``_PAYLOAD_RESULT_KEYS``/``JobResult``, once here) —
    ``tests/unit/core/jobs/test_job_type_contract.py`` proves
    ``_PAYLOAD_RESULT_KEYS`` and ``JobResult`` agree, and this function's
    own keys are exercised by the same test suite's ``result`` assertions.
    """
    result: PublicJobResult = {}
    if "failures" in job.payload:
        result["failures"] = job.payload["failures"]
    if "skipped_pages" in job.payload:
        result["skipped_pages"] = job.payload["skipped_pages"]
    if "skipped_indices" in job.payload:
        result["skipped_indices"] = job.payload["skipped_indices"]
    if "refined" in job.payload:
        result["refined"] = job.payload["refined"]
    if "run_id" in job.payload:
        result["run_id"] = job.payload["run_id"]
    if "proposal_count" in job.payload:
        result["proposal_count"] = job.payload["proposal_count"]
    if "words_exported_detection" in job.result:
        result["words_exported_detection"] = job.result["words_exported_detection"]
    if "words_exported_recognition" in job.result:
        result["words_exported_recognition"] = job.result["words_exported_recognition"]
    if "pages_skipped_not_validated" in job.result:
        result["pages_skipped_not_validated"] = job.result["pages_skipped_not_validated"]
    if "book_path" in job.result:
        result["book_path"] = job.result["book_path"]
    if "manifest_path" in job.result:
        result["manifest_path"] = job.result["manifest_path"]
    if "page_keys" in job.result:
        result["page_keys"] = job.result["page_keys"]
    if "alignment_summaries" in job.result:
        result["alignment_summaries"] = job.result["alignment_summaries"]
    if "warnings" in job.result:
        result["warnings"] = job.result["warnings"]
    if "source_error" in job.result:
        result["source_error"] = job.result["source_error"]
    if "result_id" in job.result:
        result["result_id"] = job.result["result_id"]
    if "generation" in job.result:
        result["generation"] = job.result["generation"]
    if "disposition" in job.result:
        result["disposition"] = job.result["disposition"]
    if "group_count" in job.result:
        result["group_count"] = job.result["group_count"]
    if "unresolved_count" in job.result:
        result["unresolved_count"] = job.result["unresolved_count"]
    return result


def to_public_job(job: Job) -> PublicJob:
    """Adapt an internal runner ``Job`` into the public wire ``Job`` model.

    Single source of truth for the runner → public field mapping, shared by
    both REST responses (``api/jobs.py``) and SSE frames (``_emit`` below) —
    see ``docs/issues/2026-07-21-jobs-api-openapi-mismatch.md`` (P1-JOBS-API).
    Field renames from the old ad hoc dump: ``job_id`` → ``id``, ``job_type``
    → ``type``, ``progress_current``/``progress_total``/``message`` → nested
    ``progress.current``/``progress.total``/``progress.message``,
    ``started_at``/``completed_at`` collapse into a single ``updated_at``.

    ``result`` unifies the runner's two ad hoc output channels into one
    public field: the allowlisted output keys handlers write into
    ``job.payload`` (``_PAYLOAD_RESULT_KEYS`` — e.g. ``save_project``'s
    ``skipped_pages``/``skipped_indices``), plus ``job.result`` (today only
    ``export``'s terminal stats, which ``JobRunner._emit`` also keeps
    merging flat at the SSE frame's top level for backward compatibility —
    both places now carry the same data). ``None`` when neither channel
    wrote anything.
    """
    result = _build_public_result(job)
    return PublicJob(
        id=job.job_id,
        type=PublicJobType(job.job_type),
        project_id=job.project_id,
        status=PublicJobStatus(job.status.value),
        progress=PublicJobProgress(
            current=job.progress_current,
            total=job.progress_total,
            message=job.message,
        ),
        error_message=job.error_message or None,
        created_at=job.created_at,
        updated_at=job.completed_at or job.started_at or job.created_at,
        result=result or None,
    )


class LabelingPageLease(Protocol):
    """The descriptor lease a queued job owns until reaching a terminal state."""

    @property
    def image_descriptor(self) -> int:
        """Return the open descriptor backing this immutable page image."""
        ...

    def close(self) -> None:
        """Release the caller-owned descriptor exactly once."""
        ...


# docs/architecture/02-backend.md: job types whose handlers
# call ``loader.run_ocr`` on an ``asyncio.to_thread`` worker — the only
# handlers gated by ``JobRunner``'s OCR concurrency semaphore. Verified
# against the handlers registered below: ``reload_ocr.py``, ``rotate.py``,
# ``auto_rotate_all.py``, and ``load_page.py`` each call ``loader.run_ocr``;
# ``save_project`` / ``export`` / ``refine_bboxes`` do not.
_OCR_HEAVY_JOB_TYPES = frozenset({"reload_ocr", "rotate_page", "auto_rotate_all", "load_page"})


class JobRunner:
    """Single-process asyncio job runner.

    ``submit`` enqueues a job and returns its ``job_id`` immediately.
    ``run_forever`` processes jobs from the internal queue until
    ``stop()`` is called.
    """

    def __init__(
        self,
        broker: JobEventBroker,
        *,
        context: dict[str, Any] | None = None,
        max_concurrent_ocr_jobs: int = 1,
    ) -> None:
        self._broker = broker
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._stop = asyncio.Event()
        self._running_tasks: set[asyncio.Task[None]] = set()
        # Optional context dict for handlers — e.g. ``{"settings": settings}``.
        # Populated by ``build_app`` so handlers can access app-level config
        # without a full DI graph (handlers run outside FastAPI request context).
        self.context: dict[str, Any] = context or {}
        self._labeling_page_leases: dict[str, LabelingPageLease] = {}
        self._automation: AutomationBroker | None = None
        self._admission_lock: threading.RLock = threading.RLock()
        self._admissions: dict[str, tuple[str, str]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        # Task 3: caps concurrent OCR-heavy jobs (see ``_OCR_HEAVY_JOB_TYPES``).
        # ``<= 0`` disables the cap — no semaphore, unbounded like every
        # other job type.
        self._ocr_semaphore: asyncio.Semaphore | None = (
            asyncio.Semaphore(max_concurrent_ocr_jobs) if max_concurrent_ocr_jobs > 0 else None
        )

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def set_automation_broker(self, broker: AutomationBroker) -> None:
        """Publish job assignments inside the snapshot's mutation boundary."""
        self._automation = broker
        self._admission_lock = broker.lock

    def _store_job(self, job: Job) -> None:
        broker = self._automation
        if broker is None:
            self._jobs[job.job_id] = job
            return
        with broker.lock:
            self._jobs[job.job_id] = job
            raw_index = job.payload.get("page_index")
            index = raw_index if isinstance(raw_index, int) else None
            _ = broker.publish("job_changed", project_id=job.project_id, page_index=index, job_id=job.job_id)

    def submit_idempotent(
        self,
        job_type: str,
        *,
        request_id: str,
        project_id: str | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> str:
        """Atomically admit one key/input pair, including terminal jobs."""
        if not request_id or len(request_id) > 200:
            raise ValueError("request_id must contain 1..200 characters")
        # Normalize and detach caller-owned mutable input before admission.
        detached = TypeAdapter[dict[str, JsonValue]](dict[str, JsonValue]).validate_python(payload or {})
        fingerprint = json.dumps([job_type, project_id, detached], sort_keys=True, separators=(",", ":"))
        with self._admission_lock:
            existing = self._admissions.get(request_id)
            if existing is not None:
                if existing[0] != fingerprint:
                    raise RequestIdConflictError("request_id was already used with different inputs")
                return existing[1]
            job_id = self.submit(job_type, project_id=project_id, payload=detached)
            self._admissions[request_id] = (fingerprint, job_id)
            return job_id

    def lookup_idempotent(
        self,
        job_type: str,
        *,
        request_id: str,
        project_id: str | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> str | None:
        """Look up one prior logical request before validating mutable state."""
        if not request_id or len(request_id) > 200:
            raise ValueError("request_id must contain 1..200 characters")
        detached = TypeAdapter[dict[str, JsonValue]](dict[str, JsonValue]).validate_python(payload or {})
        fingerprint = json.dumps([job_type, project_id, detached], sort_keys=True, separators=(",", ":"))
        with self._admission_lock:
            existing = self._admissions.get(request_id)
            if existing is None:
                return None
            if existing[0] != fingerprint:
                raise RequestIdConflictError("request_id was already used with different inputs")
            return existing[1]

    def submit(
        self,
        job_type: str,
        *,
        project_id: str | None = None,
        payload: dict[str, Any] | None = None,
        labeling_page_lease: LabelingPageLease | None = None,
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
        self._store_job(job)
        if labeling_page_lease is not None:
            self._labeling_page_leases[job_id] = labeling_page_lease
        try:
            calling_loop = asyncio.get_running_loop()
        except RuntimeError:
            calling_loop = None  # Sync routes enqueue onto the runner's loop below.
        if self._loop is None or self._loop is calling_loop:
            self._queue.put_nowait(job)
        else:
            _ = self._loop.call_soon_threadsafe(self._queue.put_nowait, job)
        return job_id

    def get_labeling_page_lease(self, job_id: str) -> LabelingPageLease | None:
        """Return the page lease owned by one queued/running job, if any."""
        return self._labeling_page_leases.get(job_id)

    def _close_labeling_page_lease(self, job_id: str) -> None:
        """Release an OCR job's descriptor after its handler reaches a terminal state."""
        lease = self._labeling_page_leases.pop(job_id, None)
        if lease is not None:
            lease.close()

    async def run_forever(self) -> None:
        """Consume jobs from the queue until ``stop()`` is called."""
        self._loop = asyncio.get_running_loop()
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
        """Cancel running jobs and drain queued jobs before the runner stops."""
        self._stop.set()
        while not self._queue.empty():
            queued = self._queue.get_nowait()
            current = self._jobs.get(queued.job_id)
            if current is None or current.status is not JobStatus.QUEUED:
                continue
            cancelled = current.model_copy(
                update={
                    "status": JobStatus.CANCELLED,
                    "completed_at": datetime.now(UTC),
                }
            )
            self._store_job(cancelled)
            self._close_labeling_page_lease(queued.job_id)
            await self._emit(cancelled)
        tasks = tuple(self._running_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def request_cancel(self, job_id: str) -> Job | None:
        """Cooperatively cancel a queued or running job.

        Sets the job's status to ``CANCELLED`` and emits a cancel event via
        the broker. Returns the updated ``Job`` (in CANCELLED state) whether
        or not a real state change occurred. Returns ``None`` if the job is
        not found.

        Spec §5.10 "Cooperative cancel; only valid for queued / running."
        For terminal jobs (already complete/error/cancelled) the method
        returns the existing job unchanged — idempotent on terminal states.

        The running task is NOT forcibly stopped — handlers must periodically
        check their cancellation token. Stub handlers (sleep(0)) complete
        before cancel arrives in practice; the cancel path is exercised via
        the ``queued`` state in tests.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status in _TERMINAL:
            return job  # already terminal — return as-is
        was_queued = job.status is JobStatus.QUEUED
        cancelled = job.model_copy(
            update={
                "status": JobStatus.CANCELLED,
                "completed_at": datetime.now(UTC),
            }
        )
        self._store_job(cancelled)
        if was_queued:
            self._close_labeling_page_lease(job_id)
        await self._emit(cancelled)
        return cancelled

    def is_cancelled(self, job_id: str) -> bool:
        """Return whether ``job_id`` has been cooperatively cancelled.

        The shared way for a handler to ask "has this been cancelled" —
        modeled on the inline ``runner._jobs[...].status == CANCELLED`` poll
        the export handler used before every other long-running handler grew
        its own copy of it. Call between units of work (a page, a batch) so
        the check happens without reaching into ``self._jobs`` directly. See
        ``docs/issues/2026-07-21-job-cancel-incomplete.md`` (P1-CANCEL).
        """
        job = self._jobs.get(job_id)
        return job is not None and job.status is JobStatus.CANCELLED

    async def update_progress(
        self,
        job_id: str,
        *,
        current: int,
        total: int,
        message: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        """Update progress counters and broadcast a progress event.

        ``result`` (optional) attaches a structured payload to the job that is
        merged into every subsequent emitted event — used by handlers (e.g.
        export) to surface stats on the terminal event.  Handlers should set
        ``result`` only on the terminal ``update_progress`` call (the one whose
        ``current == total``), not on intermediate progress updates.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return
        updated = job.model_copy(
            update={
                "progress_current": current,
                "progress_total": total,
                "message": message or job.message,
                "result": result if result is not None else job.result,
            }
        )
        self._store_job(updated)
        await self._emit(updated)

    async def _emit(self, job: Job) -> None:
        """Publish an SSE frame: the public ``Job`` model plus an ``event`` field.

        ``event`` names the SSE event kind (``progress`` while running,
        else the terminal status value). It is a distinct field from the
        job model's own ``type`` (job kind, e.g. ``"export"``) — the old
        flat shape used ``type`` for the event kind, which would collide
        with the public model's ``type`` field, hence the rename. See
        ``docs/issues/2026-07-21-job-sse-fe-be-shape-mismatch.md`` (P1-JOB-SSE).
        """
        ev_type = job.status.value if job.status in _TERMINAL else "progress"
        event: dict[str, object] = dict(to_public_job(job).model_dump(mode="json"))
        event["event"] = ev_type
        if job.result:
            event.update(job.result)
        await self._broker.publish(job.job_id, event)
        if job.status in _TERMINAL:
            await self._broker.close(job.job_id)

    async def _run_one(self, job: Job) -> None:
        current = self._jobs.get(job.job_id)
        if current is not None and current.status is JobStatus.CANCELLED:
            self._close_labeling_page_lease(job.job_id)
            return
        log.info("running job %s (%s)", job.job_id, job.job_type)
        running = job.model_copy(
            update={
                "status": JobStatus.RUNNING,
                "started_at": datetime.now(UTC),
            }
        )
        self._store_job(running)
        await self._emit(running)

        try:
            try:
                handler = _HANDLERS.get(job.job_type)
                if handler is None:
                    raise NotImplementedError(f"no handler for job type {job.job_type!r}")
                # Task 3: only OCR-heavy job types wait on the semaphore; every
                # other job type runs unbounded exactly as before.
                if self._ocr_semaphore is not None and job.job_type in _OCR_HEAVY_JOB_TYPES:
                    async with self._ocr_semaphore:
                        await handler(self, running)
                else:
                    await handler(self, running)
            except asyncio.CancelledError:
                current = self._jobs.get(job.job_id)
                if current is None or current.status is not JobStatus.CANCELLED:
                    cancelled = running.model_copy(
                        update={
                            "status": JobStatus.CANCELLED,
                            "completed_at": datetime.now(UTC),
                        }
                    )
                    self._store_job(cancelled)
                    await self._emit(cancelled)
                raise
            except Exception as exc:
                current = self._jobs.get(job.job_id)
                if current is not None and current.status is JobStatus.CANCELLED:
                    return
                log.exception("job %s failed", job.job_id)
                failed = self._jobs[job.job_id].model_copy(
                    update={
                        "status": JobStatus.ERROR,
                        "completed_at": datetime.now(UTC),
                        "error_message": str(exc),
                    }
                )
                self._store_job(failed)
                await self._emit(failed)
                return

            current = self._jobs.get(job.job_id)
            if current is not None and current.status is JobStatus.CANCELLED:
                return
            completed = self._jobs[job.job_id].model_copy(
                update={
                    "status": JobStatus.COMPLETE,
                    "completed_at": datetime.now(UTC),
                }
            )
            self._store_job(completed)
            await self._emit(completed)
        finally:
            self._close_labeling_page_lease(job.job_id)


async def _handle_reload_ocr(runner: JobRunner, job: Job) -> None:
    """Reload-OCR handler — delegates to ``core/jobs/handlers/reload_ocr``.

    Issue #307 (spec-23-B1): real OCR via ``LocalDoctrPageLoader.run_ocr``
    with four-stage progress reporting and ``ocr_failed`` notification
    on failure.
    """
    from .handlers.reload_ocr import handle_reload_ocr  # lazy import

    await handle_reload_ocr(runner, job)


async def _handle_save_project(runner: JobRunner, job: Job) -> None:
    """save_project handler — delegates to ``core/jobs/handlers/save_project``.

    Issue #308 (spec-23-B2): iterates dirty pages and persists each via
    ``persist_page_to_file``; records failures + emits per-page progress.
    """
    from .handlers.save_project import handle_save_project  # lazy import

    await handle_save_project(runner, job)


async def _handle_export(runner: JobRunner, job: Job) -> None:
    """Export handler — delegates to ``core/jobs/handlers/export.handle_export``.

    Issue #226: full DocTR export pipeline (WordFilter, output layout, cancel).
    """
    from .handlers.export import handle_export  # lazy to avoid circular

    await handle_export(runner, job)


async def _handle_rotate_page(runner: JobRunner, job: Job) -> None:
    """Rotate-page handler — delegates to ``core/jobs/handlers/rotate``.

    Issue #263: M9.1 manual rotate (202+job pattern).
    """
    from .handlers.rotate import handle_rotate_page  # lazy import

    await handle_rotate_page(runner, job)


async def _handle_auto_rotate_all(runner: JobRunner, job: Job) -> None:
    """Auto-rotate-all handler — delegates to ``core/jobs/handlers/auto_rotate_all``.

    Issue #264: M9.2 auto-rotate-all (202+job pattern).
    """
    from .handlers.auto_rotate_all import handle_auto_rotate_all  # lazy import

    await handle_auto_rotate_all(runner, job)


async def _handle_refine_bboxes(runner: JobRunner, job: Job) -> None:
    """Refine-bboxes handler — delegates to ``core/jobs/handlers/refine``.

    Lane A / Task A1: expand/refine word bounding boxes for the requested
    scope. The handler body is synchronous (no OCR engine call) so it is
    invoked directly (no ``asyncio.to_thread``).
    """
    from .handlers.refine import handle_refine_bboxes  # lazy import

    handle_refine_bboxes(runner, job)


async def _handle_propose_page_kinds(runner: JobRunner, job: Job) -> None:
    """propose_page_kinds handler — delegates to
    ``core/jobs/handlers/propose_page_kinds``.

    Classifies every page of the active project's book via pgdp-measure's
    book-scoped page-template classifier and records proposals durably.
    """
    from .handlers.propose_page_kinds import handle_propose_page_kinds  # lazy import

    await handle_propose_page_kinds(runner, job)


async def _handle_propose_regions(runner: JobRunner, job: Job) -> None:
    """propose_regions handler — delegates to ``core/jobs/handlers/propose_regions``.

    Book-scoped region proposal run. Never writes the page blob — see the handler's
    own docstring for the invariant it holds.
    """
    from .handlers.propose_regions import handle_propose_regions  # lazy import

    await handle_propose_regions(runner, job)


async def _handle_load_page(runner: JobRunner, job: Job) -> None:
    """Load-page handler — delegates to ``core/jobs/handlers/load_page``.

    docs/specs/2026-08-08-page-load-progress-design.md "Move page loading
    onto the job system": submitted by ``GET .../pages/{idx}`` only on a
    genuine store miss (in-memory state and the labeled store both empty),
    so the OCR-on-first-load cost reports named stages instead of blocking
    the request silently.
    """
    from .handlers.load_page import handle_load_page  # lazy import

    await handle_load_page(runner, job)


async def _handle_prepare_pgdp(runner: JobRunner, job: Job) -> None:
    from .handlers.prepare_pgdp import handle_prepare_pgdp

    await handle_prepare_pgdp(runner, job)


async def _handle_source_alignment(runner: JobRunner, job: Job) -> None:
    from .handlers.source_alignment import handle_source_alignment

    await handle_source_alignment(runner, job)


_HANDLERS: dict[str, Handler] = {
    "reload_ocr": _handle_reload_ocr,
    "save_project": _handle_save_project,
    "export": _handle_export,
    "rotate_page": _handle_rotate_page,
    "auto_rotate_all": _handle_auto_rotate_all,
    "refine_bboxes": _handle_refine_bboxes,
    "propose_page_kinds": _handle_propose_page_kinds,
    "propose_regions": _handle_propose_regions,
    "load_page": _handle_load_page,
    "prepare_pgdp": _handle_prepare_pgdp,
    "source_alignment": _handle_source_alignment,
}


def registered_job_types() -> frozenset[str]:
    """Return every ``job_type`` string a registered handler accepts.

    Public accessor so tests (and the public ``JobType`` enum) can be
    checked for agreement without reaching into the private ``_HANDLERS``
    dict — see ``docs/issues/2026-07-21-jobs-api-openapi-mismatch.md``
    (P1-JOBS-API), "Derive the job type list from the runner's registered
    handlers."
    """
    return frozenset(_HANDLERS)


def registered_handlers() -> Mapping[str, Handler]:
    """Return the ``job_type -> handler wrapper`` registry, read-only.

    Public accessor mirroring ``registered_job_types()``/
    ``payload_result_keys()`` so tests can statically resolve each
    handler's real implementation module (each wrapper does a lazy
    ``from .handlers.<name> import <fn>`` inside its body — see
    ``tests/unit/core/jobs/test_job_type_contract.py``) without reaching
    into the private ``_HANDLERS`` dict.
    """
    return MappingProxyType(_HANDLERS)


__all__ = [
    "Job",
    "JobRunner",
    "JobStatus",
    "payload_result_keys",
    "registered_handlers",
    "registered_job_types",
    "to_public_job",
]

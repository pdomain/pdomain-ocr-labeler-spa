"""Unit tests for OCR-heavy job concurrency cap.

Architecture: ``docs/architecture/02-backend.md``. ``JobRunner`` gates
concurrent execution of OCR-heavy job types (``reload_ocr`` / ``rotate_page`` /
``auto_rotate_all`` — the handlers that call ``loader.run_ocr``) behind an
``asyncio.Semaphore`` sized by ``max_concurrent_ocr_jobs``. Other job types
run unbounded.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from pdomain_ocr_labeler_spa.core.jobs import runner as runner_module
from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner, JobStatus


class _ConcurrencyTracker:
    """Records the peak number of simultaneous in-flight ``handler`` calls."""

    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    async def handler(self, runner: JobRunner, job: Job) -> None:
        self.current += 1
        self.peak = max(self.peak, self.current)
        await asyncio.sleep(0.05)
        self.current -= 1


class _ClosingLease:
    """Small descriptor-owner stand-in for the runner's terminal cleanup test."""

    def __init__(self) -> None:
        self.closed = False

    @property
    def image_descriptor(self) -> int:
        """The test handler only needs a stable descriptor-shaped value."""
        return 1

    def close(self) -> None:
        self.closed = True


class _LeaseTracker:
    """Confirms the queued job retains its independently owned page lease."""

    def __init__(self, lease: _ClosingLease) -> None:
        self._lease = lease
        self.observed_open_lease = False

    async def handler(self, runner: JobRunner, job: Job) -> None:
        self.observed_open_lease = runner.get_labeling_page_lease(job.job_id) is self._lease
        assert not self._lease.closed


def _make_job(job_type: str) -> Job:
    return Job(
        job_id=uuid4().hex,
        job_type=job_type,
        status=JobStatus.QUEUED,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_reload_ocr_jobs_capped_at_max_concurrent(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = _ConcurrencyTracker()
    monkeypatch.setitem(runner_module._HANDLERS, "reload_ocr", tracker.handler)

    job_runner = JobRunner(JobEventBroker(), max_concurrent_ocr_jobs=1)
    jobs = [_make_job("reload_ocr") for _ in range(3)]

    await asyncio.gather(*(job_runner._run_one(job) for job in jobs))

    assert tracker.peak == 1


@pytest.mark.asyncio
async def test_save_project_jobs_run_unbounded(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = _ConcurrencyTracker()
    monkeypatch.setitem(runner_module._HANDLERS, "save_project", tracker.handler)

    job_runner = JobRunner(JobEventBroker(), max_concurrent_ocr_jobs=1)
    jobs = [_make_job("save_project") for _ in range(3)]

    await asyncio.gather(*(job_runner._run_one(job) for job in jobs))

    assert tracker.peak == 3


@pytest.mark.asyncio
async def test_max_concurrent_ocr_jobs_disabled_when_non_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    """``<= 0`` disables the cap — reload_ocr jobs then run unbounded too."""
    tracker = _ConcurrencyTracker()
    monkeypatch.setitem(runner_module._HANDLERS, "reload_ocr", tracker.handler)

    job_runner = JobRunner(JobEventBroker(), max_concurrent_ocr_jobs=0)
    jobs = [_make_job("reload_ocr") for _ in range(3)]

    await asyncio.gather(*(job_runner._run_one(job) for job in jobs))

    assert tracker.peak == 3


@pytest.mark.asyncio
async def test_queued_ocr_job_keeps_its_page_lease_until_handler_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP cleanup cannot close the duplicate source descriptor owned by OCR."""
    lease = _ClosingLease()
    tracker = _LeaseTracker(lease)
    monkeypatch.setitem(runner_module._HANDLERS, "reload_ocr", tracker.handler)
    job_runner = JobRunner(JobEventBroker())

    job_id = job_runner.submit("reload_ocr", labeling_page_lease=lease)
    job = job_runner.get_job(job_id)
    assert job is not None

    await job_runner._run_one(job)

    assert tracker.observed_open_lease
    assert lease.closed
    assert job_runner.get_labeling_page_lease(job_id) is None

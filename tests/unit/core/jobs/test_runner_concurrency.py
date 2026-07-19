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

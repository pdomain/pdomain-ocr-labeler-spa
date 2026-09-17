"""Unit tests for ``JobRunner.is_cancelled`` — the shared cancel-check helper.

P1-CANCEL (``docs/issues/2026-07-21-job-cancel-incomplete.md``): every
long-running handler asks "has this been cancelled" through one shared
method instead of copying a ``runner._jobs[...].status`` poll into each
handler.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner, JobStatus


def _make_job(job_id: str, *, status: JobStatus = JobStatus.RUNNING) -> Job:
    return Job(
        job_id=job_id,
        job_type="export",
        status=status,
        created_at=datetime.now(UTC),
    )


def test_is_cancelled_false_for_running_job() -> None:
    runner = JobRunner(JobEventBroker())
    runner._jobs["j1"] = _make_job("j1", status=JobStatus.RUNNING)

    assert runner.is_cancelled("j1") is False


def test_is_cancelled_true_after_status_flips_to_cancelled() -> None:
    runner = JobRunner(JobEventBroker())
    runner._jobs["j1"] = _make_job("j1", status=JobStatus.RUNNING)

    assert runner.is_cancelled("j1") is False

    runner._jobs["j1"] = runner._jobs["j1"].model_copy(update={"status": JobStatus.CANCELLED})

    assert runner.is_cancelled("j1") is True


def test_is_cancelled_false_for_unknown_job_id() -> None:
    runner = JobRunner(JobEventBroker())

    assert runner.is_cancelled("does-not-exist") is False


def test_is_cancelled_false_for_other_terminal_statuses() -> None:
    runner = JobRunner(JobEventBroker())
    runner._jobs["j1"] = _make_job("j1", status=JobStatus.COMPLETE)
    runner._jobs["j2"] = _make_job("j2", status=JobStatus.ERROR)

    assert runner.is_cancelled("j1") is False
    assert runner.is_cancelled("j2") is False

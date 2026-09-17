"""Contract tests: the public ``Job``/``JobType``/``JobStatus`` models agree
with what the runner actually produces.

``docs/issues/2026-07-21-jobs-api-openapi-mismatch.md`` (P1-JOBS-API): the
public wire model and the runner's internal record drifted because nothing
proved they agreed. These tests are that proof — each one fails the moment
a handler is registered without a matching ``JobType`` member, a runner
status is added without a matching public ``JobStatus`` member, or
``to_public_job`` stops mapping every runner field.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pdomain_ocr_labeler_spa.core.jobs.runner import Job as RunnerJob
from pdomain_ocr_labeler_spa.core.jobs.runner import (
    JobStatus as RunnerJobStatus,
)
from pdomain_ocr_labeler_spa.core.jobs.runner import (
    registered_job_types,
    to_public_job,
)
from pdomain_ocr_labeler_spa.core.models import Job as PublicJob
from pdomain_ocr_labeler_spa.core.models import JobStatus as PublicJobStatus
from pdomain_ocr_labeler_spa.core.models import JobType as PublicJobType


def test_every_registered_handler_has_a_job_type_member() -> None:
    """Every ``job_type`` string a handler is registered under must be a
    ``JobType`` enum member — and vice versa, so the enum never lists a type
    the runner cannot actually run."""
    handler_types = registered_job_types()
    enum_values = {member.value for member in PublicJobType}
    assert handler_types == enum_values, (
        f"JobType enum vs. registered handlers disagree: "
        f"handlers only={handler_types - enum_values}, enum only={enum_values - handler_types}"
    )


def test_every_runner_status_has_a_public_status_member() -> None:
    """The public ``JobStatus`` must reach every status the runner can set."""
    runner_values = {member.value for member in RunnerJobStatus}
    public_values = {member.value for member in PublicJobStatus}
    assert runner_values == public_values, (
        f"JobStatus enums disagree: runner only={runner_values - public_values}, "
        f"public only={public_values - runner_values}"
    )


def _make_runner_job(
    *,
    job_id: str = "job-1",
    job_type: str = "export",
    status: RunnerJobStatus = RunnerJobStatus.RUNNING,
    project_id: str | None = "proj-1",
    progress_current: int = 3,
    progress_total: int = 10,
    message: str = "working",
    error_message: str = "",
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> RunnerJob:
    return RunnerJob(
        job_id=job_id,
        job_type=job_type,
        status=status,
        project_id=project_id,
        progress_current=progress_current,
        progress_total=progress_total,
        message=message,
        error_message=error_message,
        created_at=created_at or datetime.now(UTC),
        started_at=started_at,
        completed_at=completed_at,
    )


def test_to_public_job_maps_every_field() -> None:
    """``to_public_job`` renames runner fields onto the declared ``Job`` model."""
    runner_job = _make_runner_job()
    public_job = to_public_job(runner_job)

    assert isinstance(public_job, PublicJob)
    assert public_job.id == runner_job.job_id
    assert public_job.type.value == runner_job.job_type
    assert public_job.project_id == runner_job.project_id
    assert public_job.status.value == runner_job.status.value
    assert public_job.progress.current == runner_job.progress_current
    assert public_job.progress.total == runner_job.progress_total
    assert public_job.progress.message == runner_job.message
    assert public_job.created_at == runner_job.created_at


def test_to_public_job_maps_empty_error_message_to_none() -> None:
    """Runner ``error_message`` defaults to ``""``; the public model uses
    ``None`` for "no error" instead."""
    runner_job = _make_runner_job(error_message="")
    assert to_public_job(runner_job).error_message is None


def test_to_public_job_carries_a_real_error_message() -> None:
    runner_job = _make_runner_job(error_message="boom")
    assert to_public_job(runner_job).error_message == "boom"


def test_to_public_job_updated_at_prefers_completed_then_started_then_created() -> None:
    created = datetime(2026, 1, 1, tzinfo=UTC)
    started = datetime(2026, 1, 2, tzinfo=UTC)
    completed = datetime(2026, 1, 3, tzinfo=UTC)

    only_created = _make_runner_job(created_at=created)
    assert to_public_job(only_created).updated_at == created

    with_started = _make_runner_job(created_at=created, started_at=started)
    assert to_public_job(with_started).updated_at == started

    with_completed = _make_runner_job(created_at=created, started_at=started, completed_at=completed)
    assert to_public_job(with_completed).updated_at == completed


def test_to_public_job_rejects_an_unregistered_job_type() -> None:
    """An internal job whose ``job_type`` has no ``JobType`` member must
    raise loudly, never silently coerce to a wrong public type."""
    runner_job = _make_runner_job(job_type="not_a_real_job_type")
    with pytest.raises(ValueError, match="not_a_real_job_type"):
        to_public_job(runner_job)

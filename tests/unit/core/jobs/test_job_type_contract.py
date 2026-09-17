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

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pydantic
import pytest

from pdomain_ocr_labeler_spa.core.jobs import handlers as handlers_pkg
from pdomain_ocr_labeler_spa.core.jobs.runner import Job as RunnerJob
from pdomain_ocr_labeler_spa.core.jobs.runner import (
    JobStatus as RunnerJobStatus,
)
from pdomain_ocr_labeler_spa.core.jobs.runner import (
    payload_result_keys,
    registered_job_types,
    to_public_job,
)
from pdomain_ocr_labeler_spa.core.models import Job as PublicJob
from pdomain_ocr_labeler_spa.core.models import JobProgress as PublicJobProgress
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
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
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
        payload=payload or {},
        result=result or {},
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


# ── result field: handler-written payload/result data reaches the public model ──


@pytest.mark.parametrize("status", [RunnerJobStatus.COMPLETE, RunnerJobStatus.CANCELLED])
def test_to_public_job_carries_save_project_skipped_page_result(status: RunnerJobStatus) -> None:
    """A cancelled or completed ``save_project`` job's ``payload["skipped_pages"]``/
    ``payload["skipped_indices"]`` (written by ``handle_save_project``) must be
    reachable through the public model — ``PageActionsCompact`` reads exactly
    this to warn a person that pages were skipped
    (docs/issues/2026-07-21-jobs-api-openapi-mismatch.md, P1-JOBS-API)."""
    runner_job = _make_runner_job(
        job_type="save_project",
        status=status,
        payload={
            "failures": [{"page_index": 2, "error": "disk full"}],
            "skipped_pages": 1,
            "skipped_indices": [3],
        },
        completed_at=datetime.now(UTC),
    )

    public_job = to_public_job(runner_job)

    assert public_job.result is not None
    assert public_job.result.get("skipped_pages") == 1
    assert public_job.result.get("skipped_indices") == [3]
    assert public_job.result.get("failures") == [{"page_index": 2, "error": "disk full"}]


def test_to_public_job_result_is_none_when_nothing_was_written() -> None:
    runner_job = _make_runner_job(payload={}, result={})
    assert to_public_job(runner_job).result is None


def test_job_result_rejects_wrong_value_type_for_a_known_key() -> None:
    """``Job.result`` is a typed ``JobResult`` (a ``TypedDict``), not
    ``dict[str, Any]`` — pydantic validates known keys' value types.
    Under the old ``dict[str, Any] | None`` field type, an ``Any`` value
    was accepted for every key, so this would not have raised."""
    with pytest.raises(pydantic.ValidationError):
        PublicJob(
            id="job-1",
            type=PublicJobType.SAVE_PROJECT,
            project_id="proj-1",
            status=PublicJobStatus.COMPLETE,
            progress=PublicJobProgress(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            result={"skipped_pages": "not-an-int"},  # pyright: ignore[reportArgumentType]
        )


def test_to_public_job_merges_job_result_alongside_payload_output_keys() -> None:
    """The export terminal-stats channel (``job.result``, merged flat into the
    SSE frame today) and the ``job.payload`` output channel (``save_project``/
    ``refine_bboxes``/``propose_page_kinds``) both land in the same public
    ``result`` field — the two paths agree at the public-model boundary."""
    runner_job = _make_runner_job(
        job_type="export",
        payload={"skipped_pages": 0},
        result={"words_exported_detection": 5},
    )
    public_job = to_public_job(runner_job)
    assert public_job.result == {"skipped_pages": 0, "words_exported_detection": 5}


def test_payload_result_keys_cover_every_key_a_handler_writes() -> None:
    """Contract test: every ``job.payload["<key>"] = ...`` write in any
    handler module must be in ``payload_result_keys()`` — the allowlist
    ``to_public_job`` uses to surface ``job.payload`` output through the
    public model. A handler that starts writing a new output key without
    updating the allowlist fails this test instead of silently dropping
    the field off the wire, the way ``skipped_pages``/``skipped_indices``
    did (docs/issues/2026-07-21-jobs-api-openapi-mismatch.md, P1-JOBS-API).
    """
    handlers_dir = Path(handlers_pkg.__file__).parent
    pattern = re.compile(r'job\.payload\["([A-Za-z0-9_]+)"\]\s*=')

    written_keys: set[str] = set()
    for path in handlers_dir.glob("*.py"):
        written_keys |= set(pattern.findall(path.read_text(encoding="utf-8")))

    allowlist = payload_result_keys()
    missing = written_keys - allowlist
    assert not missing, (
        f"handler(s) write job.payload key(s) not in payload_result_keys(): {missing} "
        f"— add them to runner._PAYLOAD_RESULT_KEYS so to_public_job() surfaces them"
    )

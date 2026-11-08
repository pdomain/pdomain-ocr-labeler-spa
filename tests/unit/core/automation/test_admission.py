from __future__ import annotations

import asyncio

import pytest

from pdomain_ocr_labeler_spa.core.automation.events import AutomationBroker
from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import JobRunner, RequestIdConflictError


async def test_atomic_request_admission_and_conflict() -> None:
    runner = JobRunner(JobEventBroker())
    broker = AutomationBroker()
    runner.set_automation_broker(broker)

    def submit() -> str:
        return runner.submit_idempotent("prepare_pgdp", request_id="same", payload={"pages": ["1"]})

    results = await asyncio.gather(*(asyncio.to_thread(submit) for _ in range(20)))
    assert len(set(results)) == 1
    assert len(runner.list_jobs()) == 1
    assert broker.revision == 1
    with pytest.raises(RequestIdConflictError):
        _ = runner.submit_idempotent("prepare_pgdp", request_id="same", payload={"pages": ["2"]})
    _ = await runner.request_cancel(results[0])
    assert submit() == results[0]
    assert runner.submit_idempotent("prepare_pgdp", request_id="new", payload={"pages": ["1"]}) != results[0]


def test_lookup_before_mutable_generation_validation() -> None:
    runner = JobRunner(JobEventBroker())
    payload = {"expected_generation": 2}
    assert runner.lookup_idempotent("source_alignment", request_id="r", payload=payload) is None
    job_id = runner.submit_idempotent("source_alignment", request_id="r", payload=payload)
    assert runner.lookup_idempotent("source_alignment", request_id="r", payload=payload) == job_id
    with pytest.raises(RequestIdConflictError):
        _ = runner.lookup_idempotent("source_alignment", request_id="r", payload={"expected_generation": 3})

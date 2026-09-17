"""Cancel tests for the ``save_project`` job handler — P1-CANCEL.

``docs/issues/2026-07-21-job-cancel-incomplete.md`` names every handler that
loops over pages without noticing a cooperative cancel. These tests assert a
cancel requested partway through the dirty-page loop leaves the remaining
pages untouched (still dirty, ready for a later save), the job ends
CANCELLED, and the final message says how much was saved — mirroring how
``tests/unit/core/test_export_handler.py``'s cancel test flips job status
via a mock side effect mid-loop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.handlers.save_project import handle_save_project
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner, JobStatus
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.notifications import NotificationQueue
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState


def _dirty_project_state(tmp_path: Path, *, page_count: int) -> ProjectState:
    """A project with ``page_count`` pages, every one dirty (unsaved)."""
    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=[tmp_path / f"{i:03d}.png" for i in range(page_count)],
        ground_truth_map={},
        total_pages=page_count,
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)
    for page_index in range(page_count):
        outcome = PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=object())
        pstate = PageState(page_index=page_index, page_record=outcome)
        pstate.generation = 1
        pstate.last_saved_generation = 0
        project_state._page_states[page_index] = pstate
    return project_state


def _runner_and_job(project_state: ProjectState) -> tuple[JobRunner, Job]:
    # No page_store wired — handle_save_project takes its "in-memory only
    # session" clean-success branch, which needs no event-store fixture.
    runner = JobRunner(
        JobEventBroker(),
        context={
            "project_state": project_state,
            "notification_queue": NotificationQueue(),
            "settings": object(),
        },
    )
    job = Job(
        job_id="j1",
        job_type="save_project",
        status=JobStatus.RUNNING,
        project_id="book1",
        payload={},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    return runner, job


@pytest.mark.asyncio
async def test_cancel_partway_leaves_remaining_pages_dirty(tmp_path: Path) -> None:
    """A cancel noticed after the first page's save leaves pages 1 and 2 dirty."""
    project_state = _dirty_project_state(tmp_path, page_count=3)
    runner, job = _runner_and_job(project_state)

    # The handler's own progress calls are the only per-page hook available;
    # flip the job to CANCELLED right after the first page reports progress
    # (its own save already completed), so the loop's next-iteration check
    # sees it before page 1 starts.
    original_update_progress = runner.update_progress
    calls = 0

    async def _update_progress_then_maybe_cancel(
        job_id: str,
        *,
        current: int,
        total: int,
        message: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        nonlocal calls
        calls += 1
        await original_update_progress(job_id, current=current, total=total, message=message, result=result)
        if calls == 2:  # 1 = pre-loop "Saving N page(s)"; 2 = page 0's own report.
            current_job = runner._jobs["j1"]
            runner._jobs["j1"] = current_job.model_copy(update={"status": JobStatus.CANCELLED})

    runner.update_progress = _update_progress_then_maybe_cancel

    await handle_save_project(runner, job)

    # Page 0 was saved (clean, no store wired); pages 1 and 2 are untouched.
    assert project_state.page_states[0].last_saved_generation == 1
    assert project_state.page_states[1].last_saved_generation == 0
    assert project_state.page_states[2].last_saved_generation == 0

    final_job = runner.get_job("j1")
    assert final_job is not None
    assert final_job.status is JobStatus.CANCELLED
    assert "cancelled" in final_job.message.lower()
    assert "1 of 3" in final_job.message


@pytest.mark.asyncio
async def test_cancel_before_the_first_page_saves_nothing(tmp_path: Path) -> None:
    """A cancel requested before the job starts running leaves every page dirty."""
    project_state = _dirty_project_state(tmp_path, page_count=2)
    runner, job = _runner_and_job(project_state)

    runner._jobs["j1"] = job.model_copy(update={"status": JobStatus.CANCELLED})

    await handle_save_project(runner, job)

    assert project_state.page_states[0].last_saved_generation == 0
    assert project_state.page_states[1].last_saved_generation == 0

    final_job = runner.get_job("j1")
    assert final_job is not None
    assert final_job.status is JobStatus.CANCELLED
    assert "0 of 2" in final_job.message

"""Cancel tests for the ``auto_rotate_all`` job handler — P1-CANCEL.

``docs/issues/2026-07-21-job-cancel-incomplete.md`` names ``handle_auto_
rotate_all`` as the handler that never noticed a cooperative cancel: Cancel
reported the job as cancelled while the page loop kept detecting and
rotating to the end. These tests assert a cancel requested partway through
the page loop stops the loop before any further page is touched, leaves the
job CANCELLED, and reports a final message naming how much work was done —
mirroring how ``tests/unit/core/test_export_handler.py``'s cancel test
flips job status via a mock side effect mid-loop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.handlers.auto_rotate_all import handle_auto_rotate_all
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner, JobStatus
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.notifications import NotificationQueue
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
from pdomain_ocr_labeler_spa.settings import Settings


def _make_png(h: int, w: int) -> bytes:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


class _UnusedPageLoader:
    """``PageLoader`` stand-in — ``run_ocr`` must never be called.

    ``handle_auto_rotate_all`` resolves a page loader unconditionally before
    its page loop, even when every page in this test stays upright (chosen
    == 0) and no page ever reaches the rotate/re-OCR branch.
    """

    def run_ocr(self, page_index: int, **kwargs: Any) -> Any:
        raise AssertionError("run_ocr must not be called — every page in this test is upright")


def _runner_and_job(tmp_path: Path, *, page_count: int) -> tuple[JobRunner, Job, list[Path]]:
    image_paths = [tmp_path / f"{i:03d}.png" for i in range(page_count)]
    for path in image_paths:
        path.write_bytes(_make_png(100, 200))

    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=page_count,
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    settings = Settings(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        config_root=tmp_path / "config",
    )

    runner = JobRunner(
        JobEventBroker(),
        context={
            "project_state": project_state,
            "notification_queue": NotificationQueue(),
            "settings": settings,
            # Bypasses _build_ocr_fn's production wiring requirement — the
            # stub detect_fn below never calls it.
            "auto_rotate_ocr_fn": lambda image: None,
            "page_loader": _UnusedPageLoader(),
        },
    )
    job = Job(
        job_id="j1",
        job_type="auto_rotate_all",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id, "page_count": page_count},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    return runner, job, image_paths


@pytest.mark.asyncio
async def test_cancel_partway_stops_before_the_next_page(tmp_path: Path) -> None:
    """A cancel noticed after page 0's detect call leaves pages 1 and 2 untouched."""
    runner, job, image_paths = _runner_and_job(tmp_path, page_count=3)
    original_bytes = [p.read_bytes() for p in image_paths]

    detect_calls: list[int] = []

    def fake_detect(image: Any, *, ocr_fn: Any, confidence_threshold: float = 0.6, **kw: Any) -> Any:
        detect_calls.append(len(detect_calls))
        if len(detect_calls) == 1:
            # Simulate a cancel request landing while page 0 is in flight.
            current = runner._jobs["j1"]
            runner._jobs["j1"] = current.model_copy(update={"status": JobStatus.CANCELLED})
        # Always upright — no rotation machinery needed for this test.
        doc = MagicMock()
        doc.pages = [MagicMock()]
        return 0, doc, []

    runner.context["auto_rotate_detect_fn"] = fake_detect

    await handle_auto_rotate_all(runner, job)

    # Only page 0's detect call happened — the loop stopped at the top of
    # the next iteration once it noticed the cancel.
    assert len(detect_calls) == 1

    # No page image was touched (chosen == 0 for the one page processed, and
    # no further page was even loaded).
    for path, original in zip(image_paths, original_bytes, strict=True):
        assert path.read_bytes() == original

    final_job = runner.get_job("j1")
    assert final_job is not None
    assert final_job.status is JobStatus.CANCELLED
    assert "cancelled" in final_job.message.lower()
    assert "1 of 3" in final_job.message


@pytest.mark.asyncio
async def test_cancel_before_the_first_page_processes_nothing(tmp_path: Path) -> None:
    """A cancel requested before the job starts running leaves every page untouched."""
    runner, job, image_paths = _runner_and_job(tmp_path, page_count=2)
    original_bytes = [p.read_bytes() for p in image_paths]

    runner._jobs["j1"] = job.model_copy(update={"status": JobStatus.CANCELLED})

    detect_calls: list[int] = []

    def fake_detect(image: Any, *, ocr_fn: Any, confidence_threshold: float = 0.6, **kw: Any) -> Any:
        detect_calls.append(len(detect_calls))
        doc = MagicMock()
        doc.pages = [MagicMock()]
        return 0, doc, []

    runner.context["auto_rotate_detect_fn"] = fake_detect

    await handle_auto_rotate_all(runner, job)

    assert detect_calls == []
    for path, original in zip(image_paths, original_bytes, strict=True):
        assert path.read_bytes() == original

    final_job = runner.get_job("j1")
    assert final_job is not None
    assert final_job.status is JobStatus.CANCELLED
    assert "0 of 2" in final_job.message

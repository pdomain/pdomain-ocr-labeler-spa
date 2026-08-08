"""Wave 0.4: save must not clear dirty bit without a content blob (P0-SAVE-DIRTY)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pdomain_book_tools.ocr.page import Page
from pdomain_ops.page_aggregate import PageAggregate
from pdomain_ops.pages import PageRecord

from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner, JobStatus
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.notifications import NotificationQueue
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState


def _bbox(x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {
        "top_left": {"x": x0, "y": y0},
        "bottom_right": {"x": x1, "y": y1},
        "is_normalized": False,
    }


def _make_page() -> Page:
    return Page.from_dict(
        {
            "width": 100,
            "height": 100,
            "page_index": 0,
            "bounding_box": _bbox(0, 0, 100, 100),
            "items": [
                {
                    "type": "Block",
                    "child_type": "BLOCKS",
                    "block_category": "PARAGRAPH",
                    "items": [
                        {
                            "type": "Block",
                            "child_type": "WORDS",
                            "block_category": "LINE",
                            "items": [
                                {
                                    "type": "Word",
                                    "text": "hi",
                                    "ground_truth_text": "hi",
                                    "bounding_box": _bbox(0, 0, 10, 10),
                                    "word_labels": [],
                                }
                            ],
                            "bounding_box": _bbox(0, 0, 100, 20),
                        }
                    ],
                    "bounding_box": _bbox(0, 0, 100, 40),
                }
            ],
        }
    )


def _make_fake_project(project_dir: Path) -> Project:
    return Project(
        project_id="book1",
        project_root=project_dir,
        image_paths=[project_dir / "001.png"],
        ground_truth_map={},
        total_pages=1,
    )


async def _run_save_project(runner: JobRunner, job: Job) -> None:
    from pdomain_ocr_labeler_spa.core.jobs.handlers.save_project import handle_save_project

    await handle_save_project(runner, job)


def _make_job() -> Job:
    return Job(
        job_id=uuid4().hex,
        job_type="save_project",
        status=JobStatus.QUEUED,
        created_at=datetime.now(UTC),
    )


@pytest.mark.integration
def test_save_project_does_not_clean_when_page_id_missing(tmp_path: Path) -> None:
    """Missing page_id: track skip and leave generation dirty."""
    project_dir = tmp_path / "book1"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")

    store = LabelerPageStore(project_dir=project_dir)
    try:
        project_state = ProjectState()
        project_state.set_loaded_project(_make_fake_project(project_dir))
        page = _make_page()
        pstate = PageState(
            page_index=0,
            page_record=PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page),
        )
        pstate.page_id = None
        pstate.generation = 3
        pstate.last_saved_generation = 0
        project_state._page_states[0] = pstate

        runner = JobRunner(
            JobEventBroker(),
            context={
                "project_state": project_state,
                "notification_queue": NotificationQueue(),
                "settings": object(),
                "page_store": store,
            },
        )
        job = _make_job()
        runner._jobs[job.job_id] = job
        asyncio.run(_run_save_project(runner, job))

        assert pstate.last_saved_generation == 0, (
            "page_id unset must not advance last_saved_generation (false clean)"
        )
        assert job.payload.get("skipped_pages") == 1
    finally:
        store.close()


@pytest.mark.integration
def test_save_project_does_not_clean_on_changelog_only(tmp_path: Path) -> None:
    """Changelog-only fallback (no serializable payload) must leave dirty bit set."""
    project_dir = tmp_path / "book1"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")

    store = LabelerPageStore(project_dir=project_dir)
    try:
        page_id = uuid4()
        store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))

        project_state = ProjectState()
        project_state.set_loaded_project(_make_fake_project(project_dir))
        # Payload without to_dict → changelog-only path.
        pstate = PageState(
            page_index=0,
            page_record=PageLoadOutcome(
                page_index=0,
                source=PageSource.OCR,
                payload=object(),  # no to_dict
            ),
        )
        pstate.page_id = page_id
        pstate.generation = 5
        pstate.last_saved_generation = 0
        project_state._page_states[0] = pstate

        runner = JobRunner(
            JobEventBroker(),
            context={
                "project_state": project_state,
                "notification_queue": NotificationQueue(),
                "settings": object(),
                "page_store": store,
            },
        )
        job = _make_job()
        runner._jobs[job.job_id] = job
        asyncio.run(_run_save_project(runner, job))

        assert pstate.last_saved_generation == 0, (
            "changelog-only write must not advance last_saved_generation"
        )
        assert pstate.generation == 5
    finally:
        store.close()


@pytest.mark.integration
def test_save_project_cleans_after_content_blob(tmp_path: Path) -> None:
    """Successful content blob write still advances last_saved_generation."""
    project_dir = tmp_path / "book1"
    project_dir.mkdir()
    (project_dir / "001.png").write_bytes(b"\x00")

    store = LabelerPageStore(project_dir=project_dir)
    try:
        page_id = uuid4()
        store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))
        page = _make_page()
        project_state = ProjectState()
        project_state.set_loaded_project(_make_fake_project(project_dir))
        pstate = PageState(
            page_index=0,
            page_record=PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page),
        )
        pstate.page_id = page_id
        pstate.generation = 2
        pstate.last_saved_generation = 0
        project_state._page_states[0] = pstate

        runner = JobRunner(
            JobEventBroker(),
            context={
                "project_state": project_state,
                "notification_queue": NotificationQueue(),
                "settings": object(),
                "page_store": store,
            },
        )
        job = _make_job()
        runner._jobs[job.job_id] = job
        asyncio.run(_run_save_project(runner, job))

        assert pstate.last_saved_generation == 2
    finally:
        store.close()

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from pdomain_ocr_labeler_spa.core.automation.service import AutomationService
from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import JobRunner
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState


async def test_snapshot_cannot_observe_commit_without_revision() -> None:
    project = Project(
        project_id="p",
        project_root=Path("/tmp/book"),
        image_paths=[Path("/tmp/page.png")],
        total_pages=1,
        ground_truth_map={},
    )
    state = ProjectState()
    state.set_loaded_project(project)
    page = PageState(page_index=0)
    state.set_page_state(0, page)
    service = AutomationService(project_state=state, runner=JobRunner(JobEventBroker()))
    written = threading.Event()
    release = threading.Event()

    def mutate() -> None:
        with service.broker.transaction("page_changed", project_id="p", page_index=0):
            page.generation = 1
            written.set()
            assert release.wait(timeout=2)

    mutation = asyncio.create_task(asyncio.to_thread(mutate))
    assert await asyncio.to_thread(written.wait, 2)
    snapshot = asyncio.create_task(asyncio.to_thread(service.snapshot))
    await asyncio.sleep(0.01)
    assert not snapshot.done()
    release.set()
    await mutation
    result = await snapshot
    assert result.revision == 1
    assert result.pages[0].generation == 1
    assert not result.pages[0].ready  # Snapshot never starts OCR.


async def test_snapshot_to_subscribe_change_is_replayed_and_connection_is_live() -> None:
    service = AutomationService(project_state=ProjectState(), runner=JobRunner(JobEventBroker()))
    viewer = service.viewers.register()
    snapshot = service.snapshot()
    _ = service.broker.publish("project_changed")
    sub = service.broker.subscribe(after=snapshot.revision, viewer_id=viewer.viewer_id)
    assert service.viewers.get(viewer.viewer_id).connected
    assert (await sub.receive()).revision == 1
    sub.close()
    assert not service.viewers.get(viewer.viewer_id).connected

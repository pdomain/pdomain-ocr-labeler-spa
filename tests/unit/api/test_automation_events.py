from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse

from pdomain_ocr_labeler_spa.api.automation import events
from pdomain_ocr_labeler_spa.core.automation.service import AutomationService
from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import JobRunner
from pdomain_ocr_labeler_spa.core.project_state import ProjectState


async def test_last_event_id_overrides_query_cursor() -> None:
    service = AutomationService(project_state=ProjectState(), runner=JobRunner(JobEventBroker()))
    _ = service.broker.publish("page_changed", generation=1)
    _ = service.broker.publish("page_changed", generation=2)
    response = events(after=0, last_event_id="1", service=service)
    assert isinstance(response, StreamingResponse)
    stream = response.body_iterator
    assert isinstance(stream, AsyncGenerator)
    try:
        frame = await stream.__anext__()
        assert isinstance(frame, str)
        assert frame.startswith("id: 2\nevent: page_changed\n")
    finally:
        await stream.aclose()


async def test_invalid_header_cursor_resets_and_unknown_viewer_fails() -> None:
    service = AutomationService(project_state=ProjectState(), runner=JobRunner(JobEventBroker()))
    response = events(after=0, last_event_id="invalid", service=service)
    assert isinstance(response, StreamingResponse)
    stream = response.body_iterator
    assert isinstance(stream, AsyncGenerator)
    try:
        frame = await stream.__anext__()
        assert isinstance(frame, str) and "event: reset\n" in frame
    finally:
        await stream.aclose()
    assert events(viewer_id="unknown", service=service).status_code == 404

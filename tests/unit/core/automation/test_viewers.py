from __future__ import annotations

import pytest

from pdomain_ocr_labeler_spa.core.automation.events import AutomationBroker
from pdomain_ocr_labeler_spa.core.automation.viewers import (
    ReadyView,
    ViewerAck,
    ViewerCommandRequest,
    ViewerConflictError,
    ViewerRegistry,
    ViewerSelection,
)


def test_ack_exact_current_generation_supersession_and_tab() -> None:
    current = ReadyView(project_id="p", page_index=0, generation=2, word_ids={"w"})
    registry = ViewerRegistry(AutomationBroker(), lambda _project, _page: current)
    first = registry.register()
    second = registry.register()
    command = ViewerCommandRequest(
        viewer_id=first.viewer_id, project_id="p", page_index=0, selection=ViewerSelection(word_ids=["w"])
    )
    desired = registry.command(command).desired
    assert desired is not None
    wrong = ViewerAck.model_validate({**desired.model_dump(), "generation": 1})
    with pytest.raises(ViewerConflictError):
        _ = registry.ack(wrong)
    assert registry.get(first.viewer_id).pending
    observation = registry.get(first.viewer_id).last_observation
    assert observation is not None and observation.status == "failed"
    with pytest.raises(ViewerConflictError):
        _ = registry.ack(wrong.model_copy(update={"viewer_id": second.viewer_id, "generation": 2}))
    _ = registry.ack(wrong.model_copy(update={"generation": 2}))
    assert not registry.get(first.viewer_id).pending
    _ = registry.command(command)
    with pytest.raises(ViewerConflictError):
        _ = registry.ack(wrong.model_copy(update={"generation": 2}))


def test_unloaded_project_and_unknown_group_rejected() -> None:
    def ready(project: str, page: int) -> ReadyView | None:
        return ReadyView(project_id="p", page_index=page, generation=0) if project == "p" else None

    registry = ViewerRegistry(AutomationBroker(), ready)
    viewer = registry.register()
    with pytest.raises(ViewerConflictError):
        _ = registry.command(
            ViewerCommandRequest(viewer_id=viewer.viewer_id, project_id="unloaded", page_index=0)
        )
    with pytest.raises(ViewerConflictError):
        _ = registry.command(
            ViewerCommandRequest(
                viewer_id=viewer.viewer_id,
                project_id="p",
                page_index=0,
                selection=ViewerSelection(alignment_group_id="fake", alignment_id="fake"),
            )
        )

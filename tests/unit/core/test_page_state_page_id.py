"""PageState must have a page_id slot for event-store keying."""

from uuid import uuid4

from pdomain_ocr_labeler_spa.core.project_state import PageState


def test_page_state_has_page_id_slot() -> None:
    pstate = PageState(page_index=0)
    assert pstate.page_id is None


def test_page_state_page_id_settable() -> None:
    pstate = PageState(page_index=0)
    uid = uuid4()
    pstate.page_id = uid
    assert pstate.page_id == uid

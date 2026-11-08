"""Resolve viewer acknowledgements against the current domain payload."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import JsonValue

from pdomain_ocr_labeler_spa.adapters.ocr.tesseract import tesseract_capability
from pdomain_ocr_labeler_spa.adapters.source_data import SourceDataBridge, SourceDataError
from pdomain_ocr_labeler_spa.core.automation.viewers import ReadyView

from .pages import _page_payload

if TYPE_CHECKING:
    from collections.abc import Callable

    from pdomain_ocr_labeler_spa.core.persistence.config_yaml import AppConfig
    from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
    from pdomain_ocr_labeler_spa.core.project_state import ProjectState
    from pdomain_ocr_labeler_spa.settings import Settings


def runtime_capabilities(*, settings: Settings, source_data: SourceDataBridge) -> dict[str, JsonValue]:
    capability = tesseract_capability(binary=settings.tesseract_binary, language=settings.tesseract_language)
    source_error: JsonValue = None
    try:
        source_data.require_configured()
    except SourceDataError as exc:
        source_error = {"error": exc.code, "message": str(exc), "details": exc.details}
    return {
        "ocr": [
            {"engine": "local_doctr", "requires_model_weights": True},
            {
                "engine": "tesseract",
                "available": capability.available,
                "languages": list(capability.languages),
                "error": None
                if capability.available
                else {"error": "ocr_engine_unavailable", "message": capability.message, "details": None},
            },
        ],
        "pgdp": {"configured": source_error is None, "error": source_error},
    }


def ready_view_resolver(
    *,
    project_state: ProjectState,
    settings: Settings,
    app_config: AppConfig,
    page_store: Callable[[], LabelerPageStore | None],
) -> Callable[[str, int], ReadyView | None]:
    def resolve(project_id: str, page_index: int) -> ReadyView | None:
        project = project_state.loaded_project
        if project is None or project.project_id != project_id or not 0 <= page_index < project.total_pages:
            return None
        with project_state.get_page_lock(page_index):
            state = project_state.get_page_state(page_index)
            ready = ReadyView(
                project_id=project_id,
                page_index=page_index,
                generation=state.generation if state is not None else 0,
                ready=state is not None and state.page_record is not None,
            )
            if not ready.ready:
                return ready
            lease = project_state.open_labeling_page(page_index)
            try:
                with project_state.bind_labeling_page(page_index, lease):
                    payload = _page_payload(
                        project_id=project_id,
                        page_index=page_index,
                        project_state=project_state,
                        settings=settings,
                        app_config=app_config,
                        page_store=page_store(),
                    )
            finally:
                if lease is not None:
                    lease.close()
            ready.word_ids = {
                word.word_id
                for line in payload.line_matches
                for word in line.word_matches
                if word.word_id is not None
            }
            ready.region_ids = {
                region.region_id for region in payload.regions if region.region_id is not None
            }
            ready.proposal_ids = {proposal.proposal_id for proposal in payload.proposals}
            if state is not None and state.source_alignment is not None:
                from pdomain_ocr_labeler_spa.core.source_alignment import ocr_signature

                outcome = state.page_record
                if outcome is not None:
                    from pdomain_book_tools.ocr.page import Page

                    if isinstance(outcome.payload, Page):
                        alignment = state.source_alignment
                        if alignment.ocr_signature == ocr_signature(outcome.payload):
                            ready.alignment_id = alignment.result_id
                            ready.alignment_group_ids = {group.group_id for group in alignment.groups}
            return ready

    return resolve

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import TYPE_CHECKING, Literal

from ...core.automation.service import AutomationService
from ...core.ocr.predictor import PredictorCache
from ...core.ocr_config_state import OCRConfigCarrier
from ...core.project_state import ProjectState
from .local_doctr import LocalDoctrPageLoader
from .tesseract import OCRCancelledError, TesseractPageLoader

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from contextlib import AbstractContextManager
    from pathlib import Path

    from ...core.models import Project
    from ...core.page_state import PageLoader
    from ...core.persistence.page_store import LabelerPageStore
    from ...settings import Settings

OCREngineChoice = Literal["local_doctr", "tesseract"]


@contextmanager
def page_loader_commit_guard(
    *,
    project: Project,
    context: Mapping[str, object],
    store: LabelerPageStore | None,
    cancelled: Callable[[], bool] | None,
) -> Iterator[None]:
    """Pin project identity while committing, after all expensive OCR work finishes."""
    service = context.get("automation")
    broker = service.broker if isinstance(service, AutomationService) else None
    state = context.get("project_state")
    with (
        broker.transaction() if broker is not None else nullcontext(),
        state.mutation_lock if isinstance(state, ProjectState) else nullcontext(),
    ):
        if isinstance(state, ProjectState) and state.loaded_project is not project:
            raise RuntimeError("OCR project changed before durable commit")
        if store is not None and "page_store" in context and context["page_store"] is not store:
            raise RuntimeError("OCR project store changed before durable commit")
        if cancelled is not None and cancelled():
            raise OCRCancelledError("Tesseract OCR cancelled before durable commit")
        yield


def build_page_loader(
    *,
    project: Project,
    settings: Settings,
    context: Mapping[str, object],
    store: LabelerPageStore | None,
    image_path_resolver: Callable[[int], Path] | None = None,
    engine: OCREngineChoice | None = None,
    cancelled: Callable[[], bool] | None = None,
    commit_guard: Callable[[], AbstractContextManager[None]] | None = None,
) -> PageLoader:
    """Choose an explicit live OCR provider without loading unrelated model weights."""
    selected_engine = engine if engine is not None else settings.ocr_engine
    if selected_engine == "tesseract":
        return TesseractPageLoader(
            project=project,
            binary=settings.tesseract_binary,
            language=settings.tesseract_language,
            timeout_s=settings.ocr_timeout_s,
            store=store,
            image_path_resolver=image_path_resolver,
            cancelled=cancelled,
            commit_guard=commit_guard
            or (
                lambda: page_loader_commit_guard(
                    project=project,
                    context=context,
                    store=store,
                    cancelled=cancelled,
                )
            ),
        )
    if selected_engine != "local_doctr":
        raise ValueError(f"OCR PageLoader engine unavailable: {selected_engine}")
    predictor_cache = context.get("predictor_cache")
    carrier = context.get("ocr_config_carrier")
    if not isinstance(predictor_cache, PredictorCache) or not isinstance(carrier, OCRConfigCarrier):
        raise RuntimeError("DocTR page loader requires predictor_cache and ocr_config_carrier")
    detection_key, recognition_key, hf_revision = carrier.snapshot()
    return LocalDoctrPageLoader(
        project=project,
        predictor_cache=predictor_cache,
        detection_key=detection_key,
        recognition_key=recognition_key,
        hf_revision=hf_revision,
        data_root=settings.data_root,
        cache_root=settings.cache_root,
        store=store,
        image_path_resolver=image_path_resolver,
    )

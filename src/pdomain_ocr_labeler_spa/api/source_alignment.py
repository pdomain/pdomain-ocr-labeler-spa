"""Inspect and review composed source/OCR groups without changing human text."""

from __future__ import annotations

from typing import Annotated, ClassVar

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pdomain_book_tools.ocr.page import Page
from pydantic import BaseModel, ConfigDict, Field

from ..core.jobs.runner import JobRunner, RequestIdConflictError
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..core.source_alignment import (
    ReviewDecision,
    SourceAlignmentResponse,
    load_source_evidence,
    ocr_signature,
    persist_alignment,
)
from ..core.source_text import SourceTextPreview, source_text_preview_for_page
from .dependencies import bind_page_labeling_lease, get_job_runner, get_page_store_optional, get_project_state

router = APIRouter(prefix="/api/projects", tags=["source-alignment"])
State = Annotated[ProjectState, Depends(get_project_state)]
Runner = Annotated[JobRunner, Depends(get_job_runner)]
Store = Annotated[LabelerPageStore | None, Depends(get_page_store_optional)]


class StartAlignmentRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=200)
    expected_generation: int = Field(ge=0)


class StartAlignmentResponse(BaseModel):
    job_id: str


class ReviewAlignmentRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    expected_generation: int = Field(ge=0)
    result_id: str
    decision: ReviewDecision
    note: str = Field(default="", max_length=10000)
    reviewed_text: str | None = Field(default=None, max_length=10000)


def _error(code: str, message: str, *, status: int = 409) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message, "details": None})


def _resolve(state: ProjectState, project_id: str, page_index: int) -> tuple[Page, int] | JSONResponse:
    project = state.loaded_project
    if project is None or project.project_id != project_id or not 0 <= page_index < project.total_pages:
        return _error("page_not_found", "Project/page is not loaded", status=404)
    pstate = state.get_page_state(page_index)
    if pstate is None or pstate.page_record is None or not isinstance(pstate.page_record.payload, Page):
        return _error("page_not_loaded", "Load scan OCR before using source alignment", status=400)
    return pstate.page_record.payload, pstate.generation


def _source_text_page_is_loaded(state: ProjectState, project_id: str, page_index: int) -> JSONResponse | None:
    """Check source identity only; source text never requires OCR page state."""
    project = state.loaded_project
    if project is None or project.project_id != project_id or not 0 <= page_index < project.total_pages:
        return _error("page_not_found", "Project/page is not loaded", status=404)
    return None


@router.get(
    "/{project_id}/pages/{page_index}/source-text",
    response_model=SourceTextPreview,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def get_source_text(project_id: str, page_index: int, state: State) -> SourceTextPreview | JSONResponse:
    """Return verified F2/P3 source text without loading, mutating, or using OCR."""
    with state.mutation_lock, state.get_page_lock(page_index):
        error = _source_text_page_is_loaded(state, project_id, page_index)
        if error is not None:
            return error
        try:
            return source_text_preview_for_page(state, page_index)
        except ValueError as exc:
            return _error("source_text_invalid", str(exc), status=400)


@router.get("/{project_id}/pages/{page_index}/source-alignment", response_model=SourceAlignmentResponse)
def get_alignment(project_id: str, page_index: int, state: State) -> SourceAlignmentResponse | JSONResponse:
    with state.mutation_lock, state.get_page_lock(page_index):
        resolved = _resolve(state, project_id, page_index)
        if isinstance(resolved, JSONResponse):
            return resolved
        page, generation = resolved
        pstate = state.get_page_state(page_index)
        result = pstate.source_alignment if pstate is not None else None
        return SourceAlignmentResponse(
            generation=generation,
            result=result,
            stale=result is not None and result.ocr_signature != ocr_signature(page),
        )


@router.post(
    "/{project_id}/pages/{page_index}/source-alignment",
    status_code=202,
    response_model=StartAlignmentResponse,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def start_alignment(
    project_id: str, page_index: int, body: StartAlignmentRequest, state: State, runner: Runner
) -> StartAlignmentResponse | JSONResponse:
    payload = {"page_index": page_index, "expected_generation": body.expected_generation}
    try:
        existing = runner.lookup_idempotent(
            "source_alignment", request_id=body.request_id, project_id=project_id, payload=payload
        )
        if existing is not None:
            return StartAlignmentResponse(job_id=existing)
    except RequestIdConflictError as exc:
        return _error("request_id_conflict", str(exc))
    with state.mutation_lock, state.get_page_lock(page_index):
        resolved = _resolve(state, project_id, page_index)
        if isinstance(resolved, JSONResponse):
            return resolved
        if resolved[1] != body.expected_generation:
            return _error("stale_generation", "Page generation changed; inspect the current page")
        try:
            if load_source_evidence(state, page_index) is None:
                return _error(
                    "source_alignment_unavailable", "Prepared F2/P3 evidence is unavailable", status=404
                )
            job_id = runner.submit_idempotent(
                "source_alignment", request_id=body.request_id, project_id=project_id, payload=payload
            )
        except RequestIdConflictError as exc:
            return _error("request_id_conflict", str(exc))
        except ValueError as exc:
            return _error("source_alignment_invalid", str(exc), status=400)
        return StartAlignmentResponse(job_id=job_id)


@router.patch(
    "/{project_id}/pages/{page_index}/source-alignment/groups/{group_id}",
    response_model=SourceAlignmentResponse,
)
def review_alignment(
    project_id: str,
    page_index: int,
    group_id: str,
    body: ReviewAlignmentRequest,
    *,
    state: State,
    store: Store,
) -> SourceAlignmentResponse | JSONResponse:
    with state.mutation_lock, state.get_page_lock(page_index):
        resolved = _resolve(state, project_id, page_index)
        if isinstance(resolved, JSONResponse):
            return resolved
        page, generation = resolved
        pstate = state.get_page_state(page_index)
        if pstate is None or pstate.source_alignment is None:
            return _error(
                "source_alignment_missing", "Run source alignment before reviewing groups", status=404
            )
        result = pstate.source_alignment
        if (
            generation != body.expected_generation
            or result.result_id != body.result_id
            or result.ocr_signature != ocr_signature(page)
        ):
            return _error(
                "stale_alignment", "Alignment identity, generation or OCR changed; inspect the current result"
            )
        if not any(group.group_id == group_id for group in result.groups):
            return _error(
                "alignment_group_missing", "Group does not belong to the current alignment", status=404
            )
        updated = result.model_copy(
            update={
                "groups": tuple(
                    group.model_copy(
                        update={
                            "decision": body.decision,
                            "note": body.note,
                            "reviewed_text": body.reviewed_text,
                        }
                    )
                    if group.group_id == group_id
                    else group
                    for group in result.groups
                )
            }
        )
        try:
            persist_alignment(state=pstate, page=page, result=updated, store=store)
        except OSError as exc:
            return _error("alignment_persist_failed", str(exc), status=503)
        return SourceAlignmentResponse(generation=pstate.generation, result=updated)

"""``/api/projects/{project_id}/pages/{page_index}/lines`` and ``/paragraphs`` router (§5.5).

Spec authority:
- ``specs/01-data-models.md §2`` — wire shapes for line/paragraph routes.
- ``specs/02-backend.md §5.5`` — endpoint contracts.
- ``docs/specs/2026-05-12-backend-design.md`` — autosave constraint.

Each mutation handler:
1. Guards 404 (project not loaded or page out of range).
2. Applies the logical mutation (stub — full structural mutation is M3-proper).
3. Returns the current ``PagePayload`` snapshot (autosave side-effect implicit).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.project_state import ProjectState
from .dependencies import get_project_state
from .middleware.error_handler import ApiError
from .pages import PagePayload

router = APIRouter(prefix="/api/projects", tags=["lines", "paragraphs"])


# ── Request models ─────────────────────────────────────────────────────


class CopyLineGtRequest(BaseModel):
    """Spec §2 line 337."""

    direction: Literal["gt_to_ocr", "ocr_to_gt"]


class DeleteScopeRequest(BaseModel):
    """Spec §2 lines 340-344."""

    scope: Literal["paragraph", "line", "word"]
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    word_indices: list[tuple[int, int]] = []


class MergeScopeRequest(BaseModel):
    """Spec §2 lines 346-349."""

    scope: Literal["paragraph", "line"]
    paragraph_indices: list[int] = []
    line_indices: list[int] = []


class SplitParagraphAfterLineRequest(BaseModel):
    """Spec §2 lines 351-353."""

    paragraph_index: int
    after_line_index: int


class SplitLineAfterWordRequest(BaseModel):
    """Spec §2 lines 355-357."""

    line_index: int
    after_word_index: int


class SplitLineWithSelectedWordsRequest(BaseModel):
    """Spec §2 lines 359-362."""

    line_index: int
    word_indices: list[int]
    mode: Literal["extract_to_new", "split_into_two"]


class GroupSelectedWordsIntoNewParagraphRequest(BaseModel):
    """Spec §2 lines 364-365."""

    word_indices: list[tuple[int, int]]


# ── Helpers ────────────────────────────────────────────────────────────


def _project_not_found(project_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="project_not_found",
            message=f"project not found: {project_id}",
        ).model_dump(),
    )


def _page_not_found(page_index: int) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="page_not_found",
            message=f"page not found: {page_index}",
        ).model_dump(),
    )


def _check_project_and_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState,
) -> JSONResponse | None:
    """Return an error response if the project/page isn't valid, else None."""
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _project_not_found(project_id)
    if page_index < 0 or page_index >= project.total_pages:
        return _page_not_found(page_index)
    return None


def _page_payload(project_id: str, page_index: int) -> JSONResponse:
    """Return the current ``PagePayload`` snapshot for a valid page."""
    payload = PagePayload(project_id=project_id, page_index=page_index)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


# ── Routes ─────────────────────────────────────────────────────────────


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/copy-gt",
    response_model=PagePayload,
)
def copy_line_gt(
    project_id: str,
    page_index: int,
    line_index: int,
    body: CopyLineGtRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../lines/{li}/copy-gt`` — copy GT↔OCR text for a line."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/delete",
    response_model=PagePayload,
)
def delete_scope(
    project_id: str,
    page_index: int,
    body: DeleteScopeRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../delete`` — delete a scope (paragraph/line/word set)."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/merge",
    response_model=PagePayload,
)
def merge_scope(
    project_id: str,
    page_index: int,
    body: MergeScopeRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../merge`` — merge a set of paragraphs or lines."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/{paragraph_index}/split-after-line",
    response_model=PagePayload,
)
def split_paragraph_after_line(
    project_id: str,
    page_index: int,
    paragraph_index: int,
    body: SplitParagraphAfterLineRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../paragraphs/{pi}/split-after-line`` — split paragraph at a line boundary."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/split-after-word",
    response_model=PagePayload,
)
def split_line_after_word(
    project_id: str,
    page_index: int,
    line_index: int,
    body: SplitLineAfterWordRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../lines/{li}/split-after-word`` — split line at a word boundary."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/split-with-selected",
    response_model=PagePayload,
)
def split_line_with_selected_words(
    project_id: str,
    page_index: int,
    line_index: int,
    body: SplitLineWithSelectedWordsRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../lines/{li}/split-with-selected`` — extract selected words into a new line."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/words/group-into-paragraph",
    response_model=PagePayload,
)
def group_selected_words_into_new_paragraph(
    project_id: str,
    page_index: int,
    body: GroupSelectedWordsIntoNewParagraphRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../words/group-into-paragraph`` — group selected words into a new paragraph."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _page_payload(project_id, page_index)


def install_lines_paragraphs_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the lines/paragraphs router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "CopyLineGtRequest",
    "DeleteScopeRequest",
    "GroupSelectedWordsIntoNewParagraphRequest",
    "MergeScopeRequest",
    "SplitLineAfterWordRequest",
    "SplitLineWithSelectedWordsRequest",
    "SplitParagraphAfterLineRequest",
    "install_lines_paragraphs_router",
    "router",
]

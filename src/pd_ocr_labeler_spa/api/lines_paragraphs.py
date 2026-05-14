"""``/api/projects/{project_id}/pages/{page_index}/lines`` and ``/paragraphs`` router (M3+).

Spec authority:
- ``specs/01-data-models.md §2`` — wire shapes for line/paragraph routes.
- ``specs/02-backend.md §5.5`` — endpoint contracts.

Route handlers are stubs returning 501 until M3 plumbing lands.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .pages import PagePayload

router = APIRouter(prefix="/api/projects", tags=["lines", "paragraphs"])


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


_NOT_IMPLEMENTED = JSONResponse(
    status_code=501,
    content={"error": "not_implemented", "message": "line/paragraph routes land in M3"},
)


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/copy-gt",
    response_model=PagePayload,
)
def copy_line_gt(project_id: str, page_index: int, line_index: int, body: CopyLineGtRequest) -> JSONResponse:
    """``POST .../lines/{li}/copy-gt`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/delete",
    response_model=PagePayload,
)
def delete_scope(project_id: str, page_index: int, body: DeleteScopeRequest) -> JSONResponse:
    """``POST .../delete`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/merge",
    response_model=PagePayload,
)
def merge_scope(project_id: str, page_index: int, body: MergeScopeRequest) -> JSONResponse:
    """``POST .../merge`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/{paragraph_index}/split-after-line",
    response_model=PagePayload,
)
def split_paragraph_after_line(
    project_id: str, page_index: int, paragraph_index: int, body: SplitParagraphAfterLineRequest
) -> JSONResponse:
    """``POST .../paragraphs/{pi}/split-after-line`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/split-after-word",
    response_model=PagePayload,
)
def split_line_after_word(
    project_id: str, page_index: int, line_index: int, body: SplitLineAfterWordRequest
) -> JSONResponse:
    """``POST .../lines/{li}/split-after-word`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/split-with-selected",
    response_model=PagePayload,
)
def split_line_with_selected_words(
    project_id: str, page_index: int, line_index: int, body: SplitLineWithSelectedWordsRequest
) -> JSONResponse:
    """``POST .../lines/{li}/split-with-selected`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/group-into-paragraph",
    response_model=PagePayload,
)
def group_selected_words_into_new_paragraph(
    project_id: str, page_index: int, body: GroupSelectedWordsIntoNewParagraphRequest
) -> JSONResponse:
    """``POST .../words/group-into-paragraph`` — stub; M3."""
    return _NOT_IMPLEMENTED


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

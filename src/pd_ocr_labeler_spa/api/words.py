"""``/api/projects/{project_id}/pages/{page_index}/words`` router — word wire shapes (M3+).

Spec authority:
- ``specs/01-data-models.md §2`` — wire shapes for word routes.
- ``specs/02-backend.md §5.4`` — endpoint contracts.

Route handlers are stubs returning 501 until M3 word-mutation plumbing lands.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.models import BBox
from .pages import PagePayload

router = APIRouter(prefix="/api/projects", tags=["words"])


class UpdateWordGroundTruthRequest(BaseModel):
    """Spec §2 line 285."""

    text: str


class ApplyStyleRequest(BaseModel):
    """Spec §2 lines 288-290."""

    style: str
    scope: Literal["whole", "part"] = "whole"


class ApplyComponentRequest(BaseModel):
    """Spec §2 lines 293-295."""

    component: str
    enabled: bool


class ToggleValidatedRequest(BaseModel):
    """Spec §2 lines 297-298."""

    validated: bool | None = None


class ValidateBatchRequest(BaseModel):
    """Spec §2 lines 300-306."""

    scope: Literal["page", "paragraph", "line", "word"]
    line_index: int | None = None
    word_indices: list[tuple[int, int]] = []
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    validated: bool


class AddWordRequest(BaseModel):
    """Spec §2 lines 308-311."""

    line_index: int | None = None
    bbox: BBox
    text: str = ""


class ReboxWordRequest(BaseModel):
    """Spec §2 lines 313-314."""

    bbox: BBox


class NudgeBboxRequest(BaseModel):
    """Spec §2 lines 316-321."""

    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0
    refine_after: bool = False


class SplitWordRequest(BaseModel):
    """Spec §2 lines 323-325."""

    x_fraction: float
    direction: Literal["horizontal", "vertical"]


class MergeWordsRequest(BaseModel):
    """Spec §2 lines 327-328."""

    direction: Literal["left", "right"]


class ErasePixelsRequest(BaseModel):
    """Spec §2 lines 330-332."""

    bbox: BBox
    fill_value: int = 255


_NOT_IMPLEMENTED = JSONResponse(
    status_code=501,
    content={"error": "not_implemented", "message": "word routes land in M3"},
)


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/gt",
    response_model=PagePayload,
)
def update_word_ground_truth(
    project_id: str, page_index: int, line_index: int, word_index: int, body: UpdateWordGroundTruthRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/gt`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/style",
    response_model=PagePayload,
)
def apply_style(
    project_id: str, page_index: int, line_index: int, word_index: int, body: ApplyStyleRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/style`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/component",
    response_model=PagePayload,
)
def apply_component(
    project_id: str, page_index: int, line_index: int, word_index: int, body: ApplyComponentRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/component`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/validated",
    response_model=PagePayload,
)
def toggle_validated(
    project_id: str, page_index: int, line_index: int, word_index: int, body: ToggleValidatedRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/validated`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/validate-batch",
    response_model=PagePayload,
)
def validate_batch(project_id: str, page_index: int, body: ValidateBatchRequest) -> JSONResponse:
    """``POST .../words/validate-batch`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/add",
    response_model=PagePayload,
)
def add_word(project_id: str, page_index: int, body: AddWordRequest) -> JSONResponse:
    """``POST .../words/add`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/rebox",
    response_model=PagePayload,
)
def rebox_word(
    project_id: str, page_index: int, line_index: int, word_index: int, body: ReboxWordRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/rebox`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/nudge",
    response_model=PagePayload,
)
def nudge_bbox(
    project_id: str, page_index: int, line_index: int, word_index: int, body: NudgeBboxRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/nudge`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/split",
    response_model=PagePayload,
)
def split_word(
    project_id: str, page_index: int, line_index: int, word_index: int, body: SplitWordRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/split`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/merge",
    response_model=PagePayload,
)
def merge_words(
    project_id: str, page_index: int, line_index: int, word_index: int, body: MergeWordsRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/merge`` — stub; M3."""
    return _NOT_IMPLEMENTED


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/erase-pixels",
    response_model=PagePayload,
)
def erase_pixels(
    project_id: str, page_index: int, line_index: int, word_index: int, body: ErasePixelsRequest
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/erase-pixels`` — stub; M3."""
    return _NOT_IMPLEMENTED


def install_words_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the words router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "AddWordRequest",
    "ApplyComponentRequest",
    "ApplyStyleRequest",
    "ErasePixelsRequest",
    "MergeWordsRequest",
    "NudgeBboxRequest",
    "ReboxWordRequest",
    "SplitWordRequest",
    "ToggleValidatedRequest",
    "UpdateWordGroundTruthRequest",
    "ValidateBatchRequest",
    "install_words_router",
    "router",
]

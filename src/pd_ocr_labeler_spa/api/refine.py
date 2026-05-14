"""``/api/projects/{project_id}/pages/{page_index}/refine`` router (M3+).

Spec authority:
- ``specs/01-data-models.md §2`` — ``RefineScopeRequest`` shape.
- ``specs/02-backend.md §5.6`` — endpoint contract.

Route handler is a stub returning 501 until M3 OCR/refine plumbing lands.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .pages import PagePayload

router = APIRouter(prefix="/api/projects", tags=["refine"])


class RefineScopeRequest(BaseModel):
    """Body for ``POST .../refine`` — spec §2 lines 371-378."""

    scope: Literal["page", "paragraph", "line", "word"]
    mode: Literal["refine", "expand_then_refine", "expand_only"] = "refine"
    padding_px: int = 2
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    word_indices: list[tuple[int, int]] = []


@router.post("/{project_id}/pages/{page_index}/refine", response_model=PagePayload)
def refine_scope(project_id: str, page_index: int, body: RefineScopeRequest) -> JSONResponse:
    """``POST .../refine`` — stub; M3."""
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "message": "refine route lands in M3"},
    )


def install_refine_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the refine router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "RefineScopeRequest",
    "install_refine_router",
    "router",
]

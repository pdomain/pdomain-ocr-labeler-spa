"""``/api/normalize`` router — text normalization availability probe.

Spec authority:
- ``docs/specs/2026-05-12-text-normalization-design.md §Toggle UI``
- Issue #261 — "When pd_book_tools.text.normalize unavailable
  (checked via GET /api/normalize/available): show 'Requires
  pd-book-tools ≥ X.Y.Z' and disable toggles."

Routes:
- ``GET /api/normalize/available`` — returns ``{"available": bool}``.
  ``true`` when ``pd_book_tools.text.normalize`` is importable (i.e.
  the installed pd-book-tools version exposes the normalize API).
  ``false`` otherwise. Frontend uses this to gate the normalize UI
  section in ``<OCRConfigModal />``.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.text_normalize import is_available

router = APIRouter(prefix="/api/normalize", tags=["normalize"])


class NormalizeAvailableResponse(BaseModel):
    """Response for ``GET /api/normalize/available`` — spec §Toggle UI."""

    available: bool


@router.get("/available", response_model=NormalizeAvailableResponse)
def normalize_available() -> JSONResponse:
    """``GET /api/normalize/available`` — probe for normalize module.

    Returns ``{"available": true}`` when the installed ``pd_book_tools``
    exposes ``pd_book_tools.text.normalize.normalize_string``.
    Returns ``{"available": false}`` when the module is absent (older pin).

    Used by ``<OCRConfigModal />`` to decide whether to render the
    text-normalization toggles as enabled or greyed-out with a tooltip.
    Issue #261 acceptance: route registered, returns 200 JSON payload.
    """
    return JSONResponse(
        status_code=200,
        content={"available": is_available()},
    )


def install_normalize_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the normalize router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "install_normalize_router",
    "normalize_available",
    "router",
]

"""``/api/ocr-config`` router — read-only skeleton (M3 slice 8a).

Spec authority:

- ``specs/02-backend.md §5.8`` lines 317-322 — endpoint contracts.
- ``specs/01-data-models.md`` lines 374-400 — DTO shapes (defined in
  ``core/ocr_models.py`` per iter 7 / commit 9201caa).

What slice 8a ships:

- ``GET /api/ocr-config`` returns a hardcoded "stock fallback" payload
  composed from the iter-7 DTOs. Both detection and recognition lists
  contain a single ``stock`` option, ``selection_reason="stock-fallback"``,
  ``hf_pinned_revision=None``. No model loading, no HuggingFace probe,
  no local weights scan — slice 8b+ work that goes through
  ``core/page_state.ensure_page_model`` and the ``IOCREngine`` adapter.

What this slice deliberately does NOT do:

- ``POST /api/ocr-config/models`` — mutates selection state, requires
  an ``OCRConfigCarrier`` + persistence (slice 8b+).
- ``POST /api/ocr-config/rescan`` — requires the HF / local discovery
  pipeline (slice 8b+).
- Any real provenance computation. ``"stock-fallback"`` is honest
  while no probing exists; future slices will start emitting other
  values from the spec literal set as the discovery pipeline lands.

The route shape stays spec-canonical so future slice expansions are
purely additive on the response body — same URL, same DTO, richer
content.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..core.ocr_models import GetOCRConfigResponse, OCRModelOption

router = APIRouter(prefix="/api/ocr-config", tags=["ocr-config"])


# Slice 8a stock options. Hoisted to module level so they're built once
# rather than per-request. ``OCRModelOption`` is a frozen pydantic model
# (``extra="forbid"``); sharing instances across requests is safe.
_STOCK_DETECTION = OCRModelOption(
    key="stock",
    label="Stock (bundled DocTR)",
    source="stock",
    is_default=True,
)

_STOCK_RECOGNITION = OCRModelOption(
    key="stock",
    label="Stock (bundled DocTR)",
    source="stock",
    is_default=True,
)


@router.get("", response_model=GetOCRConfigResponse)
def get_ocr_config() -> GetOCRConfigResponse:
    """Return a slice-8a stock-fallback OCR config snapshot.

    Spec §02-backend.md §5.8 line 319. The response body is honest for
    a no-discovery-yet world: only stock options, only ``stock-fallback``
    as the selection reason. When slice 8b wires real HF / local
    discovery this body grows; the route shape stays the same.
    """
    return GetOCRConfigResponse(
        detection_options=[_STOCK_DETECTION],
        recognition_options=[_STOCK_RECOGNITION],
        selected_detection=_STOCK_DETECTION.key,
        selected_recognition=_STOCK_RECOGNITION.key,
        hf_pinned_revision=None,
        selection_reason="stock-fallback",
    )


def install_ocr_config_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the OCR config router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "install_ocr_config_router",
    "router",
]

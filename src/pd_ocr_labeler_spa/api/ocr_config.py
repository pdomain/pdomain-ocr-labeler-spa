"""``/api/ocr-config`` router — read + stateless-mutate (M3 slices 8a + 8c-i).

Spec authority:

- ``specs/02-backend.md §5.8`` lines 317-322 — endpoint contracts.
- ``specs/01-data-models.md`` lines 374-400 — DTO shapes (defined in
  ``core/ocr_models.py`` per iter 7 / commit 9201caa).

What slice 8a shipped:

- ``GET /api/ocr-config`` returns a hardcoded "stock fallback" payload
  composed from the iter-7 DTOs. Both detection and recognition lists
  contain a single ``stock`` option, ``selection_reason="stock-fallback"``,
  ``hf_pinned_revision=None``. No model loading, no HuggingFace probe,
  no local weights scan.

What slice 8c-i adds:

- ``POST /api/ocr-config/models`` validates the request keys against
  the same stock-only option lists and echoes a ``GetOCRConfigResponse``
  back. Selection is **not yet persisted** — that needs an
  ``OCRConfigCarrier`` + ``ocr_config.json`` writeback (slice 8c-ii+).
  Unknown keys → 400. The route shape is spec-canonical so when the
  carrier lands the route body becomes "validate → carrier.set(...) →
  return current snapshot" without changing the wire contract.

What this router still deliberately does NOT do:

- ``POST /api/ocr-config/rescan`` — requires the HF / local discovery
  pipeline (slice 8c-ii+).
- Persist a selection. The mutation route is stateless in slice 8c-i;
  every call validates against the stock list and returns the
  echo-shaped response.
- Any real provenance computation. ``"stock-fallback"`` is honest
  while no probing exists; future slices will start emitting other
  values from the spec literal set as the discovery pipeline lands.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.ocr_models import GetOCRConfigResponse, OCRModelOption, SetOCRModelsRequest

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


def _build_snapshot(
    selected_detection: str,
    selected_recognition: str,
    hf_pinned_revision: str | None,
) -> GetOCRConfigResponse:
    """Compose a slice-8a/-8c-i ``GetOCRConfigResponse`` from the
    stock-only option lists. Caller is responsible for validating
    that the selected keys live in the option lists; this helper
    trusts them.
    """
    return GetOCRConfigResponse(
        detection_options=[_STOCK_DETECTION],
        recognition_options=[_STOCK_RECOGNITION],
        selected_detection=selected_detection,
        selected_recognition=selected_recognition,
        hf_pinned_revision=hf_pinned_revision,
        selection_reason="stock-fallback",
    )


@router.get("", response_model=GetOCRConfigResponse)
def get_ocr_config() -> GetOCRConfigResponse:
    """Return a slice-8a stock-fallback OCR config snapshot.

    Spec §02-backend.md §5.8 line 319. The response body is honest for
    a no-discovery-yet world: only stock options, only ``stock-fallback``
    as the selection reason. When slice 8b/8c-ii wire real HF / local
    discovery this body grows; the route shape stays the same.
    """
    return _build_snapshot(
        selected_detection=_STOCK_DETECTION.key,
        selected_recognition=_STOCK_RECOGNITION.key,
        hf_pinned_revision=None,
    )


@router.post("/models", response_model=GetOCRConfigResponse)
def post_ocr_config_models(req: SetOCRModelsRequest) -> GetOCRConfigResponse:
    """Validate + echo OCR model selection (slice 8c-i, stateless).

    Spec §02-backend.md §5.8 line 320. Slice 8c-i ships the route
    shape and key-validation against the slice-8a stock-only option
    lists. Selection is NOT persisted — that needs an
    ``OCRConfigCarrier`` (slice 8c-ii+). Unknown keys → 400. Until
    real probing lands, the response always carries
    ``selection_reason="stock-fallback"``; pinning that here means a
    future drift to fake-discovery output surfaces as a test failure.
    """
    detection_keys = {_STOCK_DETECTION.key}
    recognition_keys = {_STOCK_RECOGNITION.key}
    if req.detection_key not in detection_keys:
        raise HTTPException(
            status_code=400,
            detail=f"unknown detection_key: {req.detection_key!r}",
        )
    if req.recognition_key not in recognition_keys:
        raise HTTPException(
            status_code=400,
            detail=f"unknown recognition_key: {req.recognition_key!r}",
        )
    return _build_snapshot(
        selected_detection=req.detection_key,
        selected_recognition=req.recognition_key,
        hf_pinned_revision=req.hf_pinned_revision,
    )


def install_ocr_config_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the OCR config router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "install_ocr_config_router",
    "router",
]

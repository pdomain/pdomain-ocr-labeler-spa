"""``IOCREngine`` Protocol — every OCR backend conforms to this surface.

Spec: ``docs/architecture/02-backend.md §7``. The Protocol intentionally returns a
tuple ``(Page, OCRProvenance)`` so the engine reports both the parsed
document and which models / revisions produced it. ``Page`` is the
``pd_book_tools`` domain class; deferring its import to ``TYPE_CHECKING``
keeps the Protocol importable in tests that don't need pd-book-tools
loaded (faster CI, smaller blast radius for accidental import-time
side effects).

``OCRProvenance`` is a lightweight v1 model carrying the model keys
the spec ``§5.8`` exposes via ``GET /api/ocr-config`` — the full
provenance shape (recognition revision, detection revision, run
timestamp, …) lands when M3 wires ``core/ocr/provenance.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    # Imported lazily — ``pd_book_tools.ocr.document.Page`` is heavy and
    # the Protocol surface only needs the *type*, not the runtime class.
    from pd_book_tools.ocr.document import Page


class OCRProvenance(BaseModel):
    """Which OCR backend + models produced a given ``Page``.

    Minimal v1 shape; spec §5.8 fields land in M3 alongside the real
    ``local_doctr`` impl.
    """

    engine: str  # "local_doctr" | "modal" | "shared_container"
    detection_key: str
    recognition_key: str
    hf_revision: str | None = None


@runtime_checkable
class IOCREngine(Protocol):
    """OCR backend interface.

    ``image`` is a ``numpy.ndarray`` (HxWxC, uint8) — typed as ``Any``
    on the Protocol surface to avoid forcing a numpy import on every
    consumer. The concrete impls type more strictly.
    """

    async def ocr_page(
        self,
        image: Any,
        *,
        detection_key: str,
        recognition_key: str,
        hf_revision: str | None,
    ) -> tuple[Page, OCRProvenance]: ...

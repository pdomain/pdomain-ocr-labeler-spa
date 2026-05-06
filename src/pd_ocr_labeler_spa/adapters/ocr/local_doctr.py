"""Local-DocTR OCR backend — body lands in M3.

Spec: ``specs/02-backend.md §7`` ("``local_doctr.py`` wraps
``pd_book_tools.ocr.document.Document.from_image_ocr_via_doctr`` and a
predictor cache (``_get_or_create_predictor``)") and ``specs/16-milestones.md
M3`` (where the wiring lands).

Until M3 the ``ocr_page`` body is a plain ``raise NotImplementedError``
— deliberately distinct from ``NotImplementedYet`` (which marks
"never wired in v1" backends). The distinction lets readers grep for
the spec-named seam class without picking up "M3 hasn't shipped yet"
TODOs by mistake.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import IOCREngine, OCRProvenance

if TYPE_CHECKING:
    from pd_book_tools.ocr.document import Page


class LocalDoctrOCR(IOCREngine):
    """Wrapper around DocTR; predictor-cached. Body lands in M3."""

    async def ocr_page(
        self,
        image: Any,
        *,
        detection_key: str,
        recognition_key: str,
        hf_revision: str | None,
    ) -> tuple[Page, OCRProvenance]:
        raise NotImplementedError("LocalDoctrOCR.ocr_page wires up in M3 (see specs/16-milestones.md)")

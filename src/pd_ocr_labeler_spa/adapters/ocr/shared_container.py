"""Shared-container OCR backend — Protocol seam only; raises ``NotImplementedYet``.

Spec: ``specs/02-backend.md §7`` + ``specs/17-decisions.md D-018``. Same
shape as ``modal.py`` — the Protocol seam exists in v1 so a future
deployment that hits a shared OCR container is a wiring change not a
route refactor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.exceptions import NotImplementedYet
from .base import IOCREngine, OCRProvenance

if TYPE_CHECKING:
    from pd_book_tools.ocr.document import Page


class SharedContainerOCR(IOCREngine):
    async def ocr_page(
        self,
        image: Any,
        *,
        detection_key: str,
        recognition_key: str,
        hf_revision: str | None,
    ) -> tuple[Page, OCRProvenance]:
        raise NotImplementedYet("shared_container OCR adapter not yet wired")

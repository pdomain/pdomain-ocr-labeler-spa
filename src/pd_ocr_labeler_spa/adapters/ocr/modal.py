"""Modal OCR backend — Protocol seam only; raises ``NotImplementedYet``.

Spec: ``specs/02-backend.md §7`` ("``modal.py`` ... raises
``NotImplementedYet('modal OCR adapter not yet wired')`` from its
``ocr_page`` method") + ``specs/17-decisions.md D-018``.

The seam is real (the class exists, ``Settings.ocr_engine = "modal"``
will wire to this in ``bootstrap.py``) but the body is deliberately
absent in v1 — when off-machine GPU is needed, only this method's body
needs filling in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.exceptions import NotImplementedYet
from .base import IOCREngine, OCRProvenance

if TYPE_CHECKING:
    from pd_book_tools.ocr.document import Page


class ModalOCR(IOCREngine):
    async def ocr_page(
        self,
        image: Any,
        *,
        detection_key: str,
        recognition_key: str,
        hf_revision: str | None,
    ) -> tuple[Page, OCRProvenance]:
        raise NotImplementedYet("modal OCR adapter not yet wired")

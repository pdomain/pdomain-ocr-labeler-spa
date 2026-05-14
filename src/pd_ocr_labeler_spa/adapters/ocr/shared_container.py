"""Shared-container OCR backend — Protocol seam only; raises ``NotImplementedYet``.

Spec: ``docs/architecture/02-backend.md §7`` + ``specs/17-decisions.md D-018``. Same
shape as ``modal.py`` — the Protocol seam exists in v1 so a future
deployment that hits a shared OCR container is a wiring change not a
route refactor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.exceptions import NotImplementedYet
from .base import OCRProvenance

if TYPE_CHECKING:
    from pd_book_tools.ocr.document import Page


class SharedContainerOCR:
    """Shared-container OCR backend — Protocol seam; body raises ``NotImplementedYet``.

    Conformance to ``IOCREngine`` is purely structural (PEP 544); no
    explicit subclass — see ``adapters/__init__.py`` for the policy.
    (B-46.)
    """

    async def ocr_page(
        self,
        image: Any,
        *,
        detection_key: str,
        recognition_key: str,
        hf_revision: str | None,
    ) -> tuple[Page, OCRProvenance]:
        raise NotImplementedYet("shared_container OCR adapter not yet wired")

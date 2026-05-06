"""OCR adapter package re-exports.

Per D-018 the full axis (``local_doctr | modal | shared_container``)
ships in v1 — only ``LocalDoctrOCR`` will be wired by M3; ``ModalOCR``
and ``SharedContainerOCR`` raise ``NotImplementedYet`` so a
misconfigured ``Settings.ocr_engine`` fails loudly with a recognisable
error.
"""

from __future__ import annotations

from .base import IOCREngine, OCRProvenance
from .local_doctr import LocalDoctrOCR
from .modal import ModalOCR
from .shared_container import SharedContainerOCR

__all__ = [
    "IOCREngine",
    "OCRProvenance",
    "LocalDoctrOCR",
    "ModalOCR",
    "SharedContainerOCR",
]

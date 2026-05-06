"""Storage adapter package re-exports.

Importing from ``pd_ocr_labeler_spa.adapters.storage`` is the one
supported path; the ``base`` / ``filesystem`` modules are
implementation detail.
"""

from __future__ import annotations

from .base import IStorage
from .filesystem import FilesystemStorage

__all__ = ["IStorage", "FilesystemStorage"]

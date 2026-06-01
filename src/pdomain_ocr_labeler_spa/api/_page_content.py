"""Shared helper: load ``pdomain_book_tools.ocr.page.Page`` from the blob store.

Replaces the old ``lift_envelope_to_page`` call in words.py and
lines_paragraphs.py. After M5b the Page object always lives in the
BlobStore; envelope lifting is gone.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore

log = logging.getLogger(__name__)


def load_page_from_store(
    store: LabelerPageStore,
    page_id: Any,
) -> Page | None:
    """Load the ``Page`` content object for ``page_id`` from BlobStore.

    Returns ``None`` on any failure (missing aggregate, missing blob, corrupt JSON).
    Never raises.
    """
    try:
        from pdomain_book_tools.ocr.page import Page

        agg = store.get_page(page_id)
        record = agg.record
        if record.provenance is None:
            return None
        head = record.provenance.nodes.get(record.provenance.head_id)
        if head is None or not head.blob_refs:
            return None
        page_json_bytes = store.blobs.read(head.blob_refs[0])
        page_dict = json.loads(page_json_bytes.decode("utf-8"))
        return Page.from_dict(page_dict)
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("load_page_from_store: failed for page_id=%s: %s", page_id, exc)
        return None


__all__ = ["load_page_from_store"]

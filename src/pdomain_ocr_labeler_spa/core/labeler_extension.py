"""Labeler-specific page extension stored in ``extensions["labeler"]``.

This is the labeler's typed view-state that lives in the ``extensions``
slot of ``pdomain_ops.pages.PageRecord``. It is NOT imported by pdomain-ops.
Use ``get_extension`` / ``set_extension`` from ``pdomain_ops.pages`` to
read/write this model.

Fields that were previously on the local ``PageRecord`` and are labeler-
specific (not lifecycle/provenance core) live here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LabelerPageExtension(BaseModel):
    """Labeler view-state stored in ``extensions["labeler"]`` on a ``PageRecord``.

    Serialised via ``model_dump(mode="json")`` — all values must be JSON-safe.
    """

    # Display / load metadata
    page_number: int = 0
    """1-based page number (page_index + 1). Display use only."""

    page_source: str = "ocr"
    """How the page's OCR data was sourced. Mirrors former ``PageSource`` enum values."""

    payload_error: str | None = None
    """Set when the page content load fails. None on clean pages.
    Frontend shows 'corrupt saved data' banner when set."""

    has_edited_image: bool = False
    """True when an edited (post-erase) page image has been persisted as a blob
    for this page (Lane A / Task A4 writes ``PageState.edited_image_blob`` from
    the erase-pixels route). The frontend binds the "Reload OCR (Edited)" button's
    enabled state to this flag (Lane C / Task C2); it stays False until an erase
    actually persists an edited image."""

    # Per-session UI state (not persisted between sessions; defaults on reload)
    selection_mode: Literal["paragraph", "line", "word"] = "word"
    line_filter: Literal["unvalidated", "mismatched", "all"] = "all"

    # Future: char_bboxes, char_ranges, glyph_annotations live on PageState
    # in-memory (not in the extension) — they survive within a session but
    # are carried via PageAggregate.LabelerEdited events when saved.


__all__ = ["LabelerPageExtension"]

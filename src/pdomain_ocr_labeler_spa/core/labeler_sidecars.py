"""Labeler-only maps embedded in the page content blob (Wave 0.1).

Char ranges and char bboxes are not first-class book-tools ``Word`` fields.
They are stored under a reserved top-level key in the same JSON blob that
``save_page_content_to_store`` writes, so undo/reload rehydrate from the
versioned content hash.

See ``docs/context/decisions.md`` — 2026-07-21 Char sidecar durability.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

# Reserved top-level key inside the content blob JSON. book-tools
# ``Page.from_dict`` ignores unknown keys, so OCR structure is unaffected.
LABELER_SIDECARS_KEY = "labeler_sidecars"

# Stamped on a loaded ``Page`` object (same pattern as ``_labeler_page_id``)
# so ``ensure_page_model`` can copy maps into ``PageState``.
PAGE_SIDECARS_ATTR = "_labeler_sidecars"


@dataclass
class LabelerSidecars:
    """Char/glyph map payload carried beside ``Page.to_dict`` (Wave 0.1 / 2 T3)."""

    char_ranges_map: dict[str, Any] = field(default_factory=dict)
    char_bboxes_map: dict[str, Any] = field(default_factory=dict)
    glyph_annotations_map: dict[str, Any] = field(default_factory=dict)
    logical_page_id: str | None = None

    def is_empty(self) -> bool:
        return (
            not self.char_ranges_map
            and not self.char_bboxes_map
            and not self.glyph_annotations_map
            and self.logical_page_id is None
        )

    def to_blob_section(self) -> dict[str, Any] | None:
        """Return the JSON object for ``labeler_sidecars``, or None if empty."""
        if self.is_empty():
            return None
        out: dict[str, Any] = {}
        if self.char_ranges_map:
            out["char_ranges_map"] = dict(self.char_ranges_map)
        if self.char_bboxes_map:
            out["char_bboxes_map"] = dict(self.char_bboxes_map)
        if self.glyph_annotations_map:
            out["glyph_annotations_map"] = dict(self.glyph_annotations_map)
        if self.logical_page_id is not None:
            out["logical_page_id"] = self.logical_page_id
        return out

    @classmethod
    def from_page_state(cls, pstate: Any) -> LabelerSidecars:
        """Snapshot maps from a ``PageState`` (or any object with the attrs)."""
        ranges = getattr(pstate, "char_ranges_map", None) or {}
        bboxes = getattr(pstate, "char_bboxes_map", None) or {}
        glyphs = getattr(pstate, "glyph_annotations_map", None) or {}
        logical_page_id = getattr(pstate, "logical_page_id", None)
        return cls(
            char_ranges_map=dict(ranges) if isinstance(ranges, Mapping) else {},
            char_bboxes_map=dict(bboxes) if isinstance(bboxes, Mapping) else {},
            glyph_annotations_map=dict(glyphs) if isinstance(glyphs, Mapping) else {},
            logical_page_id=str(logical_page_id) if logical_page_id is not None else None,
        )

    @classmethod
    def from_content_dict(cls, content: Mapping[str, Any]) -> LabelerSidecars:
        """Extract sidecars from a content-blob dict (before or after from_dict)."""
        raw = content.get(LABELER_SIDECARS_KEY)
        if not isinstance(raw, Mapping):
            return cls()
        ranges = raw.get("char_ranges_map")
        bboxes = raw.get("char_bboxes_map")
        glyphs = raw.get("glyph_annotations_map")
        logical_page_id = raw.get("logical_page_id")
        return cls(
            char_ranges_map=dict(ranges) if isinstance(ranges, Mapping) else {},
            char_bboxes_map=dict(bboxes) if isinstance(bboxes, Mapping) else {},
            glyph_annotations_map=dict(glyphs) if isinstance(glyphs, Mapping) else {},
            logical_page_id=logical_page_id if isinstance(logical_page_id, str) else None,
        )


def content_dict_with_sidecars(
    page: Any,
    sidecars: LabelerSidecars | None = None,
) -> dict[str, Any]:
    """Build the JSON-serializable content blob: page dict + optional sidecars."""
    if not callable(getattr(page, "to_dict", None)):
        raise TypeError("page must expose to_dict()")
    content = dict(page.to_dict())
    section = sidecars.to_blob_section() if sidecars is not None else None
    if section is not None:
        content[LABELER_SIDECARS_KEY] = section
    else:
        # Explicit empty: do not leave a stale key if caller rebuilt without maps.
        content.pop(LABELER_SIDECARS_KEY, None)
    return content


def stamp_sidecars_on_page(page: Any, sidecars: LabelerSidecars) -> None:
    """Attach sidecars to a page object for later PageState hydration."""
    try:
        object.__setattr__(page, PAGE_SIDECARS_ATTR, sidecars)
    except Exception:  # pragma: no cover - defensive for frozen/slotted objects
        setattr(page, PAGE_SIDECARS_ATTR, sidecars)


def sidecars_from_page(page: Any) -> LabelerSidecars | None:
    """Return stamped sidecars, or None if the page was not loaded via store."""
    return getattr(page, PAGE_SIDECARS_ATTR, None)


def apply_sidecars_to_page_state(pstate: Any, sidecars: LabelerSidecars | None) -> None:
    """Replace PageState char maps from *sidecars* (clear when None/empty version).

    Always assigns new dicts so callers never share mutable maps with the
    blob payload or a previous version.
    """
    if sidecars is None:
        pstate.char_ranges_map = {}
        pstate.char_bboxes_map = {}
        pstate.glyph_annotations_map = {}
        return
    pstate.char_ranges_map = dict(sidecars.char_ranges_map)
    pstate.char_bboxes_map = dict(sidecars.char_bboxes_map)
    pstate.glyph_annotations_map = dict(sidecars.glyph_annotations_map)
    if sidecars.logical_page_id is not None:
        from uuid import UUID

        pstate.logical_page_id = UUID(sidecars.logical_page_id)


def parse_content_blob(raw: bytes | str | Mapping[str, Any]) -> tuple[dict[str, Any], LabelerSidecars]:
    """Decode a content blob into a page-shaped dict and extracted sidecars."""
    if isinstance(raw, Mapping):
        content = dict(raw)
    else:
        import json

        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise TypeError(f"content blob must be a JSON object, got {type(loaded).__name__}")
        content = loaded
    sidecars = LabelerSidecars.from_content_dict(content)
    return content, sidecars


def apply_sidecars_from_payload(pstate: Any, payload: Any) -> None:
    """If *payload* is a Page stamped with sidecars, apply them to *pstate*."""
    if payload is None:
        return
    stamped = sidecars_from_page(payload)
    if stamped is not None:
        apply_sidecars_to_page_state(pstate, stamped)


def merge_sidecars_into_mutable_content(
    content: MutableMapping[str, Any],
    sidecars: LabelerSidecars | None,
) -> None:
    """In-place attach/remove ``labeler_sidecars`` on an existing content dict."""
    if sidecars is None or sidecars.is_empty():
        content.pop(LABELER_SIDECARS_KEY, None)
        return
    section = sidecars.to_blob_section()
    if section is not None:
        content[LABELER_SIDECARS_KEY] = section


__all__ = [
    "LABELER_SIDECARS_KEY",
    "PAGE_SIDECARS_ATTR",
    "LabelerSidecars",
    "apply_sidecars_from_payload",
    "apply_sidecars_to_page_state",
    "content_dict_with_sidecars",
    "merge_sidecars_into_mutable_content",
    "parse_content_blob",
    "sidecars_from_page",
    "stamp_sidecars_on_page",
]

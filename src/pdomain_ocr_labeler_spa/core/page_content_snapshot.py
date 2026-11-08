"""Copy page content together with validated labeler-only review sidecars."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pdomain_book_tools.ocr.page import Page
from pydantic import JsonValue, TypeAdapter

from .labeler_sidecars import (
    LabelerSidecars,
    content_dict_with_sidecars,
    sidecars_from_page,
    stamp_sidecars_on_page,
)
from .source_alignment import alignment_from_page, grouped_word_bindings, ocr_signature

if TYPE_CHECKING:
    from collections.abc import Mapping


def snapshot_page_content(page: Page) -> dict[str, JsonValue]:
    """Retain current human annotations and source links in an immutable copy."""
    alignment = alignment_from_page(page)
    if alignment is not None:
        _ = grouped_word_bindings(page, alignment)
    stored = sidecars_from_page(page)
    sidecars = (
        replace(stored, source_alignment=alignment)
        if stored is not None
        else LabelerSidecars(source_alignment=alignment)
    )
    return TypeAdapter(dict[str, JsonValue]).validate_python(content_dict_with_sidecars(page, sidecars))


def restore_page_content(payload: bytes | str | Mapping[str, object]) -> Page:
    """Restore the exact page and reject stale source links before attaching them."""
    adapter = TypeAdapter(dict[str, JsonValue])
    content = (
        adapter.validate_json(payload)
        if isinstance(payload, bytes | str)
        else adapter.validate_python(payload)
    )
    sidecars = LabelerSidecars.from_content_dict(content)
    page = Page.from_dict(content)
    alignment = sidecars.source_alignment
    if alignment is not None:
        if alignment.ocr_signature != ocr_signature(page):
            raise ValueError("Source alignment is stale for the copied OCR topology")
        _ = grouped_word_bindings(page, alignment)
    stamp_sidecars_on_page(page, sidecars)
    return page

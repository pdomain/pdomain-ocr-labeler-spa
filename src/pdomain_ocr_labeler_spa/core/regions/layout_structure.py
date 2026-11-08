"""Review and export helpers for prepared-book layout structure."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pdomain_book_contracts.layout.text_hints import LayoutStructure

if TYPE_CHECKING:
    from pdomain_book_tools.ocr.page import Page
    from pdomain_book_tools.ocr.word import Word
    from pdomain_book_tools.typography import LabelingBundle

_WORD_ID_KEY = "layout_word_id"


def prepared_word_bindings(page: Page, bundle: LabelingBundle | None) -> dict[str, Word]:
    """Bind exact imported IDs once; later text/box edits never reissue them.

    This is limited to prepared bundles with the same ordered words as OCR.
    The existing per-word persisted match metadata retains the imported ID.
    Unsupported legacy pages deliberately receive no derived identities.
    """
    if bundle is None:
        return {}
    words = page.words
    allowed = {word.word_id for word in bundle.words}
    stored = [word.ground_truth_match_keys.get(_WORD_ID_KEY) for word in words]
    if any(value is not None for value in stored):
        result: dict[str, Word] = {}
        for value, word in zip(stored, words, strict=True):
            if not isinstance(value, str) or value not in allowed or value in result:
                return {}
            result[value] = word
        return result
    if len(words) != len(bundle.words) or any(
        word.text != source.text for word, source in zip(words, bundle.words, strict=True)
    ):
        return {}
    for word, source in zip(words, bundle.words, strict=True):
        word.ground_truth_match_keys[_WORD_ID_KEY] = source.word_id
    return {source.word_id: word for word, source in zip(words, bundle.words, strict=True)}


def stored_word_bindings(page: Page) -> dict[str, Word]:
    """Read imported IDs retained with words; never join on geometry."""
    result: dict[str, Word] = {}
    for word in page.words:
        word_id = word.ground_truth_match_keys.get(_WORD_ID_KEY)
        if isinstance(word_id, str):
            if word_id in result:
                raise ValueError("duplicate prepared word identity on page")
            result[word_id] = word
    return result


def reviewed_structure(
    structure: LayoutStructure, *, page: Page, bundle: LabelingBundle | None
) -> LayoutStructure:
    """Require prepared IDs for every bound line/cell before persisting review."""
    word_ids = [word_id for line in structure.lines for word_id in line.word_ids]
    word_ids.extend(
        word_id for row in structure.table_rows for cell in row.cells for word_id in cell.word_ids
    )
    if word_ids:
        bindings = prepared_word_bindings(page, bundle)
        if not bindings:
            raise ValueError(
                " ".join(
                    (
                        "Word-bound layout structure requires a prepared book with stored bundle word IDs.",
                        "Prepare this book first, or accept the ordinary region without detailed structure.",
                    )
                )
            )
        if any(word_id not in bindings for word_id in word_ids):
            raise ValueError("Layout structure names a word outside the current prepared page")
        if len(word_ids) != len(set(word_ids)):
            raise ValueError("Layout structure repeats a word ID")
    return refresh_structure_signatures(structure, page=page)


def _signature(word: Word) -> str:
    box = word.ground_truth_bounding_box or word.bounding_box
    return json.dumps([*box.to_ltrb(), box.is_normalized], separators=(",", ":"))


def refresh_structure_signatures(structure: LayoutStructure, *, page: Page) -> LayoutStructure:
    """Rebuild optional geometry snapshots by canonical imported IDs."""
    bindings = stored_word_bindings(page)

    def signatures(word_ids: tuple[str, ...]) -> tuple[str, ...]:
        if any(word_id not in bindings for word_id in word_ids):
            raise ValueError("Reviewed layout structure references a word no longer on this page")
        return tuple(_signature(bindings[word_id]) for word_id in word_ids)

    return structure.model_copy(
        update={
            "lines": tuple(
                line.model_copy(update={"word_signatures": signatures(line.word_ids)})
                for line in structure.lines
            ),
            "table_rows": tuple(
                row.model_copy(
                    update={
                        "cells": tuple(
                            cell.model_copy(update={"word_signatures": signatures(cell.word_ids)})
                            for cell in row.cells
                        )
                    }
                )
                for row in structure.table_rows
            ),
        }
    )

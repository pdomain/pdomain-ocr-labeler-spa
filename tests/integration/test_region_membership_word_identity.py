"""A membership write keeps the word ids it found.

``stable_word_id`` hashes a page-wide reading order. A leaf region joins
``page.lines``, so moving a word would renumber that order. The membership
route freezes each word's order before the move. ``TypographyCorrectionLog``
rows stay attached to the ids the page still publishes.

Line merge, split, and delete still renumber. An empty region does not.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pdomain_book_tools.typography import GRAPHEME_SEGMENTATION_VERSION, TypographyCorrection

from pdomain_ocr_labeler_spa.core.typography_review import (
    TypographyBinding,
    TypographyCorrectionLog,
    stable_page_id,
    stable_word_id,
)

_BASE = "/api/projects/book1/pages/0"
_PAGE_SHA = "a" * 64
_IMAGE_SHA = "b" * 64
_HEAD_SHA = "c" * 64


def _word_ids_by_text(payload: dict[str, Any]) -> dict[str, str]:
    return {
        wm["ocr_text"]: wm["word_id"]
        for lm in payload["line_matches"]
        for wm in lm["word_matches"]
        if wm["word_id"] is not None
    }


def _correction_for(word_id: str, text: str) -> TypographyCorrection:
    text_sha = hashlib.sha256(text.encode()).hexdigest()
    return TypographyCorrection.model_validate(
        {
            "correction_id": "correction-1",
            "word_id": word_id,
            "revision": 1,
            "supersedes_id": None,
            "base_page_sha256": _PAGE_SHA,
            "base_image_sha256": _IMAGE_SHA,
            "base_text_sha256": text_sha,
            "base_word_revision": 0,
            "replacement_text_sha256": text_sha,
            "replacement_page_sha256": _PAGE_SHA,
            "replacement_image_sha256": _IMAGE_SHA,
            "replacement_page_head_sha256": _HEAD_SHA,
            "replacement_word_revision": 1,
            "taxonomy_version": "launch-1",
            "taxonomy_hash": "2" * 64,
            "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
            "page_head_sha256": _HEAD_SHA,
            "labeler_id": "reviewer@example.test",
            "decision": "approved_edit",
            "replacement": {
                "word_id": word_id,
                "text": text,
                "text_sha256": text_sha,
                "page_content_sha256": _PAGE_SHA,
                "image_artifact_sha256": _IMAGE_SHA,
                "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
                "taxonomy_version": "launch-1",
                "taxonomy_hash": "2" * 64,
                "label_states": {"italic": "positive"},
                "spans": [
                    {
                        "span_id": "span-1",
                        "label": "italic",
                        "start": 0,
                        "end": len(text),
                        "label_source": "human",
                        "confidence_tier": "gold",
                        "alignment_evidence_id": "human-review",
                    }
                ],
                "source_evidence_ids": ["human-review"],
                "whole_word_labels": ["italic"],
                "word_revision": 1,
                "review_state": "reviewed",
            },
        }
    )


def _binding(text: str) -> TypographyBinding:
    return TypographyBinding(
        page_sha256=_PAGE_SHA,
        image_sha256=_IMAGE_SHA,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        page_head_sha256=_HEAD_SHA,
        word_revision=0,
    )


def _make_region(client: Any) -> str:
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 0, "y": 0, "width": 200, "height": 300}},
    ).json()
    return next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])


def test_word_id_is_the_reading_order_position_not_the_word(toolbar_loaded: Any) -> None:
    """The premise, pinned: the published id is a hash of the word's *position*."""
    client, _ps, _page = toolbar_loaded
    ids = _word_ids_by_text(client.get(_BASE).json())
    page_id = stable_page_id(project_id="book1", page_index=0)

    # "three" is the third word on the page: line 0 holds "one", "two".
    assert ids["three"] == stable_word_id(project_id="book1", page_id=page_id, reading_order=2, text="three")


def test_creating_an_empty_region_leaves_every_word_id_alone(toolbar_loaded: Any) -> None:
    """Confirming a region by itself is safe: an empty region contributes a line
    with no words, so nothing is renumbered. Only *membership* moves words.
    """
    client, _ps, _page = toolbar_loaded
    before = _word_ids_by_text(client.get(_BASE).json())

    _make_region(client)

    assert _word_ids_by_text(client.get(_BASE).json()) == before


def test_a_membership_write_keeps_every_word_id(toolbar_loaded: Any) -> None:
    """Moving the page's first word into a region leaves every published id."""
    client, _ps, page = toolbar_loaded
    before = _word_ids_by_text(client.get(_BASE).json())
    region_id = _make_region(client)

    moved = client.put(
        f"{_BASE}/regions/{region_id}/words", json={"word_refs": [{"line_index": 0, "word_index": 0}]}
    )
    assert moved.status_code == 200, moved.text

    after = _word_ids_by_text(client.get(_BASE).json())
    assert set(after) == set(before)
    assert after == before
    assert {w.text for w in page.words} == set(before)


def test_a_recorded_typography_correction_stays_on_its_word(toolbar_loaded: Any) -> None:
    """A correction recorded before the membership write is still that word's head."""
    client, project_state, _page = toolbar_loaded
    project_root = Path(project_state.loaded_project.project_root)
    page_id = stable_page_id(project_id="book1", page_index=0)

    before = _word_ids_by_text(client.get(_BASE).json())
    original_id = before["three"]
    log = TypographyCorrectionLog(project_root)
    log.append(
        _correction_for(original_id, "three"),
        logical_page_id=page_id,
        current=_binding("three"),
    )
    assert log.head(page_id, original_id) is not None

    region_id = _make_region(client)
    assert (
        client.put(
            f"{_BASE}/regions/{region_id}/words",
            json={"word_refs": [{"line_index": 0, "word_index": 0}]},
        ).status_code
        == 200
    )

    after = _word_ids_by_text(client.get(_BASE).json())
    assert after["three"] == original_id
    assert original_id in set(after.values())
    assert log.head(page_id, original_id) is not None

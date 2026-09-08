"""What a membership write does to word identity — a pin, not a fix.

``stable_word_id`` is derived from ``reading_order``, a page-wide positional
counter over ``page.lines``, and ``TypographyCorrectionLog.head(logical_page_id,
word_id)`` looks corrections up by that id. A leaf region is a ``WORDS``-typed
``Block``, and ``Block.lines`` returns ``[self]`` for one, so a region joins
``page.lines``: moving a word into a region renumbers ``reading_order`` and
re-keys words that nobody touched.

**This fragility is pre-existing and is owned elsewhere.** ``api/lines_paragraphs.py``
already restructures ``page.lines`` on merge, split and delete, so the region
routes add a new trigger, not the flaw. Re-keying word identity off something
stable (the bounding-box signature ``ResolvedRegion.member_word_signatures``
already uses) is a different plan's work. These tests exist so the next person
to touch either side finds the interaction stated, measured, and un-silent —
delete them only together with the keying.
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


def test_a_membership_write_re_keys_every_word_on_the_page(toolbar_loaded: Any) -> None:
    """Observed behaviour, stated exactly: moving the page's *first* word into a
    region changes the ``word_id`` of **every** word on the page, not only the one
    that moved and not only the words after it. The region sorts into
    ``page.lines`` as its own line, the moved word lands at the end of the
    page-wide ``reading_order`` counter, and every other word shifts up by one.
    """
    client, _ps, page = toolbar_loaded
    before = _word_ids_by_text(client.get(_BASE).json())
    region_id = _make_region(client)

    moved = client.put(
        f"{_BASE}/regions/{region_id}/words", json={"word_refs": [{"line_index": 0, "word_index": 0}]}
    )
    assert moved.status_code == 200, moved.text

    after = _word_ids_by_text(client.get(_BASE).json())
    assert set(after) == set(before), "no word was lost — only its published id changed"
    changed = {text for text in before if after[text] != before[text]}
    assert changed == set(before), f"expected every word re-keyed, got {sorted(changed)}"
    # Nothing about the page's *text* changed; the words are all still there.
    assert {w.text for w in page.words} == set(before)


def test_a_recorded_typography_correction_detaches_from_its_word(toolbar_loaded: Any) -> None:
    """The consequence that matters: a correction recorded against a word before
    the membership write is no longer reachable from that word afterwards. The
    journal keeps it — nothing is lost on disk — but it is now filed under an id
    no word on the page carries. ``head`` for the word's *new* id is ``None``: the
    reviewer sees an unreviewed word and the correction becomes invisible.
    """
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
    new_id = after["three"]
    assert new_id != original_id
    # The record survives — under an id the page no longer uses.
    assert log.head(page_id, original_id) is not None
    assert original_id not in set(after.values())
    # And the word it described now reads as having no correction at all.
    assert log.head(page_id, new_id) is None

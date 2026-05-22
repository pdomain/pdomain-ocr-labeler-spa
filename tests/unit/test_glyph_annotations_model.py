"""Tests for GlyphAnnotationsModel (Pydantic) and WordMatch glyph fields.

Spec: specs/20-glyph-annotations.md §3, §4.2
Issue: ConcaveTrillion/pd-ocr-labeler-spa#267
"""

import json

from pd_ocr_labeler_spa.core.models import (
    GlyphAnnotationsModel,
    LigatureMarkModel,
    WordMatch,
)
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    parse_envelope,
    serialize_envelope,
)

# ---------------------------------------------------------------------------
# GlyphAnnotationsModel
# ---------------------------------------------------------------------------


def test_glyph_annotations_model_defaults() -> None:
    ga = GlyphAnnotationsModel()
    assert ga.ligatures == []
    assert ga.long_s_positions == []
    assert ga.swash is False
    assert ga.source == "human"


def test_glyph_annotations_model_with_source() -> None:
    ga = GlyphAnnotationsModel(source="predicted")
    assert ga.source == "predicted"


def test_glyph_annotations_model_empty_is_truthy() -> None:
    """Empty GlyphAnnotationsModel() is not None — the 'reviewed nothing' state."""
    ga = GlyphAnnotationsModel()
    assert ga is not None


def test_ligature_mark_model_round_trip() -> None:
    mark = LigatureMarkModel(kind="ct", char_span=(1, 3))
    d = mark.model_dump()
    assert d["kind"] == "ct"
    # Pydantic stores tuple as-is in model_dump; JSON serialisation renders as list.
    assert list(d["char_span"]) == [1, 3]


def test_ligature_mark_model_none_span() -> None:
    mark = LigatureMarkModel(kind="fi", char_span=None)
    assert mark.char_span is None


# ---------------------------------------------------------------------------
# WordMatch glyph fields
# ---------------------------------------------------------------------------


def test_word_match_glyph_annotations_field_default_none() -> None:
    """WordMatch.glyph_annotations defaults to None (not-yet-reviewed)."""
    from pd_ocr_labeler_spa.core.models import BBox, MatchStatus

    wm = WordMatch(
        line_index=0,
        word_index=0,
        ocr_text="test",
        ground_truth_text="test",
        match_status=MatchStatus.EXACT,
        bbox=BBox(x=0, y=0, width=10, height=10),
    )
    assert wm.glyph_annotations is None
    assert wm.glyph_predictions is None


def test_word_match_glyph_annotations_populated() -> None:
    from pd_ocr_labeler_spa.core.models import BBox, MatchStatus

    ga = GlyphAnnotationsModel(
        ligatures=[LigatureMarkModel(kind="ct", char_span=(0, 2))],
        long_s_positions=[1],
        swash=False,
        source="human",
    )
    wm = WordMatch(
        line_index=0,
        word_index=0,
        ocr_text="act",
        ground_truth_text="act",
        match_status=MatchStatus.EXACT,
        bbox=BBox(x=0, y=0, width=10, height=10),
        glyph_annotations=ga,
    )
    assert wm.glyph_annotations is not None
    assert wm.glyph_annotations.ligatures[0].kind == "ct"
    assert wm.glyph_annotations.source == "human"


# ---------------------------------------------------------------------------
# Envelope reader: WordMatch.glyph_annotations populated from word dicts
# ---------------------------------------------------------------------------


def test_page_to_line_matches_propagates_glyph_annotations() -> None:
    """page_to_line_matches propagates Word.glyph_annotations to WordMatch.glyph_annotations."""
    from pathlib import Path

    from pd_book_tools.geometry.bounding_box import BoundingBox
    from pd_book_tools.ocr.block import Block, BlockCategory, BlockChildType
    from pd_book_tools.ocr.glyph_annotations import GlyphAnnotations
    from pd_book_tools.ocr.page import Page
    from pd_book_tools.ocr.word import Word

    from pd_ocr_labeler_spa.core.page_to_line_matches import page_to_line_matches

    def make_bb(x: int, y: int, w: int, h: int) -> BoundingBox:
        return BoundingBox.from_ltrb(x, y, x + w, y + h)

    # Word with glyph_annotations populated
    w_annotated = Word(
        text="sword",
        bounding_box=make_bb(10, 10, 40, 15),
        ocr_confidence=0.9,
        glyph_annotations=GlyphAnnotations(
            long_s_positions=[0],
            swash=False,
        ),
    )
    w_annotated.ground_truth_text = "sword"

    # Word with None annotations (not yet reviewed)
    w_none = Word(
        text="the",
        bounding_box=make_bb(60, 10, 20, 15),
        ocr_confidence=0.95,
    )
    w_none.ground_truth_text = "the"

    # Build a page using Block(items=Words, child_type=WORDS, category=LINE)
    line_block = Block(
        items=[w_annotated, w_none],
        bounding_box=make_bb(0, 0, 200, 20),
        child_type=BlockChildType.WORDS,
        block_category=BlockCategory.LINE,
    )
    para_block = Block(
        items=[line_block],
        bounding_box=make_bb(0, 0, 200, 50),
        child_type=BlockChildType.BLOCKS,
        block_category=BlockCategory.PARAGRAPH,
    )
    page = Page(blocks=[para_block], width=800, height=1000, page_index=0)

    _rec, lms = page_to_line_matches(page, 0, Path("001.png"))
    assert lms, "expected at least one LineMatch"
    words_out = [wm for lm in lms for wm in lm.word_matches]
    assert len(words_out) >= 2

    # Find the word that had glyph_annotations
    annotated = next(
        (w for w in words_out if w.ocr_text == "sword"),
        None,
    )
    assert annotated is not None, "expected 'sword' word in output"
    assert annotated.glyph_annotations is not None, (
        "glyph_annotations should be propagated from Word to WordMatch"
    )
    assert annotated.glyph_annotations.long_s_positions == [0]

    # Find the word with None annotations
    none_word = next((w for w in words_out if w.ocr_text == "the"), None)
    assert none_word is not None
    assert none_word.glyph_annotations is None


# ---------------------------------------------------------------------------
# glyph_predictions NEVER written to envelope
# ---------------------------------------------------------------------------


def test_glyph_predictions_absent_in_saved_envelope(
    v22_envelope_str: str,
) -> None:
    """serialize_envelope must never write glyph_predictions into word dicts."""
    env = parse_envelope(v22_envelope_str)
    s = serialize_envelope(env)
    parsed = json.loads(s)
    for line in parsed["payload"]["page"]["lines"]:
        for word in line.get("words", []):
            assert "glyph_predictions" not in word, (
                f"glyph_predictions must not be persisted, but found in word: {word}"
            )


# ---------------------------------------------------------------------------
# Three-state preservation at WordMatch level
# ---------------------------------------------------------------------------


def test_three_state_preserved_in_word_matches() -> None:
    """None / empty / populated glyph_annotations are distinct at WordMatch level."""
    from pd_ocr_labeler_spa.core.models import BBox, MatchStatus

    none_wm = WordMatch(
        line_index=0,
        word_index=0,
        ocr_text="a",
        ground_truth_text="a",
        match_status=MatchStatus.EXACT,
        bbox=BBox(x=0, y=0, width=5, height=5),
    )
    empty_wm = WordMatch(
        line_index=0,
        word_index=1,
        ocr_text="b",
        ground_truth_text="b",
        match_status=MatchStatus.EXACT,
        bbox=BBox(x=0, y=0, width=5, height=5),
        glyph_annotations=GlyphAnnotationsModel(),
    )
    pop_wm = WordMatch(
        line_index=0,
        word_index=2,
        ocr_text="ct",
        ground_truth_text="ct",
        match_status=MatchStatus.EXACT,
        bbox=BBox(x=0, y=0, width=5, height=5),
        glyph_annotations=GlyphAnnotationsModel(ligatures=[LigatureMarkModel(kind="ct", char_span=None)]),
    )

    assert none_wm.glyph_annotations is None
    assert empty_wm.glyph_annotations is not None
    assert empty_wm.glyph_annotations.ligatures == []
    assert pop_wm.glyph_annotations is not None
    assert len(pop_wm.glyph_annotations.ligatures) == 1

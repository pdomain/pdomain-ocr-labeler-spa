"""Tests for glyph bulk-mark recipes.

Spec: specs/20-glyph-annotations.md §6.2
Issue: ConcaveTrillion/pd-ocr-labeler-spa#268
"""

from pd_ocr_labeler_spa.core.glyph.bulk_mark import (
    GlyphBulkMarkParams,
    apply_bulk_mark,
)

# ---------------------------------------------------------------------------
# CT substring recipe
# ---------------------------------------------------------------------------


def test_ct_recipe_marks_words_with_ct() -> None:
    """Every word whose GT contains 'ct' gets a CT LigatureMark."""
    words = [
        {"gt": "action", "line": 0, "word": 0},  # ct at 1-3
        {"gt": "the", "line": 0, "word": 1},  # no ct
        {"gt": "traction", "line": 0, "word": 2},  # ct at 3-5
        {"gt": "victory", "line": 0, "word": 3},  # ct at 2-4 (vi-ct-ory)
    ]
    result = apply_bulk_mark(words, GlyphBulkMarkParams(recipe="ct_substring"))
    affected = result["affected_word_ids"]
    # "action", "traction", "victory" all contain "ct"
    assert len(affected) == 3
    assert (0, 0) in affected  # action
    assert (0, 1) not in affected  # "the" has no ct
    assert (0, 2) in affected  # traction
    assert (0, 3) in affected  # victory


def test_ct_recipe_five_ct_words() -> None:
    """Acceptance: fixture with 5 ct words → affected count = 5."""
    words = [{"gt": "act", "line": 0, "word": i} for i in range(5)]
    result = apply_bulk_mark(words, GlyphBulkMarkParams(recipe="ct_substring"))
    assert len(result["affected_word_ids"]) == 5


def test_ct_recipe_dry_run_no_mutations() -> None:
    """dry_run=True returns preview count without mutating annotations."""
    words = [{"gt": "act", "line": 0, "word": 0}]
    result = apply_bulk_mark(words, GlyphBulkMarkParams(recipe="ct_substring", dry_run=True))
    assert len(result["affected_word_ids"]) == 1
    # No annotations written (dry run)
    assert result["annotations"] == {}


def test_ct_recipe_skips_already_annotated() -> None:
    """skip_already_annotated=True skips words that already have glyph_annotations."""
    existing = {"ligatures": [{"kind": "ct", "char_span": None}], "source": "human"}
    words = [
        {"gt": "act", "line": 0, "word": 0, "existing_annotations": existing},
        {"gt": "fact", "line": 0, "word": 1},
    ]
    result = apply_bulk_mark(words, GlyphBulkMarkParams(recipe="ct_substring", skip_already_annotated=True))
    # Only "fact" (word 1) is affected; "act" (word 0) is skipped
    assert (0, 0) not in result["affected_word_ids"]
    assert (0, 1) in result["affected_word_ids"]


# ---------------------------------------------------------------------------
# ST substring recipe
# ---------------------------------------------------------------------------


def test_st_recipe_marks_st_words() -> None:
    words = [
        {"gt": "first", "line": 0, "word": 0},
        {"gt": "the", "line": 0, "word": 1},
        {"gt": "last", "line": 0, "word": 2},
    ]
    result = apply_bulk_mark(words, GlyphBulkMarkParams(recipe="st_substring"))
    affected = result["affected_word_ids"]
    assert (0, 0) in affected  # first (st at 3-5)
    assert (0, 2) in affected  # last (st at 2-4)
    assert (0, 1) not in affected  # "the" has no st


# ---------------------------------------------------------------------------
# long_s_typeset_era recipe
# ---------------------------------------------------------------------------


def test_long_s_recipe_marks_eligible_s_positions() -> None:
    """s not at end-of-word and not before b/k/h/f gets marked."""
    words = [
        {"gt": "son", "line": 0, "word": 0},  # s at 0, not before b/k/h/f → mark
        {"gt": "ask", "line": 0, "word": 1},  # s at 0, followed by 'k' → skip
        {"gt": "rose", "line": 0, "word": 2},  # s at 2, not at end, not before b/k/h/f → mark
        {"gt": "is", "line": 0, "word": 3},  # s at 1 = end-of-word → skip
    ]
    result = apply_bulk_mark(words, GlyphBulkMarkParams(recipe="long_s_typeset_era"))
    affected = result["affected_word_ids"]
    assert (0, 0) in affected  # son
    assert (0, 1) not in affected  # ask (s before k)
    assert (0, 2) in affected  # rose (s in middle, not before excluded char)
    assert (0, 3) not in affected  # is (s at end)


# ---------------------------------------------------------------------------
# Annotations written to output
# ---------------------------------------------------------------------------


def test_bulk_mark_annotations_format() -> None:
    """Produced annotations have correct shape including source field."""
    words = [{"gt": "act", "line": 0, "word": 0}]
    result = apply_bulk_mark(words, GlyphBulkMarkParams(recipe="ct_substring"))
    assert (0, 0) in result["affected_word_ids"]
    ann = result["annotations"].get((0, 0))
    assert ann is not None
    assert ann["source"] == "human"
    assert len(ann["ligatures"]) >= 1
    assert ann["ligatures"][0]["kind"] == "ct"

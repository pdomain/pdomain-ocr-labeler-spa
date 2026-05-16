"""Tests for ``core/page_to_line_matches.py`` — Page → (PageRecord, LineMatch[]).

Spec authority:
- ``docs/architecture/01-data-models.md §1`` — ``PageRecord``, ``LineMatch``,
  ``WordMatch``, ``MatchStatus``, ``BBox`` shapes.
- ``docs/plan-to-usable.md`` B1 — first GET auto-triggers OCR + lifting.
- Legacy parity: ``pd_ocr_labeler/viewmodels/project/word_match_view_model.py``
  (``update_from_page``).

Issue: #330 (B1 auto-OCR on first GET).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from pd_ocr_labeler_spa.core.models import BBox, MatchStatus, PageSource
from pd_ocr_labeler_spa.core.page_to_line_matches import page_to_line_matches

# ── Stub types ──────────────────────────────────────────────────────────


@dataclass
class _StubBbox:
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 10.0
    max_y: float = 5.0
    is_normalized: bool = False

    @property
    def minX(self) -> float:  # noqa: N802
        return self.min_x

    @property
    def minY(self) -> float:  # noqa: N802
        return self.min_y

    @property
    def maxX(self) -> float:  # noqa: N802
        return self.max_x

    @property
    def maxY(self) -> float:  # noqa: N802
        return self.max_y


@dataclass
class _StubWord:
    text: str = ""
    ground_truth_text: str = ""
    bounding_box: Any = None
    text_style_labels: list[str] = field(default_factory=list)
    word_components: list[str] = field(default_factory=list)
    word_labels: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.bounding_box is None:
            self.bounding_box = _StubBbox()


@dataclass
class _StubLine:
    words: list[_StubWord] = field(default_factory=list)
    ground_truth_text: str = ""
    unmatched_ground_truth_words: list[tuple[int, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class _StubParagraph:
    lines: list[_StubLine] = field(default_factory=list)


@dataclass
class _StubBlock:
    paragraphs: list[_StubParagraph] = field(default_factory=list)


@dataclass
class _StubPage:
    lines_: list[_StubLine] = field(default_factory=list)
    paragraphs_: list[_StubParagraph] = field(default_factory=list)
    items_: list[_StubBlock] = field(default_factory=list)

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubParagraph]:
        return self.paragraphs_

    @property
    def items(self) -> list[_StubBlock]:
        return self.items_


_IMAGE = Path("/tmp/test.png")


# ── Basic contract ──────────────────────────────────────────────────────


def test_none_page_returns_empty_line_matches() -> None:
    record, lms = page_to_line_matches(None, 0, _IMAGE)
    assert lms == []
    assert record.page_index == 0
    assert record.page_number == 1
    assert record.image_path == _IMAGE
    assert record.page_source == PageSource.OCR


def test_empty_page_returns_empty_line_matches() -> None:
    page = _StubPage()
    _record, lms = page_to_line_matches(page, 0, _IMAGE)
    assert lms == []


def test_single_line_exact_match() -> None:
    word = _StubWord(text="hello", ground_truth_text="hello")
    line = _StubLine(words=[word], ground_truth_text="hello")
    page = _StubPage(lines_=[line])

    _record, lms = page_to_line_matches(page, 0, _IMAGE)

    assert len(lms) == 1
    lm = lms[0]
    assert lm.line_index == 0
    assert lm.ocr_line_text == "hello"
    assert lm.ground_truth_line_text == "hello"
    assert len(lm.word_matches) == 1
    wm = lm.word_matches[0]
    assert wm.match_status == MatchStatus.EXACT
    assert wm.ocr_text == "hello"
    assert wm.ground_truth_text == "hello"
    assert wm.line_index == 0
    assert wm.word_index == 0


def test_single_line_unmatched_ocr_when_no_gt() -> None:
    word = _StubWord(text="hello", ground_truth_text="")
    line = _StubLine(words=[word])
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE)

    assert len(lms) == 1
    wm = lms[0].word_matches[0]
    assert wm.match_status == MatchStatus.UNMATCHED_OCR


def test_single_line_mismatch() -> None:
    word = _StubWord(text="hello", ground_truth_text="world")
    line = _StubLine(words=[word], ground_truth_text="world")
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE)

    wm = lms[0].word_matches[0]
    assert wm.match_status == MatchStatus.MISMATCH


def test_line_with_no_words_is_skipped() -> None:
    line = _StubLine(words=[], ground_truth_text="")
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE)
    assert lms == []


def test_page_record_has_correct_page_index() -> None:
    page = _StubPage()
    record, _ = page_to_line_matches(page, 3, _IMAGE, source=PageSource.CACHED_OCR)
    assert record.page_index == 3
    assert record.page_number == 4
    assert record.page_source == PageSource.CACHED_OCR


def test_paragraph_index_populated() -> None:
    word = _StubWord(text="a", ground_truth_text="a")
    line1 = _StubLine(words=[word])
    line2 = _StubLine(words=[_StubWord(text="b", ground_truth_text="b")])
    para0 = _StubParagraph(lines=[line1])
    para1 = _StubParagraph(lines=[line2])
    page = _StubPage(lines_=[line1, line2], paragraphs_=[para0, para1])

    _, lms = page_to_line_matches(page, 0, _IMAGE)
    assert len(lms) == 2
    assert lms[0].paragraph_index == 0
    assert lms[1].paragraph_index == 1


def test_unmatched_gt_words_inserted() -> None:
    word = _StubWord(text="hello", ground_truth_text="hello")
    # Unmatched GT word inserted at position 1 (after word 0)
    line = _StubLine(words=[word], unmatched_ground_truth_words=[(0, "extra")])
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE)
    assert len(lms) == 1
    wms = lms[0].word_matches
    assert len(wms) == 2
    # Unmatched GT is inserted at clamped position 0 (sorted reverse => insert at 0)
    unmatched = next((w for w in wms if w.match_status == MatchStatus.UNMATCHED_GT), None)
    assert unmatched is not None
    assert unmatched.ground_truth_text == "extra"
    assert unmatched.ocr_text == ""


def test_word_bbox_converted_correctly() -> None:
    bbox = _StubBbox(min_x=10.0, min_y=20.0, max_x=50.0, max_y=60.0)
    word = _StubWord(text="test", ground_truth_text="test", bounding_box=bbox)
    line = _StubLine(words=[word])
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE)
    wm = lms[0].word_matches[0]
    assert wm.bbox == BBox(x=10, y=20, width=40, height=40)


class _NoBboxWord:
    """Stub word with no bounding_box attribute at all."""

    text = "test"
    ground_truth_text = "test"
    text_style_labels: ClassVar[list[str]] = []
    word_components: ClassVar[list[str]] = []
    word_labels: ClassVar[list[str]] = []
    bounding_box = None


def test_word_without_bbox_skipped() -> None:
    word = _NoBboxWord()
    line = _StubLine(words=[word])  # type: ignore[list-item]
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE)
    # Word without bbox is skipped; line becomes empty; line is skipped
    assert lms == []


def test_line_level_counts() -> None:
    exact = _StubWord(text="a", ground_truth_text="a")
    mismatch = _StubWord(text="b", ground_truth_text="c")
    line = _StubLine(words=[exact, mismatch], ground_truth_text="a c")
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE)
    lm = lms[0]
    assert lm.exact_count == 1
    assert lm.mismatch_count == 1
    assert lm.total_word_count == 2
    assert lm.overall_match_status == MatchStatus.MISMATCH
    assert lm.is_fully_validated is False


def test_multiple_lines() -> None:
    words1 = [_StubWord(text="one", ground_truth_text="one")]
    words2 = [_StubWord(text="two", ground_truth_text="two")]
    page = _StubPage(
        lines_=[
            _StubLine(words=words1, ground_truth_text="one"),
            _StubLine(words=words2, ground_truth_text="two"),
        ]
    )

    _, lms = page_to_line_matches(page, 0, _IMAGE)
    assert len(lms) == 2
    assert lms[0].line_index == 0
    assert lms[1].line_index == 1


# ── fuzz_threshold parameter ────────────────────────────────────────────


@dataclass
class _FuzzyWord(_StubWord):
    """Stub word that returns a fixed fuzz score from ``fuzz_score_against``."""

    _fuzz_score: float = 0.7

    def fuzz_score_against(self, gt_text: str) -> float:
        """Return a controlled fuzz score for threshold testing."""
        return self._fuzz_score


def test_fuzz_threshold_high_makes_fuzzy_score_mismatch() -> None:
    """fuzz_threshold=1.0 (exact-match-only) causes score=0.7 -> MISMATCH."""
    word = _FuzzyWord(text="e", ground_truth_text="epsilon", _fuzz_score=0.7)
    line = _StubLine(words=[word])
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE, fuzz_threshold=1.0)
    assert len(lms) == 1
    wm = lms[0].word_matches[0]
    assert wm.match_status == MatchStatus.MISMATCH
    assert wm.fuzz_score == 0.7


def test_fuzz_threshold_low_makes_fuzzy_score_fuzzy() -> None:
    """fuzz_threshold=0.5 causes score=0.7 -> FUZZY (not MISMATCH)."""
    word = _FuzzyWord(text="e", ground_truth_text="epsilon", _fuzz_score=0.7)
    line = _StubLine(words=[word])
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE, fuzz_threshold=0.5)
    assert len(lms) == 1
    wm = lms[0].word_matches[0]
    assert wm.match_status == MatchStatus.FUZZY
    assert wm.fuzz_score == 0.7


def test_fuzz_threshold_default_boundary() -> None:
    """Default threshold 0.8: score=0.8 exactly -> FUZZY; score=0.79 -> MISMATCH."""
    word_above = _FuzzyWord(text="abc", ground_truth_text="abcd", _fuzz_score=0.8)
    word_below = _FuzzyWord(text="abc", ground_truth_text="abcd", _fuzz_score=0.79)

    line_above = _StubLine(words=[word_above])
    line_below = _StubLine(words=[word_below])
    page = _StubPage(lines_=[line_above, line_below])

    _, lms = page_to_line_matches(page, 0, _IMAGE)  # default threshold 0.8
    assert lms[0].word_matches[0].match_status == MatchStatus.FUZZY
    assert lms[1].word_matches[0].match_status == MatchStatus.MISMATCH


def test_fuzz_threshold_app_config_field() -> None:
    """AppConfig.fuzz_threshold field: default 0.8, configurable, round-trips."""
    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig

    # Default must be 0.8 (legacy parity).
    cfg_default = AppConfig()
    assert cfg_default.fuzz_threshold == 0.8

    # Custom value.
    cfg_custom = AppConfig(fuzz_threshold=0.5)
    assert cfg_custom.fuzz_threshold == 0.5

    # Round-trip through model_dump / dict load (simulating YAML parse).
    cfg_from_dict = AppConfig(**{"fuzz_threshold": 0.9})
    assert cfg_from_dict.fuzz_threshold == 0.9


# ── block_index round-trip (FO-7 / CU-4.1) ─────────────────────────────


def test_line_match_carries_block_index() -> None:
    """Each LineMatch must carry the block_index of its parent layout block.

    FO-7: ``page.items`` exposes the block layer (list of blocks, each with
    ``.paragraphs`` → ``.lines``).  ``page_to_line_matches`` must tag each
    produced ``LineMatch`` with the 0-based index of the block that contains
    the underlying line object.
    """
    word_a = _StubWord(text="a", ground_truth_text="a")
    word_b = _StubWord(text="b", ground_truth_text="b")
    word_c = _StubWord(text="c", ground_truth_text="c")

    line_a = _StubLine(words=[word_a])
    line_b = _StubLine(words=[word_b])
    line_c = _StubLine(words=[word_c])

    para0 = _StubParagraph(lines=[line_a])
    para1 = _StubParagraph(lines=[line_b, line_c])

    # Block 0 → para0 → line_a
    # Block 1 → para1 → line_b, line_c
    block0 = _StubBlock(paragraphs=[para0])
    block1 = _StubBlock(paragraphs=[para1])

    page = _StubPage(
        lines_=[line_a, line_b, line_c],
        paragraphs_=[para0, para1],
        items_=[block0, block1],
    )

    _, lms = page_to_line_matches(page, 0, _IMAGE)

    assert len(lms) == 3
    assert [lm.block_index for lm in lms] == [0, 1, 1]


def test_line_match_block_index_none_when_no_items() -> None:
    """When page has no ``.items`` attribute, block_index stays None on all LineMatches."""
    word = _StubWord(text="x", ground_truth_text="x")
    line = _StubLine(words=[word])
    # _StubPage with no items_ (empty) — items property returns []
    page = _StubPage(lines_=[line])

    _, lms = page_to_line_matches(page, 0, _IMAGE)

    assert len(lms) == 1
    assert lms[0].block_index is None

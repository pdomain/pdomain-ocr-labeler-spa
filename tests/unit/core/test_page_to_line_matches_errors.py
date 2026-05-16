"""Tests for error-path behaviour in page_to_line_matches.

Every test targets a path previously marked # pragma: no cover - defensive.
After this task those paths are covered and the pragma comments are removed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

from pd_ocr_labeler_spa.core.page_to_line_matches import page_to_line_matches

IMAGE_PATH = Path("/fake/image.png")


class _NoLines:
    """Object with no .lines attribute — simulates a UserPageEnvelope passed by mistake."""

    payload: ClassVar[object] = object()  # has .payload but no .lines


def test_wrong_type_logs_warning(caplog):
    """Non-None page without .lines logs WARNING, returns empty line_matches."""
    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        _record, lms = page_to_line_matches(_NoLines(), 0, IMAGE_PATH)
    assert lms == []
    assert any("no 'lines' attribute" in m or "lines" in m.lower() for m in caplog.messages), (
        f"Expected warning about missing 'lines' attribute, got: {caplog.messages}"
    )


def test_none_page_returns_empty_no_warning(caplog):
    """None page is the documented degraded path — no warning emitted."""
    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        _record, lms = page_to_line_matches(None, 0, IMAGE_PATH)
    assert lms == []
    # No warning for the documented None case
    assert not any("lines" in m.lower() for m in caplog.messages), (
        f"Unexpected warning for None page: {caplog.messages}"
    )


def test_word_missing_bbox_logs_warning(caplog):
    """A word with no bounding_box is skipped with a WARNING (not DEBUG)."""

    class _Word:
        text = "hello"
        ground_truth_text = ""
        bounding_box = None
        word_labels: ClassVar[list] = []
        text_style_labels: ClassVar[list] = []
        word_components: ClassVar[list] = []
        fuzz_score_against = None

    class _Line:
        words: ClassVar[list] = [_Word()]

    class _Page:
        lines: ClassVar[list] = [_Line()]
        paragraphs: ClassVar[list] = []
        items: ClassVar[list] = []

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        _record, lms = page_to_line_matches(_Page(), 0, IMAGE_PATH)

    assert lms == []
    assert any(
        "bbox" in m.lower() or "bounding_box" in m.lower() or "dropped" in m.lower() for m in caplog.messages
    ), f"Expected warning about dropped word, got: {caplog.messages}"


def test_fuzz_scorer_raises_logs_warning(caplog):
    """When word.fuzz_score_against raises, logs WARNING (not just DEBUG)."""

    class _BBox:
        minX = 0  # noqa: N815
        minY = 0  # noqa: N815
        maxX = 10  # noqa: N815
        maxY = 10  # noqa: N815

    class _Word:
        text = "hello"
        ground_truth_text = "world"
        bounding_box = _BBox()
        word_labels: ClassVar[list] = []
        text_style_labels: ClassVar[list] = []
        word_components: ClassVar[list] = []

        def fuzz_score_against(self, gt: str) -> float:
            raise RuntimeError("scorer broken")

    class _Line:
        words: ClassVar[list] = [_Word()]

    class _Page:
        lines: ClassVar[list] = [_Line()]
        paragraphs: ClassVar[list] = []
        items: ClassVar[list] = []

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        _record, lms = page_to_line_matches(_Page(), 0, IMAGE_PATH)

    assert len(lms) == 1  # word still appears (MISMATCH with score 0)
    assert any("fuzz" in m.lower() for m in caplog.messages), (
        f"Expected warning about fuzz scorer failure, got: {caplog.messages}"
    )


def test_paragraph_lookup_failure_logs_warning(caplog, monkeypatch):
    """When _build_line_to_paragraph_lookup raises, logs WARNING."""
    import pd_ocr_labeler_spa.core.page_to_line_matches as _mod

    def _bad_lookup(page):
        raise RuntimeError("lookup broken")

    monkeypatch.setattr(_mod, "_build_line_to_paragraph_lookup", _bad_lookup)

    class _BBox:
        minX = 0  # noqa: N815
        minY = 0  # noqa: N815
        maxX = 10  # noqa: N815
        maxY = 10  # noqa: N815

    class _Word:
        text = "hi"
        ground_truth_text = ""
        bounding_box = _BBox()
        word_labels: ClassVar[list] = []
        text_style_labels: ClassVar[list] = []
        word_components: ClassVar[list] = []
        fuzz_score_against = None

    class _Line:
        words: ClassVar[list] = [_Word()]

    class _Page:
        lines: ClassVar[list] = [_Line()]
        paragraphs: ClassVar[list] = []
        items: ClassVar[list] = []

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.page_to_line_matches"):
        _record, _lms = page_to_line_matches(_Page(), 0, IMAGE_PATH)

    assert any("paragraph" in m.lower() or "lookup" in m.lower() for m in caplog.messages), (
        f"Expected warning about lookup failure, got: {caplog.messages}"
    )

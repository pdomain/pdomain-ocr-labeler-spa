"""Unit tests for the poetry region detector.

Fixture shape follows ``test_furniture.py``: pages built from dicts through
``Page.from_dict``, boxes as pixel-space (not normalized). Page is 1000x1600;
the book's fitted text block runs from ``text_left_px=100`` to
``text_right_px=900`` (width 800px) unless a test says otherwise — chosen so
the thresholds below land on convenient pixel values:

- ``RAGGED_RIGHT_EDGE_MAD_THRESHOLD_FRAC`` (0.008) x 800 = 6.4px of right-edge MAD.
- ``INDENT_THRESHOLD_FRAC_OF_TEXT_WIDTH`` (0.03) x 800 = 24px of indent.
"""

from __future__ import annotations

from typing import Any

_PAGE_WIDTH = 1000
_PAGE_HEIGHT = 1600
_TEXT_LEFT_PX = 100
_TEXT_RIGHT_PX = 900


def _bbox(left: float, top: float, right: float, bottom: float) -> dict[str, object]:
    return {
        "top_left": {"x": left, "y": top},
        "bottom_right": {"x": right, "y": bottom},
        "is_normalized": False,
    }


def _word(text: str, left: float, top: float, right: float, bottom: float) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(left, top, right, bottom),
    }


def _line(text: str, left: float, top: float, right: float, bottom: float) -> dict[str, object]:
    """One line: a single word spanning the whole line box, so the line's own
    right edge (what the geometry signal reads) is exactly ``right``."""
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": [_word(text, left, top, right, bottom)],
        "bounding_box": _bbox(left, top, right, bottom),
    }


def _paragraph(lines: list[dict[str, object]]) -> dict[str, object]:
    def _edge(line: dict[str, object], corner: str, axis: str) -> float:
        box = line["bounding_box"]
        assert isinstance(box, dict)
        point = box[corner]
        assert isinstance(point, dict)
        value = point[axis]
        assert isinstance(value, (int, float))
        return value

    left = min(_edge(line, "top_left", "x") for line in lines)
    top = min(_edge(line, "top_left", "y") for line in lines)
    right = max(_edge(line, "bottom_right", "x") for line in lines)
    bottom = max(_edge(line, "bottom_right", "y") for line in lines)
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "items": lines,
        "bounding_box": _bbox(left, top, right, bottom),
    }


def _page(paragraphs: list[dict[str, object]]) -> Any:
    from pdomain_book_tools.ocr.page import Page

    return Page.from_dict(
        {
            "width": _PAGE_WIDTH,
            "height": _PAGE_HEIGHT,
            "page_index": 0,
            "bounding_box": _bbox(0, 0, _PAGE_WIDTH, _PAGE_HEIGHT),
            "items": paragraphs,
        }
    )


def _input(page: Any, *, text_left_px: float = _TEXT_LEFT_PX, text_right_px: float = _TEXT_RIGHT_PX) -> Any:
    from pdomain_pgdp_measure.page_templates import BookTemplates, PageClassification, PageTemplate
    from pdomain_pgdp_measure.profile_models import PageMeasurement, ProfileDiagnostic

    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput

    template = PageTemplate(
        page_class="normal_recto",
        first_band_top_px=100,
        first_band_spread_px=6,
        text_left_px=int(text_left_px),
        text_right_px=int(text_right_px),
        band_count=30,
        page_count=200,
        page_share=0.5,
    )
    measurement = PageMeasurement(
        page_name="001.png",
        source_path="book1/001.png",
        sha256=None,
        source_frame=None,
        image_mode=None,
        grayscale_threshold=None,
        foreground_pixels=None,
        foreground_bounds=None,
        margins=None,
        ink_bands=None,
        diagnostics=(ProfileDiagnostic(code="image_missing", message="test fixture"),),
    )
    return DetectorInput(
        page=page,
        page_index=0,
        measurement=measurement,
        classification=PageClassification("001.png", "normal_recto", None, (), 0.9),
        templates=BookTemplates(100.0, 4.0, 16.0, (template,), 0.9),
    )


def test_verse_with_ragged_right_edges_and_capitalized_lines_is_found() -> None:
    """A realistic stanza: indented, ragged, every line capitalized.

    Also pins that indentation on both sides — which real verse usually
    carries, per the note — does not gate the decision: ``indented_both`` is
    True here alongside ``is_poetry`` True, decided by text.
    """
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.poetry import (
        GEOMETRY_RULE_PRECISION,
        TEXT_RULE_PRECISION,
        poetry_region_detector,
    )

    lines = [
        _line("Roses Are Red,", 200, 100, 500, 125),
        _line("Violets Are Blue,", 200, 130, 650, 155),
        _line("Sugar Is Sweet,", 200, 160, 550, 185),
        _line("And So Are You.", 200, 190, 700, 215),
    ]
    page = _page([_paragraph(lines)])
    detected = poetry_region_detector(_input(page))

    assert len(detected) == 1
    region = detected[0]
    assert region.role is RegionRole.POETRY
    assert region.confidence == TEXT_RULE_PRECISION
    assert region.confidence != GEOMETRY_RULE_PRECISION
    assert region.evidence["decided_by"] == "text"
    assert region.evidence["ragged"] is True
    assert region.evidence["indented_left"] is True
    assert region.evidence["indented_right"] is True
    assert region.evidence["indented_both"] is True
    assert region.evidence["cap_frac"] == 1.0


def test_justified_prose_is_not_found() -> None:
    """Ordinary wrapped prose: flush right edges, only the first line capitalized."""
    from pdomain_ocr_labeler_spa.core.regions.poetry import poetry_region_detector

    lines = [
        _line("The quick brown fox jumps", 105, 100, 895, 125),
        _line("over the lazy dog while", 105, 130, 893, 155),
        _line("pondering life the universe", 105, 160, 896, 185),
        _line("and everything in general.", 105, 190, 894, 215),
    ]
    page = _page([_paragraph(lines)])
    detected = poetry_region_detector(_input(page))

    assert detected == []


def test_indented_both_sides_but_justified_is_not_found_even_with_unreadable_text() -> None:
    """The awkward middle the measurement warns about.

    Indented on both sides (the roadmap's literal, wrong blockquote/poetry
    rule would fire here) but its right edge is consistent (justified), not
    ragged — and its OCR text is unusable (garbled to punctuation only), so
    the detector falls back to geometry alone. Pins that raggedness, not
    indent, is what the geometry signal gates on: a naive "indented on both
    sides" rule would have misfired on this block; this detector does not.
    """
    from pdomain_ocr_labeler_spa.core.regions.poetry import poetry_region_detector

    lines = [
        _line("...", 300, 100, 700, 125),
        _line("...", 300, 130, 701, 155),
        _line("...", 300, 160, 699, 185),
        _line("...", 300, 190, 700, 215),
    ]
    page = _page([_paragraph(lines)])
    detected = poetry_region_detector(_input(page))

    assert detected == []


def test_a_short_stanza_too_short_for_raggedness_is_still_found_by_text() -> None:
    """Two lines, right edges nearly flush (raggedness reads false), but both
    capitalized — the note's own example of geometry missing what text catches."""
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.poetry import TEXT_RULE_PRECISION, poetry_region_detector

    lines = [
        _line("Yet Deem Not Aught But Virgin Love", 150, 100, 700, 125),
        _line("That Bosom E'er Could Venture In", 150, 130, 703, 155),
    ]
    page = _page([_paragraph(lines)])
    detected = poetry_region_detector(_input(page))

    assert len(detected) == 1
    region = detected[0]
    assert region.role is RegionRole.POETRY
    assert region.confidence == TEXT_RULE_PRECISION
    assert region.evidence["decided_by"] == "text"
    assert region.evidence["ragged"] is False


def test_ragged_geometry_is_found_when_ocr_text_is_unusable() -> None:
    """Raggedness alone catches a poem when its OCR text is too degraded to trust."""
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.poetry import GEOMETRY_RULE_PRECISION, poetry_region_detector

    lines = [
        _line("...", 200, 100, 500, 125),
        _line("...", 200, 130, 650, 155),
        _line("...", 200, 160, 550, 185),
        _line("...", 200, 190, 700, 215),
    ]
    page = _page([_paragraph(lines)])
    detected = poetry_region_detector(_input(page))

    assert len(detected) == 1
    region = detected[0]
    assert region.role is RegionRole.POETRY
    assert region.confidence == GEOMETRY_RULE_PRECISION
    assert region.evidence["decided_by"] == "geometry"
    assert region.evidence["text_rule_reliable"] is False


def test_a_single_line_block_is_never_proposed() -> None:
    """Raggedness cannot be measured on one line, and the text rule's own
    precision was never scored below two lines either — neither signal
    applies, so a one-line block is skipped outright."""
    from pdomain_ocr_labeler_spa.core.regions.poetry import poetry_region_detector

    lines = [_line("A Single Capitalized Line", 200, 100, 700, 125)]
    page = _page([_paragraph(lines)])
    detected = poetry_region_detector(_input(page))

    assert detected == []


def test_no_matching_template_proposes_nothing() -> None:
    """No book template for the page's own class — nothing to measure against."""
    from pdomain_pgdp_measure.page_templates import BookTemplates, PageClassification
    from pdomain_pgdp_measure.profile_models import PageMeasurement, ProfileDiagnostic

    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput
    from pdomain_ocr_labeler_spa.core.regions.poetry import poetry_region_detector

    lines = [
        _line("Roses Are Red,", 200, 100, 500, 125),
        _line("Violets Are Blue,", 200, 130, 650, 155),
    ]
    page = _page([_paragraph(lines)])
    measurement = PageMeasurement(
        page_name="001.png",
        source_path="book1/001.png",
        sha256=None,
        source_frame=None,
        image_mode=None,
        grayscale_threshold=None,
        foreground_pixels=None,
        foreground_bounds=None,
        margins=None,
        ink_bands=None,
        diagnostics=(ProfileDiagnostic(code="image_missing", message="test fixture"),),
    )
    detector_input = DetectorInput(
        page=page,
        page_index=0,
        measurement=measurement,
        classification=PageClassification("001.png", "unknown", None, (), None),
        templates=BookTemplates(None, None, None, (), 0.0),
    )
    assert poetry_region_detector(detector_input) == []


def test_poetry_detector_declares_it_depends_on_word_text() -> None:
    """Unlike a pure-geometry detector, this one reads OCR text — provenance
    must say so, or a text-only edit would never mark its proposals stale."""
    from pdomain_ocr_labeler_spa.core.regions.models import (
        FACET_LINE_STRUCTURE,
        FACET_PAGE_IMAGE,
        FACET_WORD_BOXES,
        FACET_WORD_TEXT,
    )
    from pdomain_ocr_labeler_spa.core.regions.poetry import PoetryDetector

    detector = PoetryDetector()
    assert detector.depends_on_facets == frozenset(
        {FACET_WORD_BOXES, FACET_LINE_STRUCTURE, FACET_PAGE_IMAGE, FACET_WORD_TEXT}
    )


def test_poetry_detector_is_callable_as_a_region_detector() -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.poetry import PoetryDetector

    lines = [
        _line("Roses Are Red,", 200, 100, 500, 125),
        _line("Violets Are Blue,", 200, 130, 650, 155),
    ]
    page = _page([_paragraph(lines)])
    detected = PoetryDetector()(_input(page))

    assert len(detected) == 1
    assert detected[0].role is RegionRole.POETRY

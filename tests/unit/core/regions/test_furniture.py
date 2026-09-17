"""Unit tests for the top-furniture region detector."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.page import Page
from pdomain_pgdp_measure.page_templates import (
    BookTemplates,
    PageClass,
    PageClassification,
    PageTemplate,
)
from pdomain_pgdp_measure.profile_models import CoordinateFrame, InkBand, PageMeasurement, ProfileDiagnostic

_PAGE_WIDTH = 1000
_PAGE_HEIGHT = 1600


# Pages are built from dicts through ``Page.from_dict``, the way
# tests/integration/conftest.py does. ``Word.__init__`` takes ``text``
# positionally and has no ``ocr_text`` parameter, and ``Block.__init__`` takes
# ``items`` first — the dict form sidesteps both and is what the repo already
# uses everywhere.
# Coordinates are ``float`` rather than ``int``: a normalized box carries
# fractions, and basedpyright rejects ``0.1`` against an ``int`` parameter.
def _bbox(
    left: float, top: float, right: float, bottom: float, *, normalized: bool = False
) -> dict[str, object]:
    return {
        "top_left": {"x": left, "y": top},
        "bottom_right": {"x": right, "y": bottom},
        "is_normalized": normalized,
    }


def _word(
    text: str, left: float, top: float, right: float, bottom: float, *, normalized: bool = False
) -> dict[str, object]:
    return {
        "type": "Word",
        "text": text,
        "ground_truth_text": text,
        "bounding_box": _bbox(left, top, right, bottom, normalized=normalized),
    }


def _line(words: list[dict[str, object]]) -> dict[str, object]:
    # The container boxes stay pixel-space even when the words are normalized.
    # A box marked normalized must have coordinates inside [0, 1], and a page
    # box of 1000 by 1600 does not; ``Page.is_content_normalized`` reads only
    # word boxes, so the containers' convention never matters to it.
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": _bbox(0, 0, _PAGE_WIDTH, _PAGE_HEIGHT),
    }


def _page(*lines: list[dict[str, object]]) -> Page:
    return Page.from_dict(
        {
            "width": _PAGE_WIDTH,
            "height": _PAGE_HEIGHT,
            "page_index": 0,
            "bounding_box": _bbox(0, 0, _PAGE_WIDTH, _PAGE_HEIGHT),
            "items": [_line(list(words)) for words in lines],
        }
    )


def _templates() -> BookTemplates:
    template = PageTemplate(
        page_class="normal_recto",
        first_band_top_px=100,
        first_band_spread_px=6,
        text_left_px=100,
        text_right_px=900,
        band_count=30,
        page_count=200,
        page_share=0.5,
    )
    return BookTemplates(100.0, 4.0, 16.0, (template,), 0.9)


# ``PageMeasurement.__post_init__`` enforces coherence: a measurement carrying
# ink bands must also carry the image metadata, foreground pixels, bounds and
# margins that could only come from a decoded image, and the margins must equal
# the bounds inset into the source frame. This shape satisfies all of it; I
# constructed it against the real class to check.
def _measurement(
    bands: tuple[InkBand, ...], *, source_frame: CoordinateFrame | None = None
) -> PageMeasurement:
    frame = (
        source_frame if source_frame is not None else CoordinateFrame(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
    )
    return PageMeasurement(
        page_name="001.png",
        source_path="book1/001.png",
        sha256="a" * 64,
        source_frame=frame,
        image_mode="L",
        grayscale_threshold=128,
        foreground_pixels=50_000,
        foreground_bounds=(100, 100, 900, 1500),
        margins=(100, 100, frame.width - 900, frame.height - 1500),
        ink_bands=bands,
        page_class="normal_recto",
    )


def _input(
    words: list[dict[str, object]],
    *,
    bands: tuple[InkBand, ...] = (InkBand(100, 130),),
    ordinals: tuple[int, ...] = (0,),
    page_class: PageClass = "normal_recto",
    confidence: float | None = 0.9,
    extra_line: list[dict[str, object]] | None = None,
    source_frame: CoordinateFrame | None = None,
) -> Any:
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput

    lines = [words] if extra_line is None else [words, extra_line]
    return DetectorInput(
        page=_page(*lines),
        page_index=0,
        measurement=_measurement(bands, source_frame=source_frame),
        classification=PageClassification("001.png", page_class, 2, ordinals, confidence),
        templates=_templates(),
    )


def test_a_running_head_and_a_folio_become_two_regions() -> None:
    """Hierarchy rule 3: they are always separate blocks, same physical line or not."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [
        _word("THE", 100, 105, 170, 125),
        _word("VOYAGE", 180, 105, 320, 125),
        _word("17", 870, 105, 900, 125),
    ]
    detected = furniture_region_detector(_input(words))

    assert len(detected) == 2
    head, folio = detected
    assert head.role is RegionRole.PAGE_HEADER
    assert head.box == (100, 105, 320, 125)
    assert head.confidence == 0.6
    assert folio.role is RegionRole.PAGE_NUMBER
    assert folio.box == (870, 105, 900, 125)
    assert folio.confidence == 0.8


def test_a_roman_numeral_folio_is_a_page_number() -> None:
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [
        _word("PREFACE", 100, 105, 260, 125),
        _word("xvii", 860, 105, 900, 125),
    ]
    detected = furniture_region_detector(_input(words))
    assert [d.role for d in detected] == [RegionRole.PAGE_HEADER, RegionRole.PAGE_NUMBER]


def test_a_page_with_no_furniture_bands_proposes_nothing() -> None:
    """An unclassified page and a chapter opening both record no furniture bands."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [_word("THE", 100, 105, 170, 125)]
    assert furniture_region_detector(_input(words, ordinals=())) == []


def test_words_below_the_furniture_band_are_not_furniture() -> None:
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [
        _word("THE", 100, 105, 170, 125),
        _word("body", 100, 400, 190, 420),
    ]
    detected = furniture_region_detector(_input(words))
    assert len(detected) == 1
    assert detected[0].box == (100, 105, 170, 125)


def test_a_lone_wide_cluster_is_a_header_at_reduced_confidence() -> None:
    """Confidence scores the cluster's own shape, not the page's template fit.

    ``classification.confidence`` answers "does this page fit its book", not
    "is this band a running head" — see furniture.py's module comment on the
    three confidence constants.
    """
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [_word("THE", 100, 105, 170, 125), _word("VOYAGE", 180, 105, 320, 125)]
    detected = furniture_region_detector(_input(words, confidence=0.9))
    assert len(detected) == 1
    assert detected[0].role is RegionRole.PAGE_HEADER
    assert detected[0].confidence == 0.4


def test_a_lone_folio_scores_the_folio_confidence() -> None:
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    detected = furniture_region_detector(_input([_word("17", 870, 105, 900, 125)], confidence=0.9))
    assert len(detected) == 1
    assert detected[0].role is RegionRole.PAGE_NUMBER
    assert detected[0].confidence == 0.8


def test_a_classification_with_no_confidence_is_recorded_but_does_not_move_the_score() -> None:
    """Page-fit confidence is evidence, not the score — see the coordinator's correction.

    A ``None`` classification confidence must reach the evidence dict as
    ``None`` and must leave the cluster-shape score untouched.
    """
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    detected = furniture_region_detector(_input([_word("17", 870, 105, 900, 125)], confidence=None))
    assert detected[0].confidence == 0.8
    assert detected[0].evidence["page_class_confidence"] is None


def test_an_ordinal_past_the_end_of_the_bands_proposes_nothing() -> None:
    """The classifier and the profile disagree; skip rather than guess."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [_word("THE", 100, 105, 170, 125)]
    assert furniture_region_detector(_input(words, ordinals=(0, 5))) == []


def test_the_evidence_names_the_band_and_the_cluster_width() -> None:
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [_word("THE", 100, 105, 170, 125), _word("17", 870, 105, 900, 125)]
    detected = furniture_region_detector(_input(words))
    assert detected[0].evidence["band_ordinals"] == [0]
    assert detected[0].evidence["cluster_width_px"] == 70
    assert detected[0].evidence["text_width_px"] == 800
    # Page-fit signals ride along as evidence rather than moving the score —
    # see furniture.py's module comment on the three confidence constants.
    assert detected[0].evidence["page_class_confidence"] == 0.9
    assert detected[0].evidence["template_residual_px"] == 2


def test_the_evidence_names_the_fixed_share_threshold_source() -> None:
    """``furniture_region_detector`` always judges against the fixed share."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [_word("THE", 100, 105, 170, 125), _word("17", 870, 105, 900, 125)]
    detected = furniture_region_detector(_input(words))
    assert detected[0].evidence["gap_threshold_source"] == "fixed_share"
    assert detected[0].evidence["gap_threshold_px"] == 80.0


@pytest.mark.parametrize("normalized", [False, True])
def test_a_running_head_and_a_folio_become_two_regions_in_either_convention(normalized: bool) -> None:
    """A normalized page proposes the same pixel boxes as its pixel-page equivalent.

    Ink bands are always source-frame pixels; a normalized page's word boxes
    are converted to source pixels (against ``measurement.source_frame``,
    which here equals the page's own 1000x1600 dimensions) before being
    compared against one — the fix for the defect that made every real book
    propose nothing.
    """
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    def w(text: str, left: float, top: float, right: float, bottom: float) -> dict[str, object]:
        if normalized:
            return _word(
                text,
                left / _PAGE_WIDTH,
                top / _PAGE_HEIGHT,
                right / _PAGE_WIDTH,
                bottom / _PAGE_HEIGHT,
                normalized=True,
            )
        return _word(text, left, top, right, bottom)

    words = [w("THE", 100, 105, 170, 125), w("VOYAGE", 180, 105, 320, 125), w("17", 870, 105, 900, 125)]
    detected = furniture_region_detector(_input(words))

    assert len(detected) == 2
    head, folio = detected
    assert head.role is RegionRole.PAGE_HEADER
    assert head.box == (100, 105, 320, 125)
    assert folio.role is RegionRole.PAGE_NUMBER
    assert folio.box == (870, 105, 900, 125)


def test_a_page_mixing_normalized_and_pixel_boxes_is_skipped() -> None:
    """Page.is_content_normalized raises on a mixed page; a detector cannot pick a side.

    The two words must sit in different LINE blocks. ``Block.from_dict`` refuses
    a single WORDS block whose words disagree on coordinate system, so a
    one-line mixed page cannot be built at all.
    """
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    detector_input = _input(
        [_word("THE", 100, 105, 170, 125)],
        extra_line=[_word("17", 0.9, 0.05, 0.95, 0.08, normalized=True)],
    )
    assert furniture_region_detector(detector_input) == []


def test_a_source_frame_differing_from_the_page_still_proposes_in_the_page_frame() -> None:
    """Accept converts a proposal's box against page.width/height, so the proposal must be in that frame.

    Here the decoded image is twice the page's recorded size. Bands and text
    edges are measured in that larger frame; the words are in the page frame.
    The detector must rescale the bands and text width, not the words, so the
    proposed boxes match the same-frame case exactly.
    """
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    double_frame = CoordinateFrame(width=_PAGE_WIDTH * 2, height=_PAGE_HEIGHT * 2)
    double_template = PageTemplate(
        page_class="normal_recto",
        first_band_top_px=200,
        first_band_spread_px=12,
        text_left_px=200,
        text_right_px=1800,
        band_count=30,
        page_count=200,
        page_share=0.5,
    )
    words = [
        _word("THE", 100, 105, 170, 125),
        _word("VOYAGE", 180, 105, 320, 125),
        _word("17", 870, 105, 900, 125),
    ]
    same_frame = furniture_region_detector(_input(words))
    doubled = furniture_region_detector(
        DetectorInput(
            page=_page(words),
            page_index=0,
            measurement=_measurement((InkBand(200, 260),), source_frame=double_frame),
            classification=PageClassification("001.png", "normal_recto", 2, (0,), 0.9),
            templates=BookTemplates(200.0, 8.0, 32.0, (double_template,), 0.9),
        )
    )

    assert [d.box for d in doubled] == [d.box for d in same_frame]
    assert [d.box for d in doubled] == [(100, 105, 320, 125), (870, 105, 900, 125)]

    # The reviewer's scenario: a normalized OCR page. Its words must be scaled by
    # the page's own size, not the source frame's, or the proposal lands in the
    # source frame and accept later reads it in the page frame.
    w, h = _PAGE_WIDTH, _PAGE_HEIGHT
    normalized_words = [
        _word(text, left / w, top / h, right / w, bottom / h, normalized=True)
        for text, left, top, right, bottom in (
            ("THE", 100, 105, 170, 125),
            ("VOYAGE", 180, 105, 320, 125),
            ("17", 870, 105, 900, 125),
        )
    ]
    doubled_normalized = furniture_region_detector(
        DetectorInput(
            page=_page(normalized_words),
            page_index=0,
            measurement=_measurement((InkBand(200, 260),), source_frame=double_frame),
            classification=PageClassification("001.png", "normal_recto", 2, (0,), 0.9),
            templates=BookTemplates(200.0, 8.0, 32.0, (double_template,), 0.9),
        )
    )
    assert [d.box for d in doubled_normalized] == [(100, 105, 320, 125), (870, 105, 900, 125)]


def test_a_source_frame_mismatch_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    mismatched_frame = CoordinateFrame(width=1200, height=1800)
    detector_input = _input([_word("THE", 100, 105, 170, 125)], source_frame=mismatched_frame)

    with caplog.at_level(logging.WARNING):
        furniture_region_detector(detector_input)

    assert any(
        "source_frame" in record.getMessage()
        and "1200x1800" in record.getMessage()
        and "1000x1600" in record.getMessage()
        for record in caplog.records
    )


def test_a_missing_source_frame_leaves_bands_and_text_width_unscaled() -> None:
    """A measurement with no decoded image metadata carries no ``source_frame`` at all."""
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput
    from pdomain_ocr_labeler_spa.core.regions.furniture import _source_to_page_scale

    unavailable_measurement = PageMeasurement(
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
        diagnostics=(ProfileDiagnostic(code="image_missing", message="no image on disk"),),
        page_class="unknown",
    )
    detector_input = DetectorInput(
        page=_page([_word("THE", 100, 105, 170, 125)]),
        page_index=0,
        measurement=unavailable_measurement,
        classification=PageClassification("001.png", "unknown", 2, (), None),
        templates=_templates(),
    )

    assert _source_to_page_scale(detector_input) == (1.0, 1.0)


def test_the_pooled_gaps_are_identical_pixel_values_across_page_conventions() -> None:
    """The book-level fit and the per-page detector must see identical pixel coordinates."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import _pooled_gaps

    def w(text: str, left: float, top: float, right: float, bottom: float) -> dict[str, object]:
        return _word(
            text,
            left / _PAGE_WIDTH,
            top / _PAGE_HEIGHT,
            right / _PAGE_WIDTH,
            bottom / _PAGE_HEIGHT,
            normalized=True,
        )

    words_px = [
        _word("THE", 100, 105, 170, 125),
        _word("VOYAGE", 180, 105, 320, 125),
        _word("17", 870, 105, 900, 125),
    ]
    words_norm = [w("THE", 100, 105, 170, 125), w("VOYAGE", 180, 105, 320, 125), w("17", 870, 105, 900, 125)]

    assert _pooled_gaps([_input(words_norm)]) == _pooled_gaps([_input(words_px)])


# ---------------------------------------------------------------------------
# The per-book gap fit: Otsu-midpoint, its three fallback triggers, and the
# book that motivated deriving the threshold instead of fixing it.
# ---------------------------------------------------------------------------


def test_the_otsu_fit_places_the_threshold_inside_the_valley() -> None:
    """A clear bimodal gap list: many word spaces, a wide empty valley, the head-folio gaps."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import _fit_gap_threshold_px

    word_spaces = [3.0, 5.0, 8.0, 10.0, 12.0, 15.0, 18.0, 20.0, 22.0, 26.0]
    head_folio_gaps = [118.0, 140.0, 160.0, 180.0, 210.0, 240.0, 260.0, 287.0]
    gaps = word_spaces + head_folio_gaps

    threshold_px, source = _fit_gap_threshold_px(gaps, text_width_px=1000)

    assert source == "book_fit"
    assert max(word_spaces) < threshold_px < min(head_folio_gaps)


def test_too_few_pooled_gaps_falls_back_to_the_fixed_share() -> None:
    """Fewer than 8 pooled gaps: too little evidence to fit, regardless of shape."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import (
        FOLIO_GAP_SHARE_OF_TEXT_WIDTH,
        _fit_gap_threshold_px,
    )

    gaps = [5.0, 6.0, 7.0, 150.0, 160.0, 170.0, 180.0]  # 7 gaps, a clear valley but too few
    assert len(gaps) < 8

    threshold_px, source = _fit_gap_threshold_px(gaps, text_width_px=1000)

    assert source == "fixed_share"
    assert threshold_px == 1000 * FOLIO_GAP_SHARE_OF_TEXT_WIDTH


def test_a_degenerate_gap_class_falls_back_to_the_fixed_share() -> None:
    """An Otsu split that leaves either class with fewer than two members is untrustworthy."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import (
        FOLIO_GAP_SHARE_OF_TEXT_WIDTH,
        _fit_gap_threshold_px,
    )

    # Eight clustered low values and a single outlier: the outlier's own class
    # has only one member, so the split is not trusted even though it exists.
    gaps = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 200.0]

    threshold_px, source = _fit_gap_threshold_px(gaps, text_width_px=1000)

    assert source == "fixed_share"
    assert threshold_px == 1000 * FOLIO_GAP_SHARE_OF_TEXT_WIDTH


def test_a_threshold_outside_the_text_width_band_falls_back_to_the_fixed_share() -> None:
    """A valley that sits below 2 percent of text width is not a real furniture gap."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import (
        FOLIO_GAP_SHARE_OF_TEXT_WIDTH,
        _fit_gap_threshold_px,
    )

    # Two well-separated classes by Otsu's own measure, but their midpoint
    # (about 10px) is under 2 percent of a 1000px text width (20px) — no real
    # bimodality against this book's own geometry.
    low = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    high = [12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]

    threshold_px, source = _fit_gap_threshold_px(low + high, text_width_px=1000)

    assert source == "fixed_share"
    assert threshold_px == 1000 * FOLIO_GAP_SHARE_OF_TEXT_WIDTH


_MOTIVATING_BOOK_PAGE_WIDTH = 1800
_MOTIVATING_BOOK_PAGE_HEIGHT = 2400
_MOTIVATING_BOOK_TEXT_LEFT = 50
_MOTIVATING_BOOK_TEXT_WIDTH = 1596
_MOTIVATING_BOOK_TEXT_RIGHT = _MOTIVATING_BOOK_TEXT_LEFT + _MOTIVATING_BOOK_TEXT_WIDTH


def _motivating_book_templates() -> BookTemplates:
    template = PageTemplate(
        page_class="normal_recto",
        first_band_top_px=100,
        first_band_spread_px=6,
        text_left_px=_MOTIVATING_BOOK_TEXT_LEFT,
        text_right_px=_MOTIVATING_BOOK_TEXT_RIGHT,
        band_count=30,
        page_count=200,
        page_share=0.5,
    )
    return BookTemplates(100.0, 4.0, 16.0, (template,), 0.9)


def _motivating_book_page(words: list[dict[str, object]]) -> Page:
    line: dict[str, object] = {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "items": words,
        "bounding_box": _bbox(0, 0, _MOTIVATING_BOOK_PAGE_WIDTH, _MOTIVATING_BOOK_PAGE_HEIGHT),
    }
    return Page.from_dict(
        {
            "width": _MOTIVATING_BOOK_PAGE_WIDTH,
            "height": _MOTIVATING_BOOK_PAGE_HEIGHT,
            "page_index": 0,
            "bounding_box": _bbox(0, 0, _MOTIVATING_BOOK_PAGE_WIDTH, _MOTIVATING_BOOK_PAGE_HEIGHT),
            "items": [line],
        }
    )


def _motivating_book_measurement(page_name: str) -> PageMeasurement:
    return PageMeasurement(
        page_name=page_name,
        source_path=f"book1/{page_name}",
        sha256="a" * 64,
        source_frame=CoordinateFrame(width=_MOTIVATING_BOOK_PAGE_WIDTH, height=_MOTIVATING_BOOK_PAGE_HEIGHT),
        image_mode="L",
        grayscale_threshold=128,
        foreground_pixels=50_000,
        foreground_bounds=(50, 100, 1700, 2300),
        margins=(50, 100, _MOTIVATING_BOOK_PAGE_WIDTH - 1700, _MOTIVATING_BOOK_PAGE_HEIGHT - 2300),
        ink_bands=(InkBand(100, 130),),
        page_class="normal_recto",
    )


def _motivating_book_input(page_index: int, words: list[dict[str, object]]) -> Any:
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput

    page_name = f"{page_index:03d}.png"
    return DetectorInput(
        page=_motivating_book_page(words),
        page_index=page_index,
        measurement=_motivating_book_measurement(page_name),
        classification=PageClassification(page_name, "normal_recto", 2, (0,), 0.9),
        templates=_motivating_book_templates(),
    )


def test_the_book_that_motivated_this_fit_splits_where_the_fixed_share_joins() -> None:
    """Text width 1596px: 10 percent is ~160px, but every head-folio gap here is 135-150px.

    The fixed detector never clears its own threshold and joins head and
    folio into one region on every page. The fitted threshold sits at the
    valley between the ~10-20px word spaces and the ~135-150px head-folio
    gaps, well under 135, and splits them into two.
    """
    from pdomain_ocr_labeler_spa.core.regions.furniture import FurnitureDetector, furniture_region_detector

    pages_words = [
        [
            _word("THE", 50, 105, 120, 125),
            _word("VOYAGE", 130, 105, 260, 125),
            _word("1", 410, 105, 430, 125),
        ],
        [_word("THE", 50, 105, 120, 125), _word("SHIP", 133, 105, 230, 125), _word("2", 370, 105, 390, 125)],
        [_word("THE", 50, 105, 120, 125), _word("CREW", 135, 105, 235, 125), _word("3", 380, 105, 400, 125)],
        [
            _word("OUR", 50, 105, 110, 125),
            _word("JOURNEY", 128, 105, 260, 125),
            _word("4", 395, 105, 415, 125),
        ],
        [_word("A", 50, 105, 70, 125), _word("TALE", 90, 105, 170, 125), _word("5", 305, 105, 325, 125)],
    ]
    book = [_motivating_book_input(i, words) for i, words in enumerate(pages_words)]

    fixed = furniture_region_detector(book[0])
    assert len(fixed) == 1, "10% of a 1596px text width (~160px) exceeds no head-folio gap here"

    per_page_detect = FurnitureDetector().fit(book)
    fitted = per_page_detect(book[0])
    assert len(fitted) == 2, "the fitted threshold should split the head from the folio"
    assert fitted[0].evidence["gap_threshold_source"] == "book_fit"
    assert fitted[1].evidence["gap_threshold_source"] == "book_fit"


# ---------------------------------------------------------------------------
# Fix 1 — a band far taller than its own words merged the running head with
# the body text below it (projectID408c1dd9b9318 page 41, ratio 68.9). Skip
# it, on both the per-page path and the book-level gap pool.
# ---------------------------------------------------------------------------


def test_a_band_far_taller_than_its_words_is_skipped_and_pools_no_gaps() -> None:
    """Ratio 7: over the 6x bar. Every word stacked across several lines passes the plain y-range filter."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import (
        _in_band_words,
        _pooled_gaps,
        furniture_region_detector,
    )

    words = [
        _word("RUNNING", 100, 105, 200, 125),
        _word("body1", 100, 140, 190, 160),
        _word("body2", 100, 170, 190, 190),
        _word("body3", 100, 200, 190, 220),
        _word("body4", 100, 222, 190, 242),
    ]
    # band height 140px, median word height 20px -> ratio 7, over the 6x bar.
    detector_input = _input(words, bands=(InkBand(100, 240),))

    assert _in_band_words(detector_input) is None
    assert furniture_region_detector(detector_input) == []
    assert _pooled_gaps([detector_input]) == []


def test_a_band_at_three_point_five_times_its_words_is_not_skipped() -> None:
    """The tallest legitimate band seen (projectID3fc3d7d03c613 page 30) scored 3.5 — under the bar."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import _in_band_words, furniture_region_detector

    words = [
        _word("THE", 100, 105, 170, 125),
        _word("VOYAGE", 180, 105, 320, 125),
    ]
    # band height 70px, median word height 20px -> ratio 3.5.
    detector_input = _input(words, bands=(InkBand(100, 170),))

    band = _in_band_words(detector_input)
    assert band is not None
    assert len(band.words) == 2
    assert len(furniture_region_detector(detector_input)) == 1


# ---------------------------------------------------------------------------
# Fix 2 — a folio OCR'd with surrounding punctuation still reads as a folio.
# ---------------------------------------------------------------------------


def test_a_folio_with_a_trailing_period_is_a_page_number() -> None:
    """projectID3fc3d7d03c613 page 25's folio came out as ``232.``."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [
        _word("PREFACE", 100, 105, 260, 125),
        _word("232.", 860, 105, 900, 125),
    ]
    detected = furniture_region_detector(_input(words))
    assert [d.role for d in detected] == [RegionRole.PAGE_HEADER, RegionRole.PAGE_NUMBER]


def test_a_bracketed_folio_is_a_page_number() -> None:
    """A folio bracketed as ``[17]`` must not widen the pattern to accept letters."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [
        _word("PREFACE", 100, 105, 260, 125),
        _word("[17]", 860, 105, 900, 125),
    ]
    detected = furniture_region_detector(_input(words))
    assert [d.role for d in detected] == [RegionRole.PAGE_HEADER, RegionRole.PAGE_NUMBER]


# ---------------------------------------------------------------------------
# Fix 3 — peel a digit folio off either end of a cluster, book-fitted path
# only. projectID408c1dd9b9318 pages 33, 47, 49: a long running head sits
# 53-55px from its own folio, barely wider than the book's 26-40px word
# spaces (median 30px) — no single gap threshold separates the two.
# ---------------------------------------------------------------------------


def _peel_book_pages_with_folio(folio_text: str) -> list[dict[str, object]]:
    """One page reading ``HEAD HEAD HEAD <folio_text>`` with a 54px head-to-folio gap.

    Paired with four other pages (word-space 30px, head-to-folio gap 200 to
    215px) whose pooled gaps fit the book's threshold to 127px and its median
    word space to exactly 30px — verified against the module's own Otsu math
    before writing this fixture.
    """
    return [
        _word("HEAD", 100, 105, 150, 125),
        _word("HEAD", 180, 105, 230, 125),
        _word("HEAD", 260, 105, 310, 125),
        _word(folio_text, 364, 105, 390, 125),
    ]


def _peel_book_other_pages() -> list[list[dict[str, object]]]:
    return [
        [
            _word("THE", 50, 105, 90, 125),
            _word("SHIP", 120, 105, 190, 125),
            _word("2", 390, 105, 410, 125),
        ],
        [
            _word("THE", 50, 105, 90, 125),
            _word("CREW", 120, 105, 190, 125),
            _word("3", 395, 105, 415, 125),
        ],
        [
            _word("THE", 50, 105, 90, 125),
            _word("MAST", 120, 105, 190, 125),
            _word("4", 400, 105, 420, 125),
        ],
        [
            _word("THE", 50, 105, 90, 125),
            _word("CROSS", 120, 105, 190, 125),
            _word("5", 405, 105, 425, 125),
        ],
    ]


def test_a_book_fitted_detector_peels_a_digit_folio_off_a_long_head() -> None:
    """54px head-to-folio gap, 30px median word space: 1.8x the median clears the 1.6x bar."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import FurnitureDetector

    target_words = _peel_book_pages_with_folio("27")
    book = [_input(target_words)] + [_input(words) for words in _peel_book_other_pages()]

    per_page_detect = FurnitureDetector().fit(book)
    detected = per_page_detect(book[0])

    assert len(detected) == 2
    head, folio = detected
    assert head.role is RegionRole.PAGE_HEADER
    assert head.box == (100, 105, 310, 125)
    assert folio.role is RegionRole.PAGE_NUMBER
    assert folio.box == (364, 105, 390, 125)
    assert head.evidence["gap_threshold_source"] == "book_fit"


def test_a_book_fitted_detector_peels_a_digit_folio_off_the_start_of_a_long_head() -> None:
    """The verso case: the folio leads the head line, 54px before it, against a 30px median word space.

    Mirrors the right-edge peel test. The target page contributes the same gaps
    (54, 30, 30) in a different order, so the book fits to the same threshold and
    median word space.
    """
    from pdomain_ocr_labeler_spa.core.regions.furniture import FurnitureDetector

    target_words = [
        _word("27", 100, 105, 126, 125),
        _word("HEAD", 180, 105, 230, 125),
        _word("HEAD", 260, 105, 310, 125),
        _word("HEAD", 340, 105, 390, 125),
    ]
    book = [_input(target_words)] + [_input(words) for words in _peel_book_other_pages()]

    per_page_detect = FurnitureDetector().fit(book)
    detected = per_page_detect(book[0])

    assert len(detected) == 2
    folio, head = sorted(detected, key=lambda d: d.box[0])
    assert folio.role is RegionRole.PAGE_NUMBER
    assert folio.box == (100, 105, 126, 125)
    assert head.role is RegionRole.PAGE_HEADER
    assert head.box == (180, 105, 390, 125)
    assert head.evidence["gap_threshold_source"] == "book_fit"


def test_no_qualifying_word_space_means_no_median_and_no_peel() -> None:
    """Overlapping or touching words leave no gap above zero, so there is no basis to peel."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import (
        _cluster,
        _in_band_words,
        _median_word_space_px,
        _peel_edge_folios,
    )

    assert _median_word_space_px([], 100.0) is None
    assert _median_word_space_px([-30.0, -5.0, 0.0], 100.0) is None
    assert _median_word_space_px([150.0, 200.0], 100.0) is None

    band_words = _in_band_words(_input(_peel_book_pages_with_folio("27")))
    assert band_words is not None
    clusters = _cluster(band_words.words, 127.0)
    assert _peel_edge_folios(clusters, None) is clusters


def test_a_book_fitted_detector_does_not_peel_a_digit_that_is_part_of_the_head() -> None:
    """projectID3fc3d7d03c613's verso head ends ``[ETH. ANN. 33``: 22px gap against a 20px median (1.1x)."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import FurnitureDetector

    target_words = [
        _word("[ETH.", 100, 105, 140, 125),
        _word("ANN.", 158, 105, 198, 125),
        _word("33", 220, 105, 240, 125),
    ]
    other_pages = [
        [
            _word("THE", 50, 105, 90, 125),
            _word("SHIP", 110, 105, 180, 125),
            _word("2", 380, 105, 400, 125),
        ],
        [
            _word("THE", 50, 105, 90, 125),
            _word("CREW", 110, 105, 180, 125),
            _word("3", 385, 105, 405, 125),
        ],
        [
            _word("THE", 50, 105, 90, 125),
            _word("MAST", 110, 105, 180, 125),
            _word("4", 390, 105, 410, 125),
        ],
        [
            _word("THE", 50, 105, 90, 125),
            _word("CROSS", 110, 105, 180, 125),
            _word("5", 395, 105, 415, 125),
        ],
    ]
    book = [_input(target_words)] + [_input(words) for words in other_pages]

    per_page_detect = FurnitureDetector().fit(book)
    detected = per_page_detect(book[0])

    assert len(detected) == 1
    assert detected[0].role is RegionRole.PAGE_HEADER
    assert detected[0].box == (100, 105, 240, 125)
    assert detected[0].evidence["gap_threshold_source"] == "book_fit"


def test_a_roman_numeral_edge_token_is_never_peeled() -> None:
    """A head ending in a word such as ``XII`` must keep it — roman numerals are excluded from the peel."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import FurnitureDetector

    target_words = _peel_book_pages_with_folio("XII")
    book = [_input(target_words)] + [_input(words) for words in _peel_book_other_pages()]

    per_page_detect = FurnitureDetector().fit(book)
    detected = per_page_detect(book[0])

    assert len(detected) == 1
    assert detected[0].role is RegionRole.PAGE_HEADER
    assert detected[0].box == (100, 105, 390, 125)


def test_the_unfitted_fallback_never_peels() -> None:
    """Same head-to-folio layout as the book-fit split above; the plain fallback must not split it."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    target_words = _peel_book_pages_with_folio("27")
    detected = furniture_region_detector(_input(target_words))

    assert len(detected) == 1
    assert detected[0].role is RegionRole.PAGE_HEADER

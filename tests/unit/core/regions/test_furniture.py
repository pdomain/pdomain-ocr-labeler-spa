"""Unit tests for the top-furniture region detector."""

from __future__ import annotations

from typing import Any

from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.page import Page
from pdomain_pgdp_measure.page_templates import (
    BookTemplates,
    PageClassification,
    PageTemplate,
)
from pdomain_pgdp_measure.profile_models import CoordinateFrame, InkBand, PageMeasurement

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
def _measurement(bands: tuple[InkBand, ...]) -> PageMeasurement:
    return PageMeasurement(
        page_name="001.png",
        source_path="book1/001.png",
        sha256="a" * 64,
        source_frame=CoordinateFrame(width=_PAGE_WIDTH, height=_PAGE_HEIGHT),
        image_mode="L",
        grayscale_threshold=128,
        foreground_pixels=50_000,
        foreground_bounds=(100, 100, 900, 1500),
        margins=(100, 100, _PAGE_WIDTH - 900, _PAGE_HEIGHT - 1500),
        ink_bands=bands,
        page_class="normal_recto",
    )


def _input(
    words: list[dict[str, object]],
    *,
    bands: tuple[InkBand, ...] = (InkBand(100, 130),),
    ordinals: tuple[int, ...] = (0,),
    page_class: str = "normal_recto",
    confidence: float | None = 0.9,
    extra_line: list[dict[str, object]] | None = None,
) -> Any:
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput

    lines = [words] if extra_line is None else [words, extra_line]
    return DetectorInput(
        page=_page(*lines),
        page_index=0,
        measurement=_measurement(bands),
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


def test_a_page_with_normalized_word_boxes_is_skipped() -> None:
    """Ink bands are source-frame pixels; a 0-to-1 box cannot be compared against one."""
    from pdomain_ocr_labeler_spa.core.regions.furniture import furniture_region_detector

    words = [_word("THE", 0.1, 0.05, 0.2, 0.08, normalized=True)]
    assert furniture_region_detector(_input(words)) == []


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

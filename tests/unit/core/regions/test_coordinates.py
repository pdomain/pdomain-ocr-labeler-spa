"""Unit tests for the pixel <-> page-convention box conversion."""

from __future__ import annotations

import pytest
from pdomain_book_contracts.geometry.bounding_box import BoundingBox

from pdomain_ocr_labeler_spa.core.regions.coordinates import (
    bounding_box_to_pixels,
    pixel_box_to_bounding_box,
)

# Real evidence: projectID657550412c8dc page 10, 1166x1779px, a running
# head's first word.
_REAL_PAGE_WIDTH = 1166
_REAL_PAGE_HEIGHT = 1779
_REAL_BOX = (442, 110, 653, 139)


def test_a_pixel_box_on_a_pixel_page_is_stored_unchanged() -> None:
    box = pixel_box_to_bounding_box(
        _REAL_BOX, page_width=_REAL_PAGE_WIDTH, page_height=_REAL_PAGE_HEIGHT, is_normalized=False
    )
    assert box.is_normalized is False
    assert box.to_ltrb() == (442.0, 110.0, 653.0, 139.0)


def test_a_pixel_box_on_a_normalized_page_is_divided_by_page_dimensions() -> None:
    box = pixel_box_to_bounding_box(
        _REAL_BOX, page_width=_REAL_PAGE_WIDTH, page_height=_REAL_PAGE_HEIGHT, is_normalized=True
    )
    assert box.is_normalized is True
    left, top, right, bottom = box.to_ltrb()
    assert 0.0 <= left <= 1.0
    assert 0.0 <= top <= 1.0
    assert 0.0 <= right <= 1.0
    assert 0.0 <= bottom <= 1.0


def test_the_real_page_10_box_round_trips_exactly_through_normalized_and_back() -> None:
    """Converting pixels to normalized and back must return the same integers."""
    normalized = pixel_box_to_bounding_box(
        _REAL_BOX, page_width=_REAL_PAGE_WIDTH, page_height=_REAL_PAGE_HEIGHT, is_normalized=True
    )
    pixels = bounding_box_to_pixels(normalized, page_width=_REAL_PAGE_WIDTH, page_height=_REAL_PAGE_HEIGHT)
    assert pixels == _REAL_BOX


def test_a_pixel_box_on_a_pixel_page_round_trips_exactly() -> None:
    box = pixel_box_to_bounding_box(
        _REAL_BOX, page_width=_REAL_PAGE_WIDTH, page_height=_REAL_PAGE_HEIGHT, is_normalized=False
    )
    pixels = bounding_box_to_pixels(box, page_width=_REAL_PAGE_WIDTH, page_height=_REAL_PAGE_HEIGHT)
    assert pixels == _REAL_BOX


def test_a_box_reaching_past_the_edge_of_a_normalized_page_is_rejected() -> None:
    """A pixel box whose normalized projection overflows [0, 1] is not silently clamped."""
    with pytest.raises(ValueError, match=r"\[0, ?1\]|\[0,1\]|normalized"):
        pixel_box_to_bounding_box(
            (0, 0, _REAL_PAGE_WIDTH + 500, 50),
            page_width=_REAL_PAGE_WIDTH,
            page_height=_REAL_PAGE_HEIGHT,
            is_normalized=True,
        )


def test_zero_page_dimensions_are_rejected_rather_than_dividing_by_zero() -> None:
    with pytest.raises(ValueError, match="page dimensions"):
        pixel_box_to_bounding_box(_REAL_BOX, page_width=0, page_height=0, is_normalized=True)


def test_a_normalized_stored_box_converts_back_to_pixels() -> None:
    stored = BoundingBox.from_ltrb(
        442 / _REAL_PAGE_WIDTH,
        110 / _REAL_PAGE_HEIGHT,
        653 / _REAL_PAGE_WIDTH,
        139 / _REAL_PAGE_HEIGHT,
        is_normalized=True,
    )
    assert bounding_box_to_pixels(stored, page_width=_REAL_PAGE_WIDTH, page_height=_REAL_PAGE_HEIGHT) == (
        442,
        110,
        653,
        139,
    )

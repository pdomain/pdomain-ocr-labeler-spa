"""Unit tests for the pluggable region detector interface."""

from __future__ import annotations


def test_the_null_detector_proposes_nothing() -> None:
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.regions.detector import null_region_detector

    page = Page(width=200, height=300, page_index=0, blocks=[])
    assert null_region_detector(page) == []

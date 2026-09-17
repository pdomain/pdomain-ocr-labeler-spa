"""Unit tests for the pluggable region detector interface."""

from __future__ import annotations


def _empty_detector_input() -> object:
    from pdomain_book_tools.ocr.page import Page
    from pdomain_pgdp_measure.page_templates import BookTemplates, PageClassification
    from pdomain_pgdp_measure.profile_models import PageMeasurement, ProfileDiagnostic

    from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput

    return DetectorInput(
        page=Page(width=200, height=300, page_index=0, blocks=[]),
        page_index=0,
        measurement=PageMeasurement(
            page_name="001.png",
            source_path="book1/001.png",
            sha256=None,
            source_frame=None,
            image_mode=None,
            grayscale_threshold=None,
            foreground_pixels=None,
            foreground_bounds=None,
            margins=None,
            # ``PageMeasurement.__post_init__`` requires unavailable-geometry
            # fields to travel together and requires a diagnostic explaining
            # why the image is unavailable — the plan's sample omitted both
            # and does not construct as written.
            ink_bands=None,
            diagnostics=(ProfileDiagnostic(code="image_missing", message="test fixture"),),
        ),
        classification=PageClassification("001.png", "unknown", None, ()),
        templates=BookTemplates(None, None, None, (), 0.0),
    )


def test_the_null_detector_proposes_nothing() -> None:
    from pdomain_ocr_labeler_spa.core.regions.detector import null_region_detector

    assert null_region_detector(_empty_detector_input()) == []


def test_detector_input_carries_the_page_index_and_the_book_templates() -> None:
    """The seam's whole reason to widen: a detector needs more than one page."""
    from pdomain_pgdp_measure.page_templates import BookTemplates

    detector_input = _empty_detector_input()
    assert detector_input.page_index == 0
    assert isinstance(detector_input.templates, BookTemplates)
    assert detector_input.classification.page_class == "unknown"

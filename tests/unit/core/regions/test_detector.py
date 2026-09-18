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


def test_detector_depends_on_facets_falls_back_for_a_plain_callable() -> None:
    from pdomain_ocr_labeler_spa.core.regions.detector import (
        DEFAULT_DETECTOR_FACETS,
        detector_depends_on_facets,
        null_region_detector,
    )

    assert detector_depends_on_facets(null_region_detector) == DEFAULT_DETECTOR_FACETS


def test_detector_depends_on_facets_reads_a_detector_declared_set() -> None:
    from dataclasses import dataclass

    from pdomain_ocr_labeler_spa.core.regions.detector import (
        DetectedRegion,
        DetectorInput,
        detector_depends_on_facets,
    )

    @dataclass(frozen=True)
    class _StubDetector:
        depends_on_facets: frozenset[str] = frozenset({"word_text"})

        def __call__(self, detector_input: DetectorInput) -> list[DetectedRegion]:
            del detector_input
            return []

    assert detector_depends_on_facets(_StubDetector()) == frozenset({"word_text"})


def test_composite_detector_unions_every_sub_detectors_proposals() -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.detector import CompositeDetector, DetectedRegion

    def _one(detector_input: object) -> list[DetectedRegion]:
        del detector_input
        return [DetectedRegion(role=RegionRole.PAGE_HEADER, box=(0, 0, 10, 10), confidence=0.5, evidence={})]

    def _two(detector_input: object) -> list[DetectedRegion]:
        del detector_input
        return [DetectedRegion(role=RegionRole.POETRY, box=(0, 0, 20, 20), confidence=0.9, evidence={})]

    composite = CompositeDetector((_one, _two))
    detected = composite.fit([])(_empty_detector_input())

    assert {d.role for d in detected} == {RegionRole.PAGE_HEADER, RegionRole.POETRY}


def test_composite_detector_fits_a_book_fitted_sub_detector() -> None:
    from collections.abc import Sequence

    from pdomain_ocr_labeler_spa.core.regions.detector import (
        BookFittedDetector,
        CompositeDetector,
        DetectedRegion,
        DetectorInput,
        RegionDetector,
    )

    fit_calls: list[int] = []

    class _StubBookFitted(BookFittedDetector):
        def fit(self, book: Sequence[DetectorInput]) -> RegionDetector:
            fit_calls.append(len(list(book)))

            def _detect(detector_input: DetectorInput) -> list[DetectedRegion]:
                del detector_input
                return []

            return _detect

    composite = CompositeDetector((_StubBookFitted(),))
    composite.fit([_empty_detector_input(), _empty_detector_input()])

    assert fit_calls == [2]


def test_composite_detector_depends_on_facets_is_the_union() -> None:
    from dataclasses import dataclass

    from pdomain_ocr_labeler_spa.core.regions.detector import (
        CompositeDetector,
        DetectedRegion,
        DetectorInput,
    )

    @dataclass(frozen=True)
    class _StubDetector:
        depends_on_facets: frozenset[str]

        def __call__(self, detector_input: DetectorInput) -> list[DetectedRegion]:
            del detector_input
            return []

    composite = CompositeDetector(
        (_StubDetector(frozenset({"word_boxes"})), _StubDetector(frozenset({"word_text"})))
    )
    assert composite.depends_on_facets == frozenset({"word_boxes", "word_text"})

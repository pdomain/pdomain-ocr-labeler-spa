"""The pluggable region-detector seam a proposal run calls.

Mirrors ``pdomain_book_tools.layout.registry``'s ``NullDetector`` naming: a
default that proposes nothing, so the job scaffolding is runnable and testable
before slice 4's real geometry engine exists. Slice 4 supplies a real
``RegionDetector`` through ``JobRunner.context["region_detector"]`` — this
plan does not compute a single proposal itself.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.page import Page
from pdomain_pgdp_measure.page_templates import BookTemplates, PageClassification
from pdomain_pgdp_measure.profile_models import PageMeasurement


@dataclass(frozen=True)
class DetectedRegion:
    """One region a detector proposed for one page, before it is wrapped as a ``RegionProposal``."""

    role: RegionRole
    box: tuple[int, int, int, int]
    confidence: float
    # Open-ended: shape varies per detector, same as ``RegionProposal.evidence``
    # (core/regions/models.py) that this ultimately feeds — no single
    # TypedDict fits every detector's signals.
    evidence: dict[str, Any]


@dataclass(frozen=True)
class DetectorInput:
    """Everything a detector may read about one page of one book.

    The seam started as ``Callable[[Page], ...]`` and that was not enough. A
    detector needs the page's index to find its own classification, and the
    book's fitted templates to know where the text block sits — the templates
    are the book's own measured geometry, which is what a fixed threshold can
    never be. Passing one frozen object rather than five arguments means a
    later detector that needs a sixth signal does not change every call site.
    """

    page: Page
    page_index: int
    measurement: PageMeasurement
    classification: PageClassification
    templates: BookTemplates


RegionDetector = Callable[[DetectorInput], Sequence[DetectedRegion]]
"""Takes one page and the book it belongs to, and returns what it detected."""


@runtime_checkable
class BookFittedDetector(Protocol):
    """A detector that must see the whole book before it judges any page.

    Mirrors the "fit the whole book once, then judge each page" shape
    ``fit_book_templates`` already established (``core/page_measurement.py``).
    A detector that implements this protocol never receives ``DetectorInput``
    directly from ``propose_regions`` — the handler builds a ``DetectorInput``
    for every eligible, measured page, calls ``fit`` exactly once with that
    whole sequence (off the event loop; it walks every word box in the book),
    and uses the ``RegionDetector`` it returns for the per-page loop. A plain
    ``RegionDetector`` callable that does not implement this protocol is
    called directly, unchanged, with no ``fit`` step at all.
    """

    def fit(self, book: Sequence[DetectorInput]) -> RegionDetector: ...


def null_region_detector(detector_input: DetectorInput) -> list[DetectedRegion]:
    """The default detector: proposes nothing. Keeps the job runnable with no engine wired."""
    del detector_input  # unused — this is the explicit no-op the seam defaults to
    return []


__all__ = [
    "BookFittedDetector",
    "DetectedRegion",
    "DetectorInput",
    "RegionDetector",
    "null_region_detector",
]

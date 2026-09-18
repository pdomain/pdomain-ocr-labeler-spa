"""The pluggable region-detector seam a proposal run calls.

Mirrors ``pdomain_book_tools.layout.registry``'s ``NullDetector`` naming: a
default that proposes nothing, so the job scaffolding is runnable and testable
before slice 4's real geometry engine exists. Slice 4 supplies a real
``RegionDetector`` through ``JobRunner.context["region_detector"]`` — this
plan does not compute a single proposal itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.page import Page
from pdomain_pgdp_measure.page_templates import BookTemplates, PageClassification
from pdomain_pgdp_measure.profile_models import PageMeasurement

from .models import FACET_LINE_STRUCTURE, FACET_PAGE_IMAGE, FACET_WORD_BOXES


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


class BookFittedDetector(ABC):
    """A detector that must see the whole book before it judges any page.

    A nominal base class, not a structural ``Protocol``. ``isinstance`` against
    a ``runtime_checkable`` protocol checks only that an object has an
    attribute named ``fit``, and ``fit`` is about the most common method name
    in machine learning: any scikit-learn-style model has ``fit(X, y)``. A later
    model-backed detector wrapping one would be routed down the book-fit path,
    call an incompatible ``fit``, and propose nothing for the whole run. A
    detector opts in by subclassing.

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

    @abstractmethod
    def fit(self, book: Sequence[DetectorInput]) -> RegionDetector:
        """Fit to the whole book and return the per-page detector to use."""


def null_region_detector(detector_input: DetectorInput) -> list[DetectedRegion]:
    """The default detector: proposes nothing. Keeps the job runnable with no engine wired."""
    del detector_input  # unused — this is the explicit no-op the seam defaults to
    return []


DEFAULT_DETECTOR_FACETS = frozenset({FACET_WORD_BOXES, FACET_LINE_STRUCTURE, FACET_PAGE_IMAGE})
"""What a detector is assumed to read when it does not say otherwise.

Word boxes, line/paragraph structure, and the page image — never OCR/ground-
truth text — so a text-only edit never invalidates a plain geometry
detector's proposals (spec §"A proposal goes stale per facet, not per
page"). This is the shape every detector shipped before slice 6's poetry
detector had: ``FurnitureDetector`` and ``null_region_detector`` both read
nothing else, so neither declares ``depends_on_facets`` and both fall back
to this constant via :func:`detector_depends_on_facets`.
"""


@runtime_checkable
class _DeclaresFacetDependencies(Protocol):
    """Structural marker for a detector that names the facets it reads.

    ``depends_on_facets`` is a name this module invents for exactly this
    purpose, unlike ``fit`` (see ``BookFittedDetector``'s docstring on why an
    ``isinstance`` check against a name as common as ``fit`` is unsafe). No
    other object in this codebase happens to carry an attribute with this
    exact name, so an ``isinstance`` check against it is a safe way to read a
    typed ``frozenset[str]`` off whichever detectors choose to declare one,
    without a blanket ``getattr(..., default)`` that would type as ``Any``.
    """

    depends_on_facets: frozenset[str]


def detector_depends_on_facets(detector: RegionDetector | BookFittedDetector) -> frozenset[str]:
    """The page facets ``detector``'s proposals depend on, for ``ProposalRun.depends_on``.

    Reads ``detector.depends_on_facets`` when the detector declares one — a
    geometry-and-text detector such as the poetry detector must include
    ``FACET_WORD_TEXT``, or a text-only edit would never mark its own
    proposals stale. Falls back to :data:`DEFAULT_DETECTOR_FACETS` for
    anything that does not declare one: a plain ``RegionDetector`` callable,
    or a ``BookFittedDetector`` (such as ``FurnitureDetector``) that reads
    only geometry.
    """
    if isinstance(detector, _DeclaresFacetDependencies):
        return detector.depends_on_facets
    return DEFAULT_DETECTOR_FACETS


@dataclass(frozen=True)
class CompositeDetector(BookFittedDetector):
    """Runs every sub-detector over the same book and page, and proposes the union.

    The region-proposal seam is one callable per run (``runner.context
    ["region_detector"]``); a book that wants more than one detector's
    proposals — for instance both ``FurnitureDetector``'s page furniture and
    the poetry detector's verse blocks — needs one callable that runs both
    and concatenates what each returns. Each sub-detector's own box, role,
    confidence and evidence pass through unchanged; this class only fans the
    same ``DetectorInput`` out to every sub-detector and flattens their
    results.

    A sub-detector that is itself a ``BookFittedDetector`` is fit once, over
    the same book every other sub-detector sees; a plain ``RegionDetector``
    callable is used exactly as it always was. ``depends_on_facets`` is the
    union of every sub-detector's own facets (:func:`detector_depends_on_facets`)
    so ``propose_regions`` can still build one honest ``ProposalRun.depends_on``
    for the whole run, even though its sub-detectors read different things —
    getting this wrong would make one sub-detector's proposals invisible to
    staleness once a fact only it actually depends on changes.
    """

    detectors: tuple[RegionDetector | BookFittedDetector, ...]

    @property
    def depends_on_facets(self) -> frozenset[str]:
        if not self.detectors:
            return DEFAULT_DETECTOR_FACETS
        facets: frozenset[str] = frozenset()
        for one in self.detectors:
            facets |= detector_depends_on_facets(one)
        return facets

    def fit(self, book: Sequence[DetectorInput]) -> RegionDetector:
        fitted: list[RegionDetector] = [
            one.fit(book) if isinstance(one, BookFittedDetector) else one for one in self.detectors
        ]

        def _detect(detector_input: DetectorInput) -> list[DetectedRegion]:
            detected: list[DetectedRegion] = []
            for one in fitted:
                detected.extend(one(detector_input))
            return detected

        return _detect


__all__ = [
    "DEFAULT_DETECTOR_FACETS",
    "BookFittedDetector",
    "CompositeDetector",
    "DetectedRegion",
    "DetectorInput",
    "RegionDetector",
    "detector_depends_on_facets",
    "null_region_detector",
]

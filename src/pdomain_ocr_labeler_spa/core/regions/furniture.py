"""Propose page furniture — the running head and the folio — from band geometry.

Spec authority: pdomain-ocr-synth's
docs/specs/2026-09-17-geometry-region-proposals-design.md, "Start with page
furniture" and "A furniture band becomes one or two regions, not one".
Threshold-fitting authority: pdomain-ocr-synth's
docs/issues/2026-09-17-the-furniture-gap-threshold-cannot-be-a-fixed-share.md.

``furniture_band_ordinals`` names every ink band from the top of the page down
to and including the running-head band. The classifier can say this without
ambiguity because nothing is printed above the head. It is empty for a chapter
opening and for a page the classifier declined to classify, and empty means
propose nothing — never "guess from the top band".

The band gives the vertical extent. An ``InkBand`` is a row projection and
carries no horizontal extent at all, so where the ink sits across the page comes
from the page's own word boxes. A running head and a folio share one band and
are always separate regions (region-vocabulary hierarchy rule 3), so the words
in a band are split on a horizontal gap.

**The gap threshold is fitted per book, not fixed.** Measured across six books,
a fixed 10 percent of the book's text width sat inside the correct range in
none of them — the word-space/head-gap valley moves from book to book. A
``FurnitureDetector`` (a ``BookFittedDetector``) pools every in-band word gap
across the book, places the threshold at the midpoint of the Otsu valley, and
hands each page a callable closed over that one pixel value. A plain
``furniture_region_detector`` remains as the fixed-share fallback: used when a
book's own gaps do not support a fit, and for callers that have not adopted
the book-fit seam.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NamedTuple

from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.block import Block
from pdomain_book_tools.ocr.word import Word

from .detector import BookFittedDetector, DetectedRegion, DetectorInput

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdomain_book_tools.ocr.page import Page

    from .detector import RegionDetector

log = logging.getLogger(__name__)

FOLIO_GAP_SHARE_OF_TEXT_WIDTH = 0.10
"""Split a band's words into separate regions at a gap this wide, as a last resort.

Measured against the book's own fitted text width, not a pixel constant. This
is the fallback ``FurnitureDetector.fit`` and ``furniture_region_detector``
both use when a book's own gap distribution cannot be fitted — see
``_fit_gap_threshold_px``. A running head and a folio are typically separated
by 30 to 70 percent of the text width, while the spaces inside a head run 1 to
3 percent, so 10 percent sits in a wide empty gap between the two in most
books, but not all: the fitted threshold is preferred whenever a book supports
one.
"""

GapThresholdSource = Literal["book_fit", "fixed_share"]
"""Which threshold a page's proposals were judged against — carried in evidence
so a reviewer can tell a fitted split from a fallback."""

_MIN_POOLED_GAPS = 8
"""Below this many pooled in-band gaps, a book has too little evidence to fit."""

_MIN_GAP_CLASS_SIZE = 2
"""Below this many members, the Otsu split found no real second class."""

_MIN_THRESHOLD_SHARE_OF_TEXT_WIDTH = 0.02
_MAX_THRESHOLD_SHARE_OF_TEXT_WIDTH = 0.40
"""A fitted threshold outside this band of the book's text width is not
trusted — the guard against a book with no real bimodality in its gaps."""

# The three confidences below are a guess, not a measurement. They score the
# cluster's own shape — is it isolated, is it numeric — not the page's fit to
# its book template: ``classification.confidence`` answers "does this page
# look like the rest of the book", not "is this band a running head", and a
# page whose head band sits low in its book still has a head band. No region
# ground truth exists anywhere in the suite to calibrate against yet; slice
# 5's first review pass over real proposals is what sets these for real.

_FOLIO_CONFIDENCE = 0.8
"""A numeric cluster isolated in a furniture band. Two signals agree: the
classifier called the band furniture, and the cluster reads as a folio."""

_HEADER_CONFIDENCE = 0.6
"""A wide cluster sharing a furniture band with something else. The band is
furniture and this is the part of it that is not the folio."""

_LONE_HEADER_CONFIDENCE = 0.4
"""The only cluster in the band and not numeric. Could be a running head, or
could be the top line of body text under a misplaced band."""

_FOLIO_PATTERN = re.compile(r"^[0-9ivxlcdmIVXLCDM]+$")
"""Digits, roman numerals, or both. Anything else reads as a running head."""


@dataclass(frozen=True)
class _Cluster:
    """One horizontal run of words inside the furniture bands."""

    words: list[Word]

    @property
    def box(self) -> tuple[int, int, int, int]:
        boxes = [w.bounding_box for w in self.words]
        return (
            int(min(b.minX for b in boxes)),
            int(min(b.minY for b in boxes)),
            int(max(b.maxX for b in boxes)),
            int(max(b.maxY for b in boxes)),
        )

    @property
    def text(self) -> str:
        # ``Word`` has no ``ocr_text`` attribute — the OCR text lives on the
        # ``text`` property, with ``ground_truth_text`` preferred when present.
        return " ".join(w.ground_truth_text or w.text or "" for w in self.words).strip()

    @property
    def is_folio(self) -> bool:
        stripped = self.text.replace(" ", "")
        return bool(stripped) and bool(_FOLIO_PATTERN.match(stripped))


class _BandWords(NamedTuple):
    """One page's in-band words, plus the combined y range they were read against."""

    words: list[Word]
    top: int
    bottom: int


def _page_words(page: Page) -> list[Word]:
    """Every word on the page, at any nesting depth.

    Mirrors ``block_adapter._walk_blocks``, which walks the same tree for
    blocks. Duplicated rather than generalized: one walker that yields both
    would make every call site filter, and the two callers want different
    things.
    """
    words: list[Word] = []

    def walk(items: Sequence[Word | Block]) -> None:
        for item in items:
            if isinstance(item, Word):
                words.append(item)
            else:
                walk(item.items)

    walk(page.items)
    return words


def _text_width_px(detector_input: DetectorInput) -> int | None:
    """The book's fitted text width, or ``None`` when it has no templates."""
    templates = detector_input.templates.templates
    if not templates:
        return None
    widths = [t.text_right_px - t.text_left_px for t in templates if t.text_right_px > t.text_left_px]
    return max(widths) if widths else None


def _page_is_pixel_space(detector_input: DetectorInput) -> bool:
    """Whether the page's word boxes are safe to compare against source-frame bands."""
    try:
        if detector_input.page.is_content_normalized:
            log.warning(
                "furniture: page=%s has normalized word boxes; ink bands are "
                "source-frame pixels, so this page is skipped",
                detector_input.classification.page_name,
            )
            return False
    except ValueError:
        # Page.is_content_normalized raises on a page that mixes normalized
        # and pixel boxes. Neither this detector nor the book-level fit can
        # compare either convention against a band, so the page is skipped.
        log.warning(
            "furniture: page=%s mixes normalized and pixel word boxes; skipping",
            detector_input.classification.page_name,
        )
        return False
    return True


def _band_y_range(detector_input: DetectorInput, ordinals: Sequence[int]) -> tuple[int, int] | None:
    """The furniture bands' combined y range, or ``None`` when the profile disagrees with it."""
    bands = detector_input.measurement.ink_bands or ()
    if any(ordinal >= len(bands) for ordinal in ordinals):
        log.warning(
            "furniture: page=%s names band ordinals %s but the profile recorded "
            "%d band(s) — skipping the page",
            detector_input.classification.page_name,
            list(ordinals),
            len(bands),
        )
        return None
    return (min(bands[o].y_start for o in ordinals), max(bands[o].y_end for o in ordinals))


def _in_band_words(detector_input: DetectorInput) -> _BandWords | None:
    """Every word inside one page's furniture bands, or ``None`` when the page has none to read.

    Applies the same skip conditions the detector always applied: no
    furniture bands named, source-frame word boxes, and band ordinals inside
    the profile's recorded bands. Shared between per-page detection and
    book-level gap pooling, so both walk exactly the same words.
    """
    ordinals = detector_input.classification.furniture_band_ordinals
    if not ordinals:
        return None
    if not _page_is_pixel_space(detector_input):
        return None
    y_range = _band_y_range(detector_input, ordinals)
    if y_range is None:
        return None
    top, bottom = y_range
    words = [
        word
        for word in _page_words(detector_input.page)
        if word.bounding_box.has_usable_coordinates
        # The page-level guard above reads Page.is_content_normalized, which
        # only walks words inside LINE blocks. _page_words walks the whole
        # tree, so a normalized box on a word outside any line would otherwise
        # be compared against a source-frame band y range.
        and not word.bounding_box.is_normalized
        and top <= (word.bounding_box.minY + word.bounding_box.maxY) / 2 <= bottom
    ]
    return _BandWords(words, top, bottom)


def _cluster(words: list[Word], gap_px: float) -> list[_Cluster]:
    """Split words sorted by left edge wherever the gap to the next exceeds ``gap_px``."""
    if not words:
        return []
    ordered = sorted(words, key=lambda w: w.bounding_box.minX)
    clusters: list[list[Word]] = [[ordered[0]]]
    for word in ordered[1:]:
        previous_right = max(w.bounding_box.maxX for w in clusters[-1])
        if word.bounding_box.minX - previous_right > gap_px:
            clusters.append([word])
        else:
            clusters[-1].append(word)
    return [_Cluster(group) for group in clusters]


def _pooled_gaps(book: Sequence[DetectorInput]) -> list[float]:
    """Every in-band word gap across the book, pooled for the Otsu fit.

    ``gap = next word's minX minus previous word's maxX``, after sorting the
    page's in-band words by minX — the same pairwise definition the design
    issue measured its six books against.
    """
    gaps: list[float] = []
    for detector_input in book:
        band = _in_band_words(detector_input)
        if band is None or len(band.words) < 2:
            continue
        ordered = sorted(band.words, key=lambda w: w.bounding_box.minX)
        gaps.extend(
            ordered[i + 1].bounding_box.minX - ordered[i].bounding_box.maxX for i in range(len(ordered) - 1)
        )
    return gaps


def _book_text_width_px(book: Sequence[DetectorInput]) -> int | None:
    """The book's fitted text width, read off the first input that carries one."""
    for detector_input in book:
        width = _text_width_px(detector_input)
        if width is not None:
            return width
    return None


def _otsu_split(values: Sequence[float]) -> float:
    """The classic Otsu cut: the split point maximizing between-class variance.

    Every candidate split sits between two consecutive sorted values, so the
    result is exact for a small pooled sample rather than binned into a
    histogram — the method used to find the valley in all six books measured.
    """
    ordered = sorted(values)
    total = sum(ordered)
    count = len(ordered)
    best_cut = ordered[0]
    best_variance = -1.0
    running_low_sum = 0.0
    for i in range(count - 1):
        running_low_sum += ordered[i]
        low_count = i + 1
        high_count = count - low_count
        low_mean = running_low_sum / low_count
        high_mean = (total - running_low_sum) / high_count
        variance = low_count * high_count * (low_mean - high_mean) ** 2
        if variance > best_variance:
            best_variance = variance
            best_cut = (ordered[i] + ordered[i + 1]) / 2
    return best_cut


def _fit_gap_threshold_px(
    gaps: Sequence[float], text_width_px: int | None
) -> tuple[float, GapThresholdSource]:
    """Otsu-split the pooled gaps and place the threshold at the valley's midpoint.

    Falls back to the fixed share of the book's text width whenever the
    book's own gaps do not support a fit: too few pooled gaps, an Otsu split
    that leaves either class with fewer than two members, or a fitted
    threshold implausible against the book's own text width. See the module
    docstring and the design issue this replaces.
    """
    fallback_px = text_width_px * FOLIO_GAP_SHARE_OF_TEXT_WIDTH if text_width_px is not None else 0.0
    if text_width_px is None or len(gaps) < _MIN_POOLED_GAPS:
        return fallback_px, "fixed_share"

    cut = _otsu_split(gaps)
    low = [g for g in gaps if g <= cut]
    high = [g for g in gaps if g > cut]
    if len(low) < _MIN_GAP_CLASS_SIZE or len(high) < _MIN_GAP_CLASS_SIZE:
        return fallback_px, "fixed_share"

    valley_midpoint = (max(low) + min(high)) / 2
    share = valley_midpoint / text_width_px
    if not (_MIN_THRESHOLD_SHARE_OF_TEXT_WIDTH <= share <= _MAX_THRESHOLD_SHARE_OF_TEXT_WIDTH):
        return fallback_px, "fixed_share"

    return valley_midpoint, "book_fit"


def _furniture_region_detector(
    detector_input: DetectorInput,
    *,
    gap_threshold_px: float,
    gap_threshold_source: GapThresholdSource,
) -> list[DetectedRegion]:
    """Propose one region per horizontal cluster inside the page's furniture bands."""
    band = _in_band_words(detector_input)
    if band is None or not band.words:
        return []

    text_width = _text_width_px(detector_input)
    if text_width is None:
        return []

    ordinals = detector_input.classification.furniture_band_ordinals
    clusters = _cluster(band.words, gap_threshold_px)

    detected: list[DetectedRegion] = []
    for cluster in clusters:
        left, cluster_top, right, cluster_bottom = cluster.box
        is_folio = cluster.is_folio
        if is_folio:
            confidence = _FOLIO_CONFIDENCE
        elif len(clusters) == 1:
            confidence = _LONE_HEADER_CONFIDENCE
        else:
            confidence = _HEADER_CONFIDENCE
        detected.append(
            DetectedRegion(
                role=RegionRole.PAGE_NUMBER if is_folio else RegionRole.PAGE_HEADER,
                box=(left, cluster_top, right, cluster_bottom),
                confidence=confidence,
                evidence={
                    "band_ordinals": list(ordinals),
                    "band_y_range": [band.top, band.bottom],
                    "cluster_width_px": right - left,
                    "cluster_count": len(clusters),
                    "text_width_px": text_width,
                    "gap_threshold_px": round(gap_threshold_px, 2),
                    "gap_threshold_source": gap_threshold_source,
                    "page_class": detector_input.classification.page_class,
                    "page_class_confidence": detector_input.classification.confidence,
                    "template_residual_px": detector_input.classification.template_residual_px,
                },
            )
        )
    return detected


def furniture_region_detector(detector_input: DetectorInput) -> list[DetectedRegion]:
    """Split furniture bands at the fixed share of the book's text width.

    The plain, book-fit-free detector. Kept so nothing that imports it
    breaks, so a caller that has not adopted the ``BookFittedDetector`` seam
    still gets a working default, and as the value ``FurnitureDetector.fit``
    itself falls back to when a book's own gaps cannot be fitted.
    ``FurnitureDetector`` — not this function — is what ``bootstrap.py``
    wires as the default.
    """
    text_width = _text_width_px(detector_input)
    gap_threshold_px = text_width * FOLIO_GAP_SHARE_OF_TEXT_WIDTH if text_width is not None else 0.0
    return _furniture_region_detector(
        detector_input, gap_threshold_px=gap_threshold_px, gap_threshold_source="fixed_share"
    )


@dataclass(frozen=True)
class FurnitureDetector(BookFittedDetector):
    """A ``BookFittedDetector`` that fits the furniture gap threshold to its own book.

    ``fit`` pools every in-band word gap across the book (the same in-band
    filter ``furniture_region_detector`` always applied), places the
    threshold at the midpoint of the Otsu valley, and returns a per-page
    callable closed over that one pixel threshold and its source. Never
    raises on an ordinary book — every "cannot fit" condition falls back to
    the fixed share of text width internally rather than propagating.
    """

    def fit(self, book: Sequence[DetectorInput]) -> RegionDetector:
        gaps = _pooled_gaps(book)
        text_width_px = _book_text_width_px(book)
        gap_threshold_px, gap_threshold_source = _fit_gap_threshold_px(gaps, text_width_px)

        def _detect(detector_input: DetectorInput) -> list[DetectedRegion]:
            return _furniture_region_detector(
                detector_input,
                gap_threshold_px=gap_threshold_px,
                gap_threshold_source=gap_threshold_source,
            )

        return _detect


__all__ = [
    "FOLIO_GAP_SHARE_OF_TEXT_WIDTH",
    "FurnitureDetector",
    "GapThresholdSource",
    "furniture_region_detector",
]

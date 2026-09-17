"""Propose page furniture — the running head and the folio — from band geometry.

Spec authority: pdomain-ocr-synth's
docs/specs/2026-09-17-geometry-region-proposals-design.md, "Start with page
furniture" and "A furniture band becomes one or two regions, not one".

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
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.block import Block
from pdomain_book_tools.ocr.word import Word

from .detector import DetectedRegion, DetectorInput

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdomain_book_tools.ocr.page import Page

log = logging.getLogger(__name__)

FOLIO_GAP_SHARE_OF_TEXT_WIDTH = 0.10
"""Split a band's words into separate regions at a gap this wide.

Measured against the book's own fitted text width, not a pixel constant — the
same principle the word-gap finding established, that a threshold shared across
books is wrong in every one of them. A running head and a folio are typically
separated by 30 to 70 percent of the text width, while the spaces inside a head
run 1 to 3 percent, so 10 percent sits in a wide empty gap between the two.
This is a starting value and the first review pass over real proposals should
check it.
"""

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


def furniture_region_detector(detector_input: DetectorInput) -> list[DetectedRegion]:
    """Propose one region per horizontal cluster inside the page's furniture bands."""
    ordinals = detector_input.classification.furniture_band_ordinals
    if not ordinals:
        return []

    try:
        if detector_input.page.is_content_normalized:
            log.warning(
                "furniture_region_detector: page=%s has normalized word boxes; ink bands "
                "are source-frame pixels, so this page is skipped",
                detector_input.classification.page_name,
            )
            return []
    except ValueError:
        # Page.is_content_normalized raises on a page that mixes normalized and
        # pixel boxes. A detector cannot compare either convention against a
        # band, so the page is skipped rather than half-measured.
        log.warning(
            "furniture_region_detector: page=%s mixes normalized and pixel word boxes; skipping",
            detector_input.classification.page_name,
        )
        return []

    bands = detector_input.measurement.ink_bands or ()
    if any(ordinal >= len(bands) for ordinal in ordinals):
        log.warning(
            "furniture_region_detector: page=%s names band ordinals %s but the profile "
            "recorded %d band(s) — skipping the page",
            detector_input.classification.page_name,
            list(ordinals),
            len(bands),
        )
        return []

    text_width = _text_width_px(detector_input)
    if text_width is None:
        return []

    top = min(bands[o].y_start for o in ordinals)
    bottom = max(bands[o].y_end for o in ordinals)
    in_band = [
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
    if not in_band:
        return []

    clusters = _cluster(in_band, text_width * FOLIO_GAP_SHARE_OF_TEXT_WIDTH)

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
                    "band_y_range": [top, bottom],
                    "cluster_width_px": right - left,
                    "cluster_count": len(clusters),
                    "text_width_px": text_width,
                    "gap_threshold_px": round(text_width * FOLIO_GAP_SHARE_OF_TEXT_WIDTH, 2),
                    "page_class": detector_input.classification.page_class,
                    "page_class_confidence": detector_input.classification.confidence,
                    "template_residual_px": detector_input.classification.template_residual_px,
                },
            )
        )
    return detected


__all__ = ["FOLIO_GAP_SHARE_OF_TEXT_WIDTH", "furniture_region_detector"]

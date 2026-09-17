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
from typing import Any

from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_tools.ocr.page import Page


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


RegionDetector = Callable[[Page], Sequence[DetectedRegion]]
"""Takes a ``pdomain_book_tools.ocr.page.Page`` and returns what it detected."""


def null_region_detector(page: Page) -> list[DetectedRegion]:
    """The default detector: proposes nothing. Keeps the job runnable before slice 4 lands."""
    del page  # unused — this is the explicit no-op the seam defaults to
    return []


__all__ = ["DetectedRegion", "RegionDetector", "null_region_detector"]

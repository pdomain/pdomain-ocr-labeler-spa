"""IGlyphPredictor — Protocol for glyph-annotation predictions.

Mirrors IOCREngine's seam pattern. v1 ships only `none_`; pd-ocr-trainer
delivers the local classifier when its glyph-feature work lands.

Predictions are NOT persisted — they are recomputed at page-fetch time.
The frontend renders them as greyed-out chips with accept/reject.
"""

from __future__ import annotations

from typing import Protocol

from pd_ocr_labeler_spa.core.models import WordMatch


class IGlyphPredictor(Protocol):
    """Predict glyph annotations for a list of words."""

    def predict(self, words: list[WordMatch]) -> list[dict[str, object] | None]:
        """Return one prediction dict (or None) per input word, same order."""
        ...


class NoneGlyphPredictor:
    """Default adapter — always returns None for every word."""

    def predict(self, words: list[WordMatch]) -> list[dict[str, object] | None]:
        return [None] * len(words)

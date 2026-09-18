"""IGlyphPredictor — Protocol for glyph-annotation predictions.

Mirrors IOCREngine's seam pattern. `NoneGlyphPredictor` is the only adapter
that exists, and none will be built here (decided 2026-09-18): `pd-ocr-trainer`
is retired, and no successor produces glyph features. See
`docs/context/decisions.md` and `specs/20-glyph-annotations.md` §9. The seam
stays at near-zero cost — the accept-prediction UI simply never fires.

Predictions are NOT persisted — they would be recomputed at page-fetch time.
The frontend renders them as greyed-out chips with accept/reject, when present.
"""

from __future__ import annotations

from typing import Protocol

from pdomain_ocr_labeler_spa.core.models import WordMatch


class IGlyphPredictor(Protocol):
    """Predict glyph annotations for a list of words."""

    def predict(self, words: list[WordMatch]) -> list[dict[str, object] | None]:
        """Return one prediction dict (or None) per input word, same order."""
        ...


class NoneGlyphPredictor:
    """Default adapter — always returns None for every word."""

    def predict(self, words: list[WordMatch]) -> list[dict[str, object] | None]:
        return [None] * len(words)

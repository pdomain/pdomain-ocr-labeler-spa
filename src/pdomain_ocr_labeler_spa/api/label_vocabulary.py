"""``GET /api/label-vocabulary`` — canonical text-style and word-component
vocabulary sourced from ``pdomain_book_tools``.

Spec authority: OPEN_QUESTIONS.md Q-B2-STYLE-LABELS (option b).

Why a dedicated route (not extending ocr-config):

- ``/api/ocr-config`` is concerned with OCR model selection, auto-rotate
  settings, and hardware probing — a different responsibility plane.
- The label vocabulary is stable and never changes within a running server;
  it belongs on a lightweight, cacheable endpoint that the frontend fetches
  once at startup.
- A separate route keeps the ``ocr-config`` shape stable and avoids coupling
  the model-selection contract to label-vocabulary changes.

The values are SOURCED from book-tools' canonical constants, NOT re-hardcoded:

- ``ALLOWED_TEXT_STYLE_LABELS`` — all strings accepted by
  ``normalize_text_style_label``; any other value raises ``ValueError`` (→ 500).
- ``ALLOWED_COMPONENTS`` — all strings accepted by
  ``normalize_word_component``; any other value raises ``ValueError`` (→ 500).

Both sets are sorted before returning so the response is deterministic and
diffable in snapshots/tests.
"""

from __future__ import annotations

from fastapi import APIRouter
from pdomain_book_tools.ocr.label_normalization import (
    ALLOWED_COMPONENTS,
    ALLOWED_TEXT_STYLE_LABELS,
)
from pydantic import BaseModel

router = APIRouter(prefix="/api/label-vocabulary", tags=["label-vocabulary"])


class LabelVocabularyResponse(BaseModel):
    """Canonical label vocabulary sourced from pdomain_book_tools.

    text_style_labels — values accepted by ``normalize_text_style_label``.
    word_components   — values accepted by ``normalize_word_component``.

    Both lists are sorted for deterministic ordering.
    """

    text_style_labels: list[str]
    word_components: list[str]


# Built once at import time — these constants never change between requests.
_VOCABULARY = LabelVocabularyResponse(
    text_style_labels=sorted(ALLOWED_TEXT_STYLE_LABELS),
    word_components=sorted(ALLOWED_COMPONENTS),
)


@router.get("", response_model=LabelVocabularyResponse)
def get_label_vocabulary() -> LabelVocabularyResponse:
    """Return the canonical text-style and word-component label vocabulary.

    Values are sourced directly from ``pdomain_book_tools.ocr.label_normalization``
    so the frontend can never drift from the backend's validation logic.

    The response is static (no request-time computation) and suitable for
    aggressive client-side caching (staleTime = Infinity is fine).
    """
    return _VOCABULARY


def install_label_vocabulary_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the label-vocabulary router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "LabelVocabularyResponse",
    "install_label_vocabulary_router",
    "router",
]

"""Text normalization helpers — issue #260.

Delegates to ``pd_book_tools.text.normalize.normalize_string`` when available.
When the module is absent (older pin), returns the input string unchanged and
sets ``is_available() == False`` so callers can show the "requires pd-book-tools
≥ X.Y.Z" message.

Spec authority:
- ``docs/specs/2026-05-12-text-normalization-design.md``
- ``specs/18-text-normalization.md``
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Module-level availability probe — evaluated once at import time.
try:
    from pd_book_tools.text.normalize import (  # type: ignore[import-untyped]
        normalize_string as _pd_normalize,
    )

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    _pd_normalize = None  # type: ignore[assignment]


def is_available() -> bool:
    """Return True if pd_book_tools.text.normalize is importable.

    Used by the OCRConfigModal to decide whether to enable the normalize
    toggle or show "Requires pd-book-tools ≥ X.Y.Z".
    """
    return _AVAILABLE


def normalize_string(text: str, profile: str = "ascii") -> str:
    """Normalize ``text`` using the given profile.

    When pd_book_tools.text.normalize is available, delegates to
    ``normalize_string(text, profile=profile)`` from that module.

    When unavailable, returns ``text`` unchanged and emits a debug log
    on the first call (not a warning — the caller already knows and shows
    a tooltip; flooding the log at WARNING would be noise).

    Contract (from spec):
    - ``normalize_string("ſhall", "ascii") == "shall"``
    - ``normalize_string("shall", "ascii") == "shall"``  # idempotent
    - Never raises; returns input unchanged on any error.
    """
    if not _AVAILABLE:
        return text
    try:
        result: str = _pd_normalize(text, profile=profile)
        return result
    except Exception:
        log.debug(
            "normalize_string failed for %r (profile=%r); returning unchanged",
            text,
            profile,
            exc_info=True,
        )
        return text

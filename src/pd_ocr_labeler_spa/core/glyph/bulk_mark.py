"""Glyph bulk-mark recipe engine — spec ``specs/20-glyph-annotations.md`` §6.2.

Applies one of three built-in recipes to a list of word dicts and returns
the affected word positions + the annotations to write.

This module is pure (no I/O, no FastAPI deps) so it can be unit-tested
without a loaded project.

Recipes
-------
``ct_substring``
    Every word whose GT contains the two-character sequence ``ct`` gets a
    ``LigatureMark(kind="ct", char_span=(start, start+2))``.  Multiple
    occurrences in the same word → multiple marks.

``st_substring``
    Same as ``ct_substring`` but for ``st``.

``long_s_typeset_era``
    For every lowercase ``s`` in the GT string that is *not* at the last
    position AND is *not* immediately followed by ``b``, ``k``, ``h``,
    or ``f``, add its character index to ``long_s_positions``.  This is
    a heuristic for long-s rules in early-modern typography.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

_LONG_S_EXCLUDED_FOLLOWERS: frozenset[str] = frozenset("bkhf")
"""Characters after which long-s is NOT used (typesetter convention)."""


@dataclass
class GlyphBulkMarkParams:
    """Parameters for a bulk-mark recipe run — mirrors ``GlyphBulkMarkRequest``."""

    recipe: Literal["ct_substring", "st_substring", "long_s_typeset_era"]
    skip_already_annotated: bool = True
    accept_predictions: bool = False
    dry_run: bool = False


@dataclass
class BulkMarkResult:
    """Output of ``apply_bulk_mark``.

    Attributes
    ----------
    affected_word_ids:
        ``(line_index, word_index)`` tuples of words that *would be* (or
        were) modified.  Populated even in dry-run mode.
    skipped_word_ids:
        ``(line_index, word_index)`` tuples of words that were skipped
        because they already had annotations (when
        ``skip_already_annotated=True``).
    annotations:
        Map from ``(line_index, word_index)`` → annotation dict (the shape
        written to the envelope / API wire).  Empty in dry-run mode.
    """

    affected_word_ids: list[tuple[int, int]] = field(default_factory=list)
    skipped_word_ids: list[tuple[int, int]] = field(default_factory=list)
    annotations: dict[tuple[int, int], dict[str, object]] = field(default_factory=dict)

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)  # pyright: ignore[reportAny]


def _find_substring_spans(gt: str, sub: str) -> list[tuple[int, int]]:
    """Return all non-overlapping ``[start, end)`` spans of *sub* in *gt*."""
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        idx = gt.lower().find(sub, start)
        if idx == -1:
            break
        spans.append((idx, idx + len(sub)))
        start = idx + len(sub)
    return spans


def _long_s_positions(gt: str) -> list[int]:
    """Return char indices where long-s applies (typeset-era heuristic)."""
    positions: list[int] = []
    for i, ch in enumerate(gt):
        if ch != "s":
            continue
        # Skip if at end of word
        if i == len(gt) - 1:
            continue
        # Skip if followed by an excluded character
        next_ch = gt[i + 1].lower()
        if next_ch in _LONG_S_EXCLUDED_FOLLOWERS:
            continue
        positions.append(i)
    return positions


def apply_bulk_mark(
    words: list[dict[str, object]],
    params: GlyphBulkMarkParams,
) -> BulkMarkResult:
    """Apply a bulk-mark recipe to *words* and return the result.

    Parameters
    ----------
    words:
        List of dicts, each with keys:
        - ``"gt"``: ground-truth text string
        - ``"line"``: line_index (int)
        - ``"word"``: word_index (int)
        - ``"existing_annotations"`` (optional): current annotation dict or None

    params:
        Recipe + options.

    Returns a :class:`BulkMarkResult` with affected/skipped IDs and
    the annotation dicts to write (empty if ``dry_run=True``).
    """
    result = BulkMarkResult()

    for word_dict in words:
        gt = str(word_dict.get("gt") or "")
        raw_li = word_dict.get("line", 0)
        raw_wi = word_dict.get("word", 0)
        li = int(raw_li) if isinstance(raw_li, (int, float, str)) else 0
        wi = int(raw_wi) if isinstance(raw_wi, (int, float, str)) else 0
        existing = word_dict.get("existing_annotations")
        pos = (li, wi)

        # Skip already-annotated words when requested
        if params.skip_already_annotated and existing is not None:
            result.skipped_word_ids.append(pos)
            continue

        if params.recipe in ("ct_substring", "st_substring"):
            sub = "ct" if params.recipe == "ct_substring" else "st"
            spans = _find_substring_spans(gt, sub)
            if not spans:
                continue
            kind_str = sub  # "ct" or "st"
            ligatures = [{"kind": kind_str, "char_span": list(span)} for span in spans]
            annotation: dict[str, object] = {
                "ligatures": ligatures,
                "long_s_positions": [],
                "swash": False,
                "source": "human",
            }
            result.affected_word_ids.append(pos)
            if not params.dry_run:
                result.annotations[pos] = annotation

        elif params.recipe == "long_s_typeset_era":
            positions = _long_s_positions(gt)
            if not positions:
                continue
            annotation = {
                "ligatures": [],
                "long_s_positions": positions,
                "swash": False,
                "source": "human",
            }
            result.affected_word_ids.append(pos)
            if not params.dry_run:
                result.annotations[pos] = annotation

    return result

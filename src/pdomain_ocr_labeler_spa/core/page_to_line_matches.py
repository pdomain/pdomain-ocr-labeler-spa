"""Convert a ``pdomain_book_tools.ocr.page.Page`` to SPA wire shapes.

This module provides the "lifting" layer that converts the live OCR ``Page``
object (from ``LocalDoctrPageLoader.run_ocr`` or loaded from a
``UserPageEnvelope``) into the SPA's ``PageRecord`` + ``LineMatch[]`` pair.

Spec authority:
- ``docs/architecture/01-data-models.md §1`` — ``PageRecord``, ``LineMatch``,
  ``WordMatch``, ``MatchStatus``, ``BBox`` shapes.
- ``docs/architecture/04-image-viewport.md §1`` — ``PageRecord`` fields.
- ``docs/plan-to-usable.md`` blocker B1 — ``_page_payload`` must build
  populated ``page_record`` + ``line_matches`` from the OCR outcome.

Legacy parity:
- ``pd_ocr_labeler/viewmodels/project/word_match_view_model.py:update_from_page``
  (line 52) — the authoritative ``Page → LineMatch[]`` logic.
- ``pd_ocr_labeler/operations/ocr/word_operations.py:WordOperations.classify_match_status``
  (line 26) — match-status classification algorithm.

The function is pure (no I/O, no side effects) so it can be called from both
``get_page`` and ``_page_payload`` without lock concerns.

``UserPageEnvelope → Page`` lifting is deferred — when the outcome came from
the labeled/cached lane its ``payload`` is a ``UserPageEnvelope``; the caller
must call ``Page.from_dict(envelope.payload.page)`` first if it wants populated
``LineMatch[]``.  Until that lift is wired this function will be called only on
OCR-lane outcomes (``payload`` is already a ``Page``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pdomain_book_tools.ocr.page import Page as _Page

from .models import (
    BBox,
    CharRange,
    GlyphAnnotationsModel,
    LigatureMarkModel,
    LineMatch,
    MatchStatus,
    PageRecord,
    PageSource,
    WordMatch,
)

log = logging.getLogger(__name__)


def _convert_glyph_annotations(ga_obj: object | None) -> GlyphAnnotationsModel | None:
    """Convert a ``pdomain_book_tools.GlyphAnnotations`` dataclass to ``GlyphAnnotationsModel``.

    Returns ``None`` when ``ga_obj`` is ``None`` (not-yet-reviewed state).
    Returns an empty ``GlyphAnnotationsModel()`` when ``ga_obj`` is a
    ``GlyphAnnotations`` with no marks (reviewed, nothing to annotate).

    ``source`` is NOT carried by ``pdomain_book_tools.GlyphAnnotations``; it defaults
    to ``"human"`` for any annotation that comes from a saved envelope (since
    the SPA writes those as human-authored).  The caller is responsible for
    setting ``source="predicted"`` when attaching classifier output via
    ``WordMatch.glyph_predictions``.
    """
    if ga_obj is None:
        return None
    ligatures: list[LigatureMarkModel] = []
    for lm in getattr(ga_obj, "ligatures", []) or []:  # pyright: ignore[reportAny]
        kind_val = getattr(lm, "kind", None)  # pyright: ignore[reportAny]
        if kind_val is None:
            continue
        kind_str = kind_val.value if hasattr(kind_val, "value") else str(kind_val)  # pyright: ignore[reportAny]
        span = getattr(lm, "char_span", None)  # pyright: ignore[reportAny]
        ligatures.append(LigatureMarkModel(kind=kind_str, char_span=span))
    return GlyphAnnotationsModel(
        ligatures=ligatures,
        long_s_positions=list(getattr(ga_obj, "long_s_positions", []) or []),
        swash=bool(getattr(ga_obj, "swash", False)),
        source="human",
    )


@runtime_checkable
class _HasLines(Protocol):
    """Minimal structural type for objects with a .lines attribute.

    Used in tests that pass duck-typed stubs instead of real Page objects.
    """

    lines: list[object]


# Default fuzzy-match threshold — mirrors legacy
# ``WordMatchViewModel.fuzz_threshold=0.8``
# (``pd_ocr_labeler/viewmodels/project/word_match_view_model.py:26``).
# Callers should prefer passing ``fuzz_threshold`` explicitly (sourced from
# ``AppConfig.fuzz_threshold``) rather than relying on this default.
_FUZZ_THRESHOLD = 0.8


def _classify_match_status(
    ocr_text: str,
    ground_truth_text: str,
    word_obj: object,
    fuzz_threshold: float = _FUZZ_THRESHOLD,
) -> tuple[MatchStatus, float | None]:
    """Classify match status between OCR text and ground truth.

    Algorithm mirrors legacy
    ``pd_ocr_labeler/operations/ocr/word_operations.py:WordOperations.classify_match_status``
    (line 26).

    Parameters
    ----------
    fuzz_threshold :
        Words with a fuzz score >= this value are classified as ``FUZZY``
        rather than ``MISMATCH``.  Sourced from ``AppConfig.fuzz_threshold``;
        defaults to ``_FUZZ_THRESHOLD`` (0.8) for backwards compatibility.

    Returns ``(match_status, fuzz_score | None)``.
    """
    if not ground_truth_text:
        return MatchStatus.UNMATCHED_OCR, None
    if ocr_text.strip() == ground_truth_text.strip():
        return MatchStatus.EXACT, 1.0

    # Attempt pdomain_book_tools' built-in fuzz scorer first (avoids an extra
    # thefuzz import at call time; the Word object caches the result).
    fuzz_score: float | None = None
    fuzz_scorer = getattr(word_obj, "fuzz_score_against", None)
    if callable(fuzz_scorer):
        try:
            raw_score: Any = fuzz_scorer(ground_truth_text)
            fuzz_score = float(raw_score) if raw_score is not None else None
        except Exception:
            log.warning(
                "_classify_match_status: fuzz_score_against raised for word %r — using score 0.0",
                ocr_text,
                exc_info=True,
            )

    if fuzz_score is not None and fuzz_score >= fuzz_threshold:
        return MatchStatus.FUZZY, fuzz_score

    return MatchStatus.MISMATCH, fuzz_score if fuzz_score is not None else 0.0


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)  # pyright: ignore[reportArgumentType]
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _bbox_to_model(
    bbox_obj: object,
    *,
    page_width: int | None,
    page_height: int | None,
) -> BBox:
    """Convert a pdomain-book-tools bbox to source-image pixel coordinates."""
    min_x = float(getattr(bbox_obj, "minX", 0) or 0)
    min_y = float(getattr(bbox_obj, "minY", 0) or 0)
    max_x = float(getattr(bbox_obj, "maxX", 0) or 0)
    max_y = float(getattr(bbox_obj, "maxY", 0) or 0)

    if bool(getattr(bbox_obj, "is_normalized", False)):
        if page_width is None or page_height is None:
            log.warning(
                "_bbox_to_model: normalized bbox encountered without page dimensions — "
                "coordinates may collapse to zero"
            )
        else:
            min_x *= page_width
            max_x *= page_width
            min_y *= page_height
            max_y *= page_height

    return BBox(
        x=round(min_x),
        y=round(min_y),
        width=max(0, round(max_x - min_x)),
        height=max(0, round(max_y - min_y)),
    )


def _word_to_word_match(
    word_index: int,
    line_index: int,
    word_obj: object,
    fuzz_threshold: float = _FUZZ_THRESHOLD,
    char_bboxes_map: dict[str, list[dict[str, int]]] | None = None,
    char_ranges_map: dict[str, list[dict[str, object]]] | None = None,
    page_width: int | None = None,
    page_height: int | None = None,
) -> WordMatch | None:
    """Convert one ``pdomain_book_tools.ocr.word.Word`` to a ``WordMatch``.

    Parameters
    ----------
    fuzz_threshold :
        Passed through to ``_classify_match_status``; sourced from
        ``AppConfig.fuzz_threshold`` by the ``page_to_line_matches`` caller.
    char_bboxes_map :
        Optional per-word char-bbox sidecar from ``PageState.char_bboxes_map``,
        keyed by ``"{line_index}_{word_index}"``.  When present, the matching
        entry is surfaced onto ``WordMatch.char_bboxes``.
    char_ranges_map :
        Optional per-word char-range sidecar from ``PageState.char_ranges_map``,
        keyed by ``"{line_index}_{word_index}"``.  When present, the matching
        entry is surfaced onto ``WordMatch.char_ranges``.

    Returns ``None`` on any attribute error so the caller can skip.
    """
    try:
        ocr_text: str = getattr(word_obj, "text", "") or ""
        gt_text: str = getattr(word_obj, "ground_truth_text", "") or ""

        # ``is_validated`` — Word doesn't have a first-class field today;
        # falls back to the per-page ``validated_words`` sidecar map
        # maintained by the SPA's word-mutation layer (spec-23-C1).
        # Here we just read the word_labels "validated" tag as the legacy
        # labeler does (``pd_ocr_labeler/viewmodels/.../word_match_view_model.py:241``).
        word_labels: set[str] = set(getattr(word_obj, "word_labels", []) or [])
        is_validated = "validated" in word_labels

        text_style_labels: list[str] = list(getattr(word_obj, "text_style_labels", []) or [])
        word_components: list[str] = list(getattr(word_obj, "word_components", []) or [])

        # BBox — from ``Word.bounding_box`` (a ``pdomain_book_tools.geometry.bounding_box.BoundingBox``).
        bbox_obj = getattr(word_obj, "bounding_box", None)
        if bbox_obj is None:
            log.warning(
                "_word_to_word_match: word at line=%d word=%d has no bounding_box — dropped",
                line_index,
                word_index,
            )
            return None  # Can't build a WordMatch without a bbox.
        bb = _bbox_to_model(bbox_obj, page_width=page_width, page_height=page_height)

        match_status, fuzz_score = _classify_match_status(
            ocr_text, gt_text, word_obj, fuzz_threshold=fuzz_threshold
        )

        # Composite sidecar key — stable as long as the page is not re-OCR'd.
        sidecar_key = f"{line_index}_{word_index}"

        # Char-bbox sidecar: look up by composite key.
        char_bboxes: list[BBox] | None = None
        if char_bboxes_map is not None:
            raw_bboxes = char_bboxes_map.get(sidecar_key)
            if raw_bboxes is not None:
                char_bboxes = [
                    BBox(
                        x=int(b.get("x", 0)),
                        y=int(b.get("y", 0)),
                        width=int(b.get("width", 0)),
                        height=int(b.get("height", 0)),
                    )
                    for b in raw_bboxes
                    if isinstance(b, dict)
                ]

        # Char-range sidecar: look up by composite key.
        char_ranges: list[CharRange] | None = None
        if char_ranges_map is not None:
            raw_ranges = char_ranges_map.get(sidecar_key)
            if raw_ranges is not None:
                char_ranges = [
                    CharRange(
                        start=int(r.get("start", 0)),  # pyright: ignore[reportArgumentType]
                        end=int(r.get("end", 0)),  # pyright: ignore[reportArgumentType]
                        styles=list(r.get("styles", [])),  # pyright: ignore[reportArgumentType]
                    )
                    for r in raw_ranges
                    if isinstance(r, dict)
                ]

        # Glyph annotations — propagated from ``Word.glyph_annotations`` (spec §3).
        # ``source`` defaults to "human" for envelope-loaded pages.
        # ``glyph_predictions`` is left as None here; it is injected by the
        # ``IGlyphPredictor`` adapter at payload-build time (not yet wired).
        glyph_annotations = _convert_glyph_annotations(getattr(word_obj, "glyph_annotations", None))

        return WordMatch(
            line_index=line_index,
            word_index=word_index,
            ocr_text=ocr_text,
            ground_truth_text=gt_text,
            match_status=match_status,
            fuzz_score=fuzz_score,
            is_validated=is_validated,
            text_style_labels=text_style_labels,
            word_components=word_components,
            bbox=bb,
            word_id=None,  # pdomain_book_tools doesn't expose a stable word-id today
            char_bboxes=char_bboxes,
            char_ranges=char_ranges,
            glyph_annotations=glyph_annotations,
        )
    except Exception:
        log.debug("_word_to_word_match: failed for line=%d word=%d", line_index, word_index, exc_info=True)
        return None


def _count_match_statuses(word_matches: list[WordMatch]) -> dict[MatchStatus, int]:
    counts: dict[MatchStatus, int] = dict.fromkeys(MatchStatus, 0)
    for wm in word_matches:
        counts[wm.match_status] = counts.get(wm.match_status, 0) + 1
    return counts


def _overall_match_status(word_matches: list[WordMatch]) -> MatchStatus:
    """Rollup match status for a line.

    Mirrors the legacy ``LineMatch.overall_match_status`` property
    (``pd_ocr_labeler/models/line_match_model.py:100``): any mismatch
    dominates over fuzzy; any fuzzy over exact; all-unmatched-ocr →
    unmatched_ocr; all-exact → exact; empty → unmatched_ocr.
    """
    if not word_matches:
        return MatchStatus.UNMATCHED_OCR
    statuses = {wm.match_status for wm in word_matches}
    if MatchStatus.MISMATCH in statuses:
        return MatchStatus.MISMATCH
    if MatchStatus.UNMATCHED_GT in statuses:
        return MatchStatus.MISMATCH
    has_matched = MatchStatus.EXACT in statuses or MatchStatus.FUZZY in statuses
    if MatchStatus.UNMATCHED_OCR in statuses and not has_matched:
        return MatchStatus.UNMATCHED_OCR
    if MatchStatus.FUZZY in statuses:
        return MatchStatus.FUZZY
    return MatchStatus.EXACT


def _build_line_to_paragraph_lookup(page: object) -> dict[int, int]:
    """Return ``{id(line_obj): paragraph_index}`` for all lines in *page*.

    Mirrors legacy
    ``pd_ocr_labeler/viewmodels/project/word_match_view_model.py:_build_line_paragraph_lookup``
    (line 146).
    """
    result: dict[int, int] = {}
    try:
        paragraphs = getattr(page, "paragraphs", None) or []
        for para_idx, para in enumerate(paragraphs):
            for line in getattr(para, "lines", []) or []:
                result[id(line)] = para_idx
    except Exception:
        log.warning(
            "_build_line_to_paragraph_lookup: failed — paragraph_index will be None on all lines",
            exc_info=True,
        )
    return result


def _build_line_to_block_lookup(page: object) -> dict[int, int]:
    """Return ``{id(line_obj): block_index}`` for all lines in *page*.

    FO-7: ``pdomain_book_tools`` exposes blocks via ``page.items`` (list of
    ``Block`` objects, each with ``.paragraphs`` → ``.lines``).  The SPA
    surfaces block_index onto each ``LineMatch`` so the frontend can group
    lines by their top-level layout block for navigation.

    Falls back gracefully when the page object does not expose an ``items``
    attribute — returns an empty dict, leaving ``block_index`` as ``None``
    on every ``LineMatch`` (pre-FO-7 no-op behaviour).
    """
    result: dict[int, int] = {}
    try:
        blocks = getattr(page, "items", None) or []
        for block_idx, block in enumerate(blocks):
            for para in getattr(block, "paragraphs", []) or []:
                for line in getattr(para, "lines", []) or []:
                    result[id(line)] = block_idx
    except Exception:
        log.warning(
            "_build_line_to_block_lookup: failed — block_index will be None on all lines",
            exc_info=True,
        )
    return result


def page_to_line_matches(
    page: _Page | _HasLines | object | None,
    page_index: int,
    image_path: Path,
    source: PageSource = PageSource.OCR,
    fuzz_threshold: float = _FUZZ_THRESHOLD,
    char_bboxes_map: dict[str, list[dict[str, int]]] | None = None,
    char_ranges_map: dict[str, list[dict[str, object]]] | None = None,
) -> tuple[PageRecord, list[LineMatch]]:
    """Convert a ``pdomain_book_tools.ocr.page.Page`` to ``(PageRecord, [LineMatch])``.

    Parameters
    ----------
    page :
        A live ``pdomain_book_tools.ocr.page.Page`` object (or any duck-typed
        equivalent exposing ``.lines`` / ``.paragraphs``).  ``None`` is
        tolerated — both outputs degrade gracefully to minimal defaults.
    page_index :
        0-based page index, written into the ``PageRecord`` + every
        ``LineMatch`` / ``WordMatch``.
    image_path :
        Absolute path to the source image, stored in ``PageRecord``.
    source :
        ``PageSource`` to record in ``PageRecord.page_source``.
    fuzz_threshold :
        Fuzzy-match threshold forwarded to every ``_word_to_word_match``
        call.  Words with a fuzz score >= this threshold are classified as
        ``FUZZY`` rather than ``MISMATCH``.  Callers should read this from
        ``AppConfig.fuzz_threshold`` (default ``0.8`` preserves legacy
        behaviour when no config is available).
    char_bboxes_map :
        Optional per-word char-bbox sidecar from ``PageState.char_bboxes_map``,
        keyed by ``"{line_index}_{word_index}"``.  When provided, matching
        entries are surfaced onto each ``WordMatch.char_bboxes``.
    char_ranges_map :
        Optional per-word char-range sidecar from ``PageState.char_ranges_map``,
        keyed by ``"{line_index}_{word_index}"``.  When provided, matching
        entries are surfaced onto each ``WordMatch.char_ranges``.

    Returns
    -------
    ``(PageRecord, list[LineMatch])``
        ``PageRecord`` holds page-level metadata.
        ``list[LineMatch]`` is empty when *page* has no lines or is ``None``.
    """
    from uuid import uuid4 as _uuid4

    record = PageRecord(
        page_id=_uuid4(),
        page_index=page_index,
        image_path=image_path,
        source=source.value if hasattr(source, "value") else str(source),
    )

    if page is None:
        return record, []

    # Wrong-type guard: if the object has no .lines, the caller likely passed a
    # UserPageEnvelope instead of a Page (envelope→Page lift failed upstream).
    # None is the documented "no OCR yet" path; a non-None object without .lines
    # is a caller bug — log WARNING so it's visible at default log level.
    if not hasattr(page, "lines"):
        log.warning(
            "page_to_line_matches: page has no 'lines' attribute (type=%s)"
            " — envelope→Page lift likely failed; returning empty line_matches",
            type(page).__name__,
        )
        return record, []

    line_matches: list[LineMatch] = []

    try:
        lines = getattr(page, "lines", None) or []
        page_width = _positive_int(getattr(page, "width", None))
        page_height = _positive_int(getattr(page, "height", None))
        # Defensive: skip non-iterable (e.g. Mock without __iter__)
        try:
            iter(lines)
        except TypeError:
            return record, []

        try:
            para_lookup = _build_line_to_paragraph_lookup(page)
        except Exception:
            log.warning(
                "page_to_line_matches: _build_line_to_paragraph_lookup raised"
                " — paragraph_index will be None on all lines",
                exc_info=True,
            )
            para_lookup = {}

        try:
            block_lookup = _build_line_to_block_lookup(page)
        except Exception:
            log.warning(
                "page_to_line_matches: _build_line_to_block_lookup raised"
                " — block_index will be None on all lines",
                exc_info=True,
            )
            block_lookup = {}

        for line_idx, line in enumerate(lines):
            try:
                words = getattr(line, "words", []) or []
                word_matches: list[WordMatch] = []
                for word_idx, word in enumerate(words):
                    wm = _word_to_word_match(
                        word_idx,
                        line_idx,
                        word,
                        fuzz_threshold=fuzz_threshold,
                        char_bboxes_map=char_bboxes_map,
                        char_ranges_map=char_ranges_map,
                        page_width=page_width,
                        page_height=page_height,
                    )
                    if wm is not None:
                        word_matches.append(wm)

                # Unmatched GT words (list[tuple[int, str]] insertion points).
                # Mirrors legacy ``_create_enhanced_word_matches``
                # (``pd_ocr_labeler/viewmodels/project/word_match_view_model.py:163``).
                unmatched_gt: list[tuple[int, str]] = list(
                    getattr(line, "unmatched_ground_truth_words", []) or []
                )
                for insert_idx, gt_word_text in sorted(unmatched_gt, reverse=True):
                    # Insert after the OCR word at insert_idx so display order
                    # matches the GT sequence. Insert before word_matches length
                    # guard (clamp to end of list).
                    clamped = min(insert_idx, len(word_matches))
                    um_wm = WordMatch(
                        line_index=line_idx,
                        word_index=None,
                        ocr_text="",
                        ground_truth_text=gt_word_text,
                        match_status=MatchStatus.UNMATCHED_GT,
                        fuzz_score=None,
                        bbox=BBox(x=0, y=0, width=0, height=0),
                    )
                    word_matches.insert(clamped, um_wm)

                # Skip completely empty lines (no OCR words AND no GT words).
                if not word_matches:
                    continue

                counts = _count_match_statuses(word_matches)
                validated_count = sum(1 for wm in word_matches if wm.is_validated)

                lm = LineMatch(
                    line_index=line_idx,
                    paragraph_index=para_lookup.get(id(line)),
                    block_index=block_lookup.get(id(line)),
                    ocr_line_text=getattr(line, "text", "") or "",
                    ground_truth_line_text=getattr(line, "ground_truth_text", "") or "",
                    word_matches=word_matches,
                    overall_match_status=_overall_match_status(word_matches),
                    exact_count=counts.get(MatchStatus.EXACT, 0),
                    fuzzy_count=counts.get(MatchStatus.FUZZY, 0),
                    mismatch_count=counts.get(MatchStatus.MISMATCH, 0),
                    unmatched_gt_count=counts.get(MatchStatus.UNMATCHED_GT, 0),
                    unmatched_ocr_count=counts.get(MatchStatus.UNMATCHED_OCR, 0),
                    validated_word_count=validated_count,
                    total_word_count=len(word_matches),
                    is_fully_validated=bool(word_matches) and all(wm.is_validated for wm in word_matches),
                )
                line_matches.append(lm)

            except Exception:
                log.debug("page_to_line_matches: skipping line %d (exception)", line_idx, exc_info=True)

    except Exception:
        log.debug("page_to_line_matches: failed to iterate page lines", exc_info=True)

    return record, line_matches


__all__ = ["page_to_line_matches"]

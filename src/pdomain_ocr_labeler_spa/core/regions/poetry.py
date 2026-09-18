"""Propose poetry from right-edge raggedness and the capital-initial line convention.

Measurement authority: pdomain-ocr-synth's
``docs/research/2026-09-18-ragged-right-finds-poetry-blockquote-has-no-geometric-signature.md``
(the "note"), and the evidence scripts it cites,
``/workspaces/pdomain/.m15f-evidence/poetry-blockquote/measure_blocks.py`` and
``analyze_blocks.py``. Every threshold below is a named constant copied from
that measurement, with its own docstring saying where it came from — see
each constant, not this module docstring, for the number's provenance.

**Only poetry.** The note found no working geometric or text signal for
blockquote in this corpus (2.3 percent precision at best) — its own ground
truth is 44 heterogeneous spans (letters, stage directions, a dateline) with
no shared shape. This module proposes ``RegionRole.POETRY`` only, never
``RegionRole.BLOCKQUOTE``.

**How the two signals are combined.** The note found the capital-initial
text rule stronger than the geometry rule at every threshold it swept
(95.4 percent precision / 96.3 percent recall, pooled, against raggedness's
87.5 / 93.3), so text decides whenever it has enough to go on. Geometry is
the fallback for exactly the case the note names as the reason a pure-text
rule cannot stand alone: "the geometry rule is what survives when OCR text
is poor." A block's *own* OCR text quality — not a corpus-wide setting — is
what decides which signal a block is judged by: at least half its lines
must yield a checkable leading character (:data:`MIN_CHECKABLE_LINE_SHARE`)
before the text rule is trusted; below that the block falls back to
raggedness alone. Both signals are computed and recorded in ``evidence``
regardless of which one decided, so a reviewer can see both, and
``evidence["decided_by"]`` names which one this proposal's confidence came
from.

``MIN_CHECKABLE_LINE_SHARE`` is *not* one of the note's own numbers — the
note does not measure an OCR-quality cutoff, only the two rules' precision
against ground truth. It is this module's own reasoned default for when
text is degraded enough to distrust, named and documented here so a person
can tune it without reading the algorithm around it.

**Block segmentation diverges from the measurement, deliberately.**
``measure_blocks.py`` segments text blocks itself, from row-projection ink
bands, grouping consecutive kept bands wherever the gap between them is
under 1.5x the book's median single-line gap. This module instead reads the
page's own already-computed paragraph structure (``Page.paragraphs`` /
``Block.lines``) — the same line/paragraph tree ``block_adapter.py``'s
``line_structure`` facet already hashes, and the same tree the furniture
detector's sibling would read for its blocks were it to need them. Both
methods answer "which lines belong to the same block", so the raggedness
and indent *formulas* below are exactly the note's own (median-based right-
edge MAD, and indent, each as a fraction of the book's fitted text width) —
only the segmentation mechanism differs, in favor of structure this
codebase already maintains over re-deriving it from ink bands a second time.
A paragraph boundary the reorganize pipeline places is not guaranteed to
land exactly where a gap-multiple rule over ink bands would; this is a real
divergence from what was measured, not merely a re-implementation of it, and
is called out here and in this detector's report rather than left implicit.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pdomain_book_contracts.annotation import RegionRole

from .coordinates import bounding_box_to_pixels
from .detector import DetectedRegion, DetectorInput
from .models import FACET_LINE_STRUCTURE, FACET_PAGE_IMAGE, FACET_WORD_BOXES, FACET_WORD_TEXT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdomain_book_tools.ocr.block import Block
    from pdomain_pgdp_measure.page_templates import PageTemplate

RAGGED_RIGHT_EDGE_MAD_THRESHOLD_FRAC = 0.008
"""Right-edge MAD (as a fraction of the book's fitted text width) above which
a block counts as "ragged". From the note's "The corpus and how it was
measured": "A block counts as ragged once that fraction passes 0.008. That
threshold sits in a genuinely empty gap in the data. Prose-labeled blocks
have a right-edge deviation whose 90th percentile is 0.003 of text width;
poetry-labeled blocks have a 10th percentile of 0.012 ... The two
populations' medians differ fortyfold: 0.001 for prose versus 0.041 for
poetry." Also ``analyze_blocks.py``'s ``RAGGED_T``. The note's own sweep
(0.004 to 0.030) keeps precision between 83 and 88 percent, so this is a
stable choice, not a fragile one — see "Raggedness is stable across a wide
range of thresholds"."""

CAPITAL_LINE_START_FRACTION_THRESHOLD = 0.9
"""Fraction of a block's checkable lines that must start with a capital
letter for the text rule to call it poetry. From the note's "Every rule
tested, scored against ground truth": "each line starts with a capital
letter (text only) — vs. poetry: 95.4% / 96.3%". Also ``analyze_blocks.py``'s
``cap_cond``, ``b["cap_frac"] >= 0.9``."""

MIN_LINES_FOR_POETRY_SIGNALS = 2
"""Below this many lines, neither signal below is evaluated. From the note's
"What the corpus contains": "single-line blocks (raggedness cannot be
measured on one line): 1,916 (34.1%)" — excluded from every precision/recall
number the note reports for both the raggedness rule and the capital-initial
rule, which is scored only over blocks with ``n_lines >= 2``
(``analyze_blocks.py``'s ``aligned_multi`` / the capital rule's own
``n_lines >= 2`` filter)."""

MIN_CHECKABLE_LINE_SHARE = 0.5
"""Share of a block's lines that must yield a checkable leading character
(see :func:`_checkable_leading_char`) before the text rule is trusted over
geometry. This is this module's own combination glue, not one of the note's
measured numbers — the note does not measure an OCR-quality cutoff, only
each rule's precision against ground truth text. Tune it down to trust
partial OCR text more readily; tune it up to fall back to geometry sooner."""

INDENT_THRESHOLD_FRAC_OF_TEXT_WIDTH = 0.03
"""Recorded in ``evidence`` for transparency; never gates the decision below.
From the note's "The corpus and how it was measured": "A block counts as
indented on a side once that fraction passes 0.03 (roughly one em in these
books)." Also ``measure_blocks.py``'s ``INDENT_FRAC``. The note found indent
is *not* what separates poetry — "Requiring indent in addition to raggedness
raises poetry's precision slightly ... but costs a third of its recall" —
and a block indented on both sides but not ragged is the awkward middle the
note warns reads as blockquote-shaped, not verse. This module measures
indent only so a reviewer can see it in ``evidence``; it plays no part in
``is_poetry`` below."""

TEXT_RULE_PRECISION = 0.954
"""Confidence assigned when the capital-initial text rule decides. Literally
the note's own pooled precision for that rule against ground-truth poetry —
see :data:`CAPITAL_LINE_START_FRACTION_THRESHOLD`'s docstring for the exact
figure and its source table. **Not calibrated as a per-page probability**:
it is the corpus-pooled precision of the rule that fired, and the note is
explicit that the pooled figure is carried mostly by one poetry-anthology
book — per-book precision on the other four books ranges 12.5 to 88.9
percent ("The pooled number is mostly one book — the other four are thin
evidence"). Treated here as the best available honest number for "how often
this rule was right when it fired, on the corpus it was measured against" —
not a promise that any single proposal is that likely to be correct."""

GEOMETRY_RULE_PRECISION = 0.875
"""Confidence assigned when the block falls back to raggedness alone (its
own OCR text was too degraded to trust — see :data:`MIN_CHECKABLE_LINE_SHARE`).
The note's own pooled precision for "ragged right alone, no indent
required" against ground-truth poetry — see
:data:`RAGGED_RIGHT_EDGE_MAD_THRESHOLD_FRAC`'s docstring. Same calibration
caveat as :data:`TEXT_RULE_PRECISION`: a pooled, corpus-measured precision,
not a per-page probability."""

_LEADING_PUNCTUATION_PATTERN = re.compile(r"""^[\[\("'<>/isc.,;:!?\s]*""")
_LEADING_TAG_PATTERN = re.compile(r"^<[^>]+>")
"""Mirror ``analyze_blocks.py``'s ``cap_start_frac`` exactly: strip leading
bracket/quote/punctuation characters, then strip one leading HTML-like tag
left behind (PGDP text carries ``<i>`` etc.), in that order — the same two
``re.sub`` calls, nested the same way, so this module scores the same signal
the note measured rather than something close to it."""

_DetectedBy = Literal["text", "geometry"]


def _checkable_leading_char(text: str) -> str | None:
    """The first character of ``text`` once leading punctuation/markup is stripped.

    ``None`` when nothing is left — an empty, whitespace-only, or
    all-punctuation line, which contributes to neither the numerator nor the
    denominator of :func:`_capital_start_fraction`, exactly as
    ``analyze_blocks.py``'s ``cap_start_frac`` skips a blank stripped line.
    """
    without_punctuation = _LEADING_PUNCTUATION_PATTERN.sub("", text)
    without_tag = _LEADING_TAG_PATTERN.sub("", without_punctuation).strip()
    return without_tag[0] if without_tag else None


def _capital_start_fraction(line_texts: Sequence[str]) -> tuple[float | None, int]:
    """``(cap_frac, n_checked)`` over ``line_texts`` — mirrors ``cap_start_frac``.

    ``cap_frac`` is ``None`` when no line yielded a checkable leading
    character at all.
    """
    n_checked = 0
    n_cap = 0
    for text in line_texts:
        leading = _checkable_leading_char(text)
        if leading is None:
            continue
        n_checked += 1
        if leading.isupper():
            n_cap += 1
    cap_frac = n_cap / n_checked if n_checked else None
    return cap_frac, n_checked


def _line_text(line: Block) -> str:
    """A line's text, ground truth preferred — mirrors ``furniture.py``'s ``_scaled_word_text``."""
    return line.ground_truth_text or line.text


def _source_to_page_scale(detector_input: DetectorInput) -> tuple[float, float]:
    """Factors that carry the book's fitted text edges into the page's own pixel frame.

    Duplicated from ``furniture.py``'s private helper of the same name rather
    than imported — this module's own convention, matching that module's own
    "Duplicated rather than generalized" choice for ``_page_words`` — so each
    detector module stays self-contained. See ``furniture.py``'s
    ``_source_to_page_scale`` docstring for the full rationale: templates are
    measured in ``measurement.source_frame``, but every box this detector
    proposes must be in the page's own ``page.width`` by ``page.height``
    frame, the frame ``accept`` reads a proposal back in.
    """
    page = detector_input.page
    frame = detector_input.measurement.source_frame
    if frame is None or frame.width <= 0 or frame.height <= 0:
        return 1.0, 1.0
    return page.width / frame.width, page.height / frame.height


def _matching_template(detector_input: DetectorInput) -> PageTemplate | None:
    """The book's fitted template for this page's own ``page_class``, or ``None``."""
    for template in detector_input.templates.templates:
        if template.page_class == detector_input.classification.page_class:
            return template
    return None


def _text_edges_px(detector_input: DetectorInput) -> tuple[float, float] | None:
    """``(text_left_px, text_right_px)`` in the page's own pixel frame, or ``None``.

    ``None`` when the book has no fitted template for this page's class, or
    the template's edges are degenerate — the same "nothing to measure
    against" skip ``furniture.py``'s ``_text_width_px`` applies.
    """
    template = _matching_template(detector_input)
    if template is None or template.text_right_px <= template.text_left_px:
        return None
    scale_x, _ = _source_to_page_scale(detector_input)
    return template.text_left_px * scale_x, template.text_right_px * scale_x


def _line_box_px(line: Block, *, page_width: int, page_height: int) -> tuple[int, int, int, int] | None:
    """A line's box in the page's own pixel frame, or ``None`` when it has none usable."""
    bbox = line.bounding_box
    if bbox is None or not bbox.has_usable_coordinates:
        return None
    return bounding_box_to_pixels(bbox, page_width=page_width, page_height=page_height)


def _right_edge_mad_frac(
    line_boxes: Sequence[tuple[int, int, int, int]], text_width_px: float
) -> float | None:
    """Median absolute deviation of ``line_boxes``' right edges, as a fraction of text width.

    ``None`` below :data:`MIN_LINES_FOR_POETRY_SIGNALS` usable boxes — MAD is
    not meaningful over fewer, the same reason the note excludes single-line
    blocks from this signal entirely.
    """
    if len(line_boxes) < MIN_LINES_FOR_POETRY_SIGNALS or text_width_px <= 0:
        return None
    rights = [box[2] for box in line_boxes]
    median_right = statistics.median(rights)
    mad = statistics.median(abs(right - median_right) for right in rights)
    return mad / text_width_px


def _union_box(boxes: Sequence[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    """The smallest box containing every box in ``boxes``. ``boxes`` must be non-empty."""
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _detect_paragraph(
    paragraph: Block,
    *,
    page_width: int,
    page_height: int,
    text_left_px: float,
    text_right_px: float,
) -> DetectedRegion | None:
    """One paragraph block's poetry proposal, or ``None`` when nothing fires."""
    lines = paragraph.lines
    if len(lines) < MIN_LINES_FOR_POETRY_SIGNALS:
        return None

    text_width_px = text_right_px - text_left_px
    if text_width_px <= 0:
        return None

    line_boxes = [_line_box_px(line, page_width=page_width, page_height=page_height) for line in lines]
    usable_boxes = [box for box in line_boxes if box is not None]

    right_mad_frac = _right_edge_mad_frac(usable_boxes, text_width_px)
    ragged = right_mad_frac is not None and right_mad_frac > RAGGED_RIGHT_EDGE_MAD_THRESHOLD_FRAC

    line_texts = [_line_text(line) for line in lines]
    cap_frac, n_checked = _capital_start_fraction(line_texts)
    checkable_share = n_checked / len(lines)
    text_is_reliable = cap_frac is not None and checkable_share >= MIN_CHECKABLE_LINE_SHARE

    indented_left = indented_right = False
    left_indent_frac = right_indent_frac = None
    if usable_boxes:
        median_left = statistics.median(box[0] for box in usable_boxes)
        median_right = statistics.median(box[2] for box in usable_boxes)
        left_indent_frac = (median_left - text_left_px) / text_width_px
        right_indent_frac = (text_right_px - median_right) / text_width_px
        indented_left = left_indent_frac > INDENT_THRESHOLD_FRAC_OF_TEXT_WIDTH
        indented_right = right_indent_frac > INDENT_THRESHOLD_FRAC_OF_TEXT_WIDTH

    if text_is_reliable:
        assert cap_frac is not None  # narrows for basedpyright; text_is_reliable already implies it
        is_poetry = cap_frac >= CAPITAL_LINE_START_FRACTION_THRESHOLD
        decided_by: _DetectedBy = "text"
        confidence = TEXT_RULE_PRECISION
    else:
        is_poetry = ragged
        decided_by = "geometry"
        confidence = GEOMETRY_RULE_PRECISION

    if not is_poetry:
        return None

    bbox = paragraph.bounding_box
    if bbox is not None and bbox.has_usable_coordinates:
        box = bounding_box_to_pixels(bbox, page_width=page_width, page_height=page_height)
    elif usable_boxes:
        box = _union_box(usable_boxes)
    else:
        return None

    return DetectedRegion(
        role=RegionRole.POETRY,
        box=box,
        confidence=confidence,
        evidence={
            "decided_by": decided_by,
            "n_lines": len(lines),
            "n_checkable_lines": n_checked,
            "checkable_line_share": round(checkable_share, 4),
            "text_rule_reliable": text_is_reliable,
            "cap_frac": round(cap_frac, 4) if cap_frac is not None else None,
            "cap_threshold_frac": CAPITAL_LINE_START_FRACTION_THRESHOLD,
            "right_mad_frac": round(right_mad_frac, 4) if right_mad_frac is not None else None,
            "ragged": ragged,
            "ragged_threshold_frac": RAGGED_RIGHT_EDGE_MAD_THRESHOLD_FRAC,
            "indented_left": indented_left,
            "indented_right": indented_right,
            "indented_both": indented_left and indented_right,
            "left_indent_frac": round(left_indent_frac, 4) if left_indent_frac is not None else None,
            "right_indent_frac": round(right_indent_frac, 4) if right_indent_frac is not None else None,
            "text_width_px": round(text_width_px, 1),
        },
    )


def poetry_region_detector(detector_input: DetectorInput) -> list[DetectedRegion]:
    """Propose a ``RegionRole.POETRY`` region for every paragraph that reads as verse.

    Walks the page's own paragraph structure (``Page.paragraphs``) rather
    than re-segmenting ink bands — see the module docstring's "Block
    segmentation diverges from the measurement, deliberately". Returns
    nothing when the book has no fitted template for this page's class,
    the same "nothing to measure against" skip every geometry detector in
    this package applies.
    """
    edges = _text_edges_px(detector_input)
    if edges is None:
        return []
    text_left_px, text_right_px = edges
    page = detector_input.page
    detected: list[DetectedRegion] = []
    for paragraph in page.paragraphs:
        region = _detect_paragraph(
            paragraph,
            page_width=page.width,
            page_height=page.height,
            text_left_px=text_left_px,
            text_right_px=text_right_px,
        )
        if region is not None:
            detected.append(region)
    return detected


_POETRY_DETECTOR_FACETS = frozenset(
    {FACET_WORD_BOXES, FACET_LINE_STRUCTURE, FACET_PAGE_IMAGE, FACET_WORD_TEXT}
)
"""Unlike a pure-geometry detector, this one reads OCR text (the
capital-initial rule) as well as word boxes, line structure and the page
image — so its ``ProposalRun.depends_on`` must include ``FACET_WORD_TEXT``,
or a text-only edit (fixing a misrecognized capital letter, say) would never
mark this detector's own proposals stale. See
``core/regions/detector.py``'s ``detector_depends_on_facets``, which reads
this off ``PoetryDetector.depends_on_facets`` when building the run."""


POETRY_DETECTOR_MODEL_ID = "poetry-ragged-and-capital-initial"
"""Identity to pass as ``model_id`` when starting a ``propose_regions`` run
that includes this detector.

``ProposalRun.model_id``/``model_version`` are caller-supplied per run —
``StartRegionProposalRunRequest`` (``api/regions.py``) takes them straight
from the request body, defaulting to the caller-agnostic ``"null-detector"``/
``"0.0.0"`` when a caller passes neither. That is an existing, wider design
this module does not change; what this module contributes is a real, stable
identity a caller *can* pass, so a poetry-aware run's provenance says what
actually produced it rather than falling through to the generic default."""

POETRY_DETECTOR_MODEL_VERSION = "2026-09-18.1"
"""Version to pass alongside :data:`POETRY_DETECTOR_MODEL_ID`.

Dated to the measurement this detector's thresholds are pinned to (the
note's own date, 2026-09-18), plus a revision counter for this module.
Bump the counter if a threshold above changes without the underlying
measurement being redone; bump the date if the measurement itself is."""


@dataclass(frozen=True)
class PoetryDetector:
    """Callable ``RegionDetector`` that proposes ``RegionRole.POETRY`` regions.

    A plain callable object, not a ``BookFittedDetector``: every threshold it
    uses is a fixed, named constant taken from the measurement (see the
    module docstring) rather than something fit to this book's own
    distribution, so it has no book-wide pass to make before judging a page.
    Wrap it in ``CompositeDetector`` alongside ``FurnitureDetector`` to run
    both over the same book in one proposal run.
    """

    depends_on_facets: frozenset[str] = field(default=_POETRY_DETECTOR_FACETS)

    def __call__(self, detector_input: DetectorInput) -> list[DetectedRegion]:
        return poetry_region_detector(detector_input)


__all__ = [
    "CAPITAL_LINE_START_FRACTION_THRESHOLD",
    "GEOMETRY_RULE_PRECISION",
    "INDENT_THRESHOLD_FRAC_OF_TEXT_WIDTH",
    "MIN_CHECKABLE_LINE_SHARE",
    "MIN_LINES_FOR_POETRY_SIGNALS",
    "POETRY_DETECTOR_MODEL_ID",
    "POETRY_DETECTOR_MODEL_VERSION",
    "RAGGED_RIGHT_EDGE_MAD_THRESHOLD_FRAC",
    "TEXT_RULE_PRECISION",
    "PoetryDetector",
    "poetry_region_detector",
]

"""``/api/projects/{project_id}/review-queue`` — one answer for every kind of
review work.

Spec authority: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-
what-to-review-next.md "One route, in the order the work happens". Builds on
the region queue (``api/regions.py``'s ``get_region_review_queue``, from
docs/specs/2026-09-17-book-review-queue-design.md) and the page-kinds route
(``api/page_kinds.py``, from docs/specs/2026-09-17-page-kind-review-
design.md).

Reuses the existing counting paths rather than writing second versions of
them: ``page_kinds_rows`` (the page-kinds reader), ``is_undecided`` (the
region queue's undecided predicate), and ``reviewed_word_keys`` (the
typography numerator's journal read). Reads each journal once — six reads
total for five kinds, since the word and typography kinds share the same
``WordReviewCountsJournal`` read — and opens no page.

The typography numerator is the one exception to "cheap": once its journal
holds real correction history, reading it costs about 80 microseconds a row
(measured; see ``_TYPOGRAPHY_CORRECTIONS_MAX_BYTES``), not the negligible
cost the design first projected from a book whose journal happened to be
empty. Above that threshold the ``typography`` entry reports
``available: false`` with a reason, checked by one ``stat()`` rather than a
read — the same honesty the ``glyph`` entry already has for a different
cause.

A project loaded from a labeling bundle never calls
``save_page_content_to_store`` at all — text validation is a CAS append to
``ImportedTextValidationLog`` instead, and typography corrections are keyed
by the bundle's own ``page_id``, not ``stable_page_id``. ``_word_entry``
handles two such shapes: a single-page bundle project counts from the real
thing (the bundle is already resident, and its validation journal is cheap
at one page's scale), while a multi-page labeling-bundle book reports
``word`` (and therefore ``typography``, which cannot be answered without it)
as ``available: false`` — its book manifest gives page identity without I/O,
but never a page's word total, which only its own materialized bundle
carries. See ``_word_entry``'s docstring for the full three-way split.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.project_state import ProjectState
from ..core.regions.decision_log import RegionDecisionLog
from ..core.regions.proposal_log import RegionProposalLog
from ..core.regions.resolver import is_undecided
from ..core.review_counts import WordReviewCountsJournal
from ..core.typography_review import (
    ImportedTextValidationLog,
    TypographyCorrectionLog,
    reviewed_word_keys,
    stable_page_id,
)
from .dependencies import get_project_state
from .middleware.error_handler import ApiError
from .page_kinds import PageKindsListItem, page_kinds_rows
from .typography import TYPOGRAPHY_TAXONOMY

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from pdomain_book_tools.typography import LabelingBundle

    from ..core.models import Project

router = APIRouter(prefix="/api/projects", tags=["review-queue"])

_ReviewQueueKindName = Literal["page_kind", "region", "word", "typography", "glyph"]

_GLYPH_UNAVAILABLE_REASON = "no glyph predictor is wired"

_TYPOGRAPHY_CORRECTIONS_MAX_BYTES = 512 * 1024
"""Above this, the typography numerator is not cheap to compute.

pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-review-
next.md "What each kind costs to count" projected the typography numerator
as journal-cheap on the strength of the one book measured, whose corrections
journal was empty. Measured afterwards on a fixture with real correction
history (labeler-spa `2cfc834`'s follow-up measurement): reading and parsing
``TypographyCorrectionLog.records()`` costs about 80 microseconds a row,
because every row is a pydantic ``TypographyJournalEnvelope`` with a nested
``WordTypography`` replacement, not a flat dict — file size tracks row count
closely (about 2.3 KB a row for this taxonomy). At 512 KiB (about 224 rows)
the read costs about 16ms; at 600 KiB about 20ms; at 800 KiB about 27ms. 512
KiB keeps the read in the low tens of milliseconds with headroom before the
next size step crosses further into it, and it is a size ``stat()`` answers
in one syscall — no read, no parse — so the gate itself costs nothing
per-row to evaluate, unlike a row-count threshold would.
"""

_TYPOGRAPHY_TOO_LARGE_REASON_TEMPLATE = (
    "typography-corrections journal is {size} bytes, over the {threshold} byte "
    "limit for a single request's read (see docs/issues/2026-09-18-typography-"
    "numerator-needs-a-per-page-rollup.md)"
)

_BOOK_LABELING_SESSION_WORD_UNAVAILABLE_REASON = (
    "project is a multi-page labeling-bundle book: each page's word total "
    "lives only in that page's own bundle, and the book manifest this route "
    "can read without I/O does not carry it, so answering it would mean "
    "opening every page"
)


def _no_logical_page_id(page_index: int) -> str:
    """Placeholder ``logical_page_id`` for a ``_WordCountSource`` with nothing to look up."""
    del page_index
    return ""


@dataclass(frozen=True)
class _WordCountSource:
    """What the ``typography`` entry needs from whichever ``word``-counting path ran.

    Three project shapes feed the ``word`` kind, and each keys typography
    corrections differently — see ``_word_entry``:

    - An ordinary project: pages keyed by ``stable_page_id``, counts from
      ``WordReviewCountsJournal``.
    - A single-page labeling-bundle project: one page, keyed by the bundle's
      own ``page_id`` (what ``TypographyCorrectionLog`` records for it also
      use — see ``api/typography.py``'s ``_logical_page_id``), counted from
      the resident bundle plus ``ImportedTextValidationLog``.
    - A multi-page labeling-bundle book: unavailable (see ``_word_entry``),
      so this is empty and ``logical_page_id`` is never called.

    ``total_words_by_page`` is empty exactly when the ``word`` kind could not
    count any page — the ``typography`` entry treats that the same as being
    blocked by ``word``, never as "zero work".
    """

    total_words_by_page: dict[int, int] = field(default_factory=dict)
    logical_page_id: Callable[[int], str] = _no_logical_page_id


class ReviewQueueKindEntry(BaseModel):
    """One kind's outstanding-work count, in the order the work happens.

    ``blocked_by`` names another kind that is genuinely stopping this one
    right now — live, not a fixed label: it is ``None`` once that is no
    longer true, even for a kind that is always blocked in principle (e.g.
    typography once every word is validated). A caller should pick the
    first entry, in list order, with ``outstanding > 0`` and
    ``blocked_by is None``.

    ``first_page_index`` is the earliest page a person should jump to for
    this kind's outstanding work — ``None`` when there is none
    (``outstanding == 0``) or the kind is unavailable.

    ``pages_not_counted`` and ``is_lower_bound`` matter for ``word`` and
    ``typography`` only; both default to the "nothing to distrust" value for
    the other kinds. ``is_lower_bound`` is ``True`` for ``typography``
    always (its per-head staleness check is skipped — see
    ``core.typography_review.reviewed_word_keys``) and for ``word`` whenever
    ``pages_not_counted`` is above zero.
    """

    kind: _ReviewQueueKindName
    outstanding: int
    total: int
    available: bool
    blocked_by: _ReviewQueueKindName | None
    first_page_index: int | None
    pages_not_counted: int = 0
    is_lower_bound: bool = False
    unavailable_reason: str | None = None


class ReviewQueueResponse(BaseModel):
    """The book-level answer to "what should I review next", for every kind."""

    kinds: list[ReviewQueueKindEntry]


def _review_queue_project_not_found(project_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(error="project_not_found", message=f"project not found: {project_id}").model_dump(),
    )


def _page_kind_entry(
    project: Project, project_state: ProjectState
) -> tuple[ReviewQueueKindEntry, list[PageKindsListItem]]:
    """The ``page_kind`` entry, plus the rows region eligibility is derived from."""
    rows, reviewed_count = page_kinds_rows(project, project_state)
    total = project.total_pages
    first_page_index = next((row.page_index for row in rows if not row.reviewed), None)
    entry = ReviewQueueKindEntry(
        kind="page_kind",
        outstanding=total - reviewed_count,
        total=total,
        available=True,
        blocked_by=None,
        first_page_index=first_page_index,
    )
    return entry, rows


def _region_entry(project: Project, page_kind_rows: list[PageKindsListItem]) -> ReviewQueueKindEntry:
    """The ``region`` entry, sharing ``is_undecided`` with the region-only queue.

    ``blocked_by`` is ``"page_kind"`` only when no page in the book has
    either a proposed or a confirmed kind — the same test
    ``propose_regions``'s eligibility loop applies per page, reproduced here
    from ``page_kind_rows`` alone: a page counts as having kind state when
    it carries a live review marker (``reviewed``), a confirmed kind
    (``confirmed_kind``, which is set by the live page when loaded or by a
    marker that carries one), or a proposed kind (``proposed_kind``). A
    single page confirmed by hand is enough to unblock region work, with no
    proposal run needed at all.
    """
    proposals = RegionProposalLog(project.project_root).proposals()
    latest_decisions = RegionDecisionLog(project.project_root).latest_by_proposal()
    undecided = [p for p in proposals if is_undecided(latest_decisions.get((p.proposal_id, p.run_id)))]

    any_page_has_kind_state = any(
        row.reviewed or row.confirmed_kind is not None or row.proposed_kind is not None
        for row in page_kind_rows
    )

    return ReviewQueueKindEntry(
        kind="region",
        outstanding=len(undecided),
        total=len(proposals),
        available=True,
        blocked_by=None if any_page_has_kind_state else "page_kind",
        first_page_index=min((p.page_index for p in undecided), default=None),
    )


def _word_entry(
    project: Project, project_state: ProjectState
) -> tuple[ReviewQueueKindEntry, _WordCountSource]:
    """The ``word`` entry, plus what the ``typography`` entry needs to key its lookups.

    Three project shapes, in the order checked:

    1. **A multi-page labeling-bundle book** (``project_state.
       has_book_labeling_session``). Text validation goes through
       ``ImportedTextValidationLog``, keyed by each page's own bundle
       ``page_id`` — never ``save_page_content_to_store``, so
       ``WordReviewCountsJournal`` never gets a row for these pages either.
       Reading that journal is cheap, but a page's *total* word count lives
       only in that page's own materialized bundle — the book manifest this
       route can read without I/O carries page identity, not word counts —
       so answering the denominator would mean opening every page. Reports
       ``available: false`` rather than a false zero.
    2. **A single-page labeling-bundle project** (``project_state.
       labeling_bundle is not None``). Same validation path, but the one
       page's bundle is already resident (loaded once at project-load time,
       kept for the project's life — not read per request), so its word
       list costs nothing extra to read, and
       ``ImportedTextValidationLog.decisions()`` is a plain-dict JSONL read
       — cheap at the scale of one page's words, the same class of cost as
       the region and page-kind journals. Counted from the real thing.
    3. **An ordinary project.** Unchanged: ``WordReviewCountsJournal``, keyed
       by ``stable_page_id``.
    """
    if project_state.has_book_labeling_session:
        entry = ReviewQueueKindEntry(
            kind="word",
            outstanding=0,
            total=0,
            available=False,
            blocked_by=None,
            first_page_index=None,
            unavailable_reason=_BOOK_LABELING_SESSION_WORD_UNAVAILABLE_REASON,
        )
        return entry, _WordCountSource()

    bundle = project_state.labeling_bundle
    if bundle is not None:
        return _word_entry_from_bundle(project, bundle)

    counts_by_page = WordReviewCountsJournal(project.project_root).latest_by_page()
    total = sum(counts.total_words for counts in counts_by_page.values())
    validated = sum(counts.validated_words for counts in counts_by_page.values())
    pages_not_counted = project.total_pages - len(counts_by_page)

    first_page_index: int | None = None
    for page_index in range(project.total_pages):
        counts = counts_by_page.get(page_index)
        if counts is None or counts.total_words > counts.validated_words:
            first_page_index = page_index
            break

    entry = ReviewQueueKindEntry(
        kind="word",
        outstanding=total - validated,
        total=total,
        available=True,
        blocked_by=None,
        first_page_index=first_page_index,
        pages_not_counted=pages_not_counted,
        is_lower_bound=pages_not_counted > 0,
    )
    project_id = project.project_id
    source = _WordCountSource(
        total_words_by_page={page_index: counts.total_words for page_index, counts in counts_by_page.items()},
        logical_page_id=lambda page_index, _project_id=project_id: stable_page_id(
            project_id=_project_id, page_index=page_index
        ),
    )
    return entry, source


def _word_entry_from_bundle(
    project: Project, bundle: LabelingBundle
) -> tuple[ReviewQueueKindEntry, _WordCountSource]:
    """The ``word`` entry for a single-page labeling-bundle project, counted from the real thing.

    ``save_page_content_to_store`` is never called for a bundle project —
    text validation is a CAS append to ``ImportedTextValidationLog``, keyed
    by the bundle's own word ids, never ``(line, word)`` indices in a page
    blob. The total comes from ``bundle.words`` (already resident, one page,
    no I/O); the validated count comes from the latest decision per word id
    across the whole journal (a project only ever has one bundle, so there
    is exactly one page key to match, but the filter is kept for
    correctness rather than assumed).
    """
    log = ImportedTextValidationLog(project.project_root, corpus_root=project.project_root.parent)
    validated_by_word: dict[str, bool] = {}
    for decision in log.decisions():
        if decision.page_key[1] != bundle.page_id:
            continue
        validated_by_word[decision.word_id] = decision.validated

    total = len(bundle.words)
    validated = sum(1 for word in bundle.words if validated_by_word.get(word.word_id, False))
    outstanding = total - validated

    entry = ReviewQueueKindEntry(
        kind="word",
        outstanding=outstanding,
        total=total,
        available=True,
        blocked_by=None,
        first_page_index=0 if outstanding > 0 else None,
        pages_not_counted=0,
        is_lower_bound=False,
    )
    page_id = bundle.page_id
    source = _WordCountSource(
        total_words_by_page={0: total},
        logical_page_id=lambda _page_index, _page_id=page_id: _page_id,
    )
    return entry, source


def _typography_unavailable_entry(*, reason: str) -> ReviewQueueKindEntry:
    """The ``typography`` entry when it cannot be answered — same honesty ``glyph`` has."""
    return ReviewQueueKindEntry(
        kind="typography",
        outstanding=0,
        total=0,
        available=False,
        blocked_by=None,
        first_page_index=None,
        unavailable_reason=reason,
    )


def _typography_entry(
    project: Project,
    word_source: _WordCountSource,
    *,
    word_entry: ReviewQueueKindEntry,
) -> ReviewQueueKindEntry:
    """The ``typography`` entry: a journal-only numerator over the word total.

    Unavailable whenever ``word`` is: there is no page to navigate to or
    count against without knowing whether its words are done. Otherwise
    reports unavailable, without reading the journal at all, once it is
    bigger than ``_TYPOGRAPHY_CORRECTIONS_MAX_BYTES`` — checked with one
    ``stat()``, never a read or a parse. See that constant's docstring for
    the measurement behind the threshold.

    ``blocked_by`` is ``"word"`` whenever any word is still outstanding, or
    the ``word`` kind has not counted every page yet — a page it has not
    counted has never had a word validated on it either, so it cannot be
    presumed done. While blocked, ``first_page_index`` mirrors the ``word``
    entry's: there is nothing typography-specific to navigate to until
    words clear. Once unblocked, it is the first page (among pages
    ``word_source`` has a total for) whose typography-reviewed count is
    below its word total — keyed by ``word_source.logical_page_id``, which
    is ``stable_page_id`` for an ordinary project and the loaded bundle's
    own ``page_id`` for a single-page labeling-bundle project, matching
    whichever key ``TypographyCorrectionLog`` records were written under
    for that project shape (see ``api/typography.py``'s ``_logical_page_id``).
    """
    if not word_entry.available:
        return _typography_unavailable_entry(
            reason=word_entry.unavailable_reason or "the word kind is unavailable for this project"
        )

    log = TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent)
    journal_size = 0
    with suppress(FileNotFoundError):
        journal_size = log.path.stat().st_size
    if journal_size > _TYPOGRAPHY_CORRECTIONS_MAX_BYTES:
        return _typography_unavailable_entry(
            reason=_TYPOGRAPHY_TOO_LARGE_REASON_TEMPLATE.format(
                size=journal_size, threshold=_TYPOGRAPHY_CORRECTIONS_MAX_BYTES
            )
        )

    required_labels = {label.value for label in TYPOGRAPHY_TAXONOMY.labels if label.required_for_completion}
    reviewed_keys = reviewed_word_keys(log.records(), required_labels=required_labels)

    total = sum(word_source.total_words_by_page.values())
    words_pending = word_entry.outstanding > 0 or word_entry.pages_not_counted > 0
    blocked_by: _ReviewQueueKindName | None = "word" if words_pending else None

    if blocked_by is not None:
        first_page_index = word_entry.first_page_index
    else:
        reviewed_per_logical_page: dict[str, int] = {}
        for logical_page_id, _word_id in reviewed_keys:
            reviewed_per_logical_page[logical_page_id] = reviewed_per_logical_page.get(logical_page_id, 0) + 1
        first_page_index = None
        for page_index in sorted(word_source.total_words_by_page):
            logical_page_id = word_source.logical_page_id(page_index)
            if (
                reviewed_per_logical_page.get(logical_page_id, 0)
                < word_source.total_words_by_page[page_index]
            ):
                first_page_index = page_index
                break

    return ReviewQueueKindEntry(
        kind="typography",
        outstanding=max(total - len(reviewed_keys), 0),
        total=total,
        available=True,
        blocked_by=blocked_by,
        first_page_index=first_page_index,
        is_lower_bound=True,
    )


def _glyph_entry() -> ReviewQueueKindEntry:
    """The ``glyph`` entry: unavailable, with a reason — nothing to count today.

    ``IGlyphPredictor.predict`` is never called; only ``NoneGlyphPredictor``
    exists, so there is no machine backlog of glyph predictions to work
    through.
    """
    return ReviewQueueKindEntry(
        kind="glyph",
        outstanding=0,
        total=0,
        available=False,
        blocked_by=None,
        first_page_index=None,
        unavailable_reason=_GLYPH_UNAVAILABLE_REASON,
    )


@router.get(
    "/{project_id}/review-queue",
    response_model=ReviewQueueResponse,
    operation_id="get_review_queue",
)
def get_review_queue(
    project_id: str,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """One entry per kind of review work, in the order the work happens.

    Words before typography before export; regions depend only on page
    kinds being proposed, not reviewed; glyphs sit outside the chain. See
    ``ReviewQueueKindEntry`` for what each field means and
    ``_region_entry``/``_typography_entry`` for the exact ``blocked_by``
    gates, and ``_word_entry`` for the three project shapes it counts
    (ordinary, single-page labeling-bundle, multi-page labeling-bundle book).

    Reads each of the journals it needs exactly once: the page-kind
    proposal and reviewed journals (via ``page_kinds_rows``), the region
    proposal and decision journals, and — depending on project shape — the
    word-review-counts journal or ``ImportedTextValidationLog`` (shared by
    the ``word`` and ``typography`` entries), plus the typography-
    corrections journal for the ``typography`` entry's numerator. It opens
    no page.
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _review_queue_project_not_found(project_id)

    page_kind_entry, page_kind_rows_ = _page_kind_entry(project, project_state)
    region_entry = _region_entry(project, page_kind_rows_)
    word_entry, word_source = _word_entry(project, project_state)
    typography_entry = _typography_entry(project, word_source, word_entry=word_entry)
    glyph_entry = _glyph_entry()

    response = ReviewQueueResponse(
        kinds=[page_kind_entry, region_entry, word_entry, typography_entry, glyph_entry]
    )
    return JSONResponse(status_code=200, content=response.model_dump(mode="json"))


def install_review_queue_router(app: FastAPI) -> None:
    """Register the review-queue router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "ReviewQueueKindEntry",
    "ReviewQueueResponse",
    "get_review_queue",
    "install_review_queue_router",
    "router",
]

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
region queue's undecided predicate), and
``core.typography_review_counts.TypographyReviewCountsJournal`` (the
typography numerator's own per-page rollup, written where a correction is
accepted — ``api/typography.py``'s ``append_typography_correction``). Reads
each journal once — six reads total for five kinds, since the word and
typography kinds each read their own small per-page journal — and opens
no page.

The typography numerator used to be the one exception to "cheap": before
the rollup existed (docs/issues/2026-09-18-typography-numerator-needs-a-
per-page-rollup.md), this entry answered its count by reading and parsing
the *whole book's* ``typography-corrections.jsonl``, which cost about 80
microseconds a row and forced a 512 KiB ``available: false`` ceiling once a
book's correction history grew past it. The rollup removed that ceiling —
this entry now reads one small per-page-keyed file, the same shape of cost
every other kind on this route already has.

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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pdomain_book_contracts.annotation import PageKind
from pydantic import BaseModel

from ..core.project_state import ProjectState
from ..core.regions.decision_log import RegionDecisionLog
from ..core.regions.proposal_log import RegionProposalLog
from ..core.regions.resolver import is_undecided
from ..core.review_counts import WordReviewCountsJournal
from ..core.typography_review import ImportedTextValidationLog, stable_page_id
from ..core.typography_review_counts import TypographyReviewCountsJournal
from .dependencies import get_project_state
from .middleware.error_handler import ApiError
from .page_kinds import PageKindsListItem, page_kinds_rows

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from fastapi import FastAPI
    from pdomain_book_tools.typography import LabelingBundle

    from ..core.models import Project
    from ..core.review_counts import PageWordCounts

router = APIRouter(prefix="/api/projects", tags=["review-queue"])

_ReviewQueueKindName = Literal["page_kind", "region", "word", "typography", "glyph"]

_GLYPH_UNAVAILABLE_REASON = "no glyph predictor is wired"

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
    the other kinds. For ``typography``, ``pages_not_counted`` also covers a
    word-counted page with no ``TypographyReviewCountsJournal`` row of its
    own yet — untouched, or corrected before this rollup existed; the two
    are indistinguishable from a rollup-only read, so both are excluded from
    ``total``/``outstanding`` rather than reported as a confidently wrong
    zero (see ``_typography_entry``). ``is_lower_bound`` is ``True`` for
    ``typography`` always, on top of that — its per-head staleness check is
    skipped, and its reviewed count is each word's *latest-ever* correction
    rather than one bound to the page's current epoch (see
    ``core.typography_review_counts``) — and for ``word`` whenever
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


def _is_unvouched_zero(
    page_index: int,
    counts: PageWordCounts,
    confirmed_kind_by_page: Mapping[int, PageKind | None],
) -> bool:
    """True when OCR reported zero words for *page_index* and no person has
    confirmed the page is actually blank.

    ``run_ocr`` (``adapters/ocr/local_doctr.py``) writes a
    ``WordReviewCountsJournal`` row for every OCR outcome, including one
    where detection found nothing — the same zero row a genuinely blank
    page produces. Nothing at OCR time records which of the two happened
    (BUG-RELOAD-1), so a zero-word row cannot be trusted as "done" on its
    own: a person must have looked at the page and confirmed its kind as
    ``PageKind.BLANK`` (the ``page_kind`` review kind already asks for that
    confirmation on every page) before the zero counts as satisfied review
    work. Until then this page is treated the same as one that has never
    been counted at all — excluded from ``total``/``outstanding`` and
    reported as a ``first_page_index`` candidate so a person is still sent
    to look at it.
    """
    return counts.total_words == 0 and confirmed_kind_by_page.get(page_index) != PageKind.BLANK


def _word_entry(
    project: Project,
    project_state: ProjectState,
    page_kind_rows: list[PageKindsListItem],
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
       Imported-bundle text is never OCR, so ``_is_unvouched_zero`` does not
       apply here — a zero-word bundle page is whatever the import said.
    3. **An ordinary project.** ``WordReviewCountsJournal``, keyed by
       ``stable_page_id`` — plus ``_is_unvouched_zero`` (BUG-RELOAD-1):
       reload OCR can legitimately produce a page with zero words, and that
       is indistinguishable, from the count alone, from OCR failing to find
       text a person can plainly see. A zero-word page whose kind nobody
       has confirmed as blank is excluded from ``total``/``outstanding``
       and kept in ``first_page_index`` contention — the same treatment a
       never-counted page already gets — rather than reported as
       satisfied review work.
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

    confirmed_kind_by_page = {row.page_index: row.confirmed_kind for row in page_kind_rows}
    counts_by_page = WordReviewCountsJournal(project.project_root).latest_by_page()
    countable_pages = {
        page_index: counts
        for page_index, counts in counts_by_page.items()
        if not _is_unvouched_zero(page_index, counts, confirmed_kind_by_page)
    }
    total = sum(counts.total_words for counts in countable_pages.values())
    validated = sum(counts.validated_words for counts in countable_pages.values())
    pages_not_counted = project.total_pages - len(countable_pages)

    first_page_index: int | None = None
    for page_index in range(project.total_pages):
        counts = counts_by_page.get(page_index)
        if (
            counts is None
            or _is_unvouched_zero(page_index, counts, confirmed_kind_by_page)
            or counts.total_words > counts.validated_words
        ):
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
        total_words_by_page={
            page_index: counts.total_words for page_index, counts in countable_pages.items()
        },
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
    """The ``typography`` entry: a rollup-only numerator over the word total.

    Unavailable whenever ``word`` is: there is no page to navigate to or
    count against without knowing whether its words are done. Otherwise
    reads ``TypographyReviewCountsJournal.latest_by_page`` once — one small
    file, keyed by ``logical_page_id`` — never the whole book's
    ``typography-corrections.jsonl`` this entry used to parse in full (see
    docs/issues/2026-09-18-typography-numerator-needs-a-per-page-rollup.md).

    A word-counted page (present in ``word_source.total_words_by_page``) can
    still have no rollup row of its own: nothing has ever corrected a word
    on it, or its correction history predates this rollup and nothing has
    touched it since. The two are indistinguishable from a rollup-only
    read, so both are treated the way ``word`` already treats a page it has
    never saved — excluded from ``total``/``outstanding`` and counted in
    ``pages_not_counted``, never reported as a confidently wrong zero.

    ``blocked_by`` is ``"word"`` whenever any word is still outstanding, or
    the ``word`` kind has not counted every page yet — a page it has not
    counted has never had a word validated on it either, so it cannot be
    presumed done. While blocked, ``first_page_index`` mirrors the ``word``
    entry's: there is nothing typography-specific to navigate to until words
    clear. Once unblocked, it is the first page (among pages ``word_source``
    has a total for) with no rollup row yet or whose rolled-up reviewed
    count is below its word total — keyed by ``word_source.logical_page_id``,
    the same key ``append_typography_correction`` writes rollup rows under
    (see ``api/typography.py``'s ``_logical_page_id``).

    Preserves this entry's reviewed-count semantics unchanged from before
    the rollup existed: each word id's *latest-ever* correction on its page,
    with no staleness check against the live page's current hashes (see
    ``core.typography_review_counts``) — ``is_lower_bound`` is ``True``
    unconditionally, as it always has been for this kind.
    """
    if not word_entry.available:
        return _typography_unavailable_entry(
            reason=word_entry.unavailable_reason or "the word kind is unavailable for this project"
        )

    rollup_by_page = TypographyReviewCountsJournal(project.project_root).latest_by_page()

    total = 0
    reviewed_total = 0
    pages_not_counted = 0
    reviewed_by_page_index: dict[int, int] = {}
    for page_index, page_total in word_source.total_words_by_page.items():
        row = rollup_by_page.get(word_source.logical_page_id(page_index))
        if row is None:
            pages_not_counted += 1
            continue
        total += page_total
        reviewed_total += row.typography_reviewed_words
        reviewed_by_page_index[page_index] = row.typography_reviewed_words

    words_pending = word_entry.outstanding > 0 or word_entry.pages_not_counted > 0
    blocked_by: _ReviewQueueKindName | None = "word" if words_pending else None

    if blocked_by is not None:
        first_page_index = word_entry.first_page_index
    else:
        first_page_index = None
        for page_index in sorted(word_source.total_words_by_page):
            reviewed = reviewed_by_page_index.get(page_index)
            if reviewed is None or reviewed < word_source.total_words_by_page[page_index]:
                first_page_index = page_index
                break

    return ReviewQueueKindEntry(
        kind="typography",
        outstanding=max(total - reviewed_total, 0),
        total=total,
        available=True,
        blocked_by=blocked_by,
        first_page_index=first_page_index,
        pages_not_counted=pages_not_counted,
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
    proposal and decision journals, then — depending on project shape — the
    word-review-counts journal or ``ImportedTextValidationLog`` for the
    ``word`` entry, and the typography-review-counts rollup for the
    ``typography`` entry's numerator. It opens no page.
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _review_queue_project_not_found(project_id)

    page_kind_entry, page_kind_rows_ = _page_kind_entry(project, project_state)
    region_entry = _region_entry(project, page_kind_rows_)
    word_entry, word_source = _word_entry(project, project_state, page_kind_rows_)
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

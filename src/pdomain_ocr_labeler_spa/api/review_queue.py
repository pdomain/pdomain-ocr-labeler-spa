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
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.project_state import ProjectState
from ..core.regions.decision_log import RegionDecisionLog
from ..core.regions.proposal_log import RegionProposalLog
from ..core.regions.resolver import is_undecided
from ..core.review_counts import PageWordCounts, WordReviewCountsJournal
from ..core.typography_review import TypographyCorrectionLog, reviewed_word_keys, stable_page_id
from .dependencies import get_project_state
from .middleware.error_handler import ApiError
from .page_kinds import PageKindsListItem, page_kinds_rows
from .typography import TYPOGRAPHY_TAXONOMY

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ..core.models import Project

router = APIRouter(prefix="/api/projects", tags=["review-queue"])

_ReviewQueueKindName = Literal["page_kind", "region", "word", "typography", "glyph"]

_GLYPH_UNAVAILABLE_REASON = "no glyph predictor is wired"


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


def _word_entry(project: Project) -> tuple[ReviewQueueKindEntry, dict[int, PageWordCounts]]:
    """The ``word`` entry, plus the per-page counts the ``typography`` entry reuses.

    ``total``/``outstanding`` are sums over pages the counts journal has a
    row for — a page with no row is unseen, not zero work, which is exactly
    what ``pages_not_counted`` says. ``first_page_index`` treats an unseen
    page the same as one with outstanding work: nothing can validate a word
    on a page without first going through ``save_page_content_to_store``,
    which is also what writes a page's row, so a page with no row has never
    had a word validated on it either.
    """
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
    return entry, counts_by_page


def _typography_entry(
    project: Project,
    counts_by_page: dict[int, PageWordCounts],
    *,
    word_entry: ReviewQueueKindEntry,
) -> ReviewQueueKindEntry:
    """The ``typography`` entry: a journal-only numerator over the word total.

    ``blocked_by`` is ``"word"`` whenever any word is still outstanding, or
    the counts journal has not seen every page yet — a page it has not
    counted has never had a word validated on it either (see the ``word``
    entry's docstring), so it cannot be presumed done. While blocked,
    ``first_page_index`` mirrors the ``word`` entry's: there is nothing
    typography-specific to navigate to until words clear. Once unblocked,
    it is the first page (among pages the counts journal has a row for)
    whose typography-reviewed count is below its word total.
    """
    log = TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent)
    required_labels = {label.value for label in TYPOGRAPHY_TAXONOMY.labels if label.required_for_completion}
    reviewed_keys = reviewed_word_keys(log.records(), required_labels=required_labels)

    total = sum(counts.total_words for counts in counts_by_page.values())
    words_pending = word_entry.outstanding > 0 or word_entry.pages_not_counted > 0
    blocked_by: _ReviewQueueKindName | None = "word" if words_pending else None

    if blocked_by is not None:
        first_page_index = word_entry.first_page_index
    else:
        reviewed_per_logical_page: dict[str, int] = {}
        for logical_page_id, _word_id in reviewed_keys:
            reviewed_per_logical_page[logical_page_id] = reviewed_per_logical_page.get(logical_page_id, 0) + 1
        first_page_index = None
        for page_index in sorted(counts_by_page):
            logical_page_id = stable_page_id(project_id=project.project_id, page_index=page_index)
            if reviewed_per_logical_page.get(logical_page_id, 0) < counts_by_page[page_index].total_words:
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
    gates.

    Reads each of the five journals it needs exactly once: the page-kind
    proposal and reviewed journals (via ``page_kinds_rows``), the region
    proposal and decision journals, and the word-review-counts journal
    (shared by the ``word`` and ``typography`` entries) — plus the
    typography-corrections journal for the ``typography`` entry's
    numerator. It opens no page.
    """
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _review_queue_project_not_found(project_id)

    page_kind_entry, page_kind_rows_ = _page_kind_entry(project, project_state)
    region_entry = _region_entry(project, page_kind_rows_)
    word_entry, counts_by_page = _word_entry(project)
    typography_entry = _typography_entry(project, counts_by_page, word_entry=word_entry)
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

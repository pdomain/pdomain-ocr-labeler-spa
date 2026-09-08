"""Unit tests for the one read path both the labeler and the engine use."""

from __future__ import annotations

from pathlib import Path

from pdomain_book_contracts.annotation import RegionRole

from pdomain_ocr_labeler_spa.core.regions.models import (
    Disposition,
    ProposalRun,
    RegionDecision,
    RegionProposal,
    ResolvedRegion,
)


def _proposal(proposal_id: str, confidence: float) -> RegionProposal:
    return RegionProposal(
        proposal_id=proposal_id,
        run_id="r1",
        page_index=0,
        role=RegionRole.POETRY,
        box=(10, 20, 300, 400),
        confidence=confidence,
        evidence={},
    )


def _confirmed(region_id: str) -> ResolvedRegion:
    return ResolvedRegion(
        role=RegionRole.BLOCKQUOTE,
        box=(10, 20, 300, 400),
        confirmed=True,
        confidence=None,
        proposal_id=None,
        region_id=region_id,
    )


def _run_with_digests(
    run_id: str, page_index: int, digests: dict[str, str], depends_on: frozenset[str]
) -> ProposalRun:
    return ProposalRun(
        run_id=run_id,
        model_id="pp-doclayout-plus-l",
        model_version="1.0.0",
        created_at="2026-09-08T10:00:00+00:00",
        page_facet_digests={page_index: digests},
        depends_on=depends_on,
        page_kind_decision_ref=None,
        page_kind_was_confirmed=False,
    )


def test_a_confirmed_region_wins_over_a_proposal() -> None:
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    resolved = resolve_regions(
        [_confirmed("reg-1")], [_proposal("p1", 0.99)], {}, {}, threshold=0.0, current_facet_digests={}
    )
    assert [r.region_id for r in resolved] == ["reg-1"]
    assert resolved[0].role is RegionRole.BLOCKQUOTE
    assert resolved[0].confirmed is True


def test_a_proposal_above_the_threshold_is_returned_when_nothing_is_confirmed() -> None:
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    resolved = resolve_regions([], [_proposal("p1", 0.7)], {}, {}, threshold=0.5, current_facet_digests={})
    assert len(resolved) == 1
    assert resolved[0].confirmed is False
    assert resolved[0].proposal_id == "p1"
    assert resolved[0].confidence == 0.7


def test_a_proposal_below_the_threshold_is_dropped() -> None:
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    assert resolve_regions([], [_proposal("p1", 0.2)], {}, {}, threshold=0.5, current_facet_digests={}) == []


def test_nothing_confirmed_and_nothing_above_threshold_returns_nothing() -> None:
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    assert resolve_regions([], [], {}, {}, threshold=0.5, current_facet_digests={}) == []


def test_a_rejected_proposal_is_never_returned_even_above_the_threshold() -> None:
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    rejected = RegionDecision(
        decision_id="d1",
        run_id="r1",
        proposal_id="p1",
        disposition=Disposition.REJECTED,
        region_id=None,
        actor="default",
        decided_at="2026-09-08T10:00:00+00:00",
    )
    resolved = resolve_regions(
        [], [_proposal("p1", 0.99)], {"p1": rejected}, {}, threshold=0.5, current_facet_digests={}
    )
    assert resolved == []


def test_the_unattended_row_where_both_human_stores_are_empty() -> None:
    """The execution engine's path: no confirmed regions, no decisions, a real threshold."""
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    proposals = [_proposal("p1", 0.9), _proposal("p2", 0.3)]
    resolved = resolve_regions([], proposals, {}, {}, threshold=0.5, current_facet_digests={})
    assert [r.proposal_id for r in resolved] == ["p1"]
    assert all(r.confirmed is False for r in resolved)


def test_the_labeler_row_where_the_threshold_is_zero_shows_every_proposal() -> None:
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    proposals = [_proposal("p1", 0.9), _proposal("p2", 0.01)]
    resolved = resolve_regions([], proposals, {}, {}, threshold=0.0, current_facet_digests={})
    assert [r.proposal_id for r in resolved] == ["p1", "p2"]


def test_a_text_only_change_leaves_a_geometry_proposal_current() -> None:
    """Fixing a typo must not invalidate a proposal that never read the text facet."""
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    run = _run_with_digests(
        "r1",
        0,
        {"word_boxes": "wb1", "line_structure": "ls1", "page_image": "pi1", "word_text": "wt1"},
        frozenset({"word_boxes", "line_structure", "page_image"}),
    )
    current = {"word_boxes": "wb1", "line_structure": "ls1", "page_image": "pi1", "word_text": "wt2"}

    resolved = resolve_regions(
        [], [_proposal("p1", 0.9)], {}, {"r1": run}, threshold=0.5, current_facet_digests=current
    )
    assert resolved[0].stale is False


def test_a_word_boxes_change_marks_a_geometry_proposal_stale() -> None:
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    run = _run_with_digests(
        "r1",
        0,
        {"word_boxes": "wb1", "line_structure": "ls1", "page_image": "pi1", "word_text": "wt1"},
        frozenset({"word_boxes", "line_structure", "page_image"}),
    )
    current = {"word_boxes": "wb2", "line_structure": "ls1", "page_image": "pi1", "word_text": "wt1"}

    resolved = resolve_regions(
        [], [_proposal("p1", 0.9)], {}, {"r1": run}, threshold=0.5, current_facet_digests=current
    )
    assert resolved[0].stale is True


def test_a_stale_proposal_is_still_returned_not_suppressed() -> None:
    from pdomain_ocr_labeler_spa.core.regions.resolver import resolve_regions

    run = _run_with_digests("r1", 0, {"word_boxes": "wb1"}, frozenset({"word_boxes"}))
    current = {"word_boxes": "wb2"}

    resolved = resolve_regions(
        [], [_proposal("p1", 0.9)], {}, {"r1": run}, threshold=0.5, current_facet_digests=current
    )
    assert len(resolved) == 1
    assert resolved[0].proposal_id == "p1"
    assert resolved[0].stale is True


def test_writing_proposals_leaves_the_page_content_blob_untouched(tmp_path: Path) -> None:
    """The page blob is only ever written by a human action.

    Content addressing makes this a single comparison: the journal write must
    not change what the blob store holds.
    """
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    blobs_dir = tmp_path / ".pd-pages" / "blobs"
    blobs_dir.mkdir(parents=True)
    (blobs_dir / ("a" * 64)).write_bytes(b'{"type": "Page"}')

    def _snapshot() -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(blobs_dir.iterdir())}

    before = _snapshot()

    log = RegionProposalLog(tmp_path)
    log.append_run(
        ProposalRun(
            run_id="r1",
            model_id="pp-doclayout-plus-l",
            model_version="1.0.0",
            created_at="2026-09-08T10:00:00+00:00",
            page_facet_digests={0: {"word_boxes": "a" * 64}},
            depends_on=frozenset({"word_boxes"}),
            page_kind_decision_ref=None,
            page_kind_was_confirmed=False,
        )
    )
    log.append_proposals([_proposal("p1", 0.9)])

    assert _snapshot() == before

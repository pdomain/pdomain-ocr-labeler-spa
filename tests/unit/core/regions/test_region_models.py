"""Unit tests for the region proposal, run, and decision records."""

from __future__ import annotations

import pytest


def test_a_proposal_round_trips() -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import RegionProposal

    proposal = RegionProposal(
        proposal_id="p1",
        run_id="r1",
        page_index=0,
        role=RegionRole.POETRY,
        box=(10, 20, 300, 400),
        confidence=0.82,
        evidence={"signal": "indent", "ragged_right": True},
    )
    restored = RegionProposal.from_dict(proposal.to_dict())
    assert restored == proposal
    assert restored.role is RegionRole.POETRY
    assert restored.evidence["ragged_right"] is True


def test_a_proposal_rejects_an_inverted_box() -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import RegionProposal

    with pytest.raises(ValueError, match="L <= R"):
        RegionProposal(
            proposal_id="p1",
            run_id="r1",
            page_index=0,
            role=RegionRole.POETRY,
            box=(300, 20, 10, 400),
            confidence=0.5,
            evidence={},
        )


def test_a_proposal_rejects_a_confidence_outside_zero_to_one() -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import RegionProposal

    with pytest.raises(ValueError, match="confidence"):
        RegionProposal(
            proposal_id="p1",
            run_id="r1",
            page_index=0,
            role=RegionRole.POETRY,
            box=(10, 20, 300, 400),
            confidence=1.4,
            evidence={},
        )


def test_a_run_records_what_it_was_conditioned_on() -> None:
    from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun

    run = ProposalRun(
        run_id="r1",
        model_id="pp-doclayout-plus-l",
        model_version="1.0.0",
        created_at="2026-09-08T10:00:00+00:00",
        page_facet_digests={
            0: {
                "word_boxes": "a" * 64,
                "line_structure": "b" * 64,
                "page_image": "c" * 64,
                "word_text": "d" * 64,
            },
            1: {
                "word_boxes": "e" * 64,
                "line_structure": "f" * 64,
                "page_image": "g" * 64,
                "word_text": "h" * 64,
            },
        },
        depends_on=frozenset({"word_boxes", "line_structure", "page_image"}),
        page_kind_decision_ref="pk-run-7",
        page_kind_was_confirmed=False,
    )
    restored = ProposalRun.from_dict(run.to_dict())
    assert restored == run
    assert restored.page_facet_digests[1]["word_boxes"] == "e" * 64
    assert restored.depends_on == frozenset({"word_boxes", "line_structure", "page_image"})
    assert restored.page_kind_was_confirmed is False


def test_a_run_s_facet_digests_do_not_cover_word_text_when_depends_on_omits_it() -> None:
    """A geometry-only run's ``depends_on`` need not name every facet it stored a digest for."""
    from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun

    run = ProposalRun(
        run_id="r1",
        model_id="pp-doclayout-plus-l",
        model_version="1.0.0",
        created_at="2026-09-08T10:00:00+00:00",
        page_facet_digests={0: {"word_boxes": "a" * 64, "word_text": "b" * 64}},
        depends_on=frozenset({"word_boxes"}),
        page_kind_decision_ref=None,
        page_kind_was_confirmed=False,
    )
    assert "word_text" not in run.depends_on
    assert run.page_facet_digests[0]["word_text"] == "b" * 64


def test_a_decision_records_a_rejection_distinctly_from_an_acceptance() -> None:
    from pdomain_ocr_labeler_spa.core.regions.models import Disposition, RegionDecision

    accepted = RegionDecision(
        decision_id="d1",
        run_id="r1",
        proposal_id="p1",
        disposition=Disposition.ACCEPTED,
        region_id="reg-1",
        actor="default",
        decided_at="2026-09-08T10:05:00+00:00",
    )
    rejected = RegionDecision(
        decision_id="d2",
        run_id="r1",
        proposal_id="p2",
        disposition=Disposition.REJECTED,
        region_id=None,
        actor="default",
        decided_at="2026-09-08T10:06:00+00:00",
    )
    assert RegionDecision.from_dict(accepted.to_dict()) == accepted
    assert RegionDecision.from_dict(rejected.to_dict()) == rejected
    assert rejected.region_id is None


def test_an_accepted_decision_must_name_the_region_it_produced() -> None:
    from pdomain_ocr_labeler_spa.core.regions.models import Disposition, RegionDecision

    with pytest.raises(ValueError, match="region_id"):
        RegionDecision(
            decision_id="d1",
            run_id="r1",
            proposal_id="p1",
            disposition=Disposition.ACCEPTED,
            region_id=None,
            actor="default",
            decided_at="2026-09-08T10:05:00+00:00",
        )


def test_disposition_maps_onto_a_knowledge_state() -> None:
    from pdomain_book_contracts.annotation import KnowledgeState

    from pdomain_ocr_labeler_spa.core.regions.models import Disposition

    assert Disposition.ACCEPTED.knowledge_state is KnowledgeState.POSITIVE
    assert Disposition.EDITED.knowledge_state is KnowledgeState.POSITIVE
    assert Disposition.REJECTED.knowledge_state is KnowledgeState.VERIFIED_NEGATIVE
    assert Disposition.CARRIED.knowledge_state is KnowledgeState.POSITIVE


def test_a_carried_decision_names_the_run_and_proposal_it_carried_from() -> None:
    from pdomain_ocr_labeler_spa.core.regions.models import Disposition, RegionDecision

    carried = RegionDecision(
        decision_id="d3",
        run_id="r2",
        proposal_id="p9",
        disposition=Disposition.CARRIED,
        region_id="reg-1",
        actor="default",
        decided_at="2026-09-08T12:00:00+00:00",
        carried_from_run_id="r1",
        carried_from_proposal_id="p1",
    )
    restored = RegionDecision.from_dict(carried.to_dict())
    assert restored == carried
    assert restored.carried_from_run_id == "r1"
    assert restored.carried_from_proposal_id == "p1"


def test_a_carried_decision_must_name_where_it_carried_from() -> None:
    from pdomain_ocr_labeler_spa.core.regions.models import Disposition, RegionDecision

    with pytest.raises(ValueError, match="carried_from_run_id"):
        RegionDecision(
            decision_id="d3",
            run_id="r2",
            proposal_id="p9",
            disposition=Disposition.CARRIED,
            region_id="reg-1",
            actor="default",
            decided_at="2026-09-08T12:00:00+00:00",
        )


def test_a_non_carried_decision_rejects_carried_provenance() -> None:
    from pdomain_ocr_labeler_spa.core.regions.models import Disposition, RegionDecision

    with pytest.raises(ValueError, match="only set on a carried decision"):
        RegionDecision(
            decision_id="d1",
            run_id="r1",
            proposal_id="p1",
            disposition=Disposition.ACCEPTED,
            region_id="reg-1",
            actor="default",
            decided_at="2026-09-08T10:05:00+00:00",
            carried_from_run_id="r0",
            carried_from_proposal_id="p0",
        )


def test_a_resolved_region_carries_word_membership_and_staleness() -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import ResolvedRegion

    region = ResolvedRegion(
        role=RegionRole.POETRY,
        box=(10, 20, 300, 400),
        confirmed=True,
        confidence=None,
        proposal_id=None,
        region_id="reg-1",
        member_word_signatures=((10.0, 20.0, 60.0, 40.0, False),),
    )
    assert region.member_word_signatures == ((10.0, 20.0, 60.0, 40.0, False),)
    assert region.stale is False

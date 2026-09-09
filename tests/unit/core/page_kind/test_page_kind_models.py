"""Unit tests for the page-kind proposal and run records."""

from __future__ import annotations

import pytest


def test_a_proposal_round_trips() -> None:
    from pdomain_book_contracts.annotation import PageKind

    from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal

    proposal = PageKindProposal(
        proposal_id="p1",
        run_id="r1",
        page_index=3,
        kind=PageKind.CHAPTER_OPENING,
        confidence=0.82,
        evidence={"page_class": "chapter_opening", "template_residual_px": 4},
    )
    restored = PageKindProposal.from_dict(proposal.to_dict())
    assert restored == proposal
    assert restored.kind is PageKind.CHAPTER_OPENING
    assert restored.evidence["template_residual_px"] == 4


def test_a_proposal_allows_no_confidence_for_the_classifier_s_refusal() -> None:
    from pdomain_book_contracts.annotation import PageKind

    from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal

    proposal = PageKindProposal(
        proposal_id="p1",
        run_id="r1",
        page_index=0,
        kind=PageKind.UNKNOWN,
        confidence=None,
        evidence={},
    )
    restored = PageKindProposal.from_dict(proposal.to_dict())
    assert restored.confidence is None


def test_a_proposal_rejects_a_confidence_outside_zero_to_one() -> None:
    from pdomain_book_contracts.annotation import PageKind

    from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal

    with pytest.raises(ValueError, match="confidence"):
        PageKindProposal(
            proposal_id="p1",
            run_id="r1",
            page_index=0,
            kind=PageKind.BODY,
            confidence=1.4,
            evidence={},
        )


def test_a_run_round_trips() -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposalRun

    run = PageKindProposalRun(
        run_id="r1",
        model_id="pgdp-measure/page-templates",
        model_version="first-band-templates/v3",
        created_at="2026-09-08T10:00:00+00:00",
        page_count=42,
    )
    restored = PageKindProposalRun.from_dict(run.to_dict())
    assert restored == run

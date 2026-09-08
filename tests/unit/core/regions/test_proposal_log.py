"""Unit tests for the append-only region proposal journal."""

from __future__ import annotations

from pathlib import Path

from pdomain_book_contracts.annotation import RegionRole

from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal


def _run(run_id: str = "r1") -> ProposalRun:
    return ProposalRun(
        run_id=run_id,
        model_id="pp-doclayout-plus-l",
        model_version="1.0.0",
        created_at="2026-09-08T10:00:00+00:00",
        page_facet_digests={0: {"word_boxes": "a" * 64}},
        depends_on=frozenset({"word_boxes"}),
        page_kind_decision_ref=None,
        page_kind_was_confirmed=False,
    )


def _proposal(proposal_id: str, run_id: str = "r1", page_index: int = 0) -> RegionProposal:
    return RegionProposal(
        proposal_id=proposal_id,
        run_id=run_id,
        page_index=page_index,
        role=RegionRole.POETRY,
        box=(10, 20, 300, 400),
        confidence=0.7,
        evidence={},
    )


def test_a_run_and_its_proposals_read_back(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    log = RegionProposalLog(tmp_path)
    log.append_run(_run())
    log.append_proposals([_proposal("p1"), _proposal("p2")])

    assert [r.run_id for r in log.runs()] == ["r1"]
    found = log.proposals_for_page(0)
    assert sorted(p.proposal_id for p in found) == ["p1", "p2"]


def test_a_fresh_log_is_empty_and_does_not_raise(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    log = RegionProposalLog(tmp_path)
    assert log.runs() == []
    assert log.proposals_for_page(0) == []


def test_proposals_are_filtered_by_page(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    log = RegionProposalLog(tmp_path)
    log.append_run(_run())
    log.append_proposals([_proposal("p1", page_index=0), _proposal("p2", page_index=1)])

    assert [p.proposal_id for p in log.proposals_for_page(1)] == ["p2"]


def test_a_second_run_does_not_disturb_the_first(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    log = RegionProposalLog(tmp_path)
    log.append_run(_run("r1"))
    log.append_proposals([_proposal("p1", run_id="r1")])
    log.append_run(_run("r2"))
    log.append_proposals([_proposal("p2", run_id="r2")])

    assert [r.run_id for r in log.runs()] == ["r1", "r2"]
    assert [p.proposal_id for p in log.proposals_for_page(0, run_id="r1")] == ["p1"]
    assert [p.proposal_id for p in log.proposals_for_page(0, run_id="r2")] == ["p2"]
    # Both runs survive, which is what makes one detector scoreable against another.
    assert len(log.proposals_for_page(0)) == 2


def test_appending_never_rewrites_an_existing_record(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    log = RegionProposalLog(tmp_path)
    log.append_run(_run())
    log.append_proposals([_proposal("p1")])
    first = (tmp_path / ".pd-pages" / "region-proposals.jsonl").read_bytes()

    log.append_proposals([_proposal("p2")])
    second = (tmp_path / ".pd-pages" / "region-proposals.jsonl").read_bytes()

    assert second.startswith(first)


def test_a_malformed_line_is_skipped_rather_than_failing_the_read(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    log = RegionProposalLog(tmp_path)
    log.append_run(_run())
    log.append_proposals([_proposal("p1")])
    path = tmp_path / ".pd-pages" / "region-proposals.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    assert [p.proposal_id for p in log.proposals_for_page(0)] == ["p1"]

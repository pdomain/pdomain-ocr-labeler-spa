"""Unit tests for the append-only page-kind proposal journal."""

from __future__ import annotations

import json
from pathlib import Path

from pdomain_book_contracts.annotation import PageKind

from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal, PageKindProposalRun


def _run(run_id: str = "r1", page_count: int = 2) -> PageKindProposalRun:
    return PageKindProposalRun(
        run_id=run_id,
        model_id="pgdp-measure/page-templates",
        model_version="first-band-templates/v3",
        created_at="2026-09-08T10:00:00+00:00",
        page_count=page_count,
    )


def _proposal(proposal_id: str, run_id: str = "r1", page_index: int = 0) -> PageKindProposal:
    return PageKindProposal(
        proposal_id=proposal_id,
        run_id=run_id,
        page_index=page_index,
        kind=PageKind.BODY,
        confidence=0.9,
        evidence={},
    )


def test_a_run_and_its_proposals_read_back(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog

    log = PageKindProposalLog(tmp_path)
    log.append_run(_run())
    log.append_proposals([_proposal("p1", page_index=0), _proposal("p2", page_index=1)])

    assert [r.run_id for r in log.runs()] == ["r1"]
    assert sorted(p.proposal_id for p in log.proposals_for_run("r1")) == ["p1", "p2"]


def test_a_fresh_log_is_empty_and_does_not_raise(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog

    log = PageKindProposalLog(tmp_path)
    assert log.runs() == []
    assert log.latest_proposal_for_page(0) is None


def test_latest_proposal_for_page_wins_across_runs(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog

    log = PageKindProposalLog(tmp_path)
    log.append_run(_run("r1"))
    log.append_proposals([_proposal("p1", run_id="r1", page_index=0)])
    log.append_run(_run("r2"))
    log.append_proposals([_proposal("p2", run_id="r2", page_index=0)])

    latest = log.latest_proposal_for_page(0)
    assert latest is not None
    assert latest.proposal_id == "p2"
    # Both runs survive — this is what makes one detector scoreable against another.
    assert [r.run_id for r in log.runs()] == ["r1", "r2"]


def test_appending_never_rewrites_an_existing_record(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog

    log = PageKindProposalLog(tmp_path)
    log.append_run(_run())
    log.append_proposals([_proposal("p1")])
    first = (tmp_path / ".pd-pages" / "page-kind-proposals.jsonl").read_bytes()

    log.append_proposals([_proposal("p2", page_index=1)])
    second = (tmp_path / ".pd-pages" / "page-kind-proposals.jsonl").read_bytes()

    assert second.startswith(first)


def test_a_malformed_line_is_skipped_rather_than_failing_the_read(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog

    log = PageKindProposalLog(tmp_path)
    log.append_run(_run())
    log.append_proposals([_proposal("p1")])
    path = tmp_path / ".pd-pages" / "page-kind-proposals.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    assert log.latest_proposal_for_page(0) is not None


def test_a_line_with_no_record_key_is_skipped_rather_than_raising(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog

    log = PageKindProposalLog(tmp_path)
    log.append_run(_run())
    log.append_proposals([_proposal("p1")])
    path = tmp_path / ".pd-pages" / "page-kind-proposals.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": "run"}) + "\n")
        handle.write(json.dumps({"kind": "proposal"}) + "\n")

    assert [r.run_id for r in log.runs()] == ["r1"]
    assert [p.proposal_id for p in log.proposals_for_run("r1")] == ["p1"]
    latest = log.latest_proposal_for_page(0)
    assert latest is not None
    assert latest.proposal_id == "p1"

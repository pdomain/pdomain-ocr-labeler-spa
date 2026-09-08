"""Unit tests for the append-only region decision journal."""

from __future__ import annotations

from pathlib import Path

from pdomain_ocr_labeler_spa.core.regions.models import Disposition, RegionDecision


def _decision(
    decision_id: str,
    proposal_id: str,
    disposition: Disposition,
    region_id: str | None,
    decided_at: str,
) -> RegionDecision:
    return RegionDecision(
        decision_id=decision_id,
        run_id="r1",
        proposal_id=proposal_id,
        disposition=disposition,
        region_id=region_id,
        actor="default",
        decided_at=decided_at,
    )


def test_a_decision_reads_back(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    log = RegionDecisionLog(tmp_path)
    log.append(_decision("d1", "p1", Disposition.ACCEPTED, "reg-1", "2026-09-08T10:00:00+00:00"))

    found = log.decision_for("p1", run_id="r1")
    assert found is not None
    assert found.disposition is Disposition.ACCEPTED
    assert found.region_id == "reg-1"


def test_an_unreviewed_proposal_has_no_decision(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    log = RegionDecisionLog(tmp_path)
    assert log.decision_for("p-nobody-looked", run_id="r1") is None


def test_a_rejection_is_distinguishable_from_never_looking(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    log = RegionDecisionLog(tmp_path)
    log.append(_decision("d1", "p1", Disposition.REJECTED, None, "2026-09-08T10:00:00+00:00"))

    rejected = log.decision_for("p1", run_id="r1")
    unreviewed = log.decision_for("p2", run_id="r1")
    assert rejected is not None
    assert rejected.disposition is Disposition.REJECTED
    assert unreviewed is None


def test_the_most_recent_decision_wins_and_the_earlier_one_survives(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    log = RegionDecisionLog(tmp_path)
    log.append(_decision("d1", "p1", Disposition.REJECTED, None, "2026-09-08T10:00:00+00:00"))
    log.append(_decision("d2", "p1", Disposition.ACCEPTED, "reg-1", "2026-09-08T11:00:00+00:00"))

    current = log.decision_for("p1", run_id="r1")
    assert current is not None
    assert current.decision_id == "d2"
    # Supersession is a later record, not an edit: both are still on disk.
    assert [d.decision_id for d in log.decisions()] == ["d1", "d2"]


def test_decisions_from_different_runs_do_not_collide(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    log = RegionDecisionLog(tmp_path)
    first = _decision("d1", "p1", Disposition.ACCEPTED, "reg-1", "2026-09-08T10:00:00+00:00")
    second = RegionDecision(
        decision_id="d2",
        run_id="r2",
        proposal_id="p1",
        disposition=Disposition.REJECTED,
        region_id=None,
        actor="default",
        decided_at="2026-09-08T11:00:00+00:00",
    )
    log.append(first)
    log.append(second)

    from_first = log.decision_for("p1", run_id="r1")
    from_second = log.decision_for("p1", run_id="r2")
    assert from_first is not None and from_first.disposition is Disposition.ACCEPTED
    assert from_second is not None and from_second.disposition is Disposition.REJECTED

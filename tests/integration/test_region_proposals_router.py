"""Integration tests for the region proposal list/accept/reject routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

_BASE = "/api/projects/book1/pages/0"


def _seed_proposal(
    client: Any,
    project_root: Path,
    *,
    proposal_id: str = "p1",
    confidence: float = 0.8,
    role: Any = None,
) -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    if role is None:
        role = RegionRole.POETRY

    log = RegionProposalLog(project_root)
    log.append_run(
        ProposalRun(
            run_id="r1",
            model_id="test-detector",
            model_version="0.0.0",
            created_at="2026-09-08T10:00:00+00:00",
            page_facet_digests={0: {"word_boxes": "a" * 64}},
            depends_on=frozenset({"word_boxes"}),
            page_kind_decision_ref=None,
            page_kind_was_confirmed=False,
        )
    )
    log.append_proposals(
        [
            RegionProposal(
                proposal_id=proposal_id,
                run_id="r1",
                page_index=0,
                role=role,
                box=(5, 5, 50, 50),
                confidence=confidence,
                evidence={"signal": "indent"},
            )
        ]
    )


def test_list_proposals_returns_confidence_and_evidence(toolbar_loaded: Any) -> None:
    client, project_state, _page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)

    r = client.get(f"{_BASE}/regions/proposals")
    assert r.status_code == 200, r.text
    proposals = r.json()["proposals"]
    assert len(proposals) == 1
    assert proposals[0]["confidence"] == 0.8
    assert proposals[0]["evidence"] == {"signal": "indent"}
    assert proposals[0]["disposition"] is None


def test_accept_proposal_creates_a_confirmed_region(toolbar_loaded: Any) -> None:
    client, project_state, page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)

    r = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert r.status_code == 200, r.text
    body = r.json()
    confirmed = [reg for reg in body["regions"] if reg["confirmed"]]
    assert len(confirmed) == 1
    assert confirmed[0]["role"] == "poetry"
    assert confirmed[0]["box"] == {"x": 5, "y": 5, "width": 45, "height": 45}
    assert confirmed[0]["proposal_id"] == "p1"
    assert any(
        b.additional_block_attributes.get("region_id") == confirmed[0]["region_id"] for b in page.items
    )


def test_accept_leaves_the_proposal_record_byte_identical(toolbar_loaded: Any) -> None:
    client, project_state, _page = toolbar_loaded
    project_root = project_state.loaded_project.project_root
    _seed_proposal(client, project_root)
    before = (project_root / ".pd-pages" / "region-proposals.jsonl").read_bytes()

    client.post(f"{_BASE}/regions/proposals/p1/accept")

    after = (project_root / ".pd-pages" / "region-proposals.jsonl").read_bytes()
    assert after.startswith(before)


def test_reject_proposal_records_a_verified_negative_decision(toolbar_loaded: Any) -> None:
    client, project_state, page = toolbar_loaded
    project_root = project_state.loaded_project.project_root
    _seed_proposal(client, project_root)
    before_items = len(page.items)

    r = client.post(f"{_BASE}/regions/proposals/p1/reject")
    assert r.status_code == 200, r.text
    # No page mutation on reject — the page blob is only ever written by a human
    # *confirming* something, and a rejection confirms nothing new about the page.
    assert len(page.items) == before_items

    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog
    from pdomain_ocr_labeler_spa.core.regions.models import Disposition

    decision = RegionDecisionLog(project_root).decision_for("p1", run_id="r1")
    assert decision is not None
    assert decision.disposition is Disposition.REJECTED


def test_a_rejected_proposal_never_reappears_in_the_resolved_list(toolbar_loaded: Any) -> None:
    client, project_state, _page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)
    client.post(f"{_BASE}/regions/proposals/p1/reject")

    r = client.get(_BASE)
    assert r.status_code == 200, r.text
    assert all(reg.get("proposal_id") != "p1" for reg in r.json()["regions"])


def test_accept_unknown_proposal_returns_404(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(f"{_BASE}/regions/proposals/does-not-exist/accept")
    assert r.status_code == 404, r.text


def test_accept_proposal_with_unsupported_role_returns_400(toolbar_loaded: Any) -> None:
    from pdomain_book_contracts.annotation import RegionRole

    client, project_state, page = toolbar_loaded
    before_items = len(page.items)
    # CATCHWORD is one of the 14 RegionRole values Block.ALLOWED_BLOCK_ROLE_LABELS
    # does not yet allow — same non-mutation proof as create_region's equivalent
    # test in test_regions_router.py.
    _seed_proposal(client, project_state.loaded_project.project_root, role=RegionRole.CATCHWORD)

    r = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_region_role"
    assert len(page.items) == before_items

    check = client.get(_BASE)
    assert check.status_code == 200, check.text
    assert not any(reg["confirmed"] for reg in check.json()["regions"])


def test_accept_decision_persist_failure_returns_a_structured_error(
    toolbar_loaded: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    client, project_state, _page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)

    def _raise(self: RegionDecisionLog, decision: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(RegionDecisionLog, "append", _raise)

    r = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert r.status_code == 503, r.text
    assert r.json()["error"] == "decision_persist_failed"


def test_reject_decision_persist_failure_returns_a_structured_error(
    toolbar_loaded: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    client, project_state, _page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)

    def _raise(self: RegionDecisionLog, decision: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(RegionDecisionLog, "append", _raise)

    r = client.post(f"{_BASE}/regions/proposals/p1/reject")
    assert r.status_code == 503, r.text
    assert r.json()["error"] == "decision_persist_failed"


def test_accepting_the_same_proposal_twice_adds_no_second_region(toolbar_loaded: Any) -> None:
    client, project_state, _page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)

    first = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert first.status_code == 200, first.text
    first_confirmed = [reg for reg in first.json()["regions"] if reg["confirmed"]]
    assert len(first_confirmed) == 1

    second = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert second.status_code == 200, second.text
    second_confirmed = [reg for reg in second.json()["regions"] if reg["confirmed"]]
    assert len(second_confirmed) == 1
    assert second_confirmed[0]["region_id"] == first_confirmed[0]["region_id"]


def test_accept_after_its_region_was_deleted_creates_a_fresh_region(toolbar_loaded: Any) -> None:
    client, project_state, _page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)

    first = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert first.status_code == 200, first.text
    first_region_id = next(reg["region_id"] for reg in first.json()["regions"] if reg["confirmed"])

    deleted = client.delete(f"{_BASE}/regions/{first_region_id}")
    assert deleted.status_code == 200, deleted.text
    assert not any(reg["confirmed"] for reg in deleted.json()["regions"])

    second = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert second.status_code == 200, second.text
    second_confirmed = [reg for reg in second.json()["regions"] if reg["confirmed"]]
    assert len(second_confirmed) == 1
    assert second_confirmed[0]["region_id"] != first_region_id

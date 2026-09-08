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


def _decisions_path(project_root: Path) -> Path:
    return project_root / ".pd-pages" / "region-decisions.jsonl"


def _journal_bytes(project_root: Path) -> bytes:
    path = _decisions_path(project_root)
    return path.read_bytes() if path.exists() else b""


def test_rejecting_a_proposal_whose_region_still_exists_returns_409(toolbar_loaded: Any) -> None:
    """The journal and the page blob must never state opposite facts about one
    proposal. Accepting leaves a confirmed ``Block`` on the page; appending a
    rejection beside it would publish a confirmed region whose proposal the journal
    says a person refused. Deleting the region records the rejection itself, so the
    409 asks for the one action that keeps both stores in step.
    """
    client, project_state, _page = toolbar_loaded
    project_root = project_state.loaded_project.project_root
    _seed_proposal(client, project_root)

    accepted = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert accepted.status_code == 200, accepted.text
    region_id = next(reg["region_id"] for reg in accepted.json()["regions"] if reg["confirmed"])
    journal_before = _journal_bytes(project_root)

    rejected = client.post(f"{_BASE}/regions/proposals/p1/reject")

    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"] == "proposal_already_accepted"
    assert region_id in rejected.json()["message"]
    # Nothing was appended: a refused write must not leave a half-recorded decision.
    assert _journal_bytes(project_root) == journal_before


def test_rejecting_is_allowed_again_once_the_accepted_region_is_deleted(toolbar_loaded: Any) -> None:
    """The 409 is about the *live* contradiction, not about ever having accepted.
    Once the region is gone there is nothing for the rejection to contradict.
    """
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog
    from pdomain_ocr_labeler_spa.core.regions.models import Disposition

    client, project_state, _page = toolbar_loaded
    project_root = project_state.loaded_project.project_root
    _seed_proposal(client, project_root)

    accepted = client.post(f"{_BASE}/regions/proposals/p1/accept")
    region_id = next(reg["region_id"] for reg in accepted.json()["regions"] if reg["confirmed"])
    assert client.delete(f"{_BASE}/regions/{region_id}").status_code == 200

    rejected = client.post(f"{_BASE}/regions/proposals/p1/reject")

    assert rejected.status_code == 200, rejected.text
    decision = RegionDecisionLog(project_root).decision_for("p1", run_id="r1")
    assert decision is not None
    assert decision.disposition is Disposition.REJECTED


def test_deleting_an_accepted_region_records_a_rejection_naming_its_proposal(
    toolbar_loaded: Any,
) -> None:
    """Without this the ``accepted`` decision goes on naming a ``region_id`` that no
    longer exists, and the resolver's "already promoted into a confirmed region"
    branch suppresses the proposal forever — it disappears from the payload and the
    canvas with no record that anybody removed it.
    """
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog
    from pdomain_ocr_labeler_spa.core.regions.models import Disposition

    client, project_state, _page = toolbar_loaded
    project_root = project_state.loaded_project.project_root
    _seed_proposal(client, project_root)

    accepted = client.post(f"{_BASE}/regions/proposals/p1/accept")
    region_id = next(reg["region_id"] for reg in accepted.json()["regions"] if reg["confirmed"])

    deleted = client.delete(f"{_BASE}/regions/{region_id}")
    assert deleted.status_code == 200, deleted.text

    decisions = RegionDecisionLog(project_root).decisions()
    assert [d.disposition for d in decisions] == [Disposition.ACCEPTED, Disposition.REJECTED]
    assert decisions[-1].proposal_id == "p1"
    assert decisions[-1].run_id == "r1"
    assert decisions[-1].region_id is None
    # Append-only: the earlier accept survives beside the rejection, so
    # "rejected at review" and "accepted, then later deleted" stay distinguishable.
    assert decisions[0].region_id == region_id


def test_after_deleting_an_accepted_region_the_proposal_is_declined_not_absent(
    toolbar_loaded: Any,
) -> None:
    """The proposal must still be *stated* in the payload, as a proposal a person
    declined, with no confirmed region attached. Before the fix it read as accepted
    into a region that no longer exists — the page showed nothing at all for it and
    the journal disagreed with the page.
    """
    client, project_state, _page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)

    accepted = client.post(f"{_BASE}/regions/proposals/p1/accept")
    region_id = next(reg["region_id"] for reg in accepted.json()["regions"] if reg["confirmed"])
    body = client.delete(f"{_BASE}/regions/{region_id}").json()

    proposal_view = next(p for p in body["proposals"] if p["proposal_id"] == "p1")
    assert proposal_view["disposition"] == "rejected"
    assert proposal_view["decided_region_id"] is None
    assert not any(reg["confirmed"] for reg in body["regions"])


def test_deleting_a_hand_drawn_region_records_no_decision(toolbar_loaded: Any) -> None:
    """A hand-drawn region has no proposal anybody can have decided about, and the
    delete must not fail trying to record one.
    """
    client, project_state, _page = toolbar_loaded
    project_root = project_state.loaded_project.project_root

    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 5, "y": 5, "width": 50, "height": 50}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])

    deleted = client.delete(f"{_BASE}/regions/{region_id}")

    assert deleted.status_code == 200, deleted.text
    assert _journal_bytes(project_root) == b""


def test_delete_decision_persist_failure_returns_a_structured_error(
    toolbar_loaded: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delete's decision append is guarded exactly like accept's and reject's."""
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    client, project_state, _page = toolbar_loaded
    _seed_proposal(client, project_state.loaded_project.project_root)
    accepted = client.post(f"{_BASE}/regions/proposals/p1/accept")
    region_id = next(reg["region_id"] for reg in accepted.json()["regions"] if reg["confirmed"])

    def _raise(self: RegionDecisionLog, decision: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(RegionDecisionLog, "append", _raise)

    deleted = client.delete(f"{_BASE}/regions/{region_id}")

    assert deleted.status_code == 503, deleted.text
    assert deleted.json()["error"] == "decision_persist_failed"


# ── The payload must not disagree with itself ───────────────────────────


def _seed_image_provenance(client: Any, *, image_hash: str) -> None:
    """Give the page a head whose ``blob_refs`` carry a real image at index 1.

    The OCR-ingest path writes ``[content_hash, image_hash]``; the fixture's bare
    aggregate has no provenance at all, and a labeler edit writes
    ``[content_hash]``. Only the two-entry form produces a ``page_image`` facet,
    which is what makes a store-aware payload observably different from a
    store-blind one.
    """
    from pdomain_ops.pages import ProvenanceNode

    store = client.app.state.page_store
    page_id = client.app.state.project_state.get_page_state(0).page_id
    aggregate = store.get_page(page_id)
    # Through the aggregate's own event, not by assigning ``record.provenance``:
    # the store is event-sourced, so a direct assignment is dropped on reload.
    aggregate.ocr_completed(
        provenance_node=ProvenanceNode(id="ingest-1", source="ocr"),
        blob_refs=["content-hash", image_hash],
    )
    store.save_page(aggregate)


def _seed_image_dependent_run(project_root: Path, *, image_hash: str) -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    log = RegionProposalLog(project_root)
    log.append_run(
        ProposalRun(
            run_id="r1",
            model_id="test-detector",
            model_version="0.0.0",
            created_at="2026-09-08T10:00:00+00:00",
            page_facet_digests={0: {"page_image": image_hash}},
            depends_on=frozenset({"page_image"}),
            page_kind_decision_ref=None,
            page_kind_was_confirmed=False,
        )
    )
    log.append_proposals(
        [
            RegionProposal(
                proposal_id=pid,
                run_id="r1",
                page_index=0,
                role=RegionRole.POETRY,
                box=(5, 5, 50, 50),
                confidence=0.8,
                evidence={},
            )
            for pid in ("keep", "drop")
        ]
    )


def test_stale_agrees_between_the_get_payload_and_a_mutating_route(toolbar_loaded: Any) -> None:
    """``_refresh_payload_response`` computed the payload without the page store, so
    ``_image_digest_for_page`` returned ``None`` and the ``page_image`` facet came
    out different from the one ``GET /pages/{idx}`` computes with the store in hand.
    The same page then reported ``stale=True`` on a GET and ``stale=False`` from
    every mutating route, for identical state.
    """
    client, project_state, _page = toolbar_loaded
    _seed_image_provenance(client, image_hash="image-hash-1")
    _seed_image_dependent_run(project_state.loaded_project.project_root, image_hash="image-hash-1")

    from_get = {reg["proposal_id"]: reg["stale"] for reg in client.get(_BASE).json()["regions"]}
    rejected = client.post(f"{_BASE}/regions/proposals/drop/reject")
    assert rejected.status_code == 200, rejected.text
    from_route = {reg["proposal_id"]: reg["stale"] for reg in rejected.json()["regions"]}

    assert from_get["keep"] is False, "the run's recorded image digest still matches the page"
    assert from_route["keep"] == from_get["keep"]


def test_a_text_edit_does_not_change_the_page_image_facet(toolbar_loaded: Any) -> None:
    """The labeler-edit path writes ``blob_refs=[content_hash]`` alone, so falling
    back to index 0 made ``page_image`` *be* the page-content hash on any edited
    page: fixing a typo changed the image facet and invalidated every geometry
    proposal on the page. That is precisely what per-facet digests exist to prevent.
    """
    from pdomain_ocr_labeler_spa.api.pages import _image_digest_for_page
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import compute_page_facet_digests

    client, project_state, page = toolbar_loaded
    _seed_image_provenance(client, image_hash="image-hash-1")
    store = client.app.state.page_store
    page_id = project_state.get_page_state(0).page_id

    def facets_and_head() -> tuple[dict[str, str], list[str]]:
        digest = _image_digest_for_page(page_store=store, page_id=page_id)
        head = store.get_page(page_id).record.provenance.head
        return compute_page_facet_digests(page, image_digest=digest), list(head.blob_refs)

    assert client.post(f"{_BASE}/words/0/0/gt", json={"text": "FIRST"}).status_code == 200
    first_facets, first_head = facets_and_head()
    assert client.post(f"{_BASE}/words/0/0/gt", json={"text": "SECOND"}).status_code == 200
    second_facets, second_head = facets_and_head()

    # A labeler edit really does replace the head with a one-entry content ref,
    # and the content hash really does move between the two edits.
    assert len(first_head) == 1 and len(second_head) == 1
    assert first_head != second_head
    # The edit was real...
    assert first_facets["word_text"] != second_facets["word_text"]
    # ...and it left the image facet alone, by publishing none at all.
    assert "page_image" not in first_facets
    assert "page_image" not in second_facets


# ── The decision journal is read once, not once per proposal ────────────


def test_the_decision_journal_is_read_once_per_proposal_listing(
    toolbar_loaded: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``decision_for`` re-reads and re-parses the whole JSONL on every call, and
    the list route called it once per proposal. Three proposals meant three
    full-file reads of a journal that only grows.
    """
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    client, project_state, _page = toolbar_loaded
    project_root = project_state.loaded_project.project_root
    for pid in ("p1", "p2", "p3"):
        _seed_proposal(client, project_root, proposal_id=pid)

    reads = 0
    original = RegionDecisionLog.decisions

    def counted(self: RegionDecisionLog) -> Any:
        nonlocal reads
        reads += 1
        return original(self)

    monkeypatch.setattr(RegionDecisionLog, "decisions", counted)

    listed = client.get(f"{_BASE}/regions/proposals")

    assert listed.status_code == 200, listed.text
    assert len(listed.json()["proposals"]) == 3
    assert reads == 1, f"journal read {reads} times for 3 proposals"


def test_the_decision_journal_is_read_once_per_page_payload(
    toolbar_loaded: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same cost on the hotter path: the page payload resolves every proposal on
    the page, on every load and after every mutating route.
    """
    from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog

    client, project_state, _page = toolbar_loaded
    project_root = project_state.loaded_project.project_root
    for pid in ("p1", "p2", "p3"):
        _seed_proposal(client, project_root, proposal_id=pid)
    client.get(_BASE)  # warm the page so the GET below only assembles the payload

    reads = 0
    original = RegionDecisionLog.decisions

    def counted(self: RegionDecisionLog) -> Any:
        nonlocal reads
        reads += 1
        return original(self)

    monkeypatch.setattr(RegionDecisionLog, "decisions", counted)

    payload = client.get(_BASE)

    assert payload.status_code == 200, payload.text
    assert len(payload.json()["proposals"]) == 3
    assert reads == 1, f"journal read {reads} times for 3 proposals"

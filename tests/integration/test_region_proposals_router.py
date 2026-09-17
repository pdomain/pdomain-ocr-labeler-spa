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


def test_accept_proposal_with_unsupported_role_returns_400(
    toolbar_loaded: Any, narrowed_block_vocabulary: None
) -> None:
    from pdomain_book_contracts.annotation import RegionRole

    client, project_state, page = toolbar_loaded
    before_items = len(page.items)
    # Since pdomain-book-tools 0.28.0 the engine allows all 34 RegionRole values,
    # so the fixture narrows its list to reproduce the drift this branch guards
    # against — same non-mutation proof as create_region's equivalent test in
    # test_regions_router.py.
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


def test_rejecting_on_a_page_that_is_not_loaded_writes_nothing(toolbar_loaded: Any) -> None:
    """With no live page there is nothing to check the accepted region against.
    Proceeding would append the rejection while the confirmed region survives in
    the persisted blob — the journal-versus-blob contradiction the 409 exists to
    prevent, reached through a request a caller can make. Every sibling route
    refuses in this state; this one now refuses too, and refuses *before* writing.
    """
    client, project_state, _page = toolbar_loaded
    project_root = project_state.loaded_project.project_root
    _seed_proposal(client, project_root)
    project_state._page_states.pop(0, None)

    rejected = client.post(f"{_BASE}/regions/proposals/p1/reject")

    assert rejected.status_code == 400, rejected.text
    assert rejected.json()["error"] == "page_not_loaded"
    # The assertion that matters: nothing was written on the way out.
    assert _journal_bytes(project_root) == b""


# ── The proposal-run job and its book-scoped route (Task 5) ──────────────


def test_start_proposal_run_returns_a_job_id(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post("/api/projects/book1/regions/propose", json={})
    assert r.status_code == 202, r.text
    assert r.json()["job_id"]


def test_start_proposal_run_stamps_project_id_into_the_job_payload(toolbar_loaded: Any) -> None:
    """The handler reads ``job.payload["project_id"]`` to pin itself to the book
    it was queued for; the route must put it there. ``StartRegionProposalRunRequest``
    carries only ``model_id``/``model_version``, so this cannot come from
    ``body.model_dump()`` alone — see ``api/projects.py``'s ``post_propose_page_kinds``.
    """
    client, _ps, _page = toolbar_loaded
    runner = client.app.state.job_runner

    r = client.post("/api/projects/book1/regions/propose", json={})
    assert r.status_code == 202, r.text

    job = runner.get_job(r.json()["job_id"])
    assert job is not None
    assert job.payload["project_id"] == "book1"


def test_start_proposal_run_on_unloaded_project_returns_404(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post("/api/projects/does-not-exist/regions/propose", json={})
    assert r.status_code == 404, r.text


def test_proposal_run_never_writes_the_page_blob(toolbar_loaded: Any, tmp_path: Path) -> None:
    """The invariant test: run a proposal job over a page, assert the blob is untouched.

    Marks page 0's kind reviewed first — the handler now reads page-kind state itself
    and skips any page lacking it, so an unmarked page would make this test vacuous.
    """
    import asyncio
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    client, project_state, _page = toolbar_loaded
    store = client.app.state.page_store
    runner = client.app.state.job_runner
    project = project_state.loaded_project
    assert project is not None
    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    pstate = project_state.page_states[0]
    agg_before = store.get_page(pstate.page_id)
    hash_before = (
        agg_before.record.provenance.head.blob_refs[0]
        if agg_before.record.provenance and agg_before.record.provenance.head
        else None
    )

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus

    job = Job(
        job_id="test-job",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job  # test-only direct enqueue, mirrors runner._run_one's bookkeeping
    asyncio.run(handle_propose_regions(runner, job))

    agg_after = store.get_page(pstate.page_id)
    hash_after = (
        agg_after.record.provenance.head.blob_refs[0]
        if agg_after.record.provenance and agg_after.record.provenance.head
        else None
    )
    assert hash_after == hash_before


def test_a_page_with_no_page_kind_state_gets_no_region_proposals(toolbar_loaded: Any) -> None:
    """The job reads page-kind state itself; an unproposed, unconfirmed page is skipped.

    No page in this fixture has a proposed or confirmed kind, so the run never even
    starts — nothing is written to the proposal journal.
    """
    import asyncio
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    client, project_state, _page = toolbar_loaded
    runner = client.app.state.job_runner
    project = project_state.loaded_project
    assert project is not None

    job = Job(
        job_id="test-job-2",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    asyncio.run(handle_propose_regions(runner, job))

    assert RegionProposalLog(project.project_root).runs() == []


def test_a_run_queued_for_another_book_refuses_to_propose_for_the_loaded_one(
    toolbar_loaded: Any,
) -> None:
    """Jobs dequeue later than they are submitted, and a load in between swaps
    ``loaded_project``. Proposals are durable and book-scoped, so proposing
    regions for whatever is loaded now would write one book's run into another
    book's journal. The handler must refuse rather than proceed — the same
    defect ``propose_page_kinds`` was fixed for in commit 8cb5a58.
    """
    import asyncio
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    client, project_state, _page = toolbar_loaded
    runner = client.app.state.job_runner
    project = project_state.loaded_project
    assert project is not None
    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    job = Job(
        job_id="test-job-3",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id="some-other-book",
        payload={"project_id": "some-other-book"},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    asyncio.run(handle_propose_regions(runner, job))

    assert RegionProposalLog(project.project_root).runs() == []

    reported = runner.get_job(job.job_id)
    assert reported is not None
    assert "some-other-book" in reported.message
    assert project.project_id in reported.message


# ── Verified per-page leases + a bulk reviewed-store read ────────────────
#
# pdomain-ocr-synth's docs/issues/2026-09-16-page-kind-follow-ups-parked-
# during-tasks-6-and-7.md "Still open: a run on a book-labeling project can
# measure unpinned bytes" — the same fix ``propose_page_kinds`` got, applied
# here because slice 4's real detector will read the page image too.


def _load_book_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, page_count: int) -> Any:
    """A ``TestClient`` with a book-labeling project loaded — no pages seeded yet."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from pdomain_ocr_labeler_spa.bootstrap import build_app
    from tests.integration.conftest import _tb_make_settings
    from tests.unit.core.persistence.test_book_labeling_session import _write_book

    monkeypatch.setattr(
        "pdomain_ocr_labeler_spa.api.typography.typography_page_review",
        lambda *_args: SimpleNamespace(complete=True),
    )

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    book_root = projects_root / "book1"
    _write_book(book_root, page_count=page_count, valid_images=True)

    settings = _tb_make_settings(tmp_path, projects_root=projects_root)
    app = build_app(settings)
    client = TestClient(app)
    client.__enter__()
    resp = client.post("/api/projects/load", json={"project_root": str(book_root)})
    assert resp.status_code == 200, resp.text
    return client


def _seed_page(client: Any, index: int) -> None:
    """Seed a real book-tools ``Page`` into ``PageState`` + the event store for *index*."""
    from uuid import uuid4

    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import PageRecord

    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
    from pdomain_ocr_labeler_spa.core.project_state import PageState
    from tests.integration.conftest import _tb_make_page

    store = client.app.state.page_store
    page = _tb_make_page()
    page_id = uuid4()
    store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=index, source="ocr")))

    project_state = client.app.state.project_state
    outcome = PageLoadOutcome(page_index=index, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=index, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[index] = pstate


def _run_propose_regions_job(client: Any, *, detector: Any = None) -> Any:
    """Directly invoke the handler against a fresh job, mirroring the tests above."""
    import asyncio
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus

    project_state = client.app.state.project_state
    project = project_state.loaded_project
    assert project is not None
    runner = client.app.state.job_runner
    if detector is not None:
        runner.context["region_detector"] = detector

    job = Job(
        job_id="test-lease-job",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    asyncio.run(handle_propose_regions(runner, job))
    return runner


def test_reviewed_store_is_read_once_per_run_not_once_per_eligible_page(
    toolbar_loaded: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the bulk accessor, each eligible page's reviewed check paid its own
    full-file journal parse. With ``reviewed_page_indices`` the whole run costs
    exactly one read, however many pages are eligible.
    """
    from datetime import UTC, datetime
    from uuid import uuid4

    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import PageRecord

    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
    from pdomain_ocr_labeler_spa.core.project_state import PageState

    client, project_state, page = toolbar_loaded
    project = project_state.loaded_project
    assert project is not None
    store = client.app.state.page_store

    for idx in (1, 2):
        page_id = uuid4()
        store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=idx, source="ocr")))
        outcome = PageLoadOutcome(page_index=idx, source=PageSource.OCR, payload=page)
        pstate = PageState(page_index=idx, page_record=outcome)
        pstate.page_id = page_id
        project_state._page_states[idx] = pstate

    reviewed = PageKindReviewedStore(project.project_root)
    for idx in (0, 1, 2):
        reviewed.mark_reviewed(idx, datetime.now(UTC).isoformat())

    read_calls = 0
    original_read = PageKindReviewedStore._read

    def _counting_read(self: PageKindReviewedStore) -> list[Any]:
        nonlocal read_calls
        read_calls += 1
        return original_read(self)

    monkeypatch.setattr(PageKindReviewedStore, "_read", _counting_read)

    _run_propose_regions_job(client)

    assert read_calls == 1


def test_an_ordinary_project_detector_sees_the_plain_on_disk_image_path(toolbar_loaded: Any) -> None:
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    client, project_state, _page = toolbar_loaded
    project = project_state.loaded_project
    assert project is not None
    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    recorded: list[Path] = []

    def _detector(page: Any) -> list[Any]:
        del page
        recorded.append(project_state.labeling_image_path(0))
        return []

    _run_propose_regions_job(client, detector=_detector)

    assert recorded == [project.image_paths[0]]


def test_a_book_labeling_project_detector_sees_the_sealed_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect this fix closes: a real detector reading the page image on a
    book-labeling project must see the verified sealed descriptor, never the
    raw manifest path — the same requirement ``propose_page_kinds`` now meets.
    """
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    client = _load_book_client(tmp_path, monkeypatch, page_count=1)
    _seed_page(client, 0)
    project_state = client.app.state.project_state
    project = project_state.loaded_project
    assert project is not None
    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    recorded: list[Path] = []

    def _detector(page: Any) -> list[Any]:
        del page
        recorded.append(project_state.labeling_image_path(0))
        return []

    _run_propose_regions_job(client, detector=_detector)

    assert len(recorded) == 1
    assert str(recorded[0]).startswith("/proc/self/fd/")
    # The lease is scoped to the ``detector(page)`` call — once the run has
    # finished, the descriptor it resolved to must no longer be readable.
    with pytest.raises(OSError):
        recorded[0].read_bytes()


def test_the_book_lease_is_closed_even_when_the_detector_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore

    client = _load_book_client(tmp_path, monkeypatch, page_count=1)
    _seed_page(client, 0)
    project_state = client.app.state.project_state
    project = project_state.loaded_project
    assert project is not None
    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    captured: list[Path] = []

    def _detector(page: Any) -> list[Any]:
        del page
        captured.append(project_state.labeling_image_path(0))
        raise RuntimeError("boom")

    # The detector is a swap-in callable, so the handler logs its failure and
    # skips that page rather than letting it abort the whole run. The lease
    # must still be closed on that path, which is what this test pins.
    _run_propose_regions_job(client, detector=_detector)

    assert len(captured) == 1
    with pytest.raises(OSError):
        captured[0].read_bytes()


def test_a_detector_that_raises_skips_its_page_and_does_not_kill_the_run(
    toolbar_loaded: Any,
) -> None:
    """The detector is a swap-in callable; one bad page must not abort a whole book.

    A lease failure and a detector failure are reported separately, so a
    ``ValueError`` out of a detector is never attributed to the manifest.
    """
    import asyncio
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    client, project_state, _page = toolbar_loaded
    runner = client.app.state.job_runner
    project = project_state.loaded_project
    assert project is not None
    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    def _exploding_detector(page: Any) -> list[Any]:
        del page
        raise ValueError("page mixes normalized and pixel word boxes")

    runner.context["region_detector"] = _exploding_detector
    job = Job(
        job_id="detector-raises",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job

    # The run completes rather than propagating the detector's error.
    asyncio.run(handle_propose_regions(runner, job))

    log = RegionProposalLog(project.project_root)
    runs = log.runs()
    assert len(runs) == 1
    assert log.proposals_for_page(0, run_id=runs[0].run_id) == []

"""Unit tests for the region/proposal assembly wired into ``_page_payload``.

Covers the code review's Finding 2 for task 1 of
``2026-09-08-region-routes-and-proposal-run``: the assembly logic itself
(``_resolve_regions_and_proposals``) and the image-digest fallback
(``_image_digest_for_page``) had zero direct coverage — only the low-level
``core.regions.block_adapter`` functions were unit tested. These tests assert
what a reader of ``PagePayload.regions`` / ``.proposals`` would actually see,
not the plan's shape.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

import pytest

from pdomain_ocr_labeler_spa.api.pages import _image_digest_for_page, _resolve_regions_and_proposals
from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog
from pdomain_ocr_labeler_spa.core.regions.models import (
    Disposition,
    ProposalRun,
    RegionDecision,
    RegionProposal,
)
from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog


def _region_block(region_id: str, role: str, ltrb: tuple[int, int, int, int]):
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType

    left, top, right, bottom = ltrb
    return Block(
        items=[],
        bounding_box=BoundingBox.from_ltrb(left, top, right, bottom, is_normalized=False),
        child_type=BlockChildType.WORDS,
        block_category=BlockCategory.BLOCK,
        block_role_labels=[role],
        additional_block_attributes={"region_id": region_id},
    )


def _run(
    *,
    run_id: str = "run-1",
    page_facet_digests: dict[int, dict[str, str]] | None = None,
    depends_on: frozenset[str] = frozenset(),
) -> ProposalRun:
    return ProposalRun(
        run_id=run_id,
        model_id="detector-x",
        model_version="1.0",
        created_at="2026-09-08T00:00:00Z",
        page_facet_digests=page_facet_digests or {},
        depends_on=depends_on,
        page_kind_decision_ref=None,
        page_kind_was_confirmed=False,
    )


def _proposal(
    *,
    proposal_id: str = "prop-1",
    run_id: str = "run-1",
    page_index: int = 0,
) -> RegionProposal:
    from pdomain_book_contracts.annotation import RegionRole

    return RegionProposal(
        proposal_id=proposal_id,
        run_id=run_id,
        page_index=page_index,
        role=RegionRole.CAPTION,
        box=(60, 60, 100, 100),
        confidence=0.9,
        evidence={"detector": "x", "score": 0.9},
    )


# ── _resolve_regions_and_proposals — reader-facing shape ───────────────


def test_a_confirmed_region_and_a_pending_proposal_both_reach_the_payload(tmp_path: Path) -> None:
    """The exact scenario a labeler page shows: one region a person already
    confirmed, and one proposal nobody has looked at yet — both must show up,
    and the proposal must appear twice: once as an unconfirmed region (so it
    renders on the page) and once in the proposal list (so it renders in the
    review panel)."""
    from pdomain_book_contracts.annotation import RegionRole
    from pdomain_book_tools.ocr.page import Page

    page = Page(
        width=200,
        height=300,
        page_index=0,
        blocks=[_region_block("conf-1", "paragraph", (5, 5, 50, 50))],
    )

    proposal_log = RegionProposalLog(tmp_path)
    proposal_log.append_run(_run())
    proposal_log.append_proposals([_proposal()])

    regions, proposals = _resolve_regions_and_proposals(
        page=page, project_root=tmp_path, page_index=0, page_store=None, page_id=None
    )

    assert len(regions) == 2
    confirmed_view = next(r for r in regions if r.confirmed)
    pending_view = next(r for r in regions if not r.confirmed)

    assert confirmed_view.region_id == "conf-1"
    assert confirmed_view.role is RegionRole.PARAGRAPH
    assert confirmed_view.proposal_id is None

    assert pending_view.region_id is None
    assert pending_view.proposal_id == "prop-1"
    assert pending_view.role is RegionRole.CAPTION
    assert pending_view.confidence == 0.9
    assert pending_view.stale is False

    assert len(proposals) == 1
    assert proposals[0].proposal_id == "prop-1"
    assert proposals[0].evidence == {"detector": "x", "score": 0.9}
    assert proposals[0].disposition is None
    assert proposals[0].decided_region_id is None


def test_a_rejected_proposal_shows_its_disposition_but_not_as_a_region(tmp_path: Path) -> None:
    """A rejected proposal is a fact a reviewer needs to see in the proposal
    list (``disposition="rejected"``), but it must not also render as a
    region on the page — that is what distinguishes "looked at and refused"
    from "unreviewed"."""
    from pdomain_book_tools.ocr.page import Page

    page = Page(width=200, height=300, page_index=0, blocks=[])

    proposal_log = RegionProposalLog(tmp_path)
    proposal_log.append_run(_run())
    proposal_log.append_proposals([_proposal()])

    decision_log = RegionDecisionLog(tmp_path)
    decision_log.append(
        RegionDecision(
            decision_id="dec-1",
            run_id="run-1",
            proposal_id="prop-1",
            disposition=Disposition.REJECTED,
            region_id=None,
            actor="tester",
            decided_at="2026-09-08T00:00:00Z",
        )
    )

    regions, proposals = _resolve_regions_and_proposals(
        page=page, project_root=tmp_path, page_index=0, page_store=None, page_id=None
    )

    assert regions == []
    assert len(proposals) == 1
    assert proposals[0].disposition == "rejected"
    assert proposals[0].decided_region_id is None


def test_an_accepted_proposal_carries_its_decided_region_id(tmp_path: Path) -> None:
    """An accepted decision names the region_id it produced; that id must
    reach the proposal view so the frontend can link the two."""
    from pdomain_book_tools.ocr.page import Page

    page = Page(width=200, height=300, page_index=0, blocks=[])

    proposal_log = RegionProposalLog(tmp_path)
    proposal_log.append_run(_run())
    proposal_log.append_proposals([_proposal()])

    decision_log = RegionDecisionLog(tmp_path)
    decision_log.append(
        RegionDecision(
            decision_id="dec-1",
            run_id="run-1",
            proposal_id="prop-1",
            disposition=Disposition.ACCEPTED,
            region_id="new-region-1",
            actor="tester",
            decided_at="2026-09-08T00:00:00Z",
        )
    )

    _regions, proposals = _resolve_regions_and_proposals(
        page=page, project_root=tmp_path, page_index=0, page_store=None, page_id=None
    )

    assert len(proposals) == 1
    assert proposals[0].disposition == "accepted"
    assert proposals[0].decided_region_id == "new-region-1"


def test_a_stale_proposal_s_run_reaches_the_region_view(tmp_path: Path) -> None:
    """A proposal whose run's recorded facet digest no longer matches the
    live page must resolve with ``stale=True`` on the *region* view — this is
    what the labeler renders to warn a reviewer the page moved since the
    model looked at it."""
    from pdomain_book_tools.ocr.page import Page

    page = Page(width=200, height=300, page_index=0, blocks=[])

    proposal_log = RegionProposalLog(tmp_path)
    proposal_log.append_run(
        _run(
            page_facet_digests={0: {"word_boxes": "a-digest-that-cannot-match-the-live-page"}},
            depends_on=frozenset({"word_boxes"}),
        )
    )
    proposal_log.append_proposals([_proposal()])

    regions, _proposals = _resolve_regions_and_proposals(
        page=page, project_root=tmp_path, page_index=0, page_store=None, page_id=None
    )

    assert len(regions) == 1
    assert regions[0].stale is True


# ── _image_digest_for_page — the fallback path ──────────────────────────


class _RaisingPageStore:
    """Stand-in for ``LabelerPageStore`` whose ``get_page`` always fails."""

    def get_page(self, page_id: object) -> object:
        raise RuntimeError("event store unavailable")


class _FakeHead:
    def __init__(self, blob_refs: list[str]) -> None:
        self.blob_refs = blob_refs


class _FakeProvenance:
    def __init__(self, head: _FakeHead | None) -> None:
        self.head = head


class _FakeRecord:
    def __init__(self, provenance: _FakeProvenance | None) -> None:
        self.provenance = provenance


class _FakeAggregate:
    def __init__(self, record: _FakeRecord) -> None:
        self.record = record


class _FakePageStore:
    """Stand-in for ``LabelerPageStore`` returning a canned aggregate."""

    def __init__(self, aggregate: _FakeAggregate) -> None:
        self._aggregate = aggregate

    def get_page(self, page_id: object) -> _FakeAggregate:
        return self._aggregate


def test_image_digest_returns_none_without_a_store_or_page_id() -> None:
    assert _image_digest_for_page(page_store=None, page_id=None) is None
    store = _FakePageStore(_FakeAggregate(_FakeRecord(None)))
    assert _image_digest_for_page(page_store=store, page_id=None) is None


def test_image_digest_logs_a_warning_when_the_store_raises(caplog: pytest.LogCaptureFixture) -> None:
    """A failed read degrades the page (returns ``None``) but must not do so
    silently — and not at DEBUG, which is off in production, where this runs.
    The docstring's promise that the failure is "logged, not silenced" is only
    true at WARNING or above."""
    page_id = uuid4()
    with caplog.at_level(logging.WARNING, logger="pdomain_ocr_labeler_spa.api.pages"):
        result = _image_digest_for_page(page_store=_RaisingPageStore(), page_id=page_id)

    assert result is None
    assert any(
        record.levelno >= logging.WARNING
        and "image-digest read failed" in record.message
        and str(page_id) in record.message
        for record in caplog.records
    )


def test_image_digest_returns_none_when_provenance_graph_is_empty() -> None:
    store = _FakePageStore(_FakeAggregate(_FakeRecord(None)))
    assert _image_digest_for_page(page_store=store, page_id=uuid4()) is None


def test_image_digest_returns_none_when_head_has_no_blob_refs() -> None:
    store = _FakePageStore(_FakeAggregate(_FakeRecord(_FakeProvenance(_FakeHead([])))))
    assert _image_digest_for_page(page_store=store, page_id=uuid4()) is None


def test_image_digest_returns_none_when_only_the_content_hash_is_present() -> None:
    """The OCR-ingest path writes ``[content_hash, image_hash]``; the
    labeler-edit path writes ``[content_hash]`` alone. Index 0 is the page
    *content*, so standing it in for the image would make every text edit
    change the ``page_image`` facet and invalidate every geometry proposal on
    the page. There is no image digest here, and saying so is the honest
    answer — the caller omits the facet, which reads as stale."""
    store = _FakePageStore(_FakeAggregate(_FakeRecord(_FakeProvenance(_FakeHead(["content-hash-only"])))))
    assert _image_digest_for_page(page_store=store, page_id=uuid4()) is None


def test_image_digest_prefers_index_1_when_present() -> None:
    store = _FakePageStore(
        _FakeAggregate(_FakeRecord(_FakeProvenance(_FakeHead(["content-hash", "image-hash"]))))
    )
    assert _image_digest_for_page(page_store=store, page_id=uuid4()) == "image-hash"

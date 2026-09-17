"""Region boxes on a normalized page: the API always speaks source pixels.

Real DocTR OCR emits word boxes in 0-to-1 normalized coordinates, so
``page.is_content_normalized`` is ``True`` on every real OCR'd page. These
tests pin the write routes (``create_region``, ``accept_region_proposal``,
``edit_region``) converting an incoming pixel box down to the page's own
storage convention, and the read path (``confirmed_regions_from_page``, via
``GET`` and every route's refreshed payload) converting a normalized
region's stored box back up to pixels — so ``RegionView.box`` is always
pixels, on either kind of page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_BASE = "/api/projects/book1/pages/0"

# The real evidence box from projectID657550412c8dc page 10 (1166x1779px):
# a running head's first word. Also the exact box the normalized_page_loaded
# fixture seeds its one word at, so a membership/round-trip assertion can
# compare against it directly.
_REAL_BOX = {"x": 442, "y": 110, "width": 211, "height": 29}


def _seed_proposal(client: Any, project_root: Path, *, proposal_id: str = "p1") -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    log = RegionProposalLog(project_root)
    log.append_run(
        ProposalRun(
            run_id="r1",
            model_id="test-detector",
            model_version="0.0.0",
            created_at="2026-09-17T10:00:00+00:00",
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
                role=RegionRole.PAGE_HEADER,
                box=(442, 110, 653, 139),
                confidence=0.8,
                evidence={"signal": "furniture_band"},
            )
        ]
    )


def test_accepting_a_proposal_on_a_normalized_page_returns_the_exact_pixel_box(
    normalized_page_loaded: Any,
) -> None:
    """The regression that matters most: Defect B. Accepting used to 400."""
    client, project_state, page = normalized_page_loaded
    assert page.is_content_normalized is True
    _seed_proposal(client, project_state.loaded_project.project_root)

    r = client.post(f"{_BASE}/regions/proposals/p1/accept")
    assert r.status_code == 200, r.text
    confirmed = [reg for reg in r.json()["regions"] if reg["confirmed"]]
    assert len(confirmed) == 1
    assert confirmed[0]["box"] == _REAL_BOX

    # The stored block itself carries a normalized box in [0, 1] — the page's
    # own storage convention, not the API's.
    region_id = confirmed[0]["region_id"]
    block = next(b for b in page.items if b.additional_block_attributes.get("region_id") == region_id)
    assert block.bounding_box.is_normalized is True
    left, top, right, bottom = block.bounding_box.to_ltrb()
    assert 0.0 <= left <= 1.0
    assert 0.0 <= top <= 1.0
    assert 0.0 <= right <= 1.0
    assert 0.0 <= bottom <= 1.0


def test_create_region_with_a_pixel_box_on_a_normalized_page_serves_it_back(
    normalized_page_loaded: Any,
) -> None:
    client, _ps, page = normalized_page_loaded
    assert page.is_content_normalized is True

    r = client.post(f"{_BASE}/regions", json={"role": "poetry", "box": _REAL_BOX})
    assert r.status_code == 200, r.text
    confirmed = [reg for reg in r.json()["regions"] if reg["confirmed"]]
    assert len(confirmed) == 1
    assert confirmed[0]["box"] == _REAL_BOX


def test_edit_region_box_on_a_normalized_page_round_trips_in_pixels(normalized_page_loaded: Any) -> None:
    client, _ps, _page = normalized_page_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 5, "y": 5, "width": 50, "height": 50}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])

    r = client.patch(f"{_BASE}/regions/{region_id}", json={"box": _REAL_BOX})
    assert r.status_code == 200, r.text
    region = next(reg for reg in r.json()["regions"] if reg["region_id"] == region_id)
    assert region["box"] == _REAL_BOX


def test_confirmed_regions_from_page_serves_pixels_for_a_normalized_region_block() -> None:
    """Defect C, directly against the adapter — no route in the way."""
    from pdomain_book_contracts.annotation import RegionRole
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import confirmed_regions_from_page

    page = Page(width=1166, height=1779, page_index=0, blocks=[])
    region = Block(
        items=[],
        bounding_box=BoundingBox.from_ltrb(
            442 / 1166, 110 / 1779, 653 / 1166, 139 / 1779, is_normalized=True
        ),
        child_type=BlockChildType.WORDS,
        block_category=BlockCategory.BLOCK,
        block_role_labels=[RegionRole.PAGE_HEADER.value],
        additional_block_attributes={"region_id": "r1", "source_proposal_id": "hand-drawn"},
    )
    page.add_item(region)

    resolved = confirmed_regions_from_page(page)
    assert len(resolved) == 1
    assert resolved[0].box == (442, 110, 653, 139)


def test_an_out_of_bounds_box_on_a_normalized_page_is_never_reported_as_invalid_region_role(
    normalized_page_loaded: Any,
) -> None:
    """A box reaching past the page's edge must not be mislabelled as a role error."""
    client, _ps, page = normalized_page_loaded
    assert page.is_content_normalized is True

    r = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 0, "y": 0, "width": page.width + 500, "height": 50}},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_region_box"
    assert r.json()["error"] != "invalid_region_role"

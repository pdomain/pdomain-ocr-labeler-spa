"""Unit tests for lifting confirmed Block regions off a page."""

from __future__ import annotations


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


def _plain_paragraph():
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType

    line = Block(
        items=[],
        bounding_box=BoundingBox.from_ltrb(0, 0, 10, 10, is_normalized=False),
        child_type=BlockChildType.WORDS,
        block_category=BlockCategory.LINE,
    )
    return Block(
        items=[line],
        bounding_box=BoundingBox.from_ltrb(0, 0, 10, 10, is_normalized=False),
        child_type=BlockChildType.BLOCKS,
        block_category=BlockCategory.PARAGRAPH,
    )


def test_a_region_block_lifts_into_a_confirmed_resolved_region() -> None:
    from pdomain_book_contracts.annotation import RegionRole
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import confirmed_regions_from_page

    page = Page(
        width=200,
        height=300,
        page_index=0,
        blocks=[_region_block("r1", "poetry", (10, 20, 100, 200))],
    )
    resolved = confirmed_regions_from_page(page)

    assert len(resolved) == 1
    assert resolved[0].region_id == "r1"
    assert resolved[0].role is RegionRole.POETRY
    assert resolved[0].confirmed is True
    assert resolved[0].confidence is None
    assert resolved[0].box == (10, 20, 100, 200)


def test_a_plain_paragraph_with_no_region_id_is_not_a_region() -> None:
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import confirmed_regions_from_page

    page = Page(width=200, height=300, page_index=0, blocks=[_plain_paragraph()])
    assert confirmed_regions_from_page(page) == []


def test_nested_regions_are_both_found_and_addressable() -> None:
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import (
        confirmed_regions_from_page,
        find_region_block,
    )

    inner = _region_block("inner", "caption", (30, 30, 40, 40))
    outer = Block(
        items=[inner],
        bounding_box=BoundingBox.from_ltrb(10, 10, 100, 100, is_normalized=False),
        child_type=BlockChildType.BLOCKS,
        block_category=BlockCategory.BLOCK,
        block_role_labels=["figure"],
        additional_block_attributes={"region_id": "outer"},
    )
    page = Page(width=200, height=300, page_index=0, blocks=[outer])

    ids = {r.region_id for r in confirmed_regions_from_page(page)}
    assert ids == {"outer", "inner"}
    assert find_region_block(page, "inner") is inner
    assert find_region_block(page, "missing-id") is None


def test_a_block_with_an_unrecognised_role_string_is_skipped_not_raised() -> None:
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import confirmed_regions_from_page

    stale = _region_block("r1", "poetry", (0, 0, 10, 10))
    stale.block_role_labels = ["some-future-role-not-yet-in-region-role"]
    page = Page(width=200, height=300, page_index=0, blocks=[stale])
    assert confirmed_regions_from_page(page) == []


def test_a_confirmed_region_surfaces_its_member_word_signatures() -> None:
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.page import Page
    from pdomain_book_tools.ocr.word import Word

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import confirmed_regions_from_page

    word = Word(text="verse", bounding_box=BoundingBox.from_ltrb(12, 22, 40, 38, is_normalized=False))
    region = _region_block("r1", "poetry", (10, 20, 100, 200))
    region.add_item(word)
    page = Page(width=200, height=300, page_index=0, blocks=[region])

    resolved = confirmed_regions_from_page(page)

    assert len(resolved) == 1
    assert resolved[0].member_word_signatures == (word.bbox_signature,)


def test_a_confirmed_region_surfaces_its_origin_proposal_id() -> None:
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import confirmed_regions_from_page

    promoted = _region_block("r1", "poetry", (10, 20, 100, 200))
    promoted.additional_block_attributes["source_proposal_id"] = "p1"
    page = Page(width=200, height=300, page_index=0, blocks=[promoted])

    resolved = confirmed_regions_from_page(page)

    assert resolved[0].proposal_id == "p1"


def test_a_confirmed_region_with_no_stamped_origin_surfaces_none() -> None:
    """A region blob written before this correction, or edited outside the routes."""
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import confirmed_regions_from_page

    unstamped = _region_block("r1", "poetry", (10, 20, 100, 200))
    page = Page(width=200, height=300, page_index=0, blocks=[unstamped])

    resolved = confirmed_regions_from_page(page)

    assert resolved[0].proposal_id is None

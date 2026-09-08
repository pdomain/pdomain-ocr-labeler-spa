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


def _page_with_one_word(text: str, ltrb: tuple[int, int, int, int]):
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.page import Page
    from pdomain_book_tools.ocr.word import Word

    left, top, right, bottom = ltrb
    region = _region_block("r1", "poetry", (0, 0, 200, 300))
    bbox = BoundingBox.from_ltrb(left, top, right, bottom, is_normalized=False)
    region.add_item(Word(text=text, bounding_box=bbox))
    return Page(width=200, height=300, page_index=0, blocks=[region])


def test_compute_page_facet_digests_returns_all_four_facets_deterministically() -> None:
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import compute_page_facet_digests

    page_a = _page_with_one_word("verse", (10, 10, 40, 20))
    page_b = _page_with_one_word("verse", (10, 10, 40, 20))

    digests_a = compute_page_facet_digests(page_a, image_digest="img-1")
    digests_b = compute_page_facet_digests(page_b, image_digest="img-1")

    assert set(digests_a) == {"word_boxes", "line_structure", "page_image", "word_text"}
    assert digests_a == digests_b


def test_compute_page_facet_digests_omits_page_image_when_there_is_no_image_digest() -> None:
    """No image digest means no ``page_image`` facet at all.

    Publishing a stand-in (the page-*content* hash, which is all a
    labeler-edited head carries) would make a typo fix change ``page_image``
    and invalidate every geometry proposal on the page. An omitted facet
    compares unequal to a run's recorded one, so it reads as stale — safe in
    the direction that shows a warning rather than hiding one.
    """
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import compute_page_facet_digests

    page = _page_with_one_word("verse", (10, 10, 40, 20))
    digests = compute_page_facet_digests(page, image_digest=None)

    assert "page_image" not in digests
    assert set(digests) == {"word_boxes", "line_structure", "word_text"}


def test_compute_page_facet_digests_word_text_change_does_not_move_word_boxes() -> None:
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import compute_page_facet_digests

    same_box = (10, 10, 40, 20)
    digests_a = compute_page_facet_digests(_page_with_one_word("verse", same_box), image_digest=None)
    digests_b = compute_page_facet_digests(_page_with_one_word("prose", same_box), image_digest=None)

    assert digests_a["word_boxes"] == digests_b["word_boxes"]
    assert digests_a["line_structure"] == digests_b["line_structure"]
    assert digests_a["word_text"] != digests_b["word_text"]


def test_compute_page_facet_digests_word_box_change_does_not_move_word_text() -> None:
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import compute_page_facet_digests

    digests_a = compute_page_facet_digests(_page_with_one_word("verse", (10, 10, 40, 20)), image_digest=None)
    digests_b = compute_page_facet_digests(_page_with_one_word("verse", (50, 50, 80, 60)), image_digest=None)

    assert digests_a["word_text"] == digests_b["word_text"]
    assert digests_a["word_boxes"] != digests_b["word_boxes"]


def _page_with_two_ocr_lines():
    """A page whose lines are ordinary OCR structure — no region markers."""
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
    from pdomain_book_tools.ocr.page import Page
    from pdomain_book_tools.ocr.word import Word

    def line(text: str, ltrb: tuple[int, int, int, int]) -> Block:
        left, top, right, bottom = ltrb
        return Block(
            items=[
                Word(
                    text=text,
                    bounding_box=BoundingBox.from_ltrb(left, top, right, bottom, is_normalized=False),
                )
            ],
            child_type=BlockChildType.WORDS,
            block_category=BlockCategory.LINE,
        )

    return Page(
        width=200,
        height=300,
        page_index=0,
        blocks=[line("one", (0, 0, 50, 10)), line("two", (0, 20, 50, 30))],
    )


def test_confirming_a_region_does_not_change_the_line_structure_digest() -> None:
    """``Block.lines`` returns ``[self]`` for a WORDS-typed block, so a leaf region
    joins ``page.lines``. Counting it as line structure meant confirming one
    proposal changed ``line_structure`` and marked every *other* proposal on that
    page stale against its own run — self-inflicted staleness on the exact
    workflow region review exists to support.
    """
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import compute_page_facet_digests

    page = _page_with_two_ocr_lines()
    before = compute_page_facet_digests(page, image_digest="img-1")["line_structure"]

    page.add_item(_region_block("r1", "poetry", (0, 0, 200, 300)))
    after = compute_page_facet_digests(page, image_digest="img-1")["line_structure"]

    assert after == before


def test_a_real_line_structure_change_still_moves_the_digest() -> None:
    """The skip must not turn ``line_structure`` into a digest that never changes."""
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import compute_page_facet_digests

    page = _page_with_two_ocr_lines()
    before = compute_page_facet_digests(page, image_digest="img-1")["line_structure"]

    page.lines[0].override_page_sort_order = 7
    reordered = compute_page_facet_digests(page, image_digest="img-1")["line_structure"]
    assert reordered != before

    page.remove_item(page.items[0])
    removed = compute_page_facet_digests(page, image_digest="img-1")["line_structure"]
    assert removed != reordered

"""Confirmed layout regions are written beside a DocTR export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pdomain_book_contracts.geometry.bounding_box import BoundingBox
from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
from pdomain_book_tools.ocr.page import Page
from pdomain_book_tools.ocr.word import Word

from pdomain_ocr_labeler_spa.core.jobs.handlers.export import (
    _export_page,
    _export_page_to_output_roots,
    append_confirmed_regions,
)


def _region_block(region_id: str, role: str, ltrb: tuple[int, int, int, int]) -> Block:
    left, top, right, bottom = ltrb
    return Block(
        items=[],
        bounding_box=BoundingBox.from_ltrb(left, top, right, bottom, is_normalized=False),
        child_type=BlockChildType.WORDS,
        block_category=BlockCategory.BLOCK,
        block_role_labels=[role],
        additional_block_attributes={"region_id": region_id},
    )


def _page_with_region() -> tuple[Page, Word]:
    word = Word(
        text="verse",
        bounding_box=BoundingBox.from_ltrb(12, 22, 40, 38, is_normalized=False),
    )
    region = _region_block("r1", "poetry", (10, 20, 110, 80))
    region.add_item(word)
    # add_item replaces the block box with the word box. A confirmed region
    # keeps the box a person drew, so put that box back after the word is added.
    region.bounding_box = BoundingBox.from_ltrb(10, 20, 110, 80, is_normalized=False)
    page = Page(width=200, height=300, page_index=4, blocks=[region])
    return page, word


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("JSON value must be an object")
    # isinstance(dict) leaves the parameters unknown under basedpyright.
    raw: dict[object, object] = value  # pyright: ignore[reportUnknownVariableType]
    mapping: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise TypeError("JSON object key must be a string")
        mapping[key] = item
    return mapping


def _object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("JSON value must be a list")
    raw: list[object] = value  # pyright: ignore[reportUnknownVariableType]
    return list(raw)


def _read(path: Path) -> dict[str, object]:
    # json.loads is typed as Any. _object_dict checks the shape.
    return _object_dict(json.loads(path.read_text(encoding="utf-8")))  # pyright: ignore[reportAny]


def test_append_confirmed_regions_writes_the_page_beside_detection(tmp_path: Path) -> None:
    page, word = _page_with_region()
    output = tmp_path / "out"
    assert append_confirmed_regions(page, output, prefix="book_004") == 1

    document = _read(output / "regions" / "labels.json")
    assert document["schema"] == "pdomain.layout-regions"
    assert document["version"] == 1
    pages = _object_list(document["pages"])
    assert len(pages) == 1
    entry = _object_dict(pages[0])
    assert entry["prefix"] == "book_004"
    assert entry["page_index"] == 4
    regions = _object_list(entry["regions"])
    assert len(regions) == 1
    region = _object_dict(regions[0])
    assert region["region_id"] == "r1"
    assert region["role"] == "poetry"
    assert region["box"] == {"x": 10, "y": 20, "width": 100, "height": 60}
    signature = word.bbox_signature
    assert signature is not None
    assert region["member_word_signatures"] == [list(signature)]


def test_reexport_replaces_the_same_prefix_and_keeps_another(tmp_path: Path) -> None:
    page, _word = _page_with_region()
    output = tmp_path / "out"
    assert append_confirmed_regions(page, output, prefix="book_004") == 1

    empty = Page(width=200, height=300, page_index=4, blocks=[])
    assert append_confirmed_regions(empty, output, prefix="book_004") == 0
    other = Page(width=200, height=300, page_index=5, blocks=[])
    assert append_confirmed_regions(other, output, prefix="book_005") == 0

    document = _read(output / "regions" / "labels.json")
    by_prefix: dict[str, dict[str, object]] = {}
    for item in _object_list(document["pages"]):
        entry = _object_dict(item)
        prefix = entry["prefix"]
        assert isinstance(prefix, str)
        by_prefix[prefix] = entry
    replaced = by_prefix["book_004"]["regions"]
    assert replaced == []
    assert by_prefix["book_005"]["page_index"] == 5


def test_export_page_writes_regions_when_the_image_cannot_be_read(tmp_path: Path) -> None:
    page, _word = _page_with_region()
    output = tmp_path / "out"
    _export_page(
        page,
        tmp_path / "missing.png",
        output,
        word_filter=None,
        detection=True,
        recognition=True,
        classification=False,
        prefix="book_004",
    )
    document = _read(output / "regions" / "labels.json")
    pages = _object_list(document["pages"])
    assert len(pages) == 1
    entry = _object_dict(pages[0])
    regions = _object_list(entry["regions"])
    assert len(regions) == 1


def test_each_style_folder_records_signatures_from_before_the_gt_swap(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    numpy = pytest.importorskip("numpy")

    page, word = _page_with_region()
    word.ground_truth_bounding_box = BoundingBox.from_ltrb(1, 2, 9, 8, is_normalized=False)
    signature = word.bbox_signature
    assert signature is not None
    image = tmp_path / "page.png"
    assert cv2.imwrite(str(image), numpy.full((30, 40, 3), 255, dtype="uint8"))

    roots = {"italics": tmp_path / "italics", "bold": tmp_path / "bold"}
    _export_page_to_output_roots(
        page,
        image,
        roots,
        prefix="book_004",
        style_filters=["italics", "bold"],
        component_filter=None,
        detection=False,
        recognition=False,
        classification=False,
    )

    for folder in roots.values():
        document = _read(folder / "regions" / "labels.json")
        pages = _object_list(document["pages"])
        entry = _object_dict(pages[0])
        regions = _object_list(entry["regions"])
        region = _object_dict(regions[0])
        assert region["member_word_signatures"] == [list(signature)]

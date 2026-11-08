"""Text hints bind only unique ordered OCR matches and preserve source structure."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pdomain_book_contracts.annotation import RegionRole
from pdomain_book_contracts.layout.text_hints import LayoutTextHint, LayoutTextLine

from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
from pdomain_ocr_labeler_spa.core.regions.detector import DetectorInput
from pdomain_ocr_labeler_spa.core.regions.text_layout import (
    TextLayoutDetector,
    layout_evidence_digest,
    load_layout_evidence,
    review_layout_evidence,
)

from .test_poetry import _input, _line, _page, _paragraph


def _hint(*, kind: str = "poetry", source: str = "gutenberg_html") -> LayoutTextHint:
    return LayoutTextHint.from_dict(
        {
            "kind": kind,
            "source": source,
            "text": "Roses are red Violets are blue",
            "source_ref": "edition.html",
            "lines": [
                {"text": "Roses are red", "stanza_index": 0},
                {"text": "Violets are blue", "stanza_index": 1, "indent_hint": "2em"},
            ],
        }
    )


def _verse_input() -> DetectorInput:
    page = _page(
        [
            _paragraph(
                [
                    _line("Roses are red", 100, 100, 350, 120),
                    _line("Violets are blue", 120, 150, 420, 170),
                ]
            )
        ]
    )
    return replace(_input(page), layout_hints=(_hint(),), layout_word_ids=("stored-1", "stored-2"))


def test_gutenberg_verse_keeps_stanzas_indent_and_stored_word_ids() -> None:
    result = TextLayoutDetector()(_verse_input())
    assert len(result) == 1
    assert result[0].role == RegionRole.POETRY
    assert result[0].box == (100, 100, 420, 170)
    structure = result[0].evidence["layout_structure"]
    assert structure["lines"][0]["word_ids"] == ["stored-1"]
    assert structure["lines"][1]["stanza_index"] == 1
    assert structure["lines"][1]["indent_hint"] == "2em"


def test_agreeing_sources_strengthen_rank_and_disagreement_remains_visible() -> None:
    value = _verse_input()
    agreed = replace(value, layout_hints=(_hint(), _hint(source="f2")))
    regions = TextLayoutDetector()(agreed)
    assert len(regions) == 1
    assert regions[0].confidence == 0.95
    disagreed = replace(value, layout_hints=(_hint(), _hint(kind="blockquote", source="f2")))
    regions = TextLayoutDetector()(disagreed)
    assert regions[0].evidence["layout_warnings"]


def test_legacy_verse_proposes_but_omits_word_bound_structure() -> None:
    value = replace(_verse_input(), layout_word_ids=())
    result = TextLayoutDetector()(value)
    assert len(result) == 1
    assert result[0].evidence["structure_supported"] is False
    assert "layout_structure" not in result[0].evidence
    assert "prepared" in " ".join(result[0].evidence["layout_warnings"]).lower()


@pytest.mark.parametrize("text", ["Roses red Violets are blue", "red are Roses Violets are blue"])
def test_missing_or_reordered_words_abstain(text: str) -> None:
    value = _verse_input()
    hint = LayoutTextHint(
        kind="poetry", source="f2", text=text, lines=(LayoutTextLine(text=text),), source_ref="F2.json"
    )
    assert TextLayoutDetector()(replace(value, layout_hints=(hint,))) == []


def test_repeated_phrase_abstains_instead_of_choosing_first() -> None:
    value = _verse_input()
    page = _page(
        [
            _paragraph(
                [
                    _line("Roses are red Violets are blue", 100, 100, 500, 120),
                    _line("Roses are red Violets are blue", 100, 150, 500, 170),
                ]
            )
        ]
    )
    assert TextLayoutDetector()(replace(value, page=page)) == []


def test_combining_characters_match_without_changing_source_text() -> None:
    value = _verse_input()
    page = _page([_paragraph([_line("Caf\u00e9", 100, 100, 200, 120)])])
    hint = LayoutTextHint(
        kind="poetry",
        source="f2",
        text="Cafe\u0301",
        lines=(LayoutTextLine(text="Cafe\u0301"),),
        source_ref="F2.json",
    )
    result = TextLayoutDetector()(
        replace(value, page=page, layout_word_ids=("stored-1",), layout_hints=(hint,))
    )
    assert len(result) == 1
    assert result[0].evidence["layout_hints"][0]["text"] == "Cafe\u0301"


def test_columns_are_separate_paragraphs_and_ignore_full_width_heading() -> None:
    page = _page(
        [
            _paragraph([_line("Heading", 100, 50, 900, 75)]),
            _paragraph(
                [
                    _line("Left first", 100, 100, 350, 120),
                    _line("Left second", 100, 140, 360, 160),
                ]
            ),
            _paragraph(
                [
                    _line("Right first", 600, 100, 850, 120),
                    _line("Right second", 600, 140, 860, 160),
                ]
            ),
        ]
    )
    result = TextLayoutDetector()(_input(page))
    assert len(result) == 2
    assert all(region.role == RegionRole.PARAGRAPH for region in result)
    assert [region.evidence["layout_structure"]["column_index"] for region in result] == [0, 1]
    assert result[0].box == (100, 100, 360, 160)
    assert result[1].box == (600, 100, 860, 160)


def test_true_table_requires_grid_and_data_evidence_before_column_split() -> None:
    value = _verse_input()
    page = _page(
        [
            _paragraph(
                [
                    _line("Fruit", 100, 100, 170, 120),
                    _line("Count", 600, 100, 670, 120),
                    _line("Apples", 100, 140, 180, 160),
                    _line("12", 600, 140, 630, 160),
                ]
            )
        ]
    )
    hint = LayoutTextHint(
        kind="table_candidate",
        source="gutenberg_html",
        text="Fruit Count Apples 12",
        lines=(),
        source_ref="edition.html",
        table_rows=(("Fruit", "Count"), ("Apples", "12")),
        attributes=(("table_semantics", "data"),),
    )
    value = replace(value, page=page, layout_hints=(hint,), layout_word_ids=("a", "b", "c", "d"))
    result = TextLayoutDetector()(value)
    assert len(result) == 1
    assert result[0].role == RegionRole.TABLE
    assert result[0].evidence["layout_structure"]["table_rows"][1]["cells"][1]["word_ids"] == ["d"]
    # A source table with cells arranged at inconsistent scan positions is
    # retained for review, rather than claiming an aligned table grid.
    page = _page(
        [
            _paragraph(
                [
                    _line("Fruit", 100, 100, 170, 120),
                    _line("Count", 600, 100, 670, 120),
                    _line("Apples", 250, 140, 330, 160),
                    _line("12", 750, 140, 780, 160),
                ]
            )
        ]
    )
    assert all(region.role != RegionRole.TABLE for region in TextLayoutDetector()(replace(value, page=page)))


def test_ambiguous_table_remains_reviewable_without_table_label() -> None:
    value = _verse_input()
    hint = _hint(kind="table_candidate")
    result = TextLayoutDetector()(replace(value, layout_hints=(hint,)))
    assert len(result) == 1
    assert result[0].role == RegionRole.PARAGRAPH
    assert "Unresolved table" in " ".join(result[0].evidence["layout_warnings"])


def test_normalized_and_pixel_word_boxes_produce_identical_region() -> None:
    value = _verse_input()
    expected = TextLayoutDetector()(value)[0].box
    for word in value.page.words:
        word.bounding_box = word.bounding_box.normalize(value.page.width, value.page.height)
    assert TextLayoutDetector()(value)[0].box == expected


def _loose_state(root: Path) -> ProjectState:
    state = ProjectState()
    state.set_loaded_project(
        Project(
            project_id="layout",
            project_root=root,
            image_paths=[root / "001.png"],
            ground_truth_map={},
            total_pages=1,
        )
    )
    return state


def test_loose_f2_reads_only_the_selected_page(tmp_path: Path) -> None:
    rounds = tmp_path / "rounds"
    rounds.mkdir()
    (rounds / "F2.json").write_text(
        json.dumps(
            {"001.png": "/*\nRoses are red\n\n  Violets are blue\n*/", "other.png": "/*\nUnrelated page\n*/"}
        )
    )
    state = _loose_state(tmp_path)
    evidence = load_layout_evidence(state, 0)
    assert len(evidence.hints) == 1
    assert evidence.hints[0].source == "f2"
    assert evidence.hints[0].lines[1].stanza_index == evidence.hints[0].lines[0].stanza_index + 1
    assert evidence.hints[0].lines[1].indent_hint == "2 spaces"
    assert not evidence.word_ids


def test_optional_sidecar_rejects_other_pages_and_rejected_groups(tmp_path: Path) -> None:
    edition = tmp_path / "edition"
    edition.mkdir()
    hint = _hint().to_dict()
    (edition / "layout-hints.json").write_text(
        json.dumps(
            {
                "schema": "pdomain.edition-layout-hints",
                "version": 1,
                "groups": [
                    {"page_ids": ["other.png"], "hints": [hint]},
                    {"page_ids": ["001.png"], "accepted": False, "hints": [hint]},
                    {"page_ids": ["001.png", "other.png"], "hints": [hint]},
                ],
            }
        )
    )
    state = _loose_state(tmp_path)
    evidence = load_layout_evidence(state, 0)
    assert len(evidence.hints) == 1
    # A merged candidate still needs a page-specific unique ordered OCR match.
    page = _page([_paragraph([_line("Unrelated text", 100, 100, 300, 120)])])
    result = TextLayoutDetector()(replace(_input(page), layout_hints=evidence.hints))
    assert result == []
    review = review_layout_evidence(state, 0, page)
    assert any("no unique ordered OCR match" in warning for warning in review.warnings)


def test_malformed_optional_evidence_is_visible_and_changes_staleness_digest(tmp_path: Path) -> None:
    state = _loose_state(tmp_path)
    before = layout_evidence_digest(state, 0)
    edition = tmp_path / "edition"
    edition.mkdir()
    (edition / "layout-hints.json").write_text("not json")
    after = load_layout_evidence(state, 0)
    assert after.digest != before
    assert after.warnings
    assert not after.hints


def test_two_hinted_poetry_columns_keep_both_semantic_roles_and_grouping() -> None:
    page = _page(
        [
            _paragraph(
                [
                    _line("Left first", 100, 100, 350, 120),
                    _line("Left second", 100, 140, 360, 160),
                ]
            ),
            _paragraph(
                [
                    _line("Right first", 600, 100, 850, 120),
                    _line("Right second", 600, 140, 860, 160),
                ]
            ),
        ]
    )
    hints = tuple(
        LayoutTextHint(
            kind="poetry",
            source="f2",
            text=f"{side} first {side} second",
            lines=(LayoutTextLine(text=f"{side} first"), LayoutTextLine(text=f"{side} second")),
            source_ref="F2.json",
        )
        for side in ("Left", "Right")
    )
    value = replace(_input(page), layout_hints=hints, layout_word_ids=("a", "b", "c", "d"))
    result = TextLayoutDetector()(value)
    assert len(result) == 2
    assert all(region.role == RegionRole.POETRY for region in result)
    structures = [region.evidence["layout_structure"] for region in result]
    assert [structure["column_index"] for structure in structures] == [0, 1]
    assert structures[0]["column_group_id"] == structures[1]["column_group_id"]
    assert structures[0]["lines"][0]["word_ids"] == ["a"]


def test_mixed_poetry_and_prose_columns_do_not_hide_the_prose_neighbor() -> None:
    page = _page(
        [
            _paragraph(
                [
                    _line("Left first", 100, 100, 350, 120),
                    _line("Left second", 100, 140, 360, 160),
                ]
            ),
            _paragraph(
                [
                    _line("Right first", 600, 100, 850, 120),
                    _line("Right second", 600, 140, 860, 160),
                ]
            ),
        ]
    )
    hint = LayoutTextHint(
        kind="poetry",
        source="f2",
        text="Left first Left second",
        lines=(LayoutTextLine(text="Left first"), LayoutTextLine(text="Left second")),
        source_ref="F2.json",
    )
    value = replace(_input(page), layout_hints=(hint,), layout_word_ids=("a", "b", "c", "d"))
    result = TextLayoutDetector()(value)
    assert [region.role for region in result] == [RegionRole.POETRY, RegionRole.PARAGRAPH]
    assert [region.evidence["layout_structure"]["column_index"] for region in result] == [0, 1]


def test_invalid_geometry_does_not_hide_a_second_textual_occurrence() -> None:
    page = _page(
        [
            _paragraph(
                [
                    _line("Roses are red", 100, 100, 350, 120),
                    _line("Roses are red", 100, 150, 100, 150),
                ]
            )
        ]
    )
    hint = LayoutTextHint(
        kind="poetry",
        source="f2",
        text="Roses are red",
        lines=(LayoutTextLine(text="Roses are red"),),
        source_ref="F2.json",
    )
    assert TextLayoutDetector()(replace(_input(page), layout_hints=(hint,))) == []


def test_invalid_geometry_intervening_text_cannot_be_removed_to_join_a_match() -> None:
    page = _page(
        [
            _paragraph(
                [
                    _line("Roses", 100, 100, 200, 120),
                    _line("unrelated", 100, 125, 100, 125),
                    _line("are red", 100, 150, 250, 170),
                ]
            )
        ]
    )
    hint = LayoutTextHint(
        kind="poetry",
        source="f2",
        text="Roses are red",
        lines=(LayoutTextLine(text="Roses are red"),),
        source_ref="F2.json",
    )
    assert TextLayoutDetector()(replace(_input(page), layout_hints=(hint,))) == []

"""Tests for ``core/jobs/handlers/glyph_sidecar.py`` — glyph-feature sidecar export.

Acceptance (from the sidecar contract):
- A word reviewed with no glyph features present gets an entry with empty/False
  values — distinct from a word nobody has reviewed, which gets no entry at all.
- Every crop id the sidecar emits is byte-identical to a key
  ``Page.generate_doctr_recognition_training_set`` actually wrote to
  ``labels.json`` in the same export run (the join test).
- No sidecar file is written when an export has zero reviewed words.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pdomain_ocr_labeler_spa.core.jobs.handlers.glyph_sidecar import (
    GLYPH_SIDECAR_FILENAME,
    build_glyph_feature_entries,
    recognition_crop_id,
    write_glyph_feature_sidecar,
)

# ---------------------------------------------------------------------------
# Lightweight fakes for the isolated (non-cv2) unit tests
# ---------------------------------------------------------------------------


def _fake_bbox(x1: float, y1: float, x2: float, y2: float) -> SimpleNamespace:
    """Pixel-space bounding-box stand-in — exposes what recognition_crop_id reads."""
    return SimpleNamespace(is_normalized=False, minX=x1, minY=y1, maxX=x2, maxY=y2)


def _fake_word(
    *,
    text: str,
    bbox: SimpleNamespace,
    glyph_annotations: object | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        bounding_box=bbox,
        ground_truth_text=text,
        glyph_annotations=glyph_annotations,
    )


def _fake_page(words: list[SimpleNamespace], *, page_index: int = 0) -> SimpleNamespace:
    return SimpleNamespace(words=words, page_index=page_index)


# ---------------------------------------------------------------------------
# recognition_crop_id
# ---------------------------------------------------------------------------


def test_recognition_crop_id_pixel_space_matches_page_py_formula() -> None:
    word = _fake_word(text="alpha", bbox=_fake_bbox(10, 10, 50, 30), glyph_annotations=None)
    crop_id = recognition_crop_id(word, prefix="proj", page_index=0, img_width=200, img_height=60)
    assert crop_id == "proj_0_10_50_10_30.png"


def test_recognition_crop_id_normalized_scales_before_rounding() -> None:
    from pdomain_book_tools.geometry.bounding_box import BoundingBox

    bbox = BoundingBox.from_ltrb(0.05, 0.1, 0.25, 0.5, is_normalized=True)
    word = _fake_word(text="alpha", bbox=bbox, glyph_annotations=None)
    crop_id = recognition_crop_id(word, prefix="proj", page_index=0, img_width=200, img_height=60)
    # 0.05*200=10, 0.1*60=6, 0.25*200=50, 0.5*60=30 -> ix1_ix2_iy1_iy2
    assert crop_id == "proj_0_10_50_6_30.png"


# ---------------------------------------------------------------------------
# build_glyph_feature_entries — reviewed vs never-reviewed
# ---------------------------------------------------------------------------


def test_unreviewed_word_absent_not_present_with_false() -> None:
    """glyph_annotations=None must be excluded entirely, never defaulted."""
    word = _fake_word(text="alpha", bbox=_fake_bbox(0, 0, 10, 10), glyph_annotations=None)
    entries = build_glyph_feature_entries(
        _fake_page([word]),
        prefix="proj",
        img_width=100,
        img_height=100,
        word_filter=None,
        has_label_formatter=False,
    )
    assert entries == {}


def test_reviewed_empty_word_present_with_false_values() -> None:
    """GlyphAnnotations() (reviewed, nothing present) is a real entry, not absence."""
    from pdomain_book_contracts.ocr.glyph_annotations import GlyphAnnotations

    word = _fake_word(text="beta", bbox=_fake_bbox(0, 0, 10, 10), glyph_annotations=GlyphAnnotations())
    entries = build_glyph_feature_entries(
        _fake_page([word]),
        prefix="proj",
        img_width=100,
        img_height=100,
        word_filter=None,
        has_label_formatter=False,
    )
    assert len(entries) == 1
    (entry,) = entries.values()
    assert entry == {"ligatures": [], "long_s": False, "swash": False}


def test_reviewed_word_with_features_reports_exact_shape() -> None:
    from pdomain_book_contracts.ocr.glyph_annotations import GlyphAnnotations, LigatureKind, LigatureMark

    annotations = GlyphAnnotations(
        ligatures=[LigatureMark(kind=LigatureKind.FI), LigatureMark(kind=LigatureKind.LONG_ST)],
        long_s_positions=[1],
        swash=True,
    )
    word = _fake_word(text="gamma", bbox=_fake_bbox(0, 0, 10, 10), glyph_annotations=annotations)
    entries = build_glyph_feature_entries(
        _fake_page([word]),
        prefix="proj",
        img_width=100,
        img_height=100,
        word_filter=None,
        has_label_formatter=False,
    )
    (entry,) = entries.values()
    assert entry == {"ligatures": ["FI", "LONG_ST"], "long_s": True, "swash": True}


def test_reviewed_word_without_ground_truth_text_excluded_like_recognition_export() -> None:
    """A word generate_doctr_recognition_training_set would skip must not appear here either."""
    from pdomain_book_contracts.ocr.glyph_annotations import GlyphAnnotations

    word = _fake_word(text="", bbox=_fake_bbox(0, 0, 10, 10), glyph_annotations=GlyphAnnotations())
    entries = build_glyph_feature_entries(
        _fake_page([word]),
        prefix="proj",
        img_width=100,
        img_height=100,
        word_filter=None,
        has_label_formatter=False,
    )
    assert entries == {}


def test_classification_mode_includes_words_without_ground_truth_text() -> None:
    """When label_formatter is set, recognition export skips the GT-text gate — mirror it."""
    from pdomain_book_contracts.ocr.glyph_annotations import GlyphAnnotations

    word = _fake_word(text="", bbox=_fake_bbox(0, 0, 10, 10), glyph_annotations=GlyphAnnotations())
    entries = build_glyph_feature_entries(
        _fake_page([word]),
        prefix="proj",
        img_width=100,
        img_height=100,
        word_filter=None,
        has_label_formatter=True,
    )
    assert len(entries) == 1


def test_word_filter_excludes_non_matching_words() -> None:
    from pdomain_book_contracts.ocr.glyph_annotations import GlyphAnnotations

    kept = _fake_word(text="alpha", bbox=_fake_bbox(0, 0, 10, 10), glyph_annotations=GlyphAnnotations())
    kept.marker = "keep"
    dropped = _fake_word(text="beta", bbox=_fake_bbox(20, 0, 30, 10), glyph_annotations=GlyphAnnotations())
    dropped.marker = "drop"

    def word_filter(w: SimpleNamespace) -> bool:
        return bool(w.marker == "keep")

    entries = build_glyph_feature_entries(
        _fake_page([kept, dropped]),
        prefix="proj",
        img_width=100,
        img_height=100,
        word_filter=word_filter,
        has_label_formatter=False,
    )
    assert len(entries) == 1
    assert "proj_0_0_10_0_10.png" in entries


# ---------------------------------------------------------------------------
# write_glyph_feature_sidecar — merge / empty-file semantics
# ---------------------------------------------------------------------------


def test_write_creates_sidecar_with_exact_shape(tmp_path: Path) -> None:
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    write_glyph_feature_sidecar(
        recognition_dir,
        prefix="proj",
        page_index=0,
        new_entries={"proj_0_0_10_0_10.png": {"ligatures": ["FI"], "long_s": False, "swash": True}},
    )
    sidecar_path = recognition_dir / GLYPH_SIDECAR_FILENAME
    assert sidecar_path.exists()
    data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert data == {"proj_0_0_10_0_10.png": {"ligatures": ["FI"], "long_s": False, "swash": True}}


def test_write_no_entries_does_not_create_file(tmp_path: Path) -> None:
    """An export with zero reviewed words must not create an (empty) sidecar file."""
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    write_glyph_feature_sidecar(recognition_dir, prefix="proj", page_index=0, new_entries={})
    assert not (recognition_dir / GLYPH_SIDECAR_FILENAME).exists()


def test_write_merges_across_pages_preserving_other_prefixes(tmp_path: Path) -> None:
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    write_glyph_feature_sidecar(
        recognition_dir,
        prefix="proj",
        page_index=0,
        new_entries={"proj_0_0_10_0_10.png": {"ligatures": [], "long_s": False, "swash": False}},
    )
    write_glyph_feature_sidecar(
        recognition_dir,
        prefix="proj",
        page_index=1,
        new_entries={"proj_1_0_10_0_10.png": {"ligatures": [], "long_s": True, "swash": False}},
    )
    data = json.loads((recognition_dir / GLYPH_SIDECAR_FILENAME).read_text(encoding="utf-8"))
    assert set(data) == {"proj_0_0_10_0_10.png", "proj_1_0_10_0_10.png"}


def test_write_re_export_replaces_only_same_page_entries(tmp_path: Path) -> None:
    """Re-exporting page 0 must not disturb page 1's entries, and must drop page 0's stale ones."""
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    write_glyph_feature_sidecar(
        recognition_dir,
        prefix="proj",
        page_index=0,
        new_entries={"proj_0_0_10_0_10.png": {"ligatures": [], "long_s": False, "swash": False}},
    )
    write_glyph_feature_sidecar(
        recognition_dir,
        prefix="proj",
        page_index=1,
        new_entries={"proj_1_0_10_0_10.png": {"ligatures": [], "long_s": False, "swash": False}},
    )
    # Re-export page 0 with a different word (bbox moved) and different content.
    write_glyph_feature_sidecar(
        recognition_dir,
        prefix="proj",
        page_index=0,
        new_entries={"proj_0_5_15_5_15.png": {"ligatures": ["FI"], "long_s": False, "swash": False}},
    )
    data = json.loads((recognition_dir / GLYPH_SIDECAR_FILENAME).read_text(encoding="utf-8"))
    assert set(data) == {"proj_0_5_15_5_15.png", "proj_1_0_10_0_10.png"}


def test_write_shrinking_to_empty_removes_the_file(tmp_path: Path) -> None:
    """Re-exporting the only reviewed page with zero reviewed words removes a stale sidecar."""
    recognition_dir = tmp_path / "recognition"
    recognition_dir.mkdir()
    write_glyph_feature_sidecar(
        recognition_dir,
        prefix="proj",
        page_index=0,
        new_entries={"proj_0_0_10_0_10.png": {"ligatures": [], "long_s": False, "swash": False}},
    )
    assert (recognition_dir / GLYPH_SIDECAR_FILENAME).exists()

    write_glyph_feature_sidecar(recognition_dir, prefix="proj", page_index=0, new_entries={})
    assert not (recognition_dir / GLYPH_SIDECAR_FILENAME).exists()


# ---------------------------------------------------------------------------
# Real end-to-end join test — real Page/Word/BoundingBox, real cv2 image,
# real _export_page call. This is the test that would catch a broken join.
# ---------------------------------------------------------------------------


def _build_real_page(words: list, *, page_index: int):
    from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
    from pdomain_book_tools.ocr.page import Page

    block = Block(words, child_type=BlockChildType.WORDS, block_category=BlockCategory.LINE)
    return Page(width=200, height=60, page_index=page_index, blocks=[block])


def _write_real_image(path: Path) -> None:
    import cv2
    import numpy as np

    image = np.full((60, 200, 3), 255, dtype="uint8")
    cv2.imwrite(str(path), image)


@pytest.fixture
def _real_glyph_export_deps():
    """Skip the real-dependency tests when cv2/pdomain_book_tools are unavailable."""
    pytest.importorskip("cv2")
    pytest.importorskip("pdomain_book_tools")


@pytest.mark.usefixtures("_real_glyph_export_deps")
def test_join_sidecar_keys_are_subset_of_labels_json_keys(tmp_path: Path) -> None:
    """The join test: every sidecar crop id must be a real labels.json key."""
    from pdomain_book_contracts.ocr.glyph_annotations import GlyphAnnotations, LigatureKind, LigatureMark
    from pdomain_book_tools.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.word import Word

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import _export_page

    word_unreviewed = Word(
        "alpha", BoundingBox.from_ltrb(10, 10, 50, 30, is_normalized=False), 0.9, ground_truth_text="alpha"
    )
    # glyph_annotations left at its default None — nobody reviewed this word.

    word_reviewed_empty = Word(
        "beta", BoundingBox.from_ltrb(60, 10, 100, 30, is_normalized=False), 0.9, ground_truth_text="beta"
    )
    word_reviewed_empty.glyph_annotations = GlyphAnnotations()

    word_reviewed_features = Word(
        "gamma", BoundingBox.from_ltrb(110, 10, 150, 30, is_normalized=False), 0.9, ground_truth_text="gamma"
    )
    word_reviewed_features.glyph_annotations = GlyphAnnotations(
        ligatures=[LigatureMark(kind=LigatureKind.FI), LigatureMark(kind=LigatureKind.LONG_ST)],
        long_s_positions=[1],
        swash=True,
    )

    page = _build_real_page([word_unreviewed, word_reviewed_empty, word_reviewed_features], page_index=0)

    image_path = tmp_path / "src.png"
    _write_real_image(image_path)
    output_dir = tmp_path / "out"

    _export_page(
        page,
        image_path,
        output_dir,
        word_filter=None,
        detection=False,
        recognition=True,
        classification=False,
        prefix="proj",
    )

    labels = json.loads((output_dir / "recognition" / "labels.json").read_text(encoding="utf-8"))
    sidecar = json.loads((output_dir / "recognition" / GLYPH_SIDECAR_FILENAME).read_text(encoding="utf-8"))

    # All three words were recognition-exported (all have ground_truth_text).
    assert len(labels) == 3
    # The join: every sidecar key is a real labels.json key.
    assert set(sidecar) <= set(labels)
    # Exactly the two reviewed words are in the sidecar — the unreviewed one is not.
    assert len(sidecar) == 2

    unreviewed_crop_id = "proj_0_10_50_10_30.png"
    reviewed_empty_crop_id = "proj_0_60_100_10_30.png"
    reviewed_features_crop_id = "proj_0_110_150_10_30.png"

    assert unreviewed_crop_id in labels
    assert unreviewed_crop_id not in sidecar

    assert sidecar[reviewed_empty_crop_id] == {"ligatures": [], "long_s": False, "swash": False}
    assert sidecar[reviewed_features_crop_id] == {
        "ligatures": ["FI", "LONG_ST"],
        "long_s": True,
        "swash": True,
    }


@pytest.mark.usefixtures("_real_glyph_export_deps")
def test_join_no_reviewed_words_writes_no_sidecar_file(tmp_path: Path) -> None:
    from pdomain_book_tools.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.word import Word

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import _export_page

    word = Word(
        "alpha", BoundingBox.from_ltrb(10, 10, 50, 30, is_normalized=False), 0.9, ground_truth_text="alpha"
    )
    page = _build_real_page([word], page_index=0)

    image_path = tmp_path / "src.png"
    _write_real_image(image_path)
    output_dir = tmp_path / "out"

    _export_page(
        page,
        image_path,
        output_dir,
        word_filter=None,
        detection=False,
        recognition=True,
        classification=False,
        prefix="proj",
    )

    assert (output_dir / "recognition" / "labels.json").exists()
    assert not (output_dir / "recognition" / GLYPH_SIDECAR_FILENAME).exists()


@pytest.mark.usefixtures("_real_glyph_export_deps")
def test_join_accumulates_across_pages_in_one_export_run(tmp_path: Path) -> None:
    """Two pages exported to the same output_dir accumulate sidecar entries, like labels.json does."""
    from pdomain_book_contracts.ocr.glyph_annotations import GlyphAnnotations
    from pdomain_book_tools.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.word import Word

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import _export_page

    image_path = tmp_path / "src.png"
    _write_real_image(image_path)
    output_dir = tmp_path / "out"

    for page_index in (0, 1):
        word = Word(
            "alpha",
            BoundingBox.from_ltrb(10, 10, 50, 30, is_normalized=False),
            0.9,
            ground_truth_text="alpha",
        )
        word.glyph_annotations = GlyphAnnotations()
        page = _build_real_page([word], page_index=page_index)
        _export_page(
            page,
            image_path,
            output_dir,
            word_filter=None,
            detection=False,
            recognition=True,
            classification=False,
            prefix="proj",
        )

    labels = json.loads((output_dir / "recognition" / "labels.json").read_text(encoding="utf-8"))
    sidecar = json.loads((output_dir / "recognition" / GLYPH_SIDECAR_FILENAME).read_text(encoding="utf-8"))
    assert len(labels) == 2
    assert set(sidecar) <= set(labels)
    assert len(sidecar) == 2

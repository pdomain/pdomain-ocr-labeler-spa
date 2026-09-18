"""Glyph-feature JSON sidecar writer for the DocTR recognition export.

Downstream, ``pdomain-ocr-training`` can slice recognition eval metrics (CER/WER)
by glyph features (ligatures, long-s, swash) — but only when handed a JSON
sidecar: ``dict[crop_id, {"ligatures": [str], "long_s": bool, "swash": bool}]``.
See ``pdomain_ocr_training.protocols.GlyphFeatureSet`` and
``pdomain_ocr_training._eval_backend``'s "Crop-id threading (issue #8)" /
"Per-feature glyph slicing (issue #9)" sections for the contract this module
matches by hand — this repo does not import ``pdomain-ocr-training``.

The export is the only place both facts exist at the same moment: the human's
glyph annotations for a word, and the recognition crop filename that word
becomes. ``handle_export`` (``export.py``) is the caller; this module owns the
crop-id math and the merge-write, kept separate so both are independently
testable against a real ``Page.generate_doctr_recognition_training_set`` run.

Crop-id contract
-----------------
A recognition crop id is the DocTR recognition val-set label key: the exact
key ``Page.generate_doctr_recognition_training_set`` writes into
``recognition/labels.json`` for that word — ``f"{prefix}_{page_index}_{ix1}_
{ix2}_{iy1}_{iy2}.png"``, where ``(ix1, iy1, ix2, iy2)`` come from
``pdomain_book_tools.geometry.image_ops.pixel_roi_bounds`` applied to the
word's (possibly GT) bounding box, scaled to pixel space first when
normalized. ``recognition_crop_id`` below reproduces that formula exactly, so
it must be called with the SAME prefix, page index, image dimensions, and
(GT-first-prepared) bounding box state the recognition export call used for
the same word — see ``_write_page_glyph_sidecar`` in ``export.py``.

Reviewed vs. never-reviewed
----------------------------
``Word.glyph_annotations is None`` means "nobody has looked at this word yet"
(pdomain_book_contracts.ocr.glyph_annotations module docstring). Only words
with ``glyph_annotations is not None`` get a sidecar entry — a crop absent
from the sidecar is "unknown" to the trainer, per
``_emit_glyph_slices``'s exclusion semantics. Emitting a
``{"ligatures": [], "long_s": False, "swash": False}`` entry for an
unreviewed word would assert an absence nobody checked, so that word is
skipped entirely rather than defaulted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable

# Sits next to labels.json in the same recognition/ directory it joins
# against — the crop ids used as keys here are exactly the keys DocTR's
# recognition dataset loader reads from labels.json.
GLYPH_SIDECAR_FILENAME = "glyph_features.json"


class GlyphFeatureEntry(TypedDict):
    """One crop's glyph-feature presence facts.

    Wire-shape twin of ``pdomain_ocr_training.protocols.GlyphFeatureSet``,
    reproduced by hand (this repo does not import that package).
    """

    ligatures: list[str]
    long_s: bool
    swash: bool


def recognition_crop_id(
    word: Any,
    *,
    prefix: str,
    page_index: int,
    img_width: int,
    img_height: int,
) -> str:
    """Reproduce the crop filename ``generate_doctr_recognition_training_set`` writes for *word*.

    Mirrors ``pdomain_book_tools.ocr.page.Page.generate_doctr_recognition_
    training_set`` exactly: same normalized/pixel-space branch on
    ``word.bounding_box.is_normalized``, same ``pixel_roi_bounds`` clamp, same
    ``f"{prefix}_{page_index}_{ix1}_{ix2}_{iy1}_{iy2}.png"`` template. Import
    of ``pdomain_book_tools`` is deferred so this module stays importable in
    test environments that stub it (matches ``export.py``'s convention).
    """
    from pdomain_book_tools.geometry.image_ops import pixel_roi_bounds

    bbox = word.bounding_box
    if bbox.is_normalized:
        bbox = bbox.scale(width=img_width, height=img_height)
    ix1, iy1, ix2, iy2 = pixel_roi_bounds(
        bbox.minX, bbox.minY, bbox.maxX, bbox.maxY, img_w=img_width, img_h=img_height
    )
    return f"{prefix}_{page_index}_{ix1}_{ix2}_{iy1}_{iy2}.png"


def build_glyph_feature_entries(
    page: Any,
    *,
    prefix: str,
    img_width: int,
    img_height: int,
    word_filter: Callable[[Any], bool] | None,
    has_label_formatter: bool,
) -> dict[str, GlyphFeatureEntry]:
    """Build sidecar entries for one page's recognition export.

    Applies the SAME word-inclusion rule ``generate_doctr_recognition_
    training_set`` applies (same ``word_filter``; when no ``label_formatter``
    is set, words without ``ground_truth_text`` are skipped exactly as that
    method skips them) so every crop id produced here is a crop id that call
    actually wrote to ``labels.json`` — never a superset.

    A word is included only when ``word.glyph_annotations is not None``:
    that is the one signal that distinguishes "reviewed; nothing present"
    from "never reviewed" (see module docstring).
    """
    words = page.words
    if word_filter is not None:
        words = [w for w in words if word_filter(w)]

    entries: dict[str, GlyphFeatureEntry] = {}
    for word in words:
        annotations = word.glyph_annotations
        if annotations is None:
            continue
        if not has_label_formatter and not word.ground_truth_text:
            # Same skip generate_doctr_recognition_training_set applies —
            # this word never became a labels.json entry at all.
            continue

        crop_id = recognition_crop_id(
            word,
            prefix=prefix,
            page_index=page.page_index,
            img_width=img_width,
            img_height=img_height,
        )
        entries[crop_id] = {
            "ligatures": [mark.kind.value for mark in annotations.ligatures],
            "long_s": bool(annotations.long_s_positions),
            "swash": annotations.swash,
        }
    return entries


def _load_existing_entries(sidecar_path: Path) -> dict[str, object]:
    """Read back a previously-written sidecar; ``{}`` when absent or malformed."""
    try:
        raw_text = sidecar_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    raw: object = json.loads(raw_text)
    if not isinstance(raw, dict):
        return {}
    return dict(raw)


def write_glyph_feature_sidecar(
    recognition_dir: Path,
    *,
    prefix: str,
    page_index: int,
    new_entries: dict[str, GlyphFeatureEntry],
) -> None:
    """Merge-update ``<recognition_dir>/glyph_features.json`` for one page's export.

    Mirrors the ``labels.json`` merge semantics in
    ``generate_doctr_recognition_training_set``: entries whose crop id was
    produced by this ``prefix``+``page_index`` are replaced; entries from
    other pages/prefixes are preserved (so a multi-page, multi-style export
    accumulates correctly).

    When the merged result is empty — this page contributed nothing and
    nothing else did either — the sidecar file is removed rather than left
    as an empty ``{}``. An empty sidecar file is worse than none: a reader
    that sees the file present but sees no entry for a crop would (per the
    trainer's exclusion semantics) still treat that crop as "unknown", so
    an empty file adds nothing but is easy to mistake for "reviewed; nothing
    present" for every crop.
    """
    sidecar_path = recognition_dir / GLYPH_SIDECAR_FILENAME
    existing = _load_existing_entries(sidecar_path)
    page_prefix = f"{prefix}_{page_index}_"
    merged: dict[str, object] = {
        crop_id: entry for crop_id, entry in existing.items() if not crop_id.startswith(page_prefix)
    }
    merged.update(new_entries)

    if merged:
        sidecar_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=4, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif sidecar_path.exists():
        sidecar_path.unlink()


__all__ = [
    "GLYPH_SIDECAR_FILENAME",
    "GlyphFeatureEntry",
    "build_glyph_feature_entries",
    "recognition_crop_id",
    "write_glyph_feature_sidecar",
]

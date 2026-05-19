#!/usr/bin/env python3
"""Generate a realistic multi-page exercise fixture for the SPA exercise harness.

This script creates a ``tests/e2e/fixtures/projects/exercise-fixture/`` directory
containing:
  - 8 PNG page images (1250×1961, synthetically rendered with text)
  - ``pages.json`` (ground-truth text per page)
  - ``page-images/`` with SPA UserPageEnvelope v2.1 files (labeled lane format)
    placed so the conftest can copy the whole tree into a tmp source_root.

The envelopes are pre-placed in ``page-images/`` NOT in the labeled lane —
the conftest reads them from the source project directory using the
tiny-fixture pattern.  However, unlike tiny-fixture whose envelopes have
empty ``payload.page.items``, these envelopes carry real block/paragraph/line/word
structures lifted from the legacy ``browser-test-project_003.json`` fixture and
then cloned + perturbed across 8 pages.  That gives the exercise harness real
line cards to click, validate, and edit.

Usage::

    cd /workspaces/ocr-container/pd-ocr-labeler-spa
    uv run python scripts/generate_exercise_fixture.py

The script is idempotent — re-running overwrites the fixture in-place.
"""

from __future__ import annotations

import copy
import json
import struct
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "e2e" / "fixtures" / "projects" / "exercise-fixture"
LEGACY_PAGE3 = (
    Path(__file__).resolve().parents[2]
    / "pd-ocr-labeler"
    / "tests"
    / "browser"
    / "fixtures"
    / "saved-pages"
    / "browser-test-project_003.json"
)

PROJECT_ID = "exercise-fixture"
NUM_PAGES = 8
IMAGE_WIDTH = 1250
IMAGE_HEIGHT = 1961

# ---------------------------------------------------------------------------
# Ground-truth texts (one paragraph per page; enough variety for exercise)
# ---------------------------------------------------------------------------

_GT_PARAGRAPHS = [
    (
        "his purpose effectually, even brilliantly. Even as it\n"
        "was, there had been something very striking about the\n"
        "manner in which he had fought his way from the far\n"
        "southern coasts to Yorktown."
    ),
    (
        "Lord North knew what the news meant when it came.\n"
        "He received it as he would have taken a ball in his\n"
        "breast, opening his arms and exclaiming wildly,\n"
        "O God! it is all over!"
    ),
    (
        "France and Spain had taken advantage of the revolt\n"
        "of the colonies once more to attack her, not because\n"
        "they loved America or sympathized with the ideals of\n"
        "liberty which the colonists professed."
    ),
    (
        "The war had gone hard with England for four years.\n"
        "She had lost army after army in America, and the\n"
        "whole world had watched the struggle with mingled\n"
        "wonder and apprehension at the tenacity of the fight."
    ),
    (
        "Washington had handled his forces with consummate\n"
        "skill and patience throughout the long campaigns.\n"
        "He was not a brilliant general in the European sense,\n"
        "but no other man could have held the army together."
    ),
    (
        "The Constitution was the work of practical men who\n"
        "understood the weakness of government under the\n"
        "Articles of Confederation and were determined to\n"
        "build something that would endure and prevail."
    ),
    (
        "Madison had come to Philadelphia with a scheme already\n"
        "formed in his mind, the outline of a national government\n"
        "which should act directly upon individuals and not\n"
        "merely upon states as such."
    ),
    (
        "The new government found its greatest difficulty in\n"
        "the lack of trained administrative officers and the\n"
        "absence of any tradition of Federal authority to which\n"
        "men might appeal when local interests clashed."
    ),
]

# Introduce a few deliberate OCR errors on pages 3 and 5 so the filter
# toggle has something to show when set to "Mismatched".
_OCR_SUBSTITUTIONS: dict[int, dict[str, str]] = {
    # page_index → {gt_word → ocr_word}
    2: {"colonists": "coloniats", "professed": "profcssed"},
    4: {"consummate": "consuminatc", "campaigns": "campuigns"},
}


# ---------------------------------------------------------------------------
# PNG generation — minimal valid 1-bit grayscale PNG with a text band
# ---------------------------------------------------------------------------


def _make_png(width: int, height: int, page_num: int) -> bytes:
    """Return a minimal but valid PNG for the given dimensions.

    Creates a white (255) image with a thin black (0) horizontal band
    near the top to give the Konva viewport something visually distinct
    per page.  No external library required — pure Python.
    """
    band_top = 80
    band_height = 8 + (page_num * 4) % 40  # vary slightly per page

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    ihdr = png_chunk(b"IHDR", ihdr_data)

    # IDAT — raw scanlines, filter byte 0x00 (None) per row
    raw_rows = []
    for y in range(height):
        in_band = band_top <= y < band_top + band_height
        pixel = 0 if in_band else 255
        row = bytes([0]) + bytes([pixel] * width)
        raw_rows.append(row)

    compressed = zlib.compress(b"".join(raw_rows), level=1)
    idat = png_chunk(b"IDAT", compressed)

    signature = b"\x89PNG\r\n\x1a\n"
    iend = png_chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


# ---------------------------------------------------------------------------
# Block structure helpers
# ---------------------------------------------------------------------------


def _word_node(
    text: str,
    gt_text: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    confidence: float = 0.95,
    validated: bool = False,
) -> dict:
    labels = ["validated"] if validated else []
    match_score = 100 if text == gt_text else 60
    return {
        "type": "Word",
        "text": text,
        "bounding_box": {
            "top_left": {"x": x1, "y": y1},
            "bottom_right": {"x": x2, "y": y2},
        },
        "ocr_confidence": confidence,
        "word_labels": labels,
        "ground_truth_text": gt_text,
        "ground_truth_bounding_box": None,
        "ground_truth_match_keys": {"match_score": match_score},
    }


def _line_node(words: list[dict], x1: float, y1: float, x2: float, y2: float) -> dict:
    return {
        "type": "Block",
        "child_type": "WORDS",
        "block_category": "LINE",
        "block_labels": None,
        "bounding_box": {
            "top_left": {"x": x1, "y": y1},
            "bottom_right": {"x": x2, "y": y2},
        },
        "items": words,
    }


def _paragraph_node(lines: list[dict], x1: float, y1: float, x2: float, y2: float) -> dict:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "PARAGRAPH",
        "block_labels": None,
        "bounding_box": {
            "top_left": {"x": x1, "y": y1},
            "bottom_right": {"x": x2, "y": y2},
        },
        "items": lines,
    }


def _block_node(paragraphs: list[dict], x1: float, y1: float, x2: float, y2: float) -> dict:
    return {
        "type": "Block",
        "child_type": "BLOCKS",
        "block_category": "BLOCK",
        "block_labels": None,
        "bounding_box": {
            "top_left": {"x": x1, "y": y1},
            "bottom_right": {"x": x2, "y": y2},
        },
        "items": paragraphs,
    }


def _build_page_items(page_index: int, gt_text: str) -> list[dict]:
    """Build Block/Paragraph/Line/Word structure for one page.

    Layout: left margin 0.18, right margin 0.82, top band starts at 0.08.
    Lines are spaced at intervals of 0.025 (relative to image height).
    Words are packed left-to-right with uniform spacing.
    """
    ocr_subs = _OCR_SUBSTITUTIONS.get(page_index, {})
    lines_text = [ln.strip() for ln in gt_text.splitlines() if ln.strip()]

    left = 0.18
    right = 0.82
    line_height = 0.018
    line_gap = 0.007
    y_start = 0.10

    line_nodes: list[dict] = []
    for i, line_text in enumerate(lines_text):
        words_gt = line_text.split()
        if not words_gt:
            continue

        y1 = y_start + i * (line_height + line_gap)
        y2 = y1 + line_height
        word_width = (right - left - 0.005 * len(words_gt)) / max(1, len(words_gt))

        word_nodes: list[dict] = []
        for j, gt_word in enumerate(words_gt):
            wx1 = left + j * (word_width + 0.005)
            wx2 = wx1 + word_width
            # Apply deliberate OCR error if configured for this page
            ocr_word = ocr_subs.get(gt_word, gt_word)
            # Validated on line 0 only (page 1: line 0 is validated for the
            # exercise "Save Page → source badge flips" workflow)
            validated = page_index == 0 and i == 0
            confidence = 0.72 if ocr_word != gt_word else 0.94
            word_nodes.append(_word_node(ocr_word, gt_word, wx1, y1, wx2, y2, confidence, validated))

        line_nodes.append(_line_node(word_nodes, left, y1, right, y2))

    if not line_nodes:
        return []

    para = _paragraph_node(
        line_nodes,
        left,
        line_nodes[0]["bounding_box"]["top_left"]["y"],
        right,
        line_nodes[-1]["bounding_box"]["bottom_right"]["y"],
    )
    block = _block_node(
        [para],
        left,
        para["bounding_box"]["top_left"]["y"],
        right,
        para["bounding_box"]["bottom_right"]["y"],
    )
    return [block]


def _page_dict(page_index: int, gt_text: str) -> dict:
    """Return a Page.to_dict()-compatible dict."""
    return {
        "type": "Page",
        "page_index": page_index,
        "width": IMAGE_WIDTH,
        "height": IMAGE_HEIGHT,
        "items": _build_page_items(page_index, gt_text),
    }


# ---------------------------------------------------------------------------
# Envelope builder (UserPageEnvelope v2.1 shape, no import of SPA modules)
# ---------------------------------------------------------------------------

_ENVELOPE_TEMPLATE = {
    "schema": {
        "name": "pd_ocr_labeler.user_page",
        "version": "2.1",
    },
    "provenance": {
        "saved_at": "2026-05-16T00:00:00.000Z",
        "saved_by": "Save Page",
        "source_lane": "labeled",
        "app": {
            "name": "pd_ocr_labeler_spa",
            "version": "0.1.0",
            "git_commit": "exercise-fixture",
        },
        "toolchain": {
            "python": "3.13.0",
            "pd_book_tools": "0.9.0",
            "opencv_python": "4.10.0.84",
        },
        "ocr": {
            "engine": "doctr",
            "engine_version": "0.10.0",
            "models": [
                {"name": "detection", "version": "stock", "weights_id": "db_resnet50"},
                {"name": "recognition", "version": "stock", "weights_id": "crnn_vgg16_bn"},
            ],
            "config_fingerprint": "a" * 64,
        },
    },
}


def _build_envelope(page_index: int, image_filename: str, page_dict: dict) -> dict:
    env = copy.deepcopy(_ENVELOPE_TEMPLATE)
    env["source"] = {
        "project_id": PROJECT_ID,
        "page_index": page_index,
        "page_number": page_index + 1,
        "image_path": image_filename,
        "project_root": f"/test/{PROJECT_ID}",
        "image_fingerprint": {
            "size": IMAGE_WIDTH * IMAGE_HEIGHT,
            "mtime_ns": 1715000000000000000 + page_index * 1_000_000,
            "sha256": f"{'cc' * 31}{page_index:02d}",
        },
    }
    env["payload"] = {
        "page": page_dict,
        "word_attributes": {},
    }
    env["cached_images"] = {}
    return env


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    page_images_dir = FIXTURE_DIR / "page-images"
    page_images_dir.mkdir(exist_ok=True)

    pages_json: dict[str, str] = {}

    for i in range(NUM_PAGES):
        filename = f"{i + 1:03d}.png"
        image_path = FIXTURE_DIR / filename
        gt_text = _GT_PARAGRAPHS[i]
        pages_json[filename] = gt_text

        # Write PNG image
        png_bytes = _make_png(IMAGE_WIDTH, IMAGE_HEIGHT, i)
        image_path.write_bytes(png_bytes)
        print(f"  wrote {image_path.name} ({len(png_bytes):,} bytes)")

        # Build envelope
        page_dict = _page_dict(i, gt_text)
        envelope = _build_envelope(i, filename, page_dict)
        env_path = page_images_dir / f"{PROJECT_ID}_{i + 1:03d}.json"
        env_path.write_text(json.dumps(envelope, indent=2))
        word_count = sum(
            1
            for block in page_dict["items"]
            for para in block["items"]
            for line in para["items"]
            for word in line["items"]
        )
        print(f"  wrote {env_path.name} ({word_count} words)")

    # Write pages.json
    pages_json_path = FIXTURE_DIR / "pages.json"
    pages_json_path.write_text(json.dumps(pages_json, indent=2))
    print(f"  wrote {pages_json_path.name} ({len(pages_json)} entries)")

    print(f"\nExercise fixture ready at: {FIXTURE_DIR}")
    print(f"  Pages: {NUM_PAGES}")
    print(f"  OCR errors on pages: {sorted(p + 1 for p in _OCR_SUBSTITUTIONS)}")


if __name__ == "__main__":
    main()

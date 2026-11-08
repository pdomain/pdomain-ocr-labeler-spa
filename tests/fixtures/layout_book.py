"""Prepared bundle plus caller-owned OCR used by layout review proofs."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from pdomain_book_contracts.typography import (
    GRAPHEME_SEGMENTATION_VERSION,
    REVIEW_CONTRACT_VERSION,
    ArtifactReference,
    Evidence,
    LabelingBundle,
    LabelState,
    TypographyTaxonomy,
    TypographyTaxonomyLabel,
    WordTypography,
)
from pdomain_book_tools.ocr.page import Page
from PIL import Image


def write_layout_bundle(root: Path) -> tuple[LabelingBundle, Page]:
    """Create isolated verse artifacts and matching pixel OCR, without corpus I/O."""
    root.mkdir(parents=True)
    (root / ".nobackup").touch()
    artifacts = root / "artifacts"
    artifacts.mkdir()
    image_io = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(image_io, format="PNG")
    image_bytes = image_io.getvalue()
    _ = (artifacts / "image.png").write_bytes(image_bytes)
    lines = ("First gentle verse", "Second quiet line", "Third lovely stanza", "Fourth final song")
    page_data: dict[str, object] = {
        "width": 400,
        "height": 300,
        "page_index": 0,
        "items": [
            {
                "type": "Block",
                "child_type": "WORDS",
                "block_category": "LINE",
                "items": [
                    {
                        "type": "Word",
                        "text": text,
                        "ground_truth_text": text,
                        "bounding_box": {
                            "top_left": {"x": 20 + index * 90, "y": 40 + line_index * 40},
                            "bottom_right": {"x": 90 + index * 90, "y": 60 + line_index * 40},
                            "is_normalized": False,
                        },
                    }
                    for index, text in enumerate(line.split())
                ],
            }
            for line_index, line in enumerate(lines)
        ],
    }
    page_data["items"] = [
        {
            "type": "Block",
            "child_type": "BLOCKS",
            "block_category": "BLOCK",
            "items": [
                {
                    "type": "Block",
                    "child_type": "BLOCKS",
                    "block_category": "PARAGRAPH",
                    "items": page_data["items"],
                }
            ],
        }
    ]
    page = Page.from_dict(page_data)
    page_bytes = json.dumps(page_data).encode()
    _ = (artifacts / "page.json").write_bytes(page_bytes)
    f2_bytes = json.dumps(
        {"image.png": "/*\n" + "\n".join(lines[:2]) + "\n\n" + "\n".join(lines[2:]) + "\n*/"}
    ).encode()
    _ = (artifacts / "F2.json").write_bytes(f2_bytes)

    def sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    page_sha = sha(page_bytes)
    image_sha = sha(image_bytes)
    page_id = "pgdp:layout-proof:image"
    taxonomy = TypographyTaxonomy(
        version="layout-proof-v1",
        labels=(
            TypographyTaxonomyLabel(
                value="italic", display_name="Italic", required_for_completion=True, trainable=True
            ),
        ),
    )
    page_head = (
        json.dumps(
            {
                "configuration_hash": "c" * 64,
                "image_sha256": image_sha,
                "page_id": page_id,
                "page_sha256": page_sha,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    bundle = LabelingBundle(
        schema_version=REVIEW_CONTRACT_VERSION,
        configuration_hash="c" * 64,
        taxonomy=taxonomy,
        page_id=page_id,
        page_sha256=page_sha,
        image_sha256=image_sha,
        text_sha256=sha(" ".join(lines).encode()),
        page_head_sha256=sha(page_head),
        artifacts=(
            ArtifactReference(
                artifact_id="image", relative_path="image.png", sha256=image_sha, media_type="image/png"
            ),
            ArtifactReference(
                artifact_id="page", relative_path="page.json", sha256=page_sha, media_type="application/json"
            ),
            ArtifactReference(
                artifact_id="f2", relative_path="F2.json", sha256=sha(f2_bytes), media_type="application/json"
            ),
        ),
        evidence=(
            Evidence(
                evidence_id="f2-evidence",
                artifact_id="f2",
                artifact_sha256=sha(f2_bytes),
                byte_start=0,
                byte_end=1,
            ),
        ),
        words=tuple(
            WordTypography(
                word_id=f"7ca20136-634e-5282-a071-{index:012d}",
                text=word.text,
                text_sha256=sha(word.text.encode()),
                page_content_sha256=page_sha,
                image_artifact_sha256=image_sha,
                grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
                taxonomy_version=taxonomy.version,
                taxonomy_hash=taxonomy.taxonomy_hash,
                label_states={"italic": LabelState.UNKNOWN},
                source_evidence_ids=("f2-evidence",),
            )
            for index, word in enumerate(page.words)
        ),
    )
    _ = (root / "labeling-bundle.json").write_text(bundle.model_dump_json(indent=2))
    return bundle, page

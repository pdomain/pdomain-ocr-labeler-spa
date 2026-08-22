from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from pdomain_book_tools.typography import (
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

from pdomain_ocr_labeler_spa.core.persistence.labeling_bundle import (
    load_labeling_bundle_directory,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_bundle(root: Path, *, artifact_path: Path | None = None) -> LabelingBundle:
    root.mkdir()
    artifacts = root / "artifacts"
    artifacts.mkdir()
    image = artifacts / "page.png" if artifact_path is None else artifact_path
    if artifact_path is None:
        image.write_bytes(b"png")
    page_payload = b"page-record"
    (artifacts / "page-record.json").write_bytes(page_payload)
    page_sha = _sha(page_payload)
    page_head_payload = (
        json.dumps(
            {
                "configuration_hash": "c" * 64,
                "image_sha256": _sha(b"png"),
                "page_id": "pgdp:project-1:001.png",
                "page_sha256": page_sha,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    taxonomy = TypographyTaxonomy(
        version="labeler-v1",
        labels=(
            TypographyTaxonomyLabel(
                value="italic",
                display_name="Italic",
                required_for_completion=True,
                trainable=True,
            ),
        ),
    )
    bundle = LabelingBundle(
        schema_version=REVIEW_CONTRACT_VERSION,
        configuration_hash="c" * 64,
        taxonomy=taxonomy,
        page_id="pgdp:project-1:001.png",
        page_sha256=page_sha,
        image_sha256=_sha(b"png"),
        text_sha256=_sha(b"Word"),
        page_head_sha256=_sha(page_head_payload),
        artifacts=(
            ArtifactReference(
                artifact_id="image",
                relative_path="page.png",
                sha256=_sha(b"png"),
                media_type="image/png",
            ),
            ArtifactReference(
                artifact_id="page-record",
                relative_path="page-record.json",
                sha256=_sha(page_payload),
                media_type="application/json",
            ),
        ),
        evidence=(
            Evidence(
                evidence_id="image-evidence",
                artifact_id="image",
                artifact_sha256=_sha(b"png"),
                byte_start=0,
                byte_end=1,
            ),
        ),
        words=(
            WordTypography(
                word_id="7ca20136-634e-5282-a071-0ff1c9467b8b",
                text="Word",
                text_sha256=_sha(b"Word"),
                page_content_sha256=_sha(page_payload),
                image_artifact_sha256=_sha(b"png"),
                grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
                taxonomy_version=taxonomy.version,
                taxonomy_hash=taxonomy.taxonomy_hash,
                label_states={"italic": LabelState.UNKNOWN},
                source_evidence_ids=("image-evidence",),
            ),
        ),
    )
    (root / "labeling-bundle.json").write_text(bundle.model_dump_json(indent=2))
    return bundle


def test_load_validates_and_retains_external_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    expected = _write_bundle(root)

    loaded = load_labeling_bundle_directory(root)

    assert loaded.root == root.resolve()
    assert loaded.bundle == expected
    assert loaded.artifact_paths["image"] == root / "artifacts" / "page.png"
    assert loaded.artifact_payloads["image"] == b"png"


def test_load_rejects_referenced_artifact_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    _write_bundle(root)
    (root / "artifacts" / "page.png").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="hash"):
        load_labeling_bundle_directory(root)


def test_load_rejects_page_head_hash_not_derived_from_bundle(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    bundle = _write_bundle(root)
    payload = bundle.model_dump(mode="python")
    payload["bundle_id"] = None
    payload["page_head_sha256"] = "f" * 64
    tampered = LabelingBundle.model_validate(payload)
    (root / "labeling-bundle.json").write_text(tampered.model_dump_json(indent=2))

    with pytest.raises(ValueError, match="page head"):
        load_labeling_bundle_directory(root)


def test_load_rejects_symlinked_referenced_artifact(tmp_path: Path) -> None:
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"png")
    root = tmp_path / "bundle"
    _write_bundle(root)
    image = root / "artifacts" / "page.png"
    image.unlink()
    image.symlink_to(outside)

    with pytest.raises((OSError, ValueError)):
        load_labeling_bundle_directory(root)


def test_load_rejects_referenced_fifo_without_blocking(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    _write_bundle(root)
    image = root / "artifacts" / "page.png"
    image.unlink()
    os.mkfifo(image)

    with pytest.raises(ValueError, match="regular"):
        load_labeling_bundle_directory(root)


def test_load_rejects_symlinked_bundle_file(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    bundle = _write_bundle(root)
    outside = tmp_path / "bundle.json"
    outside.write_text(json.dumps(bundle.model_dump(mode="json")))
    (root / "labeling-bundle.json").unlink()
    (root / "labeling-bundle.json").symlink_to(outside)

    with pytest.raises((OSError, ValueError)):
        load_labeling_bundle_directory(root)

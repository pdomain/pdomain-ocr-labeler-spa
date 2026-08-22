from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pdomain_book_tools.geometry import BoundingBox, Point
from pdomain_book_tools.typography import (
    GRAPHEME_SEGMENTATION_VERSION,
    REVIEW_CONTRACT_VERSION,
    TYPOGRAPHY_PAGE_RECORD_EXTERNAL_F2_SCHEMA_VERSION,
    AlignmentEvidence,
    ArtifactRef,
    ArtifactReference,
    ArtifactSource,
    BookLabelingManifest,
    BookLabelingPage,
    ConfidenceTier,
    Evidence,
    Grapheme,
    KnowledgeState,
    LabelingBundle,
    LabelSource,
    LabelState,
    OcrTokenRef,
    SourceCoordinateSpace,
    SourceSlice,
    StyleLabel,
    StyleSpan,
    TargetCoordinateSpace,
    TextIdentity,
    TypographyPageRecord,
    TypographyTaxonomy,
    TypographyTaxonomyLabel,
    WordTypography,
)

from pdomain_ocr_labeler_spa.core.persistence.book_labeling_manifest import (
    load_book_labeling_manifest_directory,
)
from pdomain_ocr_labeler_spa.core.persistence.book_labeling_session import (
    BookLabelingSession,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact(*, source: ArtifactSource, sha256: str) -> ArtifactRef:
    return ArtifactRef(
        source=source,
        source_url=None,
        local_path="fixture.bin",
        retrieved_at=datetime(2026, 8, 22, tzinfo=UTC),
        sha256=sha256,
        version="1",
        license_ref=None,
    )


def _page_record(*, f2: bytes, image_sha256: str, page_id: str) -> TypographyPageRecord:
    f2_sha256 = _sha(f2)
    page_key = f"{page_id.rsplit(':', maxsplit=1)[-1]}.png"
    member_prefix = json.dumps(page_key).encode() + b":"
    value_start = f2.index(member_prefix) + len(member_prefix)
    lexical_value = json.dumps("x").encode()
    value_end = value_start + len(lexical_value)
    source_slice = SourceSlice(
        artifact_sha256=f2_sha256,
        byte_start=value_start + 1,
        byte_end=value_end - 1,
    )
    return TypographyPageRecord(
        schema_version=TYPOGRAPHY_PAGE_RECORD_EXTERNAL_F2_SCHEMA_VERSION,
        identity=TextIdentity(
            work_id="work",
            edition_id="edition",
            book_id="book",
            project_id="project",
            pg_ebook_id=None,
            se_repository=None,
            page_id=page_id,
            image_artifact=_artifact(source=ArtifactSource.HUMAN, sha256=image_sha256),
            text_artifacts=(_artifact(source=ArtifactSource.PGDP_F2, sha256=f2_sha256),),
        ),
        original_f2_artifact_base64=None,
        original_f2_artifact_sha256=f2_sha256,
        external_f2_artifact=ArtifactReference(
            artifact_id="f2",
            relative_path="source/F2.json",
            sha256=f2_sha256,
            media_type="application/json",
        ),
        f2_page_key=page_key,
        f2_page_value_lexical_byte_range=(value_start, value_end),
        f2_decoded_page_utf8_sha256=_sha(b"x"),
        parsed_text="x",
        graphemes=(
            Grapheme(
                index=0,
                text="x",
                source_slices=(source_slice,),
                normalized_from=None,
            ),
        ),
        ocr_tokens=(
            OcrTokenRef(
                token_id="word",
                text="x",
                confidence=1.0,
                bbox=BoundingBox(
                    top_left=Point(0, 0, is_normalized=False),
                    bottom_right=Point(1, 1, is_normalized=False),
                ),
                line_id="line",
                grapheme_start=0,
                grapheme_end=1,
                alignment_id="alignment",
            ),
        ),
        style_spans=(
            StyleSpan(
                label=StyleLabel.ITALIC,
                start=0,
                end=1,
                state=KnowledgeState.POSITIVE,
                label_source=LabelSource.F2,
                confidence_tier=ConfidenceTier.GOLD,
                source_slices=(source_slice,),
                rule_ref="fixture",
                semantic_reason=None,
                warnings=(),
            ),
        ),
        structural_context=("body",),
        parser_warnings=(),
        alignments=(
            AlignmentEvidence(
                alignment_id="alignment",
                method="exact",
                source_artifact_sha256=f2_sha256,
                target_artifact_sha256=image_sha256,
                source_coordinate_space=SourceCoordinateSpace.SOURCE_GRAPHEMES,
                target_coordinate_space=TargetCoordinateSpace.OCR_GRAPHEMES,
                source_range=(0, 1),
                target_range=(0, 1),
                operations=(),
                score=1.0,
                margin=None,
                alternatives=(),
                accepted=True,
            ),
        ),
        project_comments_artifact=None,
        guideline_version="fixture",
    )


def _write_book(root: Path, *, page_count: int = 4) -> BookLabelingManifest:
    root.mkdir()
    source = root / "source"
    source.mkdir()
    page_names = tuple(f"{index:03d}.png" for index in range(page_count))
    f2 = b"{" + b",".join(json.dumps(page_name).encode() + b':"x"' for page_name in page_names) + b"}\n"
    p3 = f2
    (source / "F2.json").write_bytes(f2)
    (source / "P3.json").write_bytes(p3)
    (root / "shared-source-resolver.json").write_text(
        json.dumps(
            {
                "artifact_root": ".",
                "artifacts": {
                    "source/F2.json": _sha(f2),
                    "source/P3.json": _sha(p3),
                },
                "resolution_scope": "book_root_v1",
                "schema_version": "1.0",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
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
    pages: list[BookLabelingPage] = []
    for index, page_name in enumerate(page_names):
        page_id = f"pgdp:project:{page_name.removesuffix('.png')}"
        image = f"image-{index}".encode()
        image_sha256 = _sha(image)
        record = _page_record(f2=f2, image_sha256=image_sha256, page_id=page_id)
        record_bytes = record.to_json_bytes()
        page_sha256 = _sha(record_bytes)
        page_head = (
            json.dumps(
                {
                    "configuration_hash": "c" * 64,
                    "image_sha256": image_sha256,
                    "page_id": page_id,
                    "page_sha256": page_sha256,
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
            page_sha256=page_sha256,
            image_sha256=image_sha256,
            text_sha256=_sha(b"x"),
            page_head_sha256=_sha(page_head),
            artifacts=(
                ArtifactReference(
                    artifact_id="f2",
                    relative_path="source/F2.json",
                    sha256=_sha(f2),
                    media_type="application/json",
                ),
                ArtifactReference(
                    artifact_id="p3",
                    relative_path="source/P3.json",
                    sha256=_sha(p3),
                    media_type="application/json",
                ),
                ArtifactReference(
                    artifact_id="image",
                    relative_path="image.png",
                    sha256=image_sha256,
                    media_type="image/png",
                ),
                ArtifactReference(
                    artifact_id="page_record",
                    relative_path="page-record.json",
                    sha256=page_sha256,
                    media_type="application/json",
                ),
            ),
            evidence=(
                Evidence(
                    evidence_id="f2-evidence",
                    artifact_id="f2",
                    artifact_sha256=_sha(f2),
                    byte_start=0,
                    byte_end=1,
                ),
            ),
            words=(
                WordTypography(
                    word_id=f"7ca20136-634e-5282-a071-{index:012d}",
                    text="x",
                    text_sha256=_sha(b"x"),
                    page_content_sha256=page_sha256,
                    image_artifact_sha256=image_sha256,
                    grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
                    taxonomy_version=taxonomy.version,
                    taxonomy_hash=taxonomy.taxonomy_hash,
                    label_states={"italic": LabelState.UNKNOWN},
                    source_evidence_ids=("f2-evidence",),
                ),
            ),
        )
        page_directory = root / "pages" / f"{index:04d}-{bundle.bundle_id}"
        page_directory.mkdir(parents=True)
        bundle_bytes = bundle.to_json_bytes()
        provenance = b'{"schema_version":"1.0"}\n'
        materialization = {
            "files": {
                "image.png": image_sha256,
                "labeling-bundle.json": _sha(bundle_bytes),
                "page-record.json": page_sha256,
                "source-provenance.json": _sha(provenance),
            },
            "schema_version": "1.0",
        }
        materialization_bytes = (
            json.dumps(materialization, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        (page_directory / "image.png").write_bytes(image)
        (page_directory / "labeling-bundle.json").write_bytes(bundle_bytes)
        (page_directory / "page-record.json").write_bytes(record_bytes)
        (page_directory / "source-provenance.json").write_bytes(provenance)
        (page_directory / "materialization.json").write_bytes(materialization_bytes)
        pages.append(
            BookLabelingPage(
                page_index=index,
                page_id=page_id,
                labeling_bundle_id=bundle.bundle_id or "",
                materialization_relative_path=page_directory.relative_to(root).as_posix(),
                materialization_sha256=_sha(materialization_bytes),
                configuration_hash=bundle.configuration_hash,
                taxonomy_version=taxonomy.version,
                taxonomy_hash=taxonomy.taxonomy_hash,
            )
        )
    manifest = BookLabelingManifest(book_id="book:pgdp:project", pages=tuple(pages))
    (root / "book-labeling-manifest.json").write_bytes(manifest.to_json_bytes())
    return manifest


def _session(root: Path) -> BookLabelingSession:
    return BookLabelingSession(load_book_labeling_manifest_directory(root))


def test_opens_one_real_producer_shaped_page_without_eagerly_loading_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root)
    read_paths: list[tuple[str, ...]] = []
    from pdomain_ocr_labeler_spa.core.persistence import book_labeling_session

    real_read = book_labeling_session._read_regular_at

    def record_read(descriptor: int, parts: tuple[str, ...]) -> bytes:
        read_paths.append(parts)
        return real_read(descriptor, parts)

    monkeypatch.setattr(book_labeling_session, "_read_regular_at", record_read)
    session = _session(root)

    assert read_paths == []
    loaded = session.open_page(1)

    assert loaded.bundle.bundle_id == manifest.pages[1].labeling_bundle_id
    assert loaded.bundle.page_id == manifest.pages[1].page_id
    assert {"materialization.json", "labeling-bundle.json", "page-record.json"} <= {
        path[-1] for path in read_paths
    }
    assert "image.png" in {path[-1] for path in read_paths}
    session.close()


def test_rejects_root_replacement_after_manifest_intake(tmp_path: Path) -> None:
    root = tmp_path / "book"
    _write_book(root)
    session = _session(root)
    replacement_source = tmp_path / "replacement-source"
    _write_book(replacement_source)
    root.rename(tmp_path / "original")
    shutil.copytree(replacement_source, root)

    with pytest.raises(ValueError, match="root identity"):
        session.open_page(0)
    session.close()


def test_rejects_symlinked_page_directory_after_manifest_intake(tmp_path: Path) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root)
    session = _session(root)
    page_directory = root / manifest.pages[0].materialization_relative_path
    outside = tmp_path / "outside"
    shutil.copytree(page_directory, outside)
    shutil.rmtree(page_directory)
    page_directory.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        session.open_page(0)
    session.close()


def test_rejects_page_bundle_identity_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root)
    replacement_page = manifest.pages[0].model_copy(update={"page_id": "pgdp:project:other"})
    replacement_manifest = manifest.model_copy(update={"pages": (replacement_page, *manifest.pages[1:])})
    (root / "book-labeling-manifest.json").write_bytes(replacement_manifest.to_json_bytes())
    session = _session(root)

    with pytest.raises(ValueError, match="identity does not match"):
        session.open_page(0)
    session.close()


def test_rejects_drifting_shared_f2_bytes(tmp_path: Path) -> None:
    root = tmp_path / "book"
    _write_book(root)
    session = _session(root)
    (root / "source" / "F2.json").write_bytes(b'{"000.png":"drift"}\n')

    with pytest.raises(ValueError, match="shared source hash"):
        session.open_page(0)
    session.close()


def test_evicts_oldest_sealed_image_descriptor_when_capacity_is_exceeded(tmp_path: Path) -> None:
    root = tmp_path / "book"
    _write_book(root)
    session = _session(root)
    first = session.open_page(0)
    session.open_page(1)
    session.open_page(2)
    session.open_page(3)

    with pytest.raises(OSError):
        os.fstat(first.image_descriptor)
    session.close()

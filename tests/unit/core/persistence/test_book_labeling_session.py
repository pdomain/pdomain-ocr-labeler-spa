from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

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
    BookMatchRelationReference,
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
from PIL import Image

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


def _fixture_image(index: int) -> bytes:
    """Return a small valid PNG whose pixels distinguish adjacent fixture pages."""
    stream = io.BytesIO()
    color = (255, 0, 0) if index % 2 == 0 else (0, 0, 255)
    Image.new("RGB", (1, 1), color=color).save(stream, format="PNG")
    return stream.getvalue()


def _write_edition_companion(root: Path, *, page_ids: tuple[str, ...], relation_id: str) -> tuple[str, bytes]:
    edition = root / "edition"
    edition.mkdir()
    edition_document_bytes = b'{"schema_version":"1.0"}\n'
    projection_bytes = b'{"schema_version":"1.0","units":[]}\n'
    source_resolver_bytes = b'{"schema_version":"1.0"}\n'
    alignment_bytes = b'{"schema_version":"1.0"}\n'
    (edition / "edition-document.json").write_bytes(edition_document_bytes)
    (edition / "projection.json").write_bytes(projection_bytes)
    (edition / "source-resolver.json").write_bytes(source_resolver_bytes)
    (edition / "alignment.json").write_bytes(alignment_bytes)
    gutenberg = root / "source" / "gutenberg"
    gutenberg.mkdir()
    gutenberg_bytes = b"<html><body>fixture</body></html>\n"
    (gutenberg / "37235-h.htm").write_bytes(gutenberg_bytes)
    graph_artifact_references = (
        {
            "artifact_id": "edition-alignment-evidence",
            "kind": "matching_evidence",
            "relative_path": "edition/alignment.json",
            "sha256": _sha(alignment_bytes),
        },
        {
            "artifact_id": "edition-document",
            "kind": "edition_document",
            "relative_path": "edition/edition-document.json",
            "sha256": _sha(edition_document_bytes),
        },
        {
            "artifact_id": "edition-projection",
            "kind": "edition_projection",
            "relative_path": "edition/projection.json",
            "sha256": _sha(projection_bytes),
        },
        {
            "artifact_id": "edition-source-resolver",
            "kind": "matching_evidence",
            "relative_path": "edition/source-resolver.json",
            "sha256": _sha(source_resolver_bytes),
        },
        {
            "artifact_id": "gutenberg-source:fixture",
            "kind": "source",
            "relative_path": "source/gutenberg/37235-h.htm",
            "sha256": _sha(gutenberg_bytes),
        },
    )
    graph_relation = {
        "evidence_artifact_ids": [reference["artifact_id"] for reference in graph_artifact_references],
        "kind": "edition_alignment",
        "page_ids": list(page_ids),
        "relation_id": relation_id,
    }
    graph_identity = {
        "artifact_references": list(graph_artifact_references),
        "relations": [graph_relation],
        "schema_version": "1.0",
    }
    graph_id = _sha(json.dumps(graph_identity, sort_keys=True, separators=(",", ":")).encode())
    graph_bytes = (
        json.dumps(
            {**graph_identity, "graph_id": graph_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    matching = root / "matching"
    matching.mkdir()
    (matching / "edition-alignment.json").write_bytes(graph_bytes)
    return graph_id, graph_bytes


def _write_book(
    root: Path,
    *,
    page_count: int = 4,
    valid_images: bool = False,
    edition_companion: bool = False,
) -> BookLabelingManifest:
    root.mkdir()
    source = root / "source"
    source.mkdir()
    page_names = tuple(f"{index:03d}.png" for index in range(page_count))
    page_ids = tuple(f"pgdp:project:{page_name.removesuffix('.png')}" for page_name in page_names)
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
    edition_relation_id = "edition_alignment:fixture"
    companion_graph: tuple[str, bytes] | None = None
    if edition_companion:
        companion_graph = _write_edition_companion(
            root,
            page_ids=page_ids,
            relation_id=edition_relation_id,
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
        image = _fixture_image(index) if valid_images else f"image-{index}".encode()
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
            "shared_source_resolver": {
                "relative_path": "shared-source-resolver.json",
                "resolution_scope": "book_root_v1",
                "schema_version": "1.0",
                "sha256": _sha((root / "shared-source-resolver.json").read_bytes()),
            },
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
                relation_ids=(edition_relation_id,) if edition_companion else (),
            )
        )
    if companion_graph is None:
        match_relations: tuple[BookMatchRelationReference, ...] = ()
    else:
        graph_id, graph_bytes = companion_graph
        match_relations = (
            BookMatchRelationReference(
                relation_id=edition_relation_id,
                page_ids=tuple(page.page_id for page in pages),
                match_graph_id=graph_id,
                match_graph_relative_path="matching/edition-alignment.json",
                match_graph_sha256=_sha(graph_bytes),
            ),
        )
    manifest = BookLabelingManifest(
        book_id="book:pgdp:project",
        pages=tuple(pages),
        match_relations=match_relations,
    )
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
    loaded.close()
    session.close()


def test_opens_first_middle_and_last_pages_with_an_edition_companion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root, page_count=5, edition_companion=True)
    manifest_read_paths: list[tuple[str, ...]] = []
    read_paths: list[tuple[str, ...]] = []
    from pdomain_ocr_labeler_spa.core.persistence import (
        book_labeling_manifest,
        book_labeling_session,
    )

    real_manifest_read = book_labeling_manifest._read_regular_at
    real_read = book_labeling_session._read_regular_at

    def record_manifest_read(descriptor: int, parts: tuple[str, ...]) -> bytes:
        manifest_read_paths.append(parts)
        return real_manifest_read(descriptor, parts)

    def record_read(descriptor: int, parts: tuple[str, ...]) -> bytes:
        read_paths.append(parts)
        return real_read(descriptor, parts)

    monkeypatch.setattr(book_labeling_manifest, "_read_regular_at", record_manifest_read)
    monkeypatch.setattr(book_labeling_session, "_read_regular_at", record_read)
    session = _session(root)

    with patch.object(session, "_load_page", wraps=session._load_page) as load_page:
        for page_index in (0, 2, 4):
            loaded = session.open_page(page_index)
            assert loaded.bundle.page_id == manifest.pages[page_index].page_id
            assert loaded.artifact_payloads["f2"] == (root / "source" / "F2.json").read_bytes()
            assert loaded.artifact_payloads["p3"] == (root / "source" / "P3.json").read_bytes()
            loaded.close()

        assert [call.args for call in load_page.call_args_list] == [(0,), (2,), (4,)]
        cached = session.open_page(0)
        cached.close()
        fourth_page = session.open_page(1)
        fourth_page.close()
        reloaded = session.open_page(2)
        reloaded.close()

    assert [call.args for call in load_page.call_args_list] == [(0,), (2,), (4,), (1,), (2,)]

    relation = manifest.match_relations[0]
    graph = json.loads((root / relation.match_graph_relative_path).read_text())
    graph_artifact_hashes = {
        artifact["relative_path"]: artifact["sha256"] for artifact in graph["artifact_references"]
    }
    assert graph["graph_id"] == relation.match_graph_id
    assert graph_artifact_hashes == {
        "edition/alignment.json": _sha((root / "edition" / "alignment.json").read_bytes()),
        "edition/edition-document.json": _sha((root / "edition" / "edition-document.json").read_bytes()),
        "edition/projection.json": _sha((root / "edition" / "projection.json").read_bytes()),
        "edition/source-resolver.json": _sha((root / "edition" / "source-resolver.json").read_bytes()),
        "source/gutenberg/37235-h.htm": _sha((root / "source" / "gutenberg" / "37235-h.htm").read_bytes()),
    }
    assert relation.match_graph_relative_path == "matching/edition-alignment.json"
    assert relation.match_graph_sha256 == _sha((root / relation.match_graph_relative_path).read_bytes())
    assert manifest_read_paths == [
        ("book-labeling-manifest.json",),
        ("matching", "edition-alignment.json"),
    ]
    assert session.retained_page_count == 3
    assert not any(parts[:1] in {("edition",), ("matching",)} for parts in read_paths)
    assert ("source", "gutenberg", "37235-h.htm") not in read_paths
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


def test_rejects_page_materialization_that_does_not_pin_its_shared_source_resolver(
    tmp_path: Path,
) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root)
    page_directory = root / manifest.pages[0].materialization_relative_path
    materialization = json.loads((page_directory / "materialization.json").read_text())
    materialization["shared_source_resolver"]["sha256"] = "0" * 64
    materialization_bytes = (
        json.dumps(materialization, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    (page_directory / "materialization.json").write_bytes(materialization_bytes)
    _write_replaced_manifest(
        root,
        manifest,
        page_index=0,
        materialization_sha256=_sha(materialization_bytes),
    )
    session = _session(root)

    with pytest.raises(ValueError, match="shared source resolver"):
        session.open_page(0)
    session.close()


def test_rejects_later_page_with_a_different_resolver_identity(tmp_path: Path) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root)
    resolver_path = root / "shared-source-resolver.json"
    alternate_resolver_bytes = (
        json.dumps(
            json.loads(resolver_path.read_text()),
            indent=2,
            sort_keys=False,
        )
        + "\n"
    ).encode()
    page_directory = root / manifest.pages[1].materialization_relative_path
    materialization = json.loads((page_directory / "materialization.json").read_text())
    materialization["shared_source_resolver"]["sha256"] = _sha(alternate_resolver_bytes)
    materialization_bytes = (
        json.dumps(materialization, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    (page_directory / "materialization.json").write_bytes(materialization_bytes)
    _write_replaced_manifest(
        root,
        manifest,
        page_index=1,
        materialization_sha256=_sha(materialization_bytes),
    )
    session = _session(root)
    first = session.open_page(0)
    resolver_path.write_bytes(alternate_resolver_bytes)

    with pytest.raises(ValueError, match="source identity"):
        session.open_page(1)

    first.close()
    session.close()


def test_rejects_bundle_without_exact_page_record_and_image_references(
    tmp_path: Path,
) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root)
    page_directory = root / manifest.pages[0].materialization_relative_path
    bundle = LabelingBundle.model_validate_json((page_directory / "labeling-bundle.json").read_bytes())
    provenance = (page_directory / "source-provenance.json").read_bytes()
    artifacts = tuple(
        artifact.model_copy(update={"relative_path": "source-provenance.json", "sha256": _sha(provenance)})
        if artifact.artifact_id in {"image", "page_record"}
        else artifact
        for artifact in bundle.artifacts
    )
    replacement_bundle = bundle.model_copy(update={"artifacts": artifacts})
    bundle_bytes = replacement_bundle.to_json_bytes()
    (page_directory / "labeling-bundle.json").write_bytes(bundle_bytes)
    materialization = json.loads((page_directory / "materialization.json").read_text())
    materialization["files"]["labeling-bundle.json"] = _sha(bundle_bytes)
    materialization_bytes = (
        json.dumps(materialization, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    (page_directory / "materialization.json").write_bytes(materialization_bytes)
    _write_replaced_manifest(
        root,
        manifest,
        page_index=0,
        labeling_bundle_id=replacement_bundle.bundle_id or "",
        materialization_sha256=_sha(materialization_bytes),
    )
    session = _session(root)

    with pytest.raises(ValueError, match=r"invalid labeling bundle|page record and image"):
        session.open_page(0)
    session.close()


def test_retained_page_lease_survives_cache_eviction_and_descriptor_reuse(tmp_path: Path) -> None:
    root = tmp_path / "book"
    _write_book(root)
    session = _session(root)
    first = session.open_page(0)
    for index in (1, 2, 3):
        opened = session.open_page(index)
        opened.close()
    reused_descriptor = os.open(root / "book-labeling-manifest.json", os.O_RDONLY)
    os.close(reused_descriptor)

    assert os.read(first.image_descriptor, 1024) == b"image-0"
    assert os.get_inheritable(first.image_descriptor) is False
    first.close()
    session.close()


def _write_replaced_manifest(
    root: Path,
    manifest: BookLabelingManifest,
    *,
    page_index: int,
    labeling_bundle_id: str | None = None,
    materialization_sha256: str | None = None,
) -> None:
    page = manifest.pages[page_index]
    replacement_page = page.model_copy(
        update={
            "labeling_bundle_id": page.labeling_bundle_id
            if labeling_bundle_id is None
            else labeling_bundle_id,
            "materialization_sha256": page.materialization_sha256
            if materialization_sha256 is None
            else materialization_sha256,
        }
    )
    replacement_manifest = manifest.model_copy(
        update={
            "pages": (
                *manifest.pages[:page_index],
                replacement_page,
                *manifest.pages[page_index + 1 :],
            )
        }
    )
    (root / "book-labeling-manifest.json").write_bytes(replacement_manifest.to_json_bytes())


def test_graph_referenced_optional_layout_sidecar_is_carried_without_source_imports(tmp_path: Path) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root, page_count=2, edition_companion=True)
    payload = b'{"schema":"pdomain.edition-layout-hints","version":1,"groups":[]}'
    (root / "edition" / "layout-hints.json").write_bytes(payload)
    relation = manifest.match_relations[0]
    graph_payload = json.dumps(
        {
            "artifact_references": [
                {
                    "kind": "supporting_evidence",
                    "relative_path": "edition/layout-hints.json",
                }
            ]
        }
    ).encode()
    (root / relation.match_graph_relative_path).write_bytes(graph_payload)
    relation = relation.model_copy(update={"match_graph_sha256": _sha(graph_payload)})
    manifest = manifest.model_copy(update={"match_relations": (relation,)})
    (root / "book-labeling-manifest.json").write_bytes(manifest.to_json_bytes())
    session = _session(root)
    try:
        with session.open_page(0) as loaded:
            assert loaded.artifact_payloads["layout_hints"] == payload
            assert loaded.artifact_payloads["f2"] == (root / "source" / "F2.json").read_bytes()
    finally:
        session.close()


@pytest.mark.parametrize("tampered", [False, True])
def test_graph_referenced_source_alignment_is_pinned_to_page(tmp_path: Path, *, tampered: bool) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root, page_count=2, edition_companion=True)
    payload = b'{"schema":"pdomain.pgdp-source-alignment","version":1}'
    directory = root / "evidence" / "f2-p3"
    directory.mkdir(parents=True)
    (directory / "page.json").write_bytes(payload if not tampered else b"corrupted")
    relation = manifest.match_relations[0]
    graph_payload = json.dumps(
        {
            "artifact_references": [
                {
                    "kind": "matching_evidence",
                    "artifact_id": relation.relation_id,
                    "relative_path": "evidence/f2-p3/page.json",
                    "sha256": _sha(payload),
                }
            ]
        }
    ).encode()
    (root / relation.match_graph_relative_path).write_bytes(graph_payload)
    relation = relation.model_copy(update={"match_graph_sha256": _sha(graph_payload)})
    manifest = manifest.model_copy(update={"match_relations": (relation,)})
    (root / "book-labeling-manifest.json").write_bytes(manifest.to_json_bytes())
    with _session(root) as session:
        if tampered:
            with pytest.raises(ValueError, match="alignment evidence hash mismatch"):
                session.open_page(0)
        else:
            with session.open_page(0) as loaded:
                assert loaded.artifact_payloads["source_alignment"] == payload

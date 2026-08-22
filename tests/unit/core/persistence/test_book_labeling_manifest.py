"""Tests for manifest-only intake of a materialized labeling book."""

from __future__ import annotations

import os
import re
from hashlib import sha256
from pathlib import Path

import pytest
from pdomain_book_tools.typography import (
    BookLabelingManifest,
    BookLabelingPage,
    BookMatchRelationReference,
)

from pdomain_ocr_labeler_spa.core.persistence.book_labeling_manifest import (
    load_book_labeling_manifest_directory,
)


def _sha(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _write_book(root: Path, *, page_count: int = 2) -> BookLabelingManifest:
    root.mkdir()
    pages_root = root / "pages"
    pages_root.mkdir()
    page_ids = tuple(f"pgdp:project:{index:03d}.png" for index in range(1, page_count + 1))
    continuation_bytes = b'{"continuations":[]}\n'
    matching = root / "matching"
    matching.mkdir()
    (matching / "continuations.json").write_bytes(continuation_bytes)
    graph_sha256 = _sha(continuation_bytes)
    relation_id = "continuation-relation"
    pages = tuple(
        BookLabelingPage(
            page_index=index,
            page_id=page_id,
            labeling_bundle_id=_sha(f"bundle-{index}".encode()),
            materialization_relative_path=f"pages/{index + 1:03d}",
            materialization_sha256=_sha(f"materialization-{index}".encode()),
            configuration_hash="c" * 64,
            taxonomy_version="labeler-v1",
            taxonomy_hash="a" * 64,
            relation_ids=(relation_id,),
        )
        for index, page_id in enumerate(page_ids)
    )
    for page in pages:
        (root / page.materialization_relative_path).mkdir()
    manifest = BookLabelingManifest(
        book_id="pgdp-project",
        pages=pages,
        match_relations=(
            BookMatchRelationReference(
                relation_id=relation_id,
                page_ids=page_ids,
                match_graph_id=graph_sha256,
                match_graph_relative_path="matching/continuations.json",
                match_graph_sha256=graph_sha256,
            ),
        ),
    )
    (root / "book-labeling-manifest.json").write_bytes(manifest.to_json_bytes())
    return manifest


def test_loads_manifest_and_retains_its_exact_bytes(tmp_path: Path) -> None:
    root = tmp_path / "book"
    expected = _write_book(root)
    payload = (root / "book-labeling-manifest.json").read_bytes()

    loaded = load_book_labeling_manifest_directory(root)

    assert loaded.root == root.resolve()
    assert loaded.manifest == expected
    assert loaded.manifest_bytes == payload
    root_stat = root.stat()
    assert (loaded.root_device, loaded.root_inode) == (
        root_stat.st_dev,
        root_stat.st_ino,
    )


def test_rejects_symlinked_book_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_book(source)
    root = tmp_path / "book"
    root.symlink_to(source, target_is_directory=True)

    with pytest.raises((OSError, ValueError)):
        load_book_labeling_manifest_directory(root)


def test_rejects_symlinked_manifest_file(tmp_path: Path) -> None:
    root = tmp_path / "book"
    manifest = _write_book(root)
    outside = tmp_path / "outside-manifest.json"
    outside.write_bytes(manifest.to_json_bytes())
    manifest_path = root / "book-labeling-manifest.json"
    manifest_path.unlink()
    manifest_path.symlink_to(outside)

    with pytest.raises((OSError, ValueError)):
        load_book_labeling_manifest_directory(root)


def test_rejects_manifest_with_an_invalid_content_identity(tmp_path: Path) -> None:
    root = tmp_path / "book"
    _write_book(root)
    manifest_path = root / "book-labeling-manifest.json"
    manifest_path.write_text(
        re.sub(
            r'"manifest_id":"[0-9a-f]{64}"',
            '"manifest_id":"' + "f" * 64 + '"',
            manifest_path.read_text(),
        )
    )

    with pytest.raises(ValueError, match="invalid book labeling manifest"):
        load_book_labeling_manifest_directory(root)


def test_rejects_traversing_materialization_path(tmp_path: Path) -> None:
    root = tmp_path / "book"
    _write_book(root)
    manifest_path = root / "book-labeling-manifest.json"
    manifest_path.write_text(
        manifest_path.read_text().replace(
            '"materialization_relative_path":"pages/001"',
            '"materialization_relative_path":"../outside"',
        )
    )

    with pytest.raises(ValueError, match="invalid book labeling manifest"):
        load_book_labeling_manifest_directory(root)


def test_rejects_symlinked_materialization_directory(tmp_path: Path) -> None:
    root = tmp_path / "book"
    _write_book(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    materialization = root / "pages" / "001"
    materialization.rmdir()
    materialization.symlink_to(outside, target_is_directory=True)

    with pytest.raises((OSError, ValueError)):
        load_book_labeling_manifest_directory(root)


def test_rejects_symlinked_or_tampered_match_graph(tmp_path: Path) -> None:
    root = tmp_path / "book"
    _write_book(root)
    graph = root / "matching" / "continuations.json"
    graph.write_bytes(b'{"continuations":["tampered"]}\n')

    with pytest.raises(ValueError, match="match graph hash mismatch"):
        load_book_labeling_manifest_directory(root)

    outside = tmp_path / "outside.json"
    outside.write_bytes(b'{"continuations":[]}\n')
    graph.unlink()
    graph.symlink_to(outside)

    with pytest.raises((OSError, ValueError)):
        load_book_labeling_manifest_directory(root)


def test_loads_319_pages_without_opening_page_bundles_or_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "book"
    expected = _write_book(root, page_count=319)
    opened_paths: list[object] = []
    real_open = os.open

    def recording_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        opened_paths.append(path)
        if dir_fd is None:
            return real_open(path, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(
        "pdomain_ocr_labeler_spa.core.persistence.book_labeling_manifest.os.open",
        recording_open,
    )

    loaded = load_book_labeling_manifest_directory(root)

    assert len(loaded.manifest.pages) == 319
    assert loaded.manifest == expected
    assert "labeling-bundle.json" not in opened_paths
    assert "page.png" not in opened_paths

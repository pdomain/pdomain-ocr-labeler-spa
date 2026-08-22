"""Validated, lazy intake for a materialized typography book manifest."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pdomain_book_tools.typography import BookLabelingManifest
from pydantic import ValidationError

_MANIFEST_FILENAME = "book-labeling-manifest.json"


@dataclass(frozen=True, slots=True)
class LoadedBookLabelingManifest:
    """Verified book metadata retained without loading any page bundle or image."""

    root: Path
    manifest: BookLabelingManifest
    manifest_bytes: bytes


def _safe_parts(relative_path: str) -> tuple[str, ...]:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("book artifact path must be a confined relative path")
    return path.parts


def _open_directory_nofollow(path: Path) -> tuple[int, Path]:
    absolute_path = Path(os.path.abspath(path))
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in absolute_path.parts[1:]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, Path(os.readlink(f"/proc/self/fd/{descriptor}"))
    except BaseException:
        os.close(descriptor)
        raise


def _open_directory_at(root_descriptor: int, parts: tuple[str, ...]) -> int:
    descriptor = os.dup(root_descriptor)
    try:
        for part in parts:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_regular_at(root_descriptor: int, parts: tuple[str, ...]) -> int:
    parent_descriptor = os.dup(root_descriptor)
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=parent_descriptor,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("book input must be a regular file")
        return descriptor
    finally:
        os.close(parent_descriptor)


def _read_regular_at(root_descriptor: int, parts: tuple[str, ...]) -> bytes:
    descriptor = _open_regular_at(root_descriptor, parts)
    try:
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _load_manifest(payload: bytes) -> BookLabelingManifest:
    try:
        return BookLabelingManifest.model_validate_json(payload)
    except ValidationError as exc:
        raise ValueError("invalid book labeling manifest") from exc


def _validate_materializations(root_descriptor: int, manifest: BookLabelingManifest) -> None:
    for page in manifest.pages:
        descriptor = _open_directory_at(
            root_descriptor,
            _safe_parts(page.materialization_relative_path),
        )
        os.close(descriptor)


def _validate_match_graphs(root_descriptor: int, manifest: BookLabelingManifest) -> None:
    payloads: dict[tuple[str, ...], bytes] = {}
    for relation in manifest.match_relations:
        parts = _safe_parts(relation.match_graph_relative_path)
        payload = payloads.get(parts)
        if payload is None:
            payload = _read_regular_at(root_descriptor, parts)
            payloads[parts] = payload
        if hashlib.sha256(payload).hexdigest() != relation.match_graph_sha256:
            raise ValueError(f"match graph hash mismatch: {relation.relation_id}")


def load_book_labeling_manifest_directory(root: Path) -> LoadedBookLabelingManifest:
    """Load a book manifest and graph pins without opening page-bundle contents."""
    root_descriptor, resolved_root = _open_directory_nofollow(root)
    try:
        manifest_bytes = _read_regular_at(root_descriptor, (_MANIFEST_FILENAME,))
        manifest = _load_manifest(manifest_bytes)
        _validate_materializations(root_descriptor, manifest)
        _validate_match_graphs(root_descriptor, manifest)
    finally:
        os.close(root_descriptor)
    return LoadedBookLabelingManifest(
        root=resolved_root,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
    )


__all__ = ["LoadedBookLabelingManifest", "load_book_labeling_manifest_directory"]

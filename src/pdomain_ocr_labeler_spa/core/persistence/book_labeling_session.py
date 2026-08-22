"""Lazy, verified page intake for an immutable labeling book."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import ClassVar, Literal, Self, final

from pdomain_book_tools.typography import LabelingBundle, TypographyPageRecord
from pydantic import BaseModel, ConfigDict, ValidationError

from .book_labeling_manifest import LoadedBookLabelingManifest
from .labeling_bundle import LoadedLabelingBundle

_F_ADD_SEALS = 1033
_F_SEAL_SEAL = 0x0001
_F_SEAL_SHRINK = 0x0002
_F_SEAL_GROW = 0x0004
_F_SEAL_WRITE = 0x0008
_CACHE_CAPACITY = 3


class _Materialization(BaseModel):
    """Exact page-local file pins emitted by the producer."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    files: dict[str, str]
    schema_version: Literal["1.0"]


class _SharedSourceResolver(BaseModel):
    """Book-root source pins shared by all independently loaded pages."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    artifact_root: Literal["."]
    artifacts: dict[str, str]
    resolution_scope: Literal["book_root_v1"]
    schema_version: Literal["1.0"]


@dataclass(frozen=True, slots=True)
class _SharedSources:
    """Verified shared source bytes retained while one page is loaded."""

    f2: bytes
    p3: bytes


def _safe_parts(relative_path: str) -> tuple[str, ...]:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("book input path must be a confined relative path")
    return path.parts


def _open_directory_nofollow(path: Path) -> int:
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
        return descriptor
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


def _sealed_descriptor(payload: bytes) -> int:
    descriptor = os.memfd_create("pdomain-book-labeling-page-image", os.MFD_ALLOW_SEALING)
    try:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            written += os.write(descriptor, view[written:])
        os.lseek(descriptor, 0, os.SEEK_SET)
        _ = fcntl.fcntl(
            descriptor,
            _F_ADD_SEALS,
            _F_SEAL_WRITE | _F_SEAL_GROW | _F_SEAL_SHRINK | _F_SEAL_SEAL,
        )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _load_materialization(payload: bytes) -> _Materialization:
    try:
        materialization = _Materialization.model_validate_json(payload)
    except ValidationError as exc:
        raise ValueError("invalid page materialization") from exc
    if not materialization.files:
        raise ValueError("page materialization must pin at least one file")
    for name, value in materialization.files.items():
        if _safe_parts(name) != (name,) or not _is_sha256(value):
            raise ValueError("page materialization contains an invalid file pin")
    return materialization


def _load_shared_source_resolver(payload: bytes) -> _SharedSourceResolver:
    try:
        resolver = _SharedSourceResolver.model_validate_json(payload)
    except ValidationError as exc:
        raise ValueError("invalid shared source resolver") from exc
    expected_paths = {"source/F2.json", "source/P3.json"}
    if set(resolver.artifacts) != expected_paths or any(
        not _is_sha256(value) for value in resolver.artifacts.values()
    ):
        raise ValueError("shared source resolver must pin F2 and P3 source bytes")
    return resolver


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_page_head(bundle: LabelingBundle) -> None:
    payload = (
        json.dumps(
            {
                "configuration_hash": bundle.configuration_hash,
                "image_sha256": bundle.image_sha256,
                "page_id": bundle.page_id,
                "page_sha256": bundle.page_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    if hashlib.sha256(payload).hexdigest() != bundle.page_head_sha256:
        raise ValueError("labeling bundle page head hash is not canonical")


@final
class BookLabelingSession:
    """Open verified book pages one at a time and retain at most three images."""

    def __init__(self, loaded_manifest: LoadedBookLabelingManifest) -> None:
        self._loaded_manifest = loaded_manifest
        self._cache: dict[int, LoadedLabelingBundle] = {}
        self._closed = False
        self._lock = RLock()

    @property
    def loaded_manifest(self) -> LoadedBookLabelingManifest:
        """Return the manifest that this session retains."""
        return self._loaded_manifest

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        """Close all sealed images retained by this session."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for loaded in self._cache.values():
                os.close(loaded.image_descriptor)
            self._cache.clear()

    def open_page(self, page_index: int) -> LoadedLabelingBundle:
        """Load and retain exactly one manifest-indexed page bundle."""
        with self._lock:
            if self._closed:
                raise ValueError("book labeling session is closed")
            cached = self._cache.pop(page_index, None)
            if cached is not None:
                self._cache[page_index] = cached
                return cached
            loaded = self._load_page(page_index)
            self._cache[page_index] = loaded
            if len(self._cache) > _CACHE_CAPACITY:
                evicted = self._cache.pop(next(iter(self._cache)))
                os.close(evicted.image_descriptor)
            return loaded

    def _load_page(self, page_index: int) -> LoadedLabelingBundle:
        pages = self._loaded_manifest.manifest.pages
        if page_index < 0 or page_index >= len(pages):
            raise IndexError("book page index is outside the manifest")
        page = pages[page_index]
        root_descriptor = _open_directory_nofollow(self._loaded_manifest.root)
        try:
            root_stat = os.fstat(root_descriptor)
            if (
                root_stat.st_dev != self._loaded_manifest.root_device
                or root_stat.st_ino != self._loaded_manifest.root_inode
            ):
                raise ValueError("book root identity changed after manifest intake")
            sources = self._load_shared_sources(root_descriptor)
            page_descriptor = _open_directory_at(
                root_descriptor, _safe_parts(page.materialization_relative_path)
            )
            try:
                return self._load_page_at(page_descriptor, page_index, sources)
            finally:
                os.close(page_descriptor)
        finally:
            os.close(root_descriptor)

    def _load_shared_sources(self, root_descriptor: int) -> _SharedSources:
        resolver = _load_shared_source_resolver(
            _read_regular_at(root_descriptor, ("shared-source-resolver.json",))
        )
        f2 = _read_regular_at(root_descriptor, ("source", "F2.json"))
        p3 = _read_regular_at(root_descriptor, ("source", "P3.json"))
        if (
            hashlib.sha256(f2).hexdigest() != resolver.artifacts["source/F2.json"]
            or hashlib.sha256(p3).hexdigest() != resolver.artifacts["source/P3.json"]
        ):
            raise ValueError("shared source hash does not match its resolver pin")
        return _SharedSources(f2=f2, p3=p3)

    def _load_page_at(
        self, page_descriptor: int, page_index: int, sources: _SharedSources
    ) -> LoadedLabelingBundle:
        page = self._loaded_manifest.manifest.pages[page_index]
        materialization_bytes = _read_regular_at(page_descriptor, ("materialization.json",))
        if hashlib.sha256(materialization_bytes).hexdigest() != page.materialization_sha256:
            raise ValueError("page materialization hash does not match its manifest pin")
        materialization = _load_materialization(materialization_bytes)
        file_payloads = {
            filename: _read_regular_at(page_descriptor, (filename,)) for filename in materialization.files
        }
        for filename, payload in file_payloads.items():
            if hashlib.sha256(payload).hexdigest() != materialization.files[filename]:
                raise ValueError(f"materialization file hash mismatch: {filename}")
        bundle_payload = file_payloads.get("labeling-bundle.json")
        page_record_payload = file_payloads.get("page-record.json")
        image_payload = file_payloads.get("image.png")
        if bundle_payload is None or page_record_payload is None or image_payload is None:
            raise ValueError("page materialization lacks a required labeler file")
        bundle = self._load_bundle(bundle_payload, page_index)
        page_record = self._load_page_record(page_record_payload, bundle, sources.f2)
        self._validate_bundle_artifacts(
            bundle=bundle,
            file_payloads=file_payloads,
            page_record=page_record,
            sources=sources,
        )
        image_descriptor = _sealed_descriptor(image_payload)
        return LoadedLabelingBundle(
            root=self._loaded_manifest.root / Path(*_safe_parts(page.materialization_relative_path)),
            bundle=bundle,
            artifact_paths={
                artifact.artifact_id: self._artifact_path(page_index, artifact.relative_path)
                for artifact in bundle.artifacts
            },
            artifact_payloads={
                artifact.artifact_id: self._artifact_payload(artifact.relative_path, file_payloads, sources)
                for artifact in bundle.artifacts
            },
            image_descriptor=image_descriptor,
        )

    def _load_bundle(self, payload: bytes, page_index: int) -> LabelingBundle:
        try:
            bundle = LabelingBundle.model_validate_json(payload)
        except ValidationError as exc:
            raise ValueError("invalid labeling bundle") from exc
        page = self._loaded_manifest.manifest.pages[page_index]
        if (
            bundle.bundle_id != page.labeling_bundle_id
            or bundle.page_id != page.page_id
            or bundle.configuration_hash != page.configuration_hash
            or bundle.taxonomy.version != page.taxonomy_version
            or bundle.taxonomy.taxonomy_hash != page.taxonomy_hash
        ):
            raise ValueError("labeling bundle identity does not match its manifest page pin")
        _validate_page_head(bundle)
        return bundle

    def _load_page_record(self, payload: bytes, bundle: LabelingBundle, f2: bytes) -> TypographyPageRecord:
        try:
            page_record = TypographyPageRecord.model_validate_json(payload)
        except ValidationError as exc:
            raise ValueError("invalid typography page record") from exc
        if page_record.identity.page_id != bundle.page_id:
            raise ValueError("page record identity does not match its labeling bundle")
        page_record.revalidate_external_f2_artifact(f2)
        return page_record

    def _validate_bundle_artifacts(
        self,
        *,
        bundle: LabelingBundle,
        file_payloads: dict[str, bytes],
        page_record: TypographyPageRecord,
        sources: _SharedSources,
    ) -> None:
        seen_artifact_ids: set[str] = set()
        source_payloads = {
            "source/F2.json": sources.f2,
            "source/P3.json": sources.p3,
        }
        for artifact in bundle.artifacts:
            if artifact.artifact_id in seen_artifact_ids:
                raise ValueError("labeling bundle has duplicate artifact identifiers")
            seen_artifact_ids.add(artifact.artifact_id)
            payload = source_payloads.get(artifact.relative_path)
            if payload is None:
                payload = file_payloads.get(artifact.relative_path)
            if payload is None or hashlib.sha256(payload).hexdigest() != artifact.sha256:
                raise ValueError(f"labeling bundle artifact hash mismatch: {artifact.artifact_id}")
        if page_record.external_f2_artifact is None:
            raise ValueError("page record must retain an external F2 artifact pin")
        if (
            page_record.external_f2_artifact.relative_path != "source/F2.json"
            or page_record.external_f2_artifact.sha256 != hashlib.sha256(sources.f2).hexdigest()
        ):
            raise ValueError("page record F2 reference does not match the shared source")

    def _artifact_path(self, page_index: int, relative_path: str) -> Path:
        source_paths = {"source/F2.json", "source/P3.json"}
        if relative_path in source_paths:
            return self._loaded_manifest.root / Path(*_safe_parts(relative_path))
        page = self._loaded_manifest.manifest.pages[page_index]
        return self._loaded_manifest.root / Path(
            *_safe_parts(page.materialization_relative_path), *_safe_parts(relative_path)
        )

    @staticmethod
    def _artifact_payload(
        relative_path: str, file_payloads: dict[str, bytes], sources: _SharedSources
    ) -> bytes:
        if relative_path == "source/F2.json":
            return sources.f2
        if relative_path == "source/P3.json":
            return sources.p3
        payload = file_payloads.get(relative_path)
        if payload is None:
            raise ValueError("labeling bundle artifact is absent from the materialization")
        return payload


__all__ = ["BookLabelingSession"]

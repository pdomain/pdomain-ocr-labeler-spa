"""Validated, read-only intake for a materialized typography LabelingBundle."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pdomain_book_tools.typography import LabelingBundle
from pydantic import ValidationError

from ..models import Project

_F_ADD_SEALS = 1033
_F_SEAL_SEAL = 0x0001
_F_SEAL_SHRINK = 0x0002
_F_SEAL_GROW = 0x0004
_F_SEAL_WRITE = 0x0008


@dataclass(frozen=True)
class LoadedLabelingBundle:
    """An authoritative bundle and the exact external artifact bytes it names."""

    root: Path
    bundle: LabelingBundle
    artifact_paths: dict[str, Path]
    artifact_payloads: dict[str, bytes]
    image_descriptor: int


def _safe_parts(relative_path: str) -> tuple[str, ...]:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("artifact path must be a confined relative path")
    return path.parts


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
            raise ValueError("bundle input must be a regular file")
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
    """Retain verified bytes in an immutable anonymous Linux file."""
    descriptor = os.memfd_create("pdomain-labeling-bundle-image", os.MFD_ALLOW_SEALING)
    try:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            written += os.write(descriptor, view[written:])
        os.lseek(descriptor, 0, os.SEEK_SET)
        seals = _F_SEAL_WRITE | _F_SEAL_GROW | _F_SEAL_SHRINK | _F_SEAL_SEAL
        fcntl.fcntl(descriptor, _F_ADD_SEALS, seals)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def load_labeling_bundle_directory(root: Path) -> LoadedLabelingBundle:
    """Read one immutable materialized bundle without following any child symlink."""
    resolved = root.resolve(strict=True)
    root_descriptor = os.open(resolved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        bundle_payload = _read_regular_at(root_descriptor, ("labeling-bundle.json",))
        try:
            bundle = LabelingBundle.model_validate_json(bundle_payload)
        except ValidationError as exc:
            raise ValueError("invalid labeling bundle") from exc
        artifact_root_descriptor = os.open(
            "artifacts",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=root_descriptor,
        )
        try:
            artifact_paths: dict[str, Path] = {}
            artifact_payloads: dict[str, bytes] = {}
            for artifact in bundle.artifacts:
                if artifact.artifact_id in artifact_paths:
                    raise ValueError("duplicate artifact id")
                parts = _safe_parts(artifact.relative_path)
                payload = _read_regular_at(artifact_root_descriptor, parts)
                if hashlib.sha256(payload).hexdigest() != artifact.sha256:
                    raise ValueError(f"artifact hash mismatch: {artifact.artifact_id}")
                artifact_paths[artifact.artifact_id] = resolved / "artifacts" / Path(*parts)
                artifact_payloads[artifact.artifact_id] = payload
        finally:
            os.close(artifact_root_descriptor)
        page_artifacts = [artifact for artifact in bundle.artifacts if artifact.sha256 == bundle.page_sha256]
        if len(page_artifacts) != 1:
            raise ValueError("labeling bundle must reference exactly one current page artifact")
        page_head_payload = (
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
        if hashlib.sha256(page_head_payload).hexdigest() != bundle.page_head_sha256:
            raise ValueError("labeling bundle page head hash is not canonical")
        image_artifacts = [
            artifact for artifact in bundle.artifacts if artifact.sha256 == bundle.image_sha256
        ]
        if len(image_artifacts) != 1:
            raise ValueError("labeling bundle must reference exactly one current image artifact")
        artifact_root_descriptor = os.open(
            "artifacts",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=root_descriptor,
        )
        try:
            image_descriptor = _open_regular_at(
                artifact_root_descriptor,
                _safe_parts(image_artifacts[0].relative_path),
            )
        finally:
            os.close(artifact_root_descriptor)
        image_chunks: list[bytes] = []
        while chunk := os.read(image_descriptor, 1024 * 1024):
            image_chunks.append(chunk)
        image_payload = b"".join(image_chunks)
        if hashlib.sha256(image_payload).hexdigest() != bundle.image_sha256:
            os.close(image_descriptor)
            raise ValueError("current image changed during bundle intake")
        os.close(image_descriptor)
        image_descriptor = _sealed_descriptor(image_payload)
    finally:
        os.close(root_descriptor)
    return LoadedLabelingBundle(
        root=resolved,
        bundle=bundle,
        artifact_paths=artifact_paths,
        artifact_payloads=artifact_payloads,
        image_descriptor=image_descriptor,
    )


def build_project_from_labeling_bundle(loaded: LoadedLabelingBundle) -> Project:
    """Project the one-page portable bundle onto the existing project carrier."""
    image_artifacts = [
        artifact for artifact in loaded.bundle.artifacts if artifact.sha256 == loaded.bundle.image_sha256
    ]
    if len(image_artifacts) != 1:
        raise ValueError("labeling bundle must reference exactly one current image artifact")
    image = Path(f"/proc/self/fd/{loaded.image_descriptor}")
    text = " ".join(word.text for word in loaded.bundle.words)
    page_id_parts = loaded.bundle.page_id.split(":")
    project_id = (
        page_id_parts[1]
        if len(page_id_parts) == 3 and page_id_parts[0] == "pgdp" and page_id_parts[1]
        else loaded.root.name
    )
    return Project(
        project_id=project_id,
        project_root=loaded.root,
        image_paths=[image],
        ground_truth_map={image.name: text},
        source_lib="pdomain-typography-labeling-bundle",
        total_pages=1,
    )


__all__ = [
    "LoadedLabelingBundle",
    "build_project_from_labeling_bundle",
    "load_labeling_bundle_directory",
]

"""Stable typography identities and append-only correction persistence."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, final
from uuid import UUID, uuid4, uuid5

from pdomain_book_tools.typography import (
    CoordinateTransform,
    ModelRun,
    PageGeometry,
    ReplacementArtifact,
    TypographyCorrection,
    WordGeometry,
    make_word_id,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

_PAGE_ID_NAMESPACE = UUID("87638c97-711a-536d-80d2-6963f85ef543")


class TypographyBinding(BaseModel):
    """Current immutable inputs used to reject stale review submissions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    page_sha256: str = Field(min_length=64, max_length=64)
    image_sha256: str = Field(min_length=64, max_length=64)
    text_sha256: str = Field(min_length=64, max_length=64)
    page_head_sha256: str = Field(min_length=64, max_length=64)
    word_revision: int = Field(ge=0)


class TypographyJournalEnvelope(BaseModel):
    """Internal page-scoped wrapper around the released portable correction."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1, le=1)
    logical_page_id: str
    correction: TypographyCorrection
    replacement_artifacts: tuple[ReplacementArtifact, ...] = ()
    page_geometry: PageGeometry | None = None
    geometry: tuple[WordGeometry, ...] | None = None
    model_runs: tuple[ModelRun, ...] = ()
    coordinate_transforms: tuple[CoordinateTransform, ...] = ()

    @field_validator("logical_page_id")
    @classmethod
    def _validate_logical_page_id(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError:
            parts = value.split(":")
            if len(parts) != 3 or parts[0] != "pgdp" or not all(parts[1:]):
                raise ValueError("logical_page_id must be a UUID or canonical PGDP page id") from None
        return value


class StaleTypographyBindingError(ValueError):
    """A correction was based on a page, image, text, or revision no longer current."""


class StaleImportedTextValidationError(ValueError):
    """An imported-text decision was based on a head that is no longer current."""


class ImportedTextBinding(BaseModel):
    """Exact immutable imported word occurrence presented for text review."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str = Field(min_length=64, max_length=64)
    page_id: str
    page_sha256: str = Field(min_length=64, max_length=64)
    page_head_sha256: str = Field(min_length=64, max_length=64)
    word_id: str
    text: str
    text_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("text_sha256")
    @classmethod
    def _text_hash_matches(cls, value: str, info: object) -> str:
        data = getattr(info, "data", {})
        text = data.get("text") if isinstance(data, dict) else None
        if isinstance(text, str) and hashlib.sha256(text.encode()).hexdigest() != value:
            raise ValueError("text_sha256 must identify the exact imported text")
        return value


class ImportedTextValidationHead(BaseModel):
    """Current persistent validation decision for one imported word occurrence."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    binding: ImportedTextBinding
    occurrence_id: str
    revision: int = Field(ge=0)
    validated: bool
    head_token: str = Field(min_length=64, max_length=64)


@final
class ImportedTextValidationLog:
    """Separate append-only journal for explicit imported-bundle text review."""

    _NAME: ClassVar[str] = "imported-text-validations.jsonl"
    _RECOVERY_NAME: ClassVar[str] = "imported-text-validations.recovery.jsonl"

    def __init__(self, project_root: Path, *, corpus_root: Path | None = None) -> None:
        self._files = TypographyCorrectionLog(project_root, corpus_root=corpus_root)
        self.path = self._files.path.with_name(self._NAME)

    @staticmethod
    def _page_key(binding: ImportedTextBinding) -> tuple[str, str, str, str]:
        return (
            binding.bundle_id,
            binding.page_id,
            binding.page_sha256,
            binding.page_head_sha256,
        )

    @staticmethod
    def _token(binding: ImportedTextBinding, *, occurrence_id: str, revision: int, validated: bool) -> str:
        payload = {
            "binding": binding.model_dump(mode="json"),
            "occurrence_id": occurrence_id,
            "revision": revision,
            "validated": validated,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def head(self, binding: ImportedTextBinding) -> ImportedTextValidationHead:
        """Return the current head, recording a new page occurrence when needed."""
        parent, descriptor = self._open(create=True)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            rows, needs_newline = self._read(descriptor, recover=True, parent=parent)
            occurrence_id, changed = self._activate(rows, binding)
            if changed:
                self._append_row(
                    descriptor,
                    {
                        "kind": "activation",
                        "occurrence_id": occurrence_id,
                        "page_key": self._page_key(binding),
                    },
                    needs_newline=needs_newline,
                )
                os.fsync(descriptor)
            return self._head(rows, binding, occurrence_id)
        finally:
            os.close(descriptor)
            os.close(parent)

    def append(
        self, binding: ImportedTextBinding, *, validated: bool, expected_head: str
    ) -> ImportedTextValidationHead:
        """CAS-append an explicit validate or unvalidate decision."""
        parent, descriptor = self._open(create=True)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            rows, needs_newline = self._read(descriptor, recover=True, parent=parent)
            occurrence_id, activated = self._activate(rows, binding)
            if activated:
                self._append_row(
                    descriptor,
                    {
                        "kind": "activation",
                        "occurrence_id": occurrence_id,
                        "page_key": self._page_key(binding),
                    },
                    needs_newline=needs_newline,
                )
                needs_newline = False
            current = self._head(rows, binding, occurrence_id)
            if current.head_token != expected_head:
                raise StaleImportedTextValidationError("expected_head is not current")
            revision = current.revision + 1
            self._append_row(
                descriptor,
                {
                    "kind": "decision",
                    "binding": binding.model_dump(mode="json"),
                    "occurrence_id": occurrence_id,
                    "revision": revision,
                    "validated": validated,
                },
                needs_newline=needs_newline,
            )
            os.fsync(descriptor)
            return self._make_head(binding, occurrence_id, revision, validated)
        finally:
            os.close(descriptor)
            os.close(parent)

    def _open(self, *, create: bool) -> tuple[int, int]:
        parent = self._files._open_journal_directory(create=create)
        try:
            descriptor, created = self._files._open_regular_file(
                parent, self._NAME, flags=os.O_RDWR | os.O_APPEND, create=create
            )
            if created:
                os.fsync(parent)
            return parent, descriptor
        except Exception:
            os.close(parent)
            raise

    def _read(self, descriptor: int, *, recover: bool, parent: int) -> tuple[list[dict[str, object]], bool]:
        _ = os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        raw = b"".join(chunks)
        if not raw:
            return [], False
        terminated = raw.endswith(b"\n")
        lines = raw.split(b"\n")
        if terminated:
            lines.pop()
        trailing = None if terminated else lines.pop()
        rows = [self._parse_row(line) for line in lines]
        if trailing is None:
            return rows, False
        try:
            rows.append(self._parse_row(trailing))
            return rows, True
        except json.JSONDecodeError:
            if not recover:
                raise
            truncate_at = len(raw) - len(trailing)
            os.ftruncate(descriptor, truncate_at)
            os.fsync(descriptor)
            self._write_recovery(parent, trailing, truncate_at)
            return rows, False

    @staticmethod
    def _parse_row(payload: bytes) -> dict[str, object]:
        value = json.loads(payload)
        if not isinstance(value, dict) or value.get("kind") not in {"activation", "decision"}:
            raise ValueError("invalid imported text validation journal record")
        return value

    def _write_recovery(self, parent: int, removed: bytes, truncate_at: int) -> None:
        descriptor, created = self._files._open_regular_file(
            parent, self._RECOVERY_NAME, flags=os.O_WRONLY | os.O_APPEND, create=True
        )
        try:
            self._append_row(
                descriptor,
                {
                    "at": datetime.now(UTC).isoformat(),
                    "removed_bytes": len(removed),
                    "removed_sha256": hashlib.sha256(removed).hexdigest(),
                    "truncate_at": truncate_at,
                },
                needs_newline=False,
            )
            os.fsync(descriptor)
            if created:
                os.fsync(parent)
        finally:
            os.close(descriptor)

    @staticmethod
    def _append_row(descriptor: int, row: object, *, needs_newline: bool) -> None:
        if needs_newline:
            TypographyCorrectionLog._write_all(descriptor, b"\n")
        payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        TypographyCorrectionLog._write_all(descriptor, payload)

    def _activate(self, rows: list[dict[str, object]], binding: ImportedTextBinding) -> tuple[str, bool]:
        last = next((row for row in reversed(rows) if row.get("kind") == "activation"), None)
        page_key = list(self._page_key(binding))
        if last is not None and last.get("page_key") == page_key:
            occurrence = last.get("occurrence_id")
            if isinstance(occurrence, str):
                return occurrence, False
        occurrence_id = str(uuid4())
        rows.append({"kind": "activation", "occurrence_id": occurrence_id, "page_key": page_key})
        return occurrence_id, True

    def _head(
        self, rows: list[dict[str, object]], binding: ImportedTextBinding, occurrence_id: str
    ) -> ImportedTextValidationHead:
        for row in reversed(rows):
            if row.get("kind") != "decision" or row.get("occurrence_id") != occurrence_id:
                continue
            try:
                candidate = ImportedTextBinding.model_validate(row.get("binding"))
            except ValueError:
                continue
            if candidate == binding:
                revision = row.get("revision")
                validated = row.get("validated")
                if isinstance(revision, int) and isinstance(validated, bool):
                    return self._make_head(binding, occurrence_id, revision, validated)
        return self._make_head(binding, occurrence_id, 0, False)

    def _make_head(
        self, binding: ImportedTextBinding, occurrence_id: str, revision: int, validated: bool
    ) -> ImportedTextValidationHead:
        return ImportedTextValidationHead(
            binding=binding,
            occurrence_id=occurrence_id,
            revision=revision,
            validated=validated,
            head_token=self._token(
                binding, occurrence_id=occurrence_id, revision=revision, validated=validated
            ),
        )


def stable_word_id(*, project_id: str, page_id: str, reading_order: int, text: str) -> str:
    """Return the published UUIDv5 identity for an original OCR word."""
    return make_word_id(
        project_id=project_id,
        page_id=page_id,
        reading_order=reading_order,
        text=text,
    )


def stable_page_id(*, project_id: str, page_index: int) -> str:
    """Return a logical page UUID independent of an OCR aggregate generation."""
    if page_index < 0:
        raise ValueError("page_index must be nonnegative")
    return str(uuid5(_PAGE_ID_NAMESPACE, f"{project_id}\0{page_index}"))


@final
class TypographyCorrectionLog:
    """Project-local JSONL journal of immutable canonical corrections.

    The operating-system append lock serializes writers across worker processes.
    A correction is fsynced before ``append`` returns. Existing records are never
    rewritten; supersession is represented only by the canonical revision chain.
    """

    _RELATIVE_PATH: ClassVar[Path] = Path(".pd-pages") / "typography-corrections.jsonl"
    _RECOVERY_NAME: ClassVar[str] = "typography-corrections.recovery.jsonl"

    def __init__(
        self,
        project_root: Path,
        *,
        corpus_root: Path | None = None,
    ) -> None:
        self.project_root = Path(os.path.abspath(project_root))
        self.corpus_root = Path(os.path.abspath(corpus_root or project_root))
        try:
            self._project_relative = self.project_root.relative_to(self.corpus_root)
        except ValueError as exc:
            raise ValueError("project_root must be contained by corpus_root") from exc
        self.path: Path = self.project_root / self._RELATIVE_PATH
        self.recovery_path: Path = self.path.with_name(self._RECOVERY_NAME)

    def append(
        self,
        correction: TypographyCorrection,
        *,
        logical_page_id: str,
        current: TypographyBinding,
        replacement_artifacts: tuple[ReplacementArtifact, ...] = (),
        page_geometry: PageGeometry | None = None,
        geometry: tuple[WordGeometry, ...] | None = None,
        model_runs: tuple[ModelRun, ...] = (),
        coordinate_transforms: tuple[CoordinateTransform, ...] = (),
        artifact_payloads: tuple[tuple[ReplacementArtifact, bytes], ...] = (),
    ) -> None:
        """Validate current bindings and durably append one correction."""
        parent_descriptor = self._open_journal_directory(create=True)
        try:
            descriptor, created = self._open_regular_file(
                parent_descriptor,
                self.path.name,
                flags=os.O_RDWR | os.O_APPEND,
                create=True,
            )
            if created:
                os.fsync(parent_descriptor)
        except Exception:
            os.close(parent_descriptor)
            raise
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            records, needs_newline = self._read_descriptor(
                descriptor,
                recover_trailing=True,
                parent_descriptor=parent_descriptor,
            )
            page_id = logical_page_id
            self._validate_append(
                correction,
                logical_page_id=page_id,
                current=current,
                records=records,
            )
            for artifact, artifact_payload in artifact_payloads:
                self._publish_artifact_locked(parent_descriptor, artifact, artifact_payload)
            if needs_newline:
                self._write_all(descriptor, b"\n")
            payload = (
                json.dumps(
                    TypographyJournalEnvelope(
                        logical_page_id=page_id,
                        correction=correction,
                        replacement_artifacts=replacement_artifacts,
                        page_geometry=page_geometry,
                        geometry=geometry,
                        model_runs=model_runs,
                        coordinate_transforms=coordinate_transforms,
                    ).model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
            self._write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            os.close(parent_descriptor)

    def read_artifact(self, sha256: str) -> bytes:
        """Read and revalidate one server-owned content-addressed artifact."""
        if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
            raise ValueError("invalid artifact hash")
        journal_descriptor = self._open_journal_directory(create=False)
        try:
            artifact_descriptor = os.open(
                "typography-artifacts",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=journal_descriptor,
            )
        finally:
            os.close(journal_descriptor)
        try:
            descriptor, _created = self._open_regular_file(
                artifact_descriptor, sha256, flags=os.O_RDONLY, create=False
            )
            try:
                chunks: list[bytes] = []
                while chunk := os.read(descriptor, 1024 * 1024):
                    chunks.append(chunk)
                payload = b"".join(chunks)
            finally:
                os.close(descriptor)
        finally:
            os.close(artifact_descriptor)
        if hashlib.sha256(payload).hexdigest() != sha256:
            raise ValueError("stored artifact hash mismatch")
        return payload

    def _publish_artifact_locked(
        self,
        journal_descriptor: int,
        artifact: ReplacementArtifact,
        payload: bytes,
    ) -> None:
        if len(payload) != artifact.byte_size or hashlib.sha256(payload).hexdigest() != artifact.sha256:
            raise ValueError("replacement artifact bytes do not match declared provenance")
        try:
            os.mkdir("typography-artifacts", mode=0o700, dir_fd=journal_descriptor)
            os.fsync(journal_descriptor)
        except FileExistsError:
            pass
        artifact_descriptor = os.open(
            "typography-artifacts",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=journal_descriptor,
        )
        try:
            try:
                existing = self.read_artifact(artifact.sha256)
            except FileNotFoundError:
                temporary_name = f".{artifact.sha256}.{uuid4().hex}.tmp"
                try:
                    descriptor = os.open(
                        temporary_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=artifact_descriptor,
                    )
                    try:
                        self._write_all(descriptor, payload)
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                    os.rename(
                        temporary_name,
                        artifact.sha256,
                        src_dir_fd=artifact_descriptor,
                        dst_dir_fd=artifact_descriptor,
                    )
                    os.fsync(artifact_descriptor)
                except Exception:
                    with suppress(FileNotFoundError):
                        os.unlink(temporary_name, dir_fd=artifact_descriptor)
                    raise
            else:
                if existing != payload:
                    raise ValueError("content-addressed artifact conflict")
        finally:
            os.close(artifact_descriptor)

    def head(self, logical_page_id: str, word_id: str) -> TypographyCorrection | None:
        """Return the latest appended correction for a stable word."""
        try:
            parent_descriptor = self._open_journal_directory(create=False)
        except FileNotFoundError:
            return None
        try:
            descriptor, _created = self._open_regular_file(
                parent_descriptor,
                self.path.name,
                flags=os.O_RDONLY,
                create=False,
            )
        except FileNotFoundError:
            os.close(parent_descriptor)
            return None
        except Exception:
            os.close(parent_descriptor)
            raise
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH)
            records, _needs_newline = self._read_descriptor(
                descriptor,
                recover_trailing=False,
                parent_descriptor=parent_descriptor,
            )
        finally:
            os.close(descriptor)
            os.close(parent_descriptor)
        envelope = self._word_head(records, logical_page_id, word_id)
        return envelope.correction if envelope is not None else None

    def records(self, logical_page_id: str | None = None) -> tuple[TypographyJournalEnvelope, ...]:
        """Return a stable snapshot of valid journal records, optionally for one page."""
        try:
            parent_descriptor = self._open_journal_directory(create=False)
        except FileNotFoundError:
            return ()
        try:
            descriptor, _created = self._open_regular_file(
                parent_descriptor, self.path.name, flags=os.O_RDONLY, create=False
            )
        except FileNotFoundError:
            os.close(parent_descriptor)
            return ()
        except Exception:
            os.close(parent_descriptor)
            raise
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH)
            records, _needs_newline = self._read_descriptor(
                descriptor, recover_trailing=False, parent_descriptor=parent_descriptor
            )
        finally:
            os.close(descriptor)
            os.close(parent_descriptor)
        if logical_page_id is None:
            return tuple(records)
        page_id = logical_page_id
        return tuple(record for record in records if record.logical_page_id == page_id)

    def publish_export(self, name: str, payload: bytes) -> None:
        """Publish immutable export bytes below the no-follow journal directory."""
        if not name or name != Path(name).name:
            raise ValueError("export name must be one safe path component")
        journal_descriptor = self._open_journal_directory(create=True)
        try:
            try:
                os.mkdir("typography-exports", mode=0o700, dir_fd=journal_descriptor)
                os.fsync(journal_descriptor)
            except FileExistsError:
                pass
            export_descriptor = os.open(
                "typography-exports",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=journal_descriptor,
            )
        finally:
            os.close(journal_descriptor)
        try:
            fcntl.flock(export_descriptor, fcntl.LOCK_EX)
            try:
                descriptor, _created = self._open_regular_file(
                    export_descriptor,
                    name,
                    flags=os.O_RDONLY,
                    create=False,
                )
                try:
                    chunks: list[bytes] = []
                    while chunk := os.read(descriptor, 1024 * 1024):
                        chunks.append(chunk)
                    if b"".join(chunks) != payload:
                        raise FileExistsError("content-addressed export path conflict")
                finally:
                    os.close(descriptor)
            except FileNotFoundError:
                temporary_name = f".{name}.{uuid4().hex}.tmp"
                try:
                    descriptor = os.open(
                        temporary_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=export_descriptor,
                    )
                    try:
                        self._write_all(descriptor, payload)
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                    os.rename(
                        temporary_name,
                        name,
                        src_dir_fd=export_descriptor,
                        dst_dir_fd=export_descriptor,
                    )
                    os.fsync(export_descriptor)
                except Exception:
                    with suppress(FileNotFoundError):
                        os.unlink(temporary_name, dir_fd=export_descriptor)
                    raise
        finally:
            os.close(export_descriptor)

    @staticmethod
    def _open_absolute_directory(path: Path) -> int:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in path.parts[1:]:
                next_descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    def _open_journal_directory(self, *, create: bool) -> int:
        descriptor = self._open_absolute_directory(self.corpus_root)
        try:
            for component in self._project_relative.parts:
                next_descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                os.close(descriptor)
                descriptor = next_descriptor
            if create:
                try:
                    os.mkdir(".pd-pages", mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(
                ".pd-pages",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            return next_descriptor
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def _open_regular_file(
        parent_descriptor: int,
        name: str,
        *,
        flags: int,
        create: bool,
    ) -> tuple[int, bool]:
        safe_flags = flags | os.O_NOFOLLOW | os.O_NONBLOCK
        created = False
        if create:
            try:
                descriptor = os.open(
                    name,
                    safe_flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_descriptor,
                )
                created = True
            except FileExistsError:
                descriptor = os.open(name, safe_flags, dir_fd=parent_descriptor)
        else:
            descriptor = os.open(name, safe_flags, dir_fd=parent_descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise OSError("typography journal must be a regular file")
        return descriptor, created

    def _read_descriptor(
        self,
        descriptor: int,
        *,
        recover_trailing: bool,
        parent_descriptor: int,
    ) -> tuple[list[TypographyJournalEnvelope], bool]:
        _ = os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        raw = b"".join(chunks)
        if not raw:
            return [], False
        terminated = raw.endswith(b"\n")
        lines = raw.split(b"\n")
        if terminated:
            lines.pop()
        trailing = None if terminated else lines.pop()
        records: list[TypographyJournalEnvelope] = []
        for line in lines:
            if not line.strip():
                raise ValueError("typography journal contains an empty interior record")
            records.append(self._parse_envelope(line))
        if trailing is None:
            return records, False
        try:
            records.append(self._parse_envelope(trailing))
            return records, True
        except json.JSONDecodeError:
            if not recover_trailing:
                raise
            truncate_at = len(raw) - len(trailing)
            os.ftruncate(descriptor, truncate_at)
            os.fsync(descriptor)
            self._write_recovery_audit(parent_descriptor, trailing, truncate_at=truncate_at)
            return records, False

    def _write_recovery_audit(
        self,
        parent_descriptor: int,
        removed: bytes,
        *,
        truncate_at: int,
    ) -> None:
        descriptor, created = self._open_regular_file(
            parent_descriptor,
            self._RECOVERY_NAME,
            flags=os.O_WRONLY | os.O_APPEND,
            create=True,
        )

        try:
            payload = {
                "at": datetime.now(UTC).isoformat(),
                "removed_bytes": len(removed),
                "removed_sha256": hashlib.sha256(removed).hexdigest(),
                "truncate_at": truncate_at,
            }
            self._write_all(
                descriptor,
                (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            )
            os.fsync(descriptor)
            if created:
                os.fsync(parent_descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def current_epoch(
        records: list[TypographyJournalEnvelope] | tuple[TypographyJournalEnvelope, ...],
        *,
        logical_page_id: str,
        current: TypographyBinding,
    ) -> tuple[TypographyJournalEnvelope, ...]:
        """Return the latest journal segment rooted in the persisted page."""
        page_records = [record for record in records if record.logical_page_id == logical_page_id]
        epoch_start = 0
        for index in range(1, len(page_records)):
            previous = page_records[index - 1].correction
            candidate = page_records[index].correction
            if (
                candidate.base_page_sha256 != previous.effective_page_sha256
                or candidate.base_image_sha256 != previous.effective_image_sha256
                or candidate.page_head_sha256 != previous.effective_page_head_sha256
            ):
                epoch_start = index
        epoch = tuple(page_records[epoch_start:])
        if not epoch:
            return ()
        root = epoch[0].correction
        if (
            root.base_page_sha256 != current.page_sha256
            or root.base_image_sha256 != current.image_sha256
            or root.page_head_sha256 != current.page_head_sha256
        ):
            return ()
        return epoch

    @staticmethod
    def _write_all(descriptor: int, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - operating-system failure
                raise OSError("append-only typography journal write made no progress")
            view = view[written:]

    def _parse_envelope(self, payload: bytes) -> TypographyJournalEnvelope:
        raw = json.loads(payload)
        if isinstance(raw, dict) and "correction_id" in raw:
            raise ValueError(
                "legacy bare typography correction rows are unsupported; repair or export to v1 envelopes"
            )
        return TypographyJournalEnvelope.model_validate(raw)

    @staticmethod
    def _word_head(
        records: list[TypographyJournalEnvelope],
        logical_page_id: str,
        word_id: str,
    ) -> TypographyJournalEnvelope | None:
        return next(
            (
                record
                for record in reversed(records)
                if record.logical_page_id == logical_page_id and record.correction.word_id == word_id
            ),
            None,
        )

    @classmethod
    def _validate_append(
        cls,
        correction: TypographyCorrection,
        *,
        logical_page_id: str,
        current: TypographyBinding,
        records: list[TypographyJournalEnvelope],
    ) -> None:
        epoch = cls.current_epoch(records, logical_page_id=logical_page_id, current=current)
        epoch_records = list(epoch)
        previous_envelope = cls._word_head(epoch_records, logical_page_id, correction.word_id)
        previous = previous_envelope.correction if previous_envelope is not None else None
        page_head_envelope = next(
            (record for record in reversed(epoch_records) if record.logical_page_id == logical_page_id),
            None,
        )
        page_head = page_head_envelope.correction if page_head_envelope is not None else None
        if page_head is None:
            page_expected = {
                "base_page_sha256": current.page_sha256,
                "base_image_sha256": current.image_sha256,
                "page_head_sha256": current.page_head_sha256,
            }
        else:
            page_expected = {
                "base_page_sha256": page_head.effective_page_sha256,
                "base_image_sha256": page_head.effective_image_sha256,
                "page_head_sha256": page_head.effective_page_head_sha256,
            }
        expected = {
            **page_expected,
            "base_text_sha256": (
                previous.effective_text_sha256 if previous is not None else current.text_sha256
            ),
            "base_word_revision": (
                previous.effective_word_revision
                if previous is not None
                else (current.word_revision if page_head is None else 0)
            ),
        }
        for field_name, expected_value in expected.items():
            if getattr(correction, field_name) != expected_value:
                raise StaleTypographyBindingError(
                    f"{field_name} does not match the current typography binding"
                )

        if any(record.correction.correction_id == correction.correction_id for record in records):
            raise StaleTypographyBindingError("correction_id was already appended")

        expected_revision = 1 if previous is None else previous.revision + 1
        expected_supersedes = None if previous is None else previous.correction_id
        if correction.revision != expected_revision:
            raise StaleTypographyBindingError(
                f"revision must be {expected_revision} for the current word head"
            )
        if correction.supersedes_id != expected_supersedes:
            raise StaleTypographyBindingError("supersedes_id does not identify the current word correction")


__all__ = [
    "ImportedTextBinding",
    "ImportedTextValidationHead",
    "ImportedTextValidationLog",
    "StaleImportedTextValidationError",
    "StaleTypographyBindingError",
    "TypographyBinding",
    "TypographyCorrectionLog",
    "TypographyJournalEnvelope",
    "stable_page_id",
    "stable_word_id",
]

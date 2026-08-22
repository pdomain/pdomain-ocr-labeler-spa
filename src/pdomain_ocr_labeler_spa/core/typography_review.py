"""Stable typography identities and append-only correction persistence."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, final
from uuid import UUID, uuid5

from pdomain_book_tools.typography import TypographyCorrection, make_word_id
from pydantic import BaseModel, ConfigDict, Field

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
    logical_page_id: UUID
    correction: TypographyCorrection


class StaleTypographyBindingError(ValueError):
    """A correction was based on a page, image, text, or revision no longer current."""


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
            page_id = UUID(logical_page_id)
            self._validate_append(
                correction,
                logical_page_id=page_id,
                current=current,
                records=records,
            )
            if needs_newline:
                self._write_all(descriptor, b"\n")
            payload = (
                json.dumps(
                    TypographyJournalEnvelope(
                        logical_page_id=page_id,
                        correction=correction,
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
        envelope = self._word_head(records, UUID(logical_page_id), word_id)
        return envelope.correction if envelope is not None else None

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
        logical_page_id: UUID,
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
        logical_page_id: UUID,
        current: TypographyBinding,
        records: list[TypographyJournalEnvelope],
    ) -> None:
        previous_envelope = cls._word_head(records, logical_page_id, correction.word_id)
        previous = previous_envelope.correction if previous_envelope is not None else None
        page_head_envelope = next(
            (record for record in reversed(records) if record.logical_page_id == logical_page_id),
            None,
        )
        page_head = page_head_envelope.correction if page_head_envelope is not None else None
        if page_head is None:
            page_expected = {
                "base_page_sha256": current.page_sha256,
                "base_image_sha256": current.image_sha256,
                "base_text_sha256": current.text_sha256,
                "page_head_sha256": current.page_head_sha256,
            }
        else:
            page_expected = {
                "base_page_sha256": page_head.effective_page_sha256,
                "base_image_sha256": page_head.effective_image_sha256,
                "base_text_sha256": page_head.effective_text_sha256,
                "page_head_sha256": page_head.effective_page_head_sha256,
            }
        expected = {
            **page_expected,
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
    "StaleTypographyBindingError",
    "TypographyBinding",
    "TypographyCorrectionLog",
    "stable_page_id",
    "stable_word_id",
]

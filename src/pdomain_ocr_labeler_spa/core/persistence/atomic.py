"""Atomic write helpers. Spec: specs/2026-05-12-persistence-design.md § Atomic write helper."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _current_umask() -> int:
    """Read the process umask without leaving it changed."""
    value = os.umask(0)
    _ = os.umask(value)
    return value


def publish_atomic(tmp_name: str, path: Path) -> None:
    """Widen the staged file to the umask default, then rename it into place.

    ``tempfile.mkstemp`` hardcodes 0600 and ignores the umask by design, and
    ``os.replace`` preserves the temp file's mode. Without this chmod every
    file written here lands at 0600 regardless of the umask, which locks out
    any reader running as a different uid — including the host's restic
    backup. Start from 0666, never 0777: nothing written here is a program.
    """
    os.chmod(tmp_name, 0o666 & ~_current_umask())
    os.replace(tmp_name, path)


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON data atomically via a unique temp file + os.replace.

    The temp file is created in the same directory as ``path`` so that
    ``os.replace`` is a same-filesystem rename (atomic on POSIX; atomic
    on Windows via ``MoveFileExW(MOVEFILE_REPLACE_EXISTING)``).

    Using a random temp name (via ``tempfile.NamedTemporaryFile``) avoids
    the deterministic-name collision that would occur when two processes
    write the same target file concurrently — each writer gets its own
    private temp file and the last ``os.replace`` wins atomically.
    """
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        publish_atomic(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write bytes data atomically via a unique temp file + os.replace.

    See ``write_json_atomic`` for the rationale behind the random temp name.
    """
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        publish_atomic(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise

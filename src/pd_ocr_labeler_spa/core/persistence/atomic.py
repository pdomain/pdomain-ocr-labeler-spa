"""Atomic write helpers. Spec: specs/2026-05-12-persistence-design.md § Atomic write helper."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


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
        os.replace(tmp_name, path)
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
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise

"""Atomic write helpers. Spec: specs/2026-05-12-persistence-design.md § Atomic write helper."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


def open_staged(path: Path) -> tuple[int, Path]:
    """Create a staging file beside *path*, open for writing.

    Returns the file descriptor and the staging path. The caller writes, then
    renames it over *path*; the rename is a same-filesystem move because the
    staging file is a sibling, so it is atomic on POSIX and on Windows via
    ``MoveFileExW(MOVEFILE_REPLACE_EXISTING)``.

    This does not use ``tempfile.mkstemp``. That hardcodes 0600 and ignores
    the umask, which is right for a private scratch file and wrong for one
    about to be published: a rename preserves the mode, so the result was
    unreadable to any other uid, the host's backup included. Passing the mode
    to ``os.open`` lets the kernel apply the umask exactly as it does for a
    plain ``open()``, so no chmod and no umask read are needed. 0666 rather
    than 0777 because nothing published this way is a program.

    ``O_EXCL`` gives the same guarantee ``mkstemp`` provides: creation fails
    rather than opening an existing file or following a symlink into one. The
    random name makes a collision between concurrent writers vanishingly
    unlikely, and the retry makes it harmless if it ever happens.
    """
    while True:
        staged = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            return os.open(staged, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666), staged
        except FileExistsError:  # pragma: no cover - needs a uuid4 collision
            continue


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON data atomically: staged sibling file, then rename."""
    path = Path(path)
    fd, staged = open_staged(path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        staged.replace(path)
    except Exception:
        with contextlib.suppress(OSError):
            staged.unlink()
        raise


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write bytes atomically: staged sibling file, then rename."""
    path = Path(path)
    fd, staged = open_staged(path)
    try:
        with os.fdopen(fd, "wb") as f:
            _ = f.write(data)
        staged.replace(path)
    except Exception:
        with contextlib.suppress(OSError):
            staged.unlink()
        raise

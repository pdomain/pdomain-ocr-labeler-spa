"""Atomic write helpers to prevent partial files on crash.

Spec: `specs/2026-05-12-persistence-design.md` § Atomic write helper.

`write_json_atomic(path, data)` and `write_bytes_atomic(path, data)` write
to a `.tmp` file then `os.replace` to the target path atomically.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON data atomically via tmp+replace.

    Writes to `path.with_suffix('.tmp')` first, then atomically replaces
    the target with `os.replace`. Prevents partial files on crash.

    Args:
        path: Target file path.
        data: JSON-serializable data.
    """
    path = Path(path)
    tmp_path = path.with_suffix(".tmp")

    with open(tmp_path, "w") as f:
        json.dump(data, f)

    os.replace(tmp_path, path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write bytes atomically via tmp+replace.

    Writes to `path.with_suffix('.tmp')` first, then atomically replaces
    the target with `os.replace`. Prevents partial files on crash.

    Args:
        path: Target file path.
        data: Bytes to write.
    """
    path = Path(path)
    tmp_path = path.with_suffix(".tmp")

    with open(tmp_path, "wb") as f:
        f.write(data)

    os.replace(tmp_path, path)

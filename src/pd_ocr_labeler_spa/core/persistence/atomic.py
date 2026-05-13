"""Atomic write helpers. Spec: specs/2026-05-12-persistence-design.md § Atomic write helper."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON data atomically via tmp+replace."""
    path = Path(path)
    tmp_path = path.with_suffix(".tmp")

    with open(tmp_path, "w") as f:
        json.dump(data, f)

    os.replace(tmp_path, path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write bytes data atomically via tmp+replace."""
    path = Path(path)
    tmp_path = path.with_suffix(".tmp")

    with open(tmp_path, "wb") as f:
        f.write(data)

    os.replace(tmp_path, path)

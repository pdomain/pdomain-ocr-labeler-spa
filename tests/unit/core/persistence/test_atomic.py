"""Tests for atomic write helpers.

Spec: `specs/2026-05-12-persistence-design.md` § Atomic write helper.

Acceptance:
- `write_json_atomic` writes to `.tmp` then `os.replace`
- `write_bytes_atomic` similarly atomic
- Power-fail test: no partial file left after mid-write exit
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.persistence.atomic import (
    write_bytes_atomic,
    write_json_atomic,
)


class TestWriteJsonAtomic:
    """Test `write_json_atomic` atomicity."""

    def test_writes_json_data(self, tmp_path: Path) -> None:
        """JSON data is written correctly."""
        target = tmp_path / "test.json"
        data = {"key": "value", "nested": {"int": 42, "list": [1, 2, 3]}}

        write_json_atomic(target, data)

        assert target.exists()
        with open(target) as f:
            assert json.load(f) == data

    def test_uses_tmp_suffix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`write_json_atomic` writes to `.tmp` before replace."""
        target = tmp_path / "test.json"
        data = {"test": True}

        # Track open calls to verify `.tmp` file is used
        open_calls = []
        original_open = open

        def tracked_open(path, *args, **kwargs):
            open_calls.append(str(path))
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", tracked_open)

        write_json_atomic(target, data)

        # Verify .tmp file was created and written to
        tmp_path_str = str(target.with_suffix(".tmp"))
        assert tmp_path_str in open_calls
        # The .tmp file should have been replaced, so it shouldn't exist anymore
        assert not target.with_suffix(".tmp").exists()
        assert target.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Existing target file is overwritten."""
        target = tmp_path / "test.json"
        target.write_text("old data")

        data = {"new": "data"}
        write_json_atomic(target, data)

        assert json.loads(target.read_text()) == data

    def test_handles_complex_nested_structures(self, tmp_path: Path) -> None:
        """Complex nested JSON structures are preserved."""
        target = tmp_path / "complex.json"
        data = {
            "users": [
                {"id": 1, "name": "Alice", "tags": ["admin", "user"]},
                {"id": 2, "name": "Bob", "tags": []},
            ],
            "metadata": {
                "version": "1.0",
                "nested": {"deeply": {"buried": {"value": True}}},
            },
        }

        write_json_atomic(target, data)

        assert json.loads(target.read_text()) == data


class TestWriteBytesAtomic:
    """Test `write_bytes_atomic` atomicity."""

    def test_writes_bytes_data(self, tmp_path: Path) -> None:
        """Bytes data is written correctly."""
        target = tmp_path / "test.bin"
        data = b"binary data \x00\x01\x02\xff"

        write_bytes_atomic(target, data)

        assert target.exists()
        assert target.read_bytes() == data

    def test_uses_tmp_suffix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`write_bytes_atomic` writes to `.tmp` before replace."""
        target = tmp_path / "test.bin"
        data = b"test data"

        # Track open calls
        open_calls = []
        original_open = open

        def tracked_open(path, *args, **kwargs):
            open_calls.append(str(path))
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", tracked_open)

        write_bytes_atomic(target, data)

        # Verify .tmp file was created and written to
        tmp_path_str = str(target.with_suffix(".tmp"))
        assert tmp_path_str in open_calls
        # The .tmp file should have been replaced
        assert not target.with_suffix(".tmp").exists()
        assert target.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Existing target file is overwritten."""
        target = tmp_path / "test.bin"
        target.write_bytes(b"old")

        data = b"new binary data"
        write_bytes_atomic(target, data)

        assert target.read_bytes() == data

    def test_handles_binary_data_with_nulls(self, tmp_path: Path) -> None:
        """Binary data with null bytes is preserved."""
        target = tmp_path / "binary.dat"
        data = bytes(range(256))  # All byte values

        write_bytes_atomic(target, data)

        assert target.read_bytes() == data


class TestAtomicityPowerFailSimulation:
    """Test atomicity via power-fail simulation (fork+exit between write and replace)."""

    def test_json_no_partial_file_on_mid_write_exit(self, tmp_path: Path) -> None:
        """No partial `.json` file left if process exits between write and replace.

        This simulates a power failure by forking and calling `os._exit(1)`
        after writing the temp file but before `os.replace`.
        """
        target = tmp_path / "test.json"
        test_script = tmp_path / "test_crash.py"
        data = {"key": "value"}

        # Create a test script that exits mid-operation
        test_script.write_text(
            f"""
import os
import sys
sys.path.insert(0, {sys.path[0]!r})

from pd_ocr_labeler_spa.core.persistence.atomic import write_json_atomic
from pathlib import Path

target = Path({str(target)!r})
data = {data!r}

# Monkey-patch os.replace to exit before it completes
original_replace = os.replace
def crashing_replace(src, dst):
    # Simulate crash between write_text and replace
    os._exit(1)

os.replace = crashing_replace

try:
    write_json_atomic(target, data)
except SystemExit:
    pass
"""
        )

        # Run the script in a subprocess that will crash
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
        )

        # Process should have exited abnormally
        assert result.returncode != 0

        # The target file should NOT exist (crashed before replace)
        assert not target.exists()

        # The .tmp file should exist (was written but not replaced)
        tmp_file = target.with_suffix(".tmp")
        assert tmp_file.exists()

    def test_bytes_no_partial_file_on_mid_write_exit(self, tmp_path: Path) -> None:
        """No partial `.bin` file left if process exits between write and replace.

        This simulates a power failure by forking and calling `os._exit(1)`
        after writing the temp file but before `os.replace`.
        """
        target = tmp_path / "test.bin"
        test_script = tmp_path / "test_crash.py"
        data = b"binary content"

        # Create a test script that exits mid-operation
        test_script.write_text(
            f"""
import os
import sys
sys.path.insert(0, {sys.path[0]!r})

from pd_ocr_labeler_spa.core.persistence.atomic import write_bytes_atomic
from pathlib import Path

target = Path({str(target)!r})
data = {data!r}

# Monkey-patch os.replace to exit before it completes
original_replace = os.replace
def crashing_replace(src, dst):
    # Simulate crash between write and replace
    os._exit(1)

os.replace = crashing_replace

try:
    write_bytes_atomic(target, data)
except SystemExit:
    pass
"""
        )

        # Run the script in a subprocess that will crash
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
        )

        # Process should have exited abnormally
        assert result.returncode != 0

        # The target file should NOT exist (crashed before replace)
        assert not target.exists()

        # The .tmp file should exist (was written but not replaced)
        tmp_file = target.with_suffix(".tmp")
        assert tmp_file.exists()

    def test_idempotent_after_power_fail(self, tmp_path: Path) -> None:
        """After a power failure, retrying the write succeeds.

        If a crash leaves a .tmp file, the next write attempt should
        clean it up and succeed.
        """
        target = tmp_path / "test.json"
        tmp_file = target.with_suffix(".tmp")

        # Simulate leftover .tmp file from crashed write
        tmp_file.write_text("incomplete json")

        # New write should succeed and replace .tmp + target
        data = {"recovered": True}
        write_json_atomic(target, data)

        assert target.exists()
        assert json.loads(target.read_text()) == data
        # Old .tmp should be gone
        assert not tmp_file.exists()

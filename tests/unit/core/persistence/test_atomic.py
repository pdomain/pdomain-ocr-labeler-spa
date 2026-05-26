"""Tests for atomic write helpers. Spec: specs/2026-05-12-persistence-design.md § Atomic write helper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
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

    def test_uses_tmp_file_in_same_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`write_json_atomic` creates a temp file in the same dir before replace.

        We can't predict the exact random name, but we can assert:
        - a ``*.tmp`` file exists in the parent dir during the write, and
        - no ``*.tmp`` files remain afterwards.
        """
        target = tmp_path / "test.json"
        data = {"test": True}
        tmp_files_during_write: list[list[str]] = []

        original_replace = os.replace

        def patched_replace(src: str, dst: str) -> None:
            # Capture any .tmp files in the parent dir just before the rename.
            parent = Path(dst).parent
            tmp_files_during_write.append([p.name for p in parent.glob("*.tmp")])
            original_replace(src, dst)

        monkeypatch.setattr(os, "replace", patched_replace)

        write_json_atomic(target, data)

        # At least one .tmp existed in the same directory just before replace.
        assert tmp_files_during_write, "os.replace was never called"
        assert len(tmp_files_during_write[0]) >= 1, "no *.tmp in parent dir during write"

        # No .tmp files remain after the call.
        remaining_tmp = list(tmp_path.glob("*.tmp"))
        assert remaining_tmp == []
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

    def test_concurrent_writes_produce_unique_temp_names(self, tmp_path: Path) -> None:
        """Concurrent writes to the same target each get a distinct temp file.

        Both writers should succeed (last one wins via os.replace); the key
        property is that neither collides with the other's temp file, so no
        ``FileNotFoundError`` or torn write occurs.  After both finish, the
        target exists and no ``.tmp`` files remain.
        """
        target = tmp_path / "shared.json"
        n = 8

        def write_i(i: int) -> None:
            write_json_atomic(target, {"writer": i})

        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(write_i, range(n)))

        assert target.exists()
        result = json.loads(target.read_text())
        assert "writer" in result  # one of the n writes won
        assert list(tmp_path.glob("*.tmp")) == []  # no leftover temp files


class TestWriteBytesAtomic:
    """Test `write_bytes_atomic` atomicity."""

    def test_writes_bytes_data(self, tmp_path: Path) -> None:
        """Bytes data is written correctly."""
        target = tmp_path / "test.bin"
        data = b"binary data \x00\x01\x02\xff"

        write_bytes_atomic(target, data)

        assert target.exists()
        assert target.read_bytes() == data

    def test_uses_tmp_file_in_same_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`write_bytes_atomic` creates a temp file in the same dir before replace."""
        target = tmp_path / "test.bin"
        data = b"test data"
        tmp_files_during_write: list[list[str]] = []

        original_replace = os.replace

        def patched_replace(src: str, dst: str) -> None:
            parent = Path(dst).parent
            tmp_files_during_write.append([p.name for p in parent.glob("*.tmp")])
            original_replace(src, dst)

        monkeypatch.setattr(os, "replace", patched_replace)

        write_bytes_atomic(target, data)

        assert tmp_files_during_write, "os.replace was never called"
        assert len(tmp_files_during_write[0]) >= 1

        remaining_tmp = list(tmp_path.glob("*.tmp"))
        assert remaining_tmp == []
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

    def test_concurrent_writes_produce_unique_temp_names(self, tmp_path: Path) -> None:
        """Concurrent byte writes each get a distinct temp file, no collisions."""
        target = tmp_path / "shared.bin"
        n = 8

        def write_i(i: int) -> None:
            write_bytes_atomic(target, f"writer-{i}".encode())

        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(write_i, range(n)))

        assert target.exists()
        assert list(tmp_path.glob("*.tmp")) == []


class TestAtomicityCleanupOnFailure:
    """Test that temp files are cleaned up if os.replace raises."""

    def test_json_cleans_up_tmp_on_replace_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If os.replace raises, the temp file is removed (no orphan)."""
        target = tmp_path / "test.json"

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", failing_replace)

        with pytest.raises(OSError, match="simulated replace failure"):
            write_json_atomic(target, {"x": 1})

        assert not target.exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_bytes_cleans_up_tmp_on_replace_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If os.replace raises, the temp file is removed (no orphan)."""
        target = tmp_path / "test.bin"

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", failing_replace)

        with pytest.raises(OSError, match="simulated replace failure"):
            write_bytes_atomic(target, b"data")

        assert not target.exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_idempotent_after_power_fail_leftover(self, tmp_path: Path) -> None:
        """After a crash that leaves a stale ``.tmp`` file, a new write succeeds.

        The new writer creates its own unique temp name — it does NOT clobber
        the stale one, and after completion both stale and target state is clean.
        """
        target = tmp_path / "test.json"
        stale_tmp = tmp_path / "stale_crash.json.tmp"
        stale_tmp.write_text("incomplete json")

        # New write should succeed regardless of the stale file
        data = {"recovered": True}
        write_json_atomic(target, data)

        assert target.exists()
        assert json.loads(target.read_text()) == data
        # The new writer's temp file was cleaned up (os.replace succeeded)
        # The stale file is NOT touched by the new writer — it remains
        # as an orphan (operator cleans it up separately, or next writer
        # for that file will overwrite it via os.replace).
        # What matters: the target is correct and no NEW .tmp orphans were left.
        new_tmps = [p for p in tmp_path.glob("*.tmp") if p != stale_tmp]
        assert new_tmps == []


class TestAtomicityPowerFailSimulation:
    """Test atomicity via power-fail simulation (subprocess exit between write and replace)."""

    def test_json_no_partial_file_on_mid_write_exit(self, tmp_path: Path) -> None:
        """No partial `.json` file left if process exits between write and replace."""
        target = tmp_path / "test.json"
        test_script = tmp_path / "test_crash.py"
        data = {"key": "value"}

        test_script.write_text(
            f"""
import os
import sys
import tempfile
sys.path.insert(0, {sys.path[0]!r})

from pathlib import Path

target = Path({str(target)!r})

# Monkey-patch os.replace to exit before it completes
original_replace = os.replace
def crashing_replace(src, dst):
    os._exit(1)

os.replace = crashing_replace

from pd_ocr_labeler_spa.core.persistence.atomic import write_json_atomic

try:
    write_json_atomic(target, {data!r})
except SystemExit:
    pass
"""
        )

        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
        )

        assert result.returncode != 0
        # The target file should NOT exist (crashed before replace)
        assert not target.exists()
        # At least one .tmp orphan should exist (the crashed write left it)
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 1

    def test_bytes_no_partial_file_on_mid_write_exit(self, tmp_path: Path) -> None:
        """No partial `.bin` file left if process exits between write and replace."""
        target = tmp_path / "test.bin"
        test_script = tmp_path / "test_crash.py"
        data = b"binary content"

        test_script.write_text(
            f"""
import os
import sys
sys.path.insert(0, {sys.path[0]!r})

from pathlib import Path

target = Path({str(target)!r})

original_replace = os.replace
def crashing_replace(src, dst):
    os._exit(1)

os.replace = crashing_replace

from pd_ocr_labeler_spa.core.persistence.atomic import write_bytes_atomic

try:
    write_bytes_atomic(target, {data!r})
except SystemExit:
    pass
"""
        )

        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
        )

        assert result.returncode != 0
        assert not target.exists()
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 1

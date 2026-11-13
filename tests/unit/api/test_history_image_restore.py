"""Rotate-boundary image restore rolls back when the slot save fails."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdomain_ocr_labeler_spa.api.history import _replace_image_then


def test_a_failed_slot_save_puts_the_previous_image_back(tmp_path: Path) -> None:
    image = tmp_path / "001.png"
    image.write_bytes(b"old-scan")

    def save() -> None:
        raise RuntimeError("store")

    with pytest.raises(RuntimeError, match="store"):
        _replace_image_then(image, b"other-generation", save)
    assert image.read_bytes() == b"old-scan"
    assert list(tmp_path.iterdir()) == [image]


def test_a_successful_slot_save_keeps_the_restored_image(tmp_path: Path) -> None:
    image = tmp_path / "001.png"
    image.write_bytes(b"old-scan")
    _replace_image_then(image, b"other-generation", lambda: None)
    assert image.read_bytes() == b"other-generation"
    assert list(tmp_path.iterdir()) == [image]

"""Integration test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def tiny_png(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a path to a minimal valid 10x10 white PNG."""
    try:
        from PIL import Image

        p = tmp_path_factory.mktemp("png_fixtures") / "tiny.png"
        img = Image.new("RGB", (10, 10), color=(255, 255, 255))
        img.save(p)
        return p
    except ImportError:
        pytest.skip("PIL not available")

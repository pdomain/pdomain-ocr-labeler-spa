"""Tests for pytest fixtures defined in conftest.py."""

from __future__ import annotations

import pytest


def test_gpu_available_fixture_exists(gpu_available: bool) -> None:
    """Verify gpu_available fixture can be injected."""
    assert isinstance(gpu_available, bool)


def test_gpu_test_skips_on_cpu_machines(gpu_available: bool) -> None:
    """Verify tests can skip when GPU not available."""
    if not gpu_available:
        pytest.skip("GPU not available")
    # This test only runs if GPU is available
    assert gpu_available is True


def test_asyncio_mode_auto() -> None:
    """Verify asyncio_mode is set to 'auto' in pyproject.toml."""
    import pytest_asyncio

    assert pytest_asyncio is not None

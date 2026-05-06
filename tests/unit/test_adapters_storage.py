"""Storage adapter Protocol + filesystem impl shape pins.

Spec: ``specs/02-backend.md §1`` (module layout), ``§7`` (`IStorage`
Protocol — exact method signatures), ``§10`` (image cache served via
``IStorage`` per D-019). The Protocol surface is the source of truth
for every storage backend; the filesystem impl is the only one wired
in v1.

These are M1 entry tests: they pin the Protocol surface (so adding a
new backend later requires conscious method matching) and the
filesystem path-traversal guard (a security invariant — keys must
resolve under the configured root).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest


def test_istorage_protocol_module_exports() -> None:
    """``adapters.storage`` re-exports ``IStorage`` and ``FilesystemStorage``."""
    from pd_ocr_labeler_spa.adapters import storage

    assert hasattr(storage, "IStorage"), "IStorage must be re-exported from adapters.storage"
    assert hasattr(storage, "FilesystemStorage"), (
        "FilesystemStorage must be re-exported from adapters.storage"
    )


def test_istorage_protocol_has_spec_method_set() -> None:
    """Spec §7 fixes the Protocol's method set; this drift-checks it.

    Adding a method to the Protocol means every backend (filesystem +
    future s3) needs to grow that method — surface it loudly.
    """
    from pd_ocr_labeler_spa.adapters.storage.base import IStorage

    expected = {
        "get_bytes",
        "put_bytes",
        "exists",
        "delete",
        "list_keys",
        "presign_put",
    }
    actual = {
        name for name, _ in inspect.getmembers(IStorage, predicate=callable) if not name.startswith("_")
    }
    assert expected.issubset(actual), f"missing Protocol methods: {expected - actual}"


def test_filesystem_storage_round_trip(tmp_path: Path) -> None:
    """Write bytes, read them back, exists() flips, delete() removes."""
    import asyncio

    from pd_ocr_labeler_spa.adapters.storage.filesystem import FilesystemStorage

    fs = FilesystemStorage(root=tmp_path)

    async def _go() -> None:
        assert not await fs.exists("foo/bar.bin")
        await fs.put_bytes("foo/bar.bin", b"hello")
        assert await fs.exists("foo/bar.bin")
        assert await fs.get_bytes("foo/bar.bin") == b"hello"

        keys = await fs.list_keys("foo/")
        assert "foo/bar.bin" in keys

        await fs.delete("foo/bar.bin")
        assert not await fs.exists("foo/bar.bin")

    asyncio.run(_go())


def test_filesystem_storage_path_traversal_rejected(tmp_path: Path) -> None:
    """Keys with ``..`` segments must not escape the root.

    Spec §7 ("path-traversal guard") + general security invariant — a
    malicious client must not be able to read ``/etc/passwd`` via a
    crafted key.
    """
    import asyncio

    from pd_ocr_labeler_spa.adapters.storage.filesystem import FilesystemStorage

    fs = FilesystemStorage(root=tmp_path / "sandbox")

    async def _go() -> None:
        with pytest.raises(ValueError, match="escape"):
            await fs.get_bytes("../../etc/passwd")
        with pytest.raises(ValueError, match="escape"):
            await fs.put_bytes("../../etc/evil", b"x")

    asyncio.run(_go())


def test_filesystem_storage_presign_put_returns_relative_url(tmp_path: Path) -> None:
    """Spec §7: ``presign_put`` returns ``f"/cdn/{key}"``.

    The labeler doesn't use this method (the SPA never uploads files),
    but the seam exists for adapter parity with pgdp-prep.
    """
    from pd_ocr_labeler_spa.adapters.storage.filesystem import FilesystemStorage

    fs = FilesystemStorage(root=tmp_path)
    url = fs.presign_put("page-images/foo.png")
    assert url.endswith("/page-images/foo.png")
    assert "/cdn/" in url

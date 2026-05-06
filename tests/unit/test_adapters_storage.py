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


def test_filesystem_storage_absolute_key_rejected(tmp_path: Path) -> None:
    """Absolute-path keys (``/etc/passwd``) raise ``ValueError``.

    The previous implementation silently re-rooted them under
    ``self._root`` (so ``/etc/passwd`` ended up at
    ``<root>/etc/passwd``). That preserved the security invariant by
    accident, but contradicted the docstring that claimed the absolute
    case was "guarded." Spec §7's intent — *no* surprising re-routing
    of caller-supplied keys — favours an explicit raise. (B-45.)
    """
    import asyncio

    from pd_ocr_labeler_spa.adapters.storage.filesystem import FilesystemStorage

    fs = FilesystemStorage(root=tmp_path / "sandbox")

    async def _go() -> None:
        with pytest.raises(ValueError, match="escape"):
            await fs.put_bytes("/etc/passwd", b"pwned")
        with pytest.raises(ValueError, match="escape"):
            await fs.get_bytes("/etc/passwd")
        with pytest.raises(ValueError, match="escape"):
            await fs.delete("/etc/passwd")
        with pytest.raises(ValueError, match="escape"):
            await fs.exists("/etc/passwd")
        with pytest.raises(ValueError, match="escape"):
            await fs.list_keys("/etc")

    asyncio.run(_go())

    # And nothing was created under ``<root>/etc/`` — the previous impl
    # would have left a re-rooted file behind.
    assert not (tmp_path / "sandbox" / "etc").exists()


def test_filesystem_storage_async_methods_dispatch_blocking_io_to_threadpool() -> None:
    """B-44 pin: ``async def`` impls must not run sync FS calls bare.

    AST-scans ``filesystem.py`` and asserts that bare attribute
    references like ``path.exists()``, ``path.unlink()``,
    ``path.mkdir(...)``, ``path.rglob(...)``, ``path.is_file()``, and
    ``path.relative_to(...)`` do not appear directly inside an
    ``async def`` body — they must be wrapped in
    ``anyio.to_thread.run_sync(...)`` (or be ``anyio.Path`` calls).
    Catches a regression where a future edit drops the threadpool
    dispatch and re-introduces an event-loop-blocking call.

    The whitelist below names ``anyio.to_thread.run_sync`` and
    ``anyio.Path`` as the sanctioned async wrappers; anything else
    invoking a blocking sync method on a ``Path`` value flags.
    """
    import ast
    from pathlib import Path as _Path

    src_path = (
        _Path(__file__).parent.parent.parent
        / "src"
        / "pd_ocr_labeler_spa"
        / "adapters"
        / "storage"
        / "filesystem.py"
    )
    tree = ast.parse(src_path.read_text())

    # Names of sync ``pathlib.Path`` methods we forbid bare inside
    # ``async def`` bodies (these are the ones currently called from
    # the impl; extend if more are introduced).
    sync_path_methods = {
        "exists",
        "unlink",
        "mkdir",
        "rglob",
        "is_file",
        "relative_to",
    }

    offenders: list[tuple[str, int, str]] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            # Flag a Call as "bare sync" only when it's:
            #   - lexically inside an ``async def`` body, AND
            #   - NOT inside a nested sync ``def`` / ``lambda`` (that's
            #     the body passed to ``run_sync`` — fine), AND
            #   - NOT the awaited expression of an ``await`` (anyio.Path
            #     methods return coroutines and are always awaited).
            self._async_fn: str | None = None
            self._inside_await = 0

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            prev = self._async_fn
            self._async_fn = node.name
            for child in node.body:
                self.visit(child)
            self._async_fn = prev

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            saved = self._async_fn
            self._async_fn = None
            self.generic_visit(node)
            self._async_fn = saved

        def visit_Lambda(self, node: ast.Lambda) -> None:
            saved = self._async_fn
            self._async_fn = None
            self.generic_visit(node)
            self._async_fn = saved

        def visit_Await(self, node: ast.Await) -> None:
            self._inside_await += 1
            self.generic_visit(node)
            self._inside_await -= 1

        def visit_Call(self, node: ast.Call) -> None:
            if (
                self._async_fn is not None
                and self._inside_await == 0
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in sync_path_methods
            ):
                offenders.append((self._async_fn, node.lineno, node.func.attr))
            self.generic_visit(node)

    _Visitor().visit(tree)

    assert not offenders, (
        f"sync Path calls found bare inside async def bodies (B-44): {offenders}. "
        "Wrap in anyio.to_thread.run_sync(lambda: ...) or use anyio.Path."
    )


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

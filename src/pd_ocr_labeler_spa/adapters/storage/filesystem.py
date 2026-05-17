"""Filesystem-backed ``IStorage`` impl.

Wraps ``anyio.Path`` for async I/O over a configured root directory.
Includes the path-traversal guard required by ``docs/architecture/02-backend.md
§7``: keys with ``..`` or absolute-path tricks must not escape the
root, or the labeler running under a multi-tenant deployment could
read arbitrary host files via crafted ``GET /image-cache/...`` paths.

``presign_put`` returns ``f"/cdn/{key}"`` — kept for adapter parity
with pgdp-prep, even though the labeler SPA never PUTs through it
(the SPA is read-only against ``IStorage`` per D-019).

Async-correctness note: every method declared ``async`` dispatches
its blocking syscalls through ``anyio.to_thread.run_sync(...)`` (or
through ``anyio.Path``, which already does the same thing under the
hood). Doing sync FS calls inside ``async def`` would block the event
loop — fine in single-user mode, bad as soon as SSE / job-runner
concurrency lands in M3+. The Protocol declares these methods async
(spec §7), so the impls keep that promise honestly. (B-44.)
"""

from __future__ import annotations

from pathlib import Path

import anyio


class FilesystemStorage:
    """Concrete filesystem-backed ``IStorage`` (the only v1 impl)."""

    def __init__(self, root: Path, *, cdn_url_base: str = "/cdn") -> None:
        self._root = Path(root)
        self._cdn = cdn_url_base.rstrip("/")
        # B-54: do NOT mkdir the root here. ``__init__`` must be free
        # of FS side effects so that ``bootstrap.build_app(Settings())``
        # — which the docstring claims is "pure" — is actually pure.
        # The root is created on first write via ``put_bytes``'s
        # parent-mkdir, which covers every key by transitivity (the
        # parent of any key path under root is at least the root itself).

    # ── path-traversal guard ─────────────────────────────────────────
    def _path(self, key: str) -> Path:
        """Resolve ``key`` against ``self._root`` and refuse escape attempts.

        Two attack shapes are rejected up-front, before any FS access:

        - ``../../etc/passwd`` (relative escape via parent dir refs)
          — caught by the ``resolve()``-then-``relative_to`` check below.
        - ``/etc/passwd`` (absolute key) — rejected here with
          ``ValueError`` rather than silently re-rooted under
          ``self._root``. Storage callers are expected to use relative,
          forward-slash keys; absolute keys are an API misuse, not a
          legitimate way to address the data root. (B-45.)

        Either form raises ``ValueError`` and never touches the FS.
        """
        if key.startswith("/"):
            raise ValueError(f"key escapes data root: {key!r} (absolute paths are not valid storage keys)")
        if any(part == ".." for part in Path(key).parts):
            raise ValueError(f"key escapes data root: {key!r} (contains parent-dir reference)")
        candidate = (self._root / key).resolve()
        root = self._root.resolve()
        # candidate must be the root itself or strictly under it
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"key escapes data root: {key!r}")
        return candidate

    # ── IStorage Protocol surface ────────────────────────────────────
    async def get_bytes(self, key: str) -> bytes:
        return await anyio.Path(self._path(key)).read_bytes()

    async def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        # ``anyio.Path`` doesn't expose ``mkdir(parents=True)`` cleanly,
        # so dispatch the parent-mkdir to the threadpool to keep the
        # event loop unblocked. (B-44.)
        await anyio.to_thread.run_sync(lambda: path.parent.mkdir(parents=True, exist_ok=True))  # type: ignore[attr-defined]
        await anyio.Path(path).write_bytes(data)

    async def exists(self, key: str) -> bool:
        return await anyio.Path(self._path(key)).exists()

    async def delete(self, key: str) -> None:
        path = self._path(key)

        # ``exists()`` + ``unlink()`` are cheap-but-blocking: bundle them
        # into a single threadpool dispatch so the event loop sees one
        # await point, not two sync syscalls. (B-44.)
        def _delete() -> None:
            if path.exists():
                path.unlink()

        await anyio.to_thread.run_sync(_delete)  # type: ignore[attr-defined]

    async def list_keys(self, prefix: str) -> list[str]:
        """Return keys under ``prefix`` (forward-slash form), recursive.

        Returns ``[]`` if the prefix dir doesn't exist — symmetrical to
        most object-store list APIs that return an empty page rather
        than 404 on a non-existent prefix.
        """
        base = self._path(prefix)
        root = self._root.resolve()

        # ``rglob`` against a populated image-cache walks every entry;
        # one threadpool dispatch covers the whole walk so the event
        # loop isn't blocked per-entry. (B-44.)
        def _walk() -> list[str]:
            if not base.exists():
                return []
            if base.is_file():
                # B-53: mirror the rglob-branch shape — return the
                # canonical root-relative posix form, not the caller's
                # un-normalised prefix. Otherwise ``list_keys("foo/")``
                # against a file ``foo`` returns ``["foo/"]`` while
                # ``list_keys("foo")`` returns ``["foo"]``, and
                # key-equality across calls breaks silently.
                return [base.relative_to(root).as_posix()]
            keys = [path.relative_to(root).as_posix() for path in base.rglob("*") if path.is_file()]
            return sorted(keys)

        return await anyio.to_thread.run_sync(_walk)  # type: ignore[attr-defined]

    def presign_put(self, key: str, *, expires_in: int = 600) -> str:
        """Return the URL the labeler would PUT to for ``key``.

        Filesystem mode does direct uploads through the FastAPI process
        (the SPA never actually uses this — the seam exists for adapter
        parity with pgdp-prep). ``expires_in`` is accepted for API
        symmetry with future S3 / signed-URL backends but ignored here.
        """
        del expires_in  # unused for filesystem; signature parity only
        return f"{self._cdn}/{key.lstrip('/')}"

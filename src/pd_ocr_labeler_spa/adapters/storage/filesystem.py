"""Filesystem-backed ``IStorage`` impl.

Wraps ``anyio.Path`` for async I/O over a configured root directory.
Includes the path-traversal guard required by ``specs/02-backend.md
§7``: keys with ``..`` or absolute-path tricks must not escape the
root, or the labeler running under a multi-tenant deployment could
read arbitrary host files via crafted ``GET /image-cache/...`` paths.

``presign_put`` returns ``f"/cdn/{key}"`` — kept for adapter parity
with pgdp-prep, even though the labeler SPA never PUTs through it
(the SPA is read-only against ``IStorage`` per D-019).
"""

from __future__ import annotations

from pathlib import Path

import anyio


class FilesystemStorage:
    """Concrete filesystem-backed ``IStorage`` (the only v1 impl)."""

    def __init__(self, root: Path, *, cdn_url_base: str = "/cdn") -> None:
        self._root = Path(root)
        self._cdn = cdn_url_base.rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    # ── path-traversal guard ─────────────────────────────────────────
    def _path(self, key: str) -> Path:
        """Resolve ``key`` against ``self._root`` and refuse escape attempts.

        Two attack shapes guarded:
        - ``../../etc/passwd`` (relative escape via parent dir refs)
        - ``/etc/passwd`` (absolute key reinterpreted under root)

        Both are caught by ``Path.resolve()``-then-``relative_to`` —
        raising ``ValueError`` if the resolved path is outside the root.
        """
        clean = key.lstrip("/")
        candidate = (self._root / clean).resolve()
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
        # Parent dir creation is sync — anyio's Path proxy doesn't
        # offer ``mkdir(parents=True)`` cleanly without an extra hop.
        path.parent.mkdir(parents=True, exist_ok=True)
        await anyio.Path(path).write_bytes(data)

    async def exists(self, key: str) -> bool:
        return await anyio.Path(self._path(key)).exists()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    async def list_keys(self, prefix: str) -> list[str]:
        """Return keys under ``prefix`` (forward-slash form), recursive.

        Returns ``[]`` if the prefix dir doesn't exist — symmetrical to
        most object-store list APIs that return an empty page rather
        than 404 on a non-existent prefix.
        """
        base = self._path(prefix)
        if not base.exists():
            return []
        if base.is_file():
            return [prefix.lstrip("/")]
        keys: list[str] = []
        root = self._root.resolve()
        for path in base.rglob("*"):
            if path.is_file():
                keys.append(path.relative_to(root).as_posix())
        return sorted(keys)

    def presign_put(self, key: str, *, expires_in: int = 600) -> str:
        """Return the URL the labeler would PUT to for ``key``.

        Filesystem mode does direct uploads through the FastAPI process
        (the SPA never actually uses this — the seam exists for adapter
        parity with pgdp-prep). ``expires_in`` is accepted for API
        symmetry with future S3 / signed-URL backends but ignored here.
        """
        del expires_in  # unused for filesystem; signature parity only
        return f"{self._cdn}/{key.lstrip('/')}"

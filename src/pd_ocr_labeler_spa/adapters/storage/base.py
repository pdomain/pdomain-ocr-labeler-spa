"""``IStorage`` Protocol — surface every storage backend conforms to.

Spec: ``specs/02-backend.md §7``. Method set lifted verbatim from the
spec so a future drift between Protocol and backend implementations
fails the ``test_istorage_protocol_has_spec_method_set`` shape pin
loudly.

Keys are forward-slash-joined paths under a single root (filesystem)
or bucket prefix (S3). Implementations accept any key the labeler
constructs without further normalisation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IStorage(Protocol):
    """Object-store interface used by the labeler's image-cache + envelope I/O.

    The S3 impl is intentionally absent in v1 (``NotImplementedYet`` per
    D-019); only ``FilesystemStorage`` is wired. The Protocol method set
    is fixed by ``specs/02-backend.md §7`` — adding a method here means
    every backend grows it.
    """

    async def get_bytes(self, key: str) -> bytes: ...

    async def put_bytes(self, key: str, data: bytes) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def delete(self, key: str) -> None: ...

    async def list_keys(self, prefix: str) -> list[str]: ...

    def presign_put(self, key: str, *, expires_in: int = 600) -> str: ...

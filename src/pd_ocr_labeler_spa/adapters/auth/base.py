"""``IAuth`` Protocol + ``UserContext`` model.

Spec: ``specs/02-backend.md §7``. Every route depends on ``get_user``
which dispatches to the configured ``IAuth.verify`` — flipping
``Settings.auth_mode`` from ``none`` to a real auth backend (jwt etc.)
becomes a wiring change rather than a route-by-route rewrite.

The ``UserContext`` shape (``user_id`` + ``display_name``) is the v1
surface; later auth modes can extend with optional fields without
breaking the no-auth shape.

Per spec ``§7`` (``02-backend.md:434``) the Protocol surface accepts
``HTTPAuthorizationCredentials | None`` — exactly what FastAPI's
``HTTPBearer(auto_error=False)`` dependency yields. The dependency
layer (``api/dependencies.py::get_user``) feeds the credentials object
straight in; backends that only need the bearer string read
``creds.credentials`` themselves. Closes B-42.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel


class UserContext(BaseModel):
    """The principal injected into every route.

    For the v1 ``NoneAuth`` adapter this is always
    ``UserContext(user_id="local", display_name="Local User")`` — every
    request resolves to the same anonymous identity (D-005).
    """

    user_id: str
    display_name: str


@runtime_checkable
class IAuth(Protocol):
    """Auth backend interface; the only v1 impl is ``NoneAuth``.

    ``creds`` is FastAPI's ``HTTPAuthorizationCredentials`` object (or
    ``None`` when the request had no ``Authorization`` header). Backends
    that only need the raw bearer string read ``creds.credentials``;
    backends that need the scheme too read ``creds.scheme``.
    """

    async def verify(self, creds: HTTPAuthorizationCredentials | None) -> UserContext: ...

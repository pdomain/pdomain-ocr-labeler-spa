"""``IAuth`` Protocol + ``UserContext`` model.

Spec: ``specs/02-backend.md §7``. Every route depends on ``get_user``
which dispatches to the configured ``IAuth.verify`` — flipping
``Settings.auth_mode`` from ``none`` to a real auth backend (jwt etc.)
becomes a wiring change rather than a route-by-route rewrite.

The ``UserContext`` shape (``user_id`` + ``display_name``) is the v1
surface; later auth modes can extend with optional fields without
breaking the no-auth shape.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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

    ``credentials`` is the raw bearer-token string (or ``None`` if the
    request had no ``Authorization`` header) — backends that need
    structured ``HTTPAuthorizationCredentials`` should re-parse from
    the request in their own dependency layer.
    """

    async def verify(self, credentials: str | None) -> UserContext: ...

"""No-auth adapter — every request resolves to the same local user.

Spec: ``specs/02-backend.md §7`` ("``none_.py`` returns
``UserContext('local', 'Local User')`` for any input") +
``specs/17-decisions.md D-005`` (single anonymous principal in v1).
"""

from __future__ import annotations

from fastapi.security import HTTPAuthorizationCredentials

from .base import UserContext


class NoneAuth:
    """The v1 anonymous-everyone adapter.

    Returned ``UserContext`` is intentionally identical regardless of
    input — even a bogus ``Bearer`` header is accepted because there's
    no authentication to perform.
    """

    async def verify(self, creds: HTTPAuthorizationCredentials | None) -> UserContext:
        del creds  # unused — the labeler accepts any caller as "local"
        return UserContext(user_id="local", display_name="Local User")

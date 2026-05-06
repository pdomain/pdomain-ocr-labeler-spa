"""Auth adapter Protocol + ``none_`` impl shape pins.

Spec: ``specs/02-backend.md §7`` defines ``IAuth`` and ``UserContext``.
``specs/17-decisions.md D-005`` and the spec's §6 dependency wiring fix
the no-auth shape — every request resolves to
``UserContext(user_id="local", display_name="Local User")``.

The labeler's v1 only ships the ``none`` adapter; the seam is here so
flipping ``Settings.auth_mode`` to e.g. ``jwt`` later is a wiring
change, not a route-by-route refactor.
"""

from __future__ import annotations

import inspect


def test_iauth_protocol_module_exports() -> None:
    from pd_ocr_labeler_spa.adapters import auth

    assert hasattr(auth, "IAuth"), "IAuth must be re-exported from adapters.auth"
    assert hasattr(auth, "UserContext"), "UserContext must be re-exported"
    assert hasattr(auth, "NoneAuth"), "NoneAuth must be re-exported"


def test_iauth_protocol_method_set() -> None:
    from pd_ocr_labeler_spa.adapters.auth.base import IAuth

    methods = {name for name, _ in inspect.getmembers(IAuth, predicate=callable) if not name.startswith("_")}
    assert "verify" in methods


def test_user_context_shape() -> None:
    """Spec §7: ``UserContext(user_id, display_name)`` — both required strings."""
    from pd_ocr_labeler_spa.adapters.auth.base import UserContext

    ctx = UserContext(user_id="alice", display_name="Alice Example")
    assert ctx.user_id == "alice"
    assert ctx.display_name == "Alice Example"


def test_none_auth_returns_local_user() -> None:
    """Spec §7: ``NoneAuth.verify`` always returns ``UserContext("local", "Local User")``."""
    import asyncio

    from pd_ocr_labeler_spa.adapters.auth.none_ import NoneAuth

    auth = NoneAuth()

    async def _go() -> None:
        ctx_none = await auth.verify(None)
        ctx_some = await auth.verify("Bearer ignored")
        for ctx in (ctx_none, ctx_some):
            assert ctx.user_id == "local"
            assert ctx.display_name == "Local User"

    asyncio.run(_go())

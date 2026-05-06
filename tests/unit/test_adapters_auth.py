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

from fastapi.security import HTTPAuthorizationCredentials


def test_iauth_protocol_module_exports() -> None:
    from pd_ocr_labeler_spa.adapters import auth

    assert hasattr(auth, "IAuth"), "IAuth must be re-exported from adapters.auth"
    assert hasattr(auth, "UserContext"), "UserContext must be re-exported"
    assert hasattr(auth, "NoneAuth"), "NoneAuth must be re-exported"


def test_iauth_protocol_method_set() -> None:
    from pd_ocr_labeler_spa.adapters.auth.base import IAuth

    methods = {name for name, _ in inspect.getmembers(IAuth, predicate=callable) if not name.startswith("_")}
    assert "verify" in methods


def test_iauth_verify_signature_matches_spec() -> None:
    """Spec ``§7`` (``02-backend.md:434``) pins the verify signature:

        async def verify(self, creds: HTTPAuthorizationCredentials | None) -> UserContext: ...

    Closes B-42 (signature drift was previously invisible because the
    method-set drift-pin only checked existence, not parameter types).
    A future widening (e.g. back to ``credentials: str | None``) must
    update spec §7 first AND this test second.

    ``get_type_hints`` resolves the string annotations introduced by
    ``from __future__ import annotations`` — comparing the raw string
    form would tightly couple this test to the impl's whitespace.
    """
    import typing

    from pd_ocr_labeler_spa.adapters.auth.base import IAuth, UserContext

    sig = inspect.signature(IAuth.verify)
    # Parameters: ``self`` + the named credentials kwarg.
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["self", "creds"], (
        f"spec §7 names the credentials parameter ``creds``; got {[p.name for p in params]!r}"
    )
    hints = typing.get_type_hints(IAuth.verify)
    # Annotation: ``HTTPAuthorizationCredentials | None``.
    assert hints.get("creds") == HTTPAuthorizationCredentials | None, (
        f"spec §7 fixes the type as ``HTTPAuthorizationCredentials | None``; got {hints.get('creds')!r}"
    )
    # Return annotation: ``UserContext``.
    assert hints.get("return") is UserContext, (
        f"spec §7 fixes the return as ``UserContext``; got {hints.get('return')!r}"
    )


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
    bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="ignored")

    async def _go() -> None:
        ctx_none = await auth.verify(None)
        ctx_some = await auth.verify(bearer)
        for ctx in (ctx_none, ctx_some):
            assert ctx.user_id == "local"
            assert ctx.display_name == "Local User"

    asyncio.run(_go())

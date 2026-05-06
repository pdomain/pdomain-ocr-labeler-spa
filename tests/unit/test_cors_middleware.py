"""Regression tests for the CORS middleware on ``build_app``.

Iter-5 review B-03: ``allow_origins=["*"]`` paired with
``allow_credentials=True`` is invalid per the CORS spec — browsers
reject the response. ``pd-prep-for-pgdp`` (the declared structural
model) sets only ``allow_origins``/``allow_methods``/``allow_headers``;
spec ``specs/02-backend.md §step-7`` matches.

We introspect ``app.user_middleware`` because Starlette stores
middleware-class + kwargs on each entry. That's the cheapest way to
assert the wired config without spinning up a TestClient and round-
tripping a preflight (which can mask config bugs by being lenient).
"""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _cors_kwargs(app):
    """Return the kwargs dict CORSMiddleware was added with.

    Starlette ``Middleware`` is a dataclass-ish wrapper exposing
    ``cls`` (the middleware class) and ``kwargs`` (a dict). Older
    versions used ``options`` instead — handle both.
    """
    for entry in app.user_middleware:
        cls = getattr(entry, "cls", None)
        if cls is CORSMiddleware:
            # New Starlette: .kwargs; older: .options.
            return getattr(entry, "kwargs", None) or getattr(entry, "options", {})
    raise AssertionError("CORSMiddleware not registered on app")


def test_cors_middleware_does_not_enable_credentials() -> None:
    # B-03 framing was "wildcard + credentials" — but per B-15, the
    # invariant we actually want is "credentials stays off until
    # auth lands (M2)." Asserting unconditionally avoids a silent
    # partial-regression where a future change narrows allow_origins
    # to a single host and re-enables allow_credentials: the
    # wildcard-gated assertion would no longer fire, and only the
    # kwargs-shape pin (test below) would fail — with a misleading
    # "we changed origins" diagnostic rather than the real "we re-
    # introduced credentials" one.
    app = build_app(Settings(mode="api_only"))
    kwargs = _cors_kwargs(app)
    assert kwargs.get("allow_credentials", False) is False, (
        "CORSMiddleware enables allow_credentials. Auth is M2; until "
        "then the value must be False (or absent). See "
        "docs/BUGS_FOUND.md B-03 / B-15."
    )


def test_cors_middleware_matches_pgdp_prep_shape() -> None:
    # Spec specs/02-backend.md §step-7 lists the three wildcards; pgdp-prep
    # uses the same shape. Pin it so a refactor doesn't silently
    # reintroduce credentials.
    app = build_app(Settings(mode="api_only"))
    kwargs = _cors_kwargs(app)
    assert kwargs.get("allow_origins") == ["*"]
    assert kwargs.get("allow_methods") == ["*"]
    assert kwargs.get("allow_headers") == ["*"]
    # Either absent or explicitly False — both are acceptable.
    assert kwargs.get("allow_credentials", False) is False

"""LocalTrustMiddleware — block cross-origin requests to local-trust-required routes.

Routes in ``LOCAL_TRUST_ROUTES`` return 403 if the request carries a
``Sec-Fetch-Site`` header that is not ``same-origin``, or an ``Origin``
header that is not in the localhost allowlist.

Requests without ``Origin`` or ``Sec-Fetch-Site`` headers (e.g. curl,
starlette ``TestClient``, server-to-server) are passed through unchanged.

This guards against malicious web pages reaching a running localhost
labeler via cross-origin ``fetch()`` calls.

Spec: ``docs/specs/2026-05-24-F-002-cors-and-auth-hardening.md``.
Issue: ConcaveTrillion/pd-ocr-labeler-spa#407.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_LOCALHOST_ORIGINS: frozenset[str] = frozenset(
    {
        "http://localhost",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
)

LOCAL_TRUST_ROUTES: frozenset[str] = frozenset(
    {
        "/api/fs/ls",
        "/api/projects/source-root",
    }
)

_DENY_RESPONSE: dict[str, object] = {"detail": "cross-origin requests not permitted for this route"}


class LocalTrustMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin requests to LOCAL_TRUST_ROUTES.

    Decision logic (per F-002 spec Option A):

    1. If the request path is not in LOCAL_TRUST_ROUTES, pass through.
    2. If ``Sec-Fetch-Site`` is present and is not ``same-origin``,
       return 403.  Browsers set this forbidden header; it cannot be
       forged by JS on a malicious page.
    3. If ``Origin`` is present and is not in ``_LOCALHOST_ORIGINS``,
       return 403.
    4. Otherwise (no suspicious headers, or trusted origin), pass through.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in LOCAL_TRUST_ROUTES:
            sec_fetch_site = request.headers.get("sec-fetch-site")
            if sec_fetch_site is not None and sec_fetch_site != "same-origin":
                return JSONResponse(_DENY_RESPONSE, status_code=403)

            origin = request.headers.get("origin")
            if origin is not None and origin not in _LOCALHOST_ORIGINS:
                return JSONResponse(_DENY_RESPONSE, status_code=403)

        return await call_next(request)

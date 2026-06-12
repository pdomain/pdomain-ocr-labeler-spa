"""LocalTrustMiddleware — block cross-origin requests to local-trust-required routes.

Routes in ``LOCAL_TRUST_ROUTES`` return 403 for requests that a browser
marks as cross-origin. Same-origin requests pass on ANY port (P4.6,
parity P6/C09 — the server binds arbitrary ports in auto-port mode and
the old fixed 8080/5173 allowlist rejected literally-same-origin POSTs).

Decision order:

1. ``Sec-Fetch-Site`` present:
   - ``same-origin`` → pass. The header is *forbidden* (browsers set it;
     page JS cannot forge it), so it is an authoritative same-origin
     assertion — no further Origin checks needed.
   - anything else (``cross-site``, ``same-site``, ``none``) → 403.
2. No ``Sec-Fetch-Site`` (older browsers), ``Origin`` present:
   - pass when the Origin equals the request's own origin derived from
     the ``Host`` header (that IS the definition of same-origin), or when
     it is in the static dev allowlist (Vite on :5173 is cross-origin but
     trusted).
   - otherwise → 403.
3. Neither header (curl, httpx, starlette ``TestClient``,
   server-to-server) → pass.

A malicious *web page* can never reach case 3 — browsers always attach
``Origin`` to cross-origin fetches — and cannot forge ``Sec-Fetch-Site``
or ``Host``. An attacker controlling a local process can forge anything,
but that threat model is explicitly out of scope (F-002 spec).

Spec: ``docs/specs/2026-05-24-F-002-cors-and-auth-hardening.md`` (Option A)
+ P4.6 same-origin-on-any-port fix (parity audit C09).
Issue: pdomain/pdomain-ocr-labeler-spa#407.
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


def _strip_default_port(origin: str) -> str:
    """Normalize an origin string by dropping the scheme-default port."""
    if origin.startswith("http://") and origin.endswith(":80"):
        return origin[: -len(":80")]
    if origin.startswith("https://") and origin.endswith(":443"):
        return origin[: -len(":443")]
    return origin


def _request_origin(request: Request) -> str | None:
    """Derive the request's own origin (``scheme://host[:port]``) from Host.

    The browser sets ``Host`` to whatever it connected to, so an ``Origin``
    equal to this value is same-origin by definition — regardless of port.
    Returns ``None`` when the Host header is missing.
    """
    host = request.headers.get("host")
    if not host:
        return None
    return _strip_default_port(f"{request.url.scheme}://{host}")


class LocalTrustMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin requests to LOCAL_TRUST_ROUTES.

    See the module docstring for the decision order. Protections kept from
    the original F-002 Option A implementation: cross-site browser fetches
    are rejected via ``Sec-Fetch-Site`` (unforgeable) or via an ``Origin``
    that matches neither the request's own host-derived origin nor the
    static dev allowlist.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in LOCAL_TRUST_ROUTES:
            sec_fetch_site = request.headers.get("sec-fetch-site")
            if sec_fetch_site is not None:
                if sec_fetch_site != "same-origin":
                    return JSONResponse(_DENY_RESPONSE, status_code=403)
                # Browser-asserted same-origin — authoritative; pass.
                return await call_next(request)

            origin = request.headers.get("origin")
            if origin is not None:
                normalized = _strip_default_port(origin)
                if normalized not in _LOCALHOST_ORIGINS and normalized != _request_origin(request):
                    return JSONResponse(_DENY_RESPONSE, status_code=403)

        return await call_next(request)

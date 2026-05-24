# F-002 — Wildcard CORS plus no-auth filesystem routes exposes local filesystem metadata

> **Status**: Draft
> **Last updated**: 2026-05-24
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#407

## TL;DR

The labeler currently runs with `allow_origins=["*"]` CORS and a `NoneAuth`
adapter that accepts every caller as the local user. Two routes —
`GET /api/fs/ls` (arbitrary directory listing) and
`POST /api/projects/source-root` (persists any directory as the project root) —
have no authentication or path restriction. A malicious web page can reach a
running localhost labeler from the browser, enumerate local directory structure,
and issue state-changing POST requests. Fix: restrict CORS to `localhost` origins
only, add a `Sec-Fetch-Site` / `Origin` same-origin enforcement header, and gate
the filesystem and state-changing routes behind an explicit local-trust check
(CSRF token or `Sec-Fetch-Site: same-origin` assertion).

## Context

### Wildcard CORS

`src/pd_ocr_labeler_spa/bootstrap.py:258–263` adds `CORSMiddleware` with:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

The comment in the source ("wide setting unblocks Vite-dev (5173 → 8080)")
documents the intent: Vite's dev server at `:5173` must be able to reach the
FastAPI backend at `:8080` during development. But `allow_origins=["*"]`
permits *any* origin, including a malicious third-party website. Because
`allow_credentials` is omitted (cookies are not a vector), session hijacking is
not possible, but unauthenticated cross-origin JSON requests are.

### No-auth adapter

`src/pd_ocr_labeler_spa/adapters/auth/none_.py:15–25` (`NoneAuth.verify`)
returns `UserContext("local", "Local User")` for **any** caller, including
requests that carry no credentials at all. This is correct for a single-user
local-only tool; the problem is that paired with wildcard CORS it means any
origin gets "local user" privileges.

### Unprotected filesystem routes

`GET /api/fs/ls` (`src/pd_ocr_labeler_spa/api/fs.py:38–76`):

- Accepts an arbitrary `path` query parameter (defaults to `~`).
- Calls `Path(path).expanduser().resolve()` — will happily resolve `/`,
  `/etc`, any user-readable directory.
- Returns names of all non-hidden subdirectories with no restriction.
- No authentication dependency in the route signature.

`POST /api/projects/source-root` (`src/pd_ocr_labeler_spa/api/projects.py:632`):

- Accepts `SetSourceProjectsRootRequest{path}` in the body.
- Validates that `path` is an existing directory but places no restriction on
  *which* directory.
- Persists the directory to `config.yaml` and updates the in-process
  `SourceRootCarrier` immediately.
- No authentication dependency in the route signature.

### Routes without authentication dependencies (full inventory)

The following routes currently accept unauthenticated requests (no `Depends`
on an auth adapter):

| Route | Method | Sensitivity |
|---|---|---|
| `GET /api/fs/ls` | GET | Reads local filesystem metadata |
| `POST /api/projects/source-root` | POST | Mutates persistent config |
| `POST /api/projects/{id}/export` | POST | Enqueues long-running job writing files |
| `GET /api/projects/{id}/export/styles` | GET | Low — returns empty list today |
| `GET /api/projects/{id}/exports` | GET | Low — returns empty list today |
| `GET /api/projects` | GET | Lists project names |
| `GET /api/projects/{id}` | GET | Reads project state |
| `GET /api/projects/{id}/pages/{n}` | GET | Reads labeled page data |
| `POST /api/projects/{id}/pages/{n}/save` | POST | Writes labeled page to disk |
| `POST /api/projects/{id}/pages/{n}/words/{wid}/gt` | PATCH | Mutates labeled data |
| `POST /api/projects/{id}/ocr` | POST | Enqueues OCR job |
| `POST /discover` | POST | Force-rescans project directory |
| `GET /api/notifications/stream` | GET | SSE stream |

The highest-risk routes for a cross-origin attack are:

- `GET /api/fs/ls` — filesystem metadata disclosure
- `POST /api/projects/source-root` — persistent config mutation
- `POST /api/projects/{id}/pages/{n}/save` — labeled data overwrite
- `POST /api/projects/{id}/ocr` and `POST /api/projects/{id}/export` —
  trigger long-running jobs

### Why this matters

The labeler is a local tool. An attacker cannot reach it from the public
internet (it binds to `localhost`). But a malicious website visited in a
browser on the same machine *can* reach `http://localhost:8080` because the
browser relaxes same-origin checks for localhost in some configurations, and
because `allow_origins=["*"]` suppresses the normal CORS preflight block.
The attack surface is:

1. Directory traversal via `GET /api/fs/ls?path=/etc` to discover sensitive
   directory names.
1. State manipulation via `POST /api/projects/source-root` to point the
   labeler at attacker-controlled data.
1. Data exfiltration via `GET /api/projects/{id}/pages/{n}` (page OCR text
   and bounding boxes of labeled documents).

## Goals / Non-Goals

**Goals**

- Replace `allow_origins=["*"]` with an explicit allowlist:
  `http://localhost:5173` (Vite dev), `http://127.0.0.1:5173`, and the
  production same-origin (empty list defaults to same-origin-only in CORS
  semantics).
- Add a `LocalTrustMiddleware` (or equivalent) that rejects requests to
  designated "local-trust-required" routes when the `Origin` header is
  present and is not in the localhost allowlist.
- Gate `GET /api/fs/ls` and `POST /api/projects/source-root` behind
  the local-trust requirement.
- Ensure the Vite dev workflow continues to work without friction.
- Add tests proving that a cross-origin request to `GET /api/fs/ls` is
  rejected after the fix.

**Non-Goals**

- Adding JWT, cookie, or API-key authentication to all routes — this is
  deferred per D-042 (no auth/Postgres/managed-adapter until post-convergence).
- Restricting `GET /api/fs/ls` to a subtree of the filesystem beyond what
  the same-origin enforcement already provides — directory-tree restriction
  is a separate UX concern.
- Making the labeler multi-user — `NoneAuth` stays as-is; this spec does not
  touch the auth adapter.
- Addressing the F-001 export-path traversal — that is covered in the F-001
  spec.

## Constraints

- The fix must not break the Vite dev server (`make frontend-dev`, port 5173).
  The CORS `allow_origins` list must include the Vite dev origin when the app
  runs in dev mode.
- The fix must not break `TestClient` usage in the test suite (starlette
  `TestClient` does not send `Origin` headers by default, so the guard must
  not fire on headerless requests).
- `NoneAuth` must not be modified — the local-trust check is orthogonal to
  authentication; the auth adapter contract is preserved.
- The `CORS_ORIGINS` / `cors_allowed_origins` settings knob must be exposed
  in `Settings` (pydantic-settings, `PDLABELER_CORS_ORIGINS` env variable)
  so the allowed-origins list can be overridden without a code change.
- The `LOCAL_TRUST_REQUIRED_ROUTES` should be a hardcoded frozenset in
  `bootstrap.py` (not configurable) — this keeps the security boundary
  explicit and auditable.

## Options Considered

### Option A — Restrict CORS allowlist + `Sec-Fetch-Site` assertion (chosen)

Replace `allow_origins=["*"]` with `["http://localhost:5173",
"http://127.0.0.1:5173"]` (or empty for production) and add a thin
`LocalTrustMiddleware` that checks `Sec-Fetch-Site` and `Origin` headers on
the two highest-risk routes. `Sec-Fetch-Site: same-origin` is set by all
modern browsers for same-origin requests and is absent for cross-origin
`fetch()` from malicious pages (the attacker cannot forge it — it is a
forbidden header).

Trade-offs: very low implementation cost, no new dependencies, no user-visible
change, works well for same-machine localhost attacks. Does not help against
an attacker who controls a local process (but that threat model is out of scope
for a single-user local tool).

### Option B — Per-request CSRF token (double-submit cookie)

Issue a CSRF token in a `Set-Cookie` response header on the SPA load and
require it as an `X-CSRF-Token` request header on all state-changing routes.
Viable for a full multi-user deployment. Trade-off: requires a stateful token
store (or signed cookie), adds a round-trip for the SPA to fetch the token,
and complicates driver/test setup. Deferred to a future auth-enabled release.

### Option C — Bind to `127.0.0.1` only and add `--local-only` flag

Force the server to only bind to `127.0.0.1` (already the default), and rely
on the OS to prevent external access. Trade-off: does not protect against
same-machine browser attacks from malicious websites, which is the specific
threat `allow_origins=["*"]` enables. Insufficient on its own.

## Decision

**Option A** — three concrete changes, smallest possible footprint.

### Change 1: CORS origins — `bootstrap.py`

Replace the wildcard with an explicit list. Add a `cors_allowed_origins`
setting to `Settings`.

```python
# src/pd_ocr_labeler_spa/core/settings.py
cors_allowed_origins: list[str] = Field(
    default_factory=lambda: [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    description=(
        "CORS allow-origins list. In production the SPA is served from the same "
        "origin as the API, so this list only needs to cover the Vite dev server. "
        "Override with PDLABELER_CORS_ORIGINS env var (comma-separated). "
        "Set to [] for same-origin-only enforcement."
    ),
)
```

In `bootstrap.build_app`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)
```

Note: explicitly list allowed methods and headers rather than `["*"]`.

### Change 2: `LocalTrustMiddleware` — new file `src/pd_ocr_labeler_spa/middleware/local_trust.py`

```python
"""LocalTrustMiddleware — block cross-origin requests to local-trust-required routes.

Routes in ``LOCAL_TRUST_ROUTES`` return 403 if the request carries an ``Origin``
header that is not in the localhost allowlist.  Requests without an ``Origin``
header (e.g. curl, TestClient, server-to-server) are passed through.

This guards against malicious web pages reaching a running localhost labeler.
The check relies on ``Sec-Fetch-Site`` (preferred) or ``Origin`` (fallback).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_LOCALHOST_ORIGINS = frozenset({
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
})

LOCAL_TRUST_ROUTES: frozenset[str] = frozenset({
    "/api/fs/ls",
    "/api/projects/source-root",
})


class LocalTrustMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin requests to LOCAL_TRUST_ROUTES."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in LOCAL_TRUST_ROUTES:
            sec_fetch_site = request.headers.get("sec-fetch-site")
            if sec_fetch_site is not None and sec_fetch_site != "same-origin":
                # Browser explicitly flagged this as cross-origin.
                return JSONResponse(
                    {"detail": "cross-origin requests not permitted for this route"},
                    status_code=403,
                )
            origin = request.headers.get("origin")
            if origin is not None and origin not in _LOCALHOST_ORIGINS:
                return JSONResponse(
                    {"detail": "cross-origin requests not permitted for this route"},
                    status_code=403,
                )
        return await call_next(request)
```

Add `LocalTrustMiddleware` in `bootstrap.build_app` immediately after
`CORSMiddleware` (so it runs inside CORS but before the routers):

```python
from .middleware.local_trust import LocalTrustMiddleware

app.add_middleware(LocalTrustMiddleware)
```

### Change 3: `cors_allowed_origins` env var support

Because `Settings` uses pydantic-settings, add:

```python
model_config = SettingsConfigDict(
    env_prefix="PDLABELER_",
    env_parse_none_str="",
    # Allow list[str] from a comma-separated env var:
    json_schema_extra={"env_nested_delimiter": ","},
)
```

Or rely on pydantic-settings v2's built-in `json` parsing:
`PDLABELER_CORS_ALLOWED_ORIGINS='["http://localhost:5173"]'`.

Document this in `docs/usage/configuration.md` (create the file if absent).

## Implementation Plan

Slice 1 (test-first — CORS allowlist):

- Write `tests/unit/test_cors_hardening.py`:
  - `test_wildcard_cors_rejected` — assert `allow_origins=["*"]` is NOT
    present in the CORS middleware configuration.
  - `test_vite_dev_origin_allowed` — issue an OPTIONS preflight from
    `http://localhost:5173`; expect 200 + correct CORS response headers.
  - `test_arbitrary_origin_rejected` — issue a GET from
    `Origin: https://evil.example.com`; expect no CORS `allow-origin` header.

Slice 2 (implementation — CORS allowlist):

- Add `cors_allowed_origins` field to `Settings`.
- Update `CORSMiddleware` arguments in `bootstrap.build_app`.
- Run `make test AI=1` — confirm existing tests pass.

Slice 3 (test-first — `LocalTrustMiddleware`):

- Extend `tests/unit/test_cors_hardening.py`:
  - `test_fs_ls_cross_origin_rejected` — issue GET `/api/fs/ls?path=~` with
    `Origin: https://evil.example.com`; expect 403.
  - `test_fs_ls_localhost_origin_allowed` — same request with
    `Origin: http://localhost:5173`; expect 200.
  - `test_source_root_cross_origin_rejected` — POST `/api/projects/source-root`
    with `Origin: https://evil.example.com`; expect 403.
  - `test_local_trust_no_origin_passthrough` — GET `/api/fs/ls` with no
    `Origin` header; expect 200 (curl / TestClient scenario).
  - `test_sec_fetch_site_cross_origin_rejected` — GET `/api/fs/ls` with
    `Sec-Fetch-Site: cross-site`; expect 403.

Slice 4 (implementation — `LocalTrustMiddleware`):

- Create `src/pd_ocr_labeler_spa/middleware/__init__.py` (empty).
- Create `src/pd_ocr_labeler_spa/middleware/local_trust.py` (code in
  Decision section above).
- Wire `LocalTrustMiddleware` in `bootstrap.build_app`.
- Run `make test AI=1` + `make frontend-test AI=1`.

Slice 5 (documentation + close):

- Update `docs/architecture/02-backend.md §7` (CORS / auth section) to
  document the new constraints.
- Close #407 in the commit message.

## Test Plan

**Failing tests (prove the bugs before the fix):**

```python
# tests/unit/test_cors_hardening.py

def test_wildcard_cors_not_configured(app_settings):
    """CORS must not use allow_origins=['*'] after the fix."""
    # Before fix this assertion fails because the app uses wildcard.
    assert "*" not in app_settings.cors_allowed_origins

def test_fs_ls_cross_origin_rejected(test_client):
    """Cross-origin GET /api/fs/ls must be 403 after the fix."""
    resp = test_client.get(
        "/api/fs/ls",
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403

def test_source_root_cross_origin_rejected(test_client, tmp_path):
    """Cross-origin POST /api/projects/source-root must be 403 after the fix."""
    resp = test_client.post(
        "/api/projects/source-root",
        json={"path": str(tmp_path)},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403
```

**Regression tests (valid usage must continue to work):**

```python
def test_fs_ls_no_origin_passthrough(test_client):
    """Requests without Origin (curl, TestClient) must still work."""
    resp = test_client.get("/api/fs/ls")
    assert resp.status_code == 200

def test_fs_ls_localhost_origin_allowed(test_client):
    """Localhost Vite dev origin must be allowed."""
    resp = test_client.get(
        "/api/fs/ls",
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200

def test_cors_vite_dev_preflight(test_client):
    """OPTIONS preflight from Vite dev origin must return CORS allow headers."""
    resp = test_client.options(
        "/api/fs/ls",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
```

## Open Questions

1. **`cors_allowed_origins` default in production.** When the SPA is bundled
   into the wheel and served from the same origin as the API, `allow_origins`
   can be an empty list (same-origin-only). But the current `build_app`
   does not distinguish dev vs. production mode. Should the default be
   conditional on a `debug` / `dev_mode` setting, or should it always include
   the Vite dev ports? Recommend: always include them (they are no-ops when
   the Vite server is not running) and document that operators can override
   via `PDLABELER_CORS_ALLOWED_ORIGINS=[]` in production.

2. **`LocalTrustMiddleware` vs. a FastAPI dependency.** The middleware
   approach intercepts at the Starlette layer, before FastAPI routing. An
   alternative is a `Depends(require_local_trust)` FastAPI dependency on the
   two guarded routes. The dependency approach is more explicit and easier to
   test in isolation. Either is acceptable; this spec chose middleware for
   centralized auditability.

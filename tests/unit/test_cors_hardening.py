"""F-002 — CORS hardening and LocalTrustMiddleware tests.

Spec authority: ``docs/specs/2026-05-24-F-002-cors-and-auth-hardening.md``.

Issue: pdomain/pdomain-ocr-labeler-spa#407.

Slice 1: CORS allowlist tests.
Slice 3: LocalTrustMiddleware route-guard tests.
Slice 5: combined smoke tests.
"""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cors_kwargs(app):
    """Return the kwargs dict CORSMiddleware was added with."""
    for entry in app.user_middleware:
        cls = getattr(entry, "cls", None)
        if cls is CORSMiddleware:
            return getattr(entry, "kwargs", None) or getattr(entry, "options", {})
    raise AssertionError("CORSMiddleware not registered on app")


# ---------------------------------------------------------------------------
# Slice 1 — CORS allowlist (written before fix, expect red initially)
# ---------------------------------------------------------------------------


def test_wildcard_cors_not_in_settings() -> None:
    """Settings.cors_allowed_origins must not contain the wildcard '*'."""
    settings = Settings(mode="api_only")
    assert "*" not in settings.cors_allowed_origins, (
        "cors_allowed_origins must not include wildcard '*'. "
        "Override via PDLABELER_CORS_ALLOWED_ORIGINS env var."
    )


def test_wildcard_cors_not_configured_on_app() -> None:
    """CORSMiddleware must not be wired with allow_origins=['*']."""
    app = build_app(Settings(mode="api_only"))
    kwargs = _cors_kwargs(app)
    origins = kwargs.get("allow_origins", [])
    assert "*" not in origins, (
        "CORSMiddleware allow_origins must not include '*'. "
        "See F-002 spec: restrict to explicit localhost list."
    )


def test_cors_allow_methods_explicit() -> None:
    """CORSMiddleware allow_methods must be explicit, not ['*']."""
    app = build_app(Settings(mode="api_only"))
    kwargs = _cors_kwargs(app)
    methods = kwargs.get("allow_methods", [])
    assert "*" not in methods, "CORSMiddleware allow_methods must list explicit methods, not '*'."


def test_cors_allow_headers_explicit() -> None:
    """CORSMiddleware allow_headers must be explicit, not ['*']."""
    app = build_app(Settings(mode="api_only"))
    kwargs = _cors_kwargs(app)
    headers = kwargs.get("allow_headers", [])
    assert "*" not in headers, "CORSMiddleware allow_headers must list explicit headers, not '*'."


def test_vite_dev_origin_in_settings() -> None:
    """Default cors_allowed_origins must include the Vite dev-server origins."""
    settings = Settings(mode="api_only")
    assert "http://localhost:5173" in settings.cors_allowed_origins
    assert "http://127.0.0.1:5173" in settings.cors_allowed_origins


def test_cors_preflight_vite_origin(client: TestClient) -> None:
    """OPTIONS preflight from Vite dev origin must return CORS allow headers.

    Note: status-200 alone does not prove CORS is wired correctly;
    the allow-origin header is what browsers check.
    """
    resp = client.options(
        "/api/fs/ls",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers, (
        "Preflight from Vite dev origin must echo Access-Control-Allow-Origin."
    )


def test_cors_arbitrary_origin_not_echoed(client: TestClient) -> None:
    """A GET from an evil origin must not receive an ACAO header echoing that origin."""
    resp = client.get(
        "/api/fs/ls",
        headers={"Origin": "https://evil.example.com"},
    )
    # The middleware should NOT echo back the evil origin in ACAO.
    acao = resp.headers.get("access-control-allow-origin", "")
    assert "evil.example.com" not in acao, (
        f"CORSMiddleware must not echo a non-allowlisted origin. Received ACAO: {acao!r}"
    )


# ---------------------------------------------------------------------------
# Slice 3 — LocalTrustMiddleware route-guard tests (written before wiring)
# ---------------------------------------------------------------------------


def test_fs_ls_cross_origin_rejected(client: TestClient) -> None:
    """Cross-origin GET /api/fs/ls must be 403 after the fix."""
    resp = client.get(
        "/api/fs/ls",
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_fs_ls_localhost_origin_allowed(client: TestClient) -> None:
    """GET /api/fs/ls with a localhost origin must pass LocalTrustMiddleware."""
    resp = client.get(
        "/api/fs/ls",
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200


def test_source_root_cross_origin_rejected(client: TestClient, tmp_path) -> None:
    """Cross-origin POST /api/projects/source-root must be 403 after the fix."""
    resp = client.post(
        "/api/projects/source-root",
        json={"path": str(tmp_path)},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_local_trust_no_origin_passthrough(client: TestClient) -> None:
    """Requests without Origin (curl, TestClient) must pass LocalTrustMiddleware."""
    resp = client.get("/api/fs/ls")
    assert resp.status_code == 200


def test_sec_fetch_site_cross_site_rejected(client: TestClient) -> None:
    """GET /api/fs/ls with Sec-Fetch-Site: cross-site must be 403."""
    resp = client.get(
        "/api/fs/ls",
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert resp.status_code == 403


def test_sec_fetch_site_same_origin_allowed(client: TestClient) -> None:
    """GET /api/fs/ls with Sec-Fetch-Site: same-origin must pass."""
    resp = client.get(
        "/api/fs/ls",
        headers={"Sec-Fetch-Site": "same-origin"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Slice 5 — combined smoke: unguarded routes unaffected
# ---------------------------------------------------------------------------


def test_healthz_cross_origin_not_blocked(client: TestClient) -> None:
    """GET /healthz is not in LOCAL_TRUST_ROUTES; cross-origin must not get 403."""
    resp = client.get(
        "/healthz",
        headers={"Origin": "https://evil.example.com"},
    )
    # 403 would mean LocalTrustMiddleware is over-blocking
    assert resp.status_code != 403


def test_local_trust_does_not_block_source_root_same_origin(client: TestClient, tmp_path) -> None:
    """POST /api/projects/source-root with localhost origin must pass."""
    resp = client.post(
        "/api/projects/source-root",
        json={"path": str(tmp_path)},
        headers={"Origin": "http://localhost:8080"},
    )
    # Must not be 403 from LocalTrustMiddleware (may be 400/422 from validation)
    assert resp.status_code != 403


# ---------------------------------------------------------------------------
# P4.6 (parity P6 / C09) — same-origin requests on NON-default ports.
#
# The server binds an arbitrary port (auto-port mode, e2e, multi-instance);
# the browser then sends Origin: http://127.0.0.1:<that port>. The fixed
# 8080/5173 allowlist rejected those even though the request was literally
# same-origin (reproduced live: Origin http://127.0.0.1:8931 +
# Sec-Fetch-Site: same-origin → 403). The e2e suites couldn't catch it
# because they seed via httpx (no Origin header).
# ---------------------------------------------------------------------------


def _client_on_port(settings: Settings, port: int) -> TestClient:
    """TestClient whose base_url (and thus Host header) uses ``port``."""
    app = build_app(settings)
    return TestClient(app, base_url=f"http://127.0.0.1:{port}")


def test_source_root_same_origin_random_port_with_sec_fetch_site(settings: Settings, tmp_path) -> None:
    """Browser same-origin POST on a random port: Sec-Fetch-Site: same-origin
    is unforgeable by web content and must be honored regardless of Origin."""
    with _client_on_port(settings, 8931) as c:
        resp = c.post(
            "/api/projects/source-root",
            json={"path": str(tmp_path)},
            headers={
                "Origin": "http://127.0.0.1:8931",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert resp.status_code != 403, "same-origin request rejected on a non-default port"


def test_source_root_origin_matches_host_random_port(settings: Settings, tmp_path) -> None:
    """Older browsers send Origin without Sec-Fetch-Site: an Origin equal to
    the request's own host IS same-origin and must pass on any port."""
    with _client_on_port(settings, 8931) as c:
        resp = c.post(
            "/api/projects/source-root",
            json={"path": str(tmp_path)},
            headers={"Origin": "http://127.0.0.1:8931"},
        )
        assert resp.status_code != 403, "host-matching Origin rejected on a non-default port"


def test_fs_ls_origin_matches_host_lan_address(settings: Settings) -> None:
    """Same-origin is host equality, not a localhost-names allowlist — a LAN
    bind accessed from another machine is still same-origin."""
    app = build_app(settings)
    with TestClient(app, base_url="http://192.168.7.5:9000") as c:
        resp = c.get(
            "/api/fs/ls",
            headers={"Origin": "http://192.168.7.5:9000"},
        )
        assert resp.status_code == 200


def test_source_root_cross_port_origin_still_rejected(settings: Settings, tmp_path) -> None:
    """A mismatched-port Origin (without Sec-Fetch-Site) is cross-origin and
    must still be rejected — the P4.6 fix must not loosen the guard."""
    with _client_on_port(settings, 8931) as c:
        resp = c.post(
            "/api/projects/source-root",
            json={"path": str(tmp_path)},
            headers={"Origin": "http://127.0.0.1:9999"},
        )
        assert resp.status_code == 403


def test_source_root_evil_origin_with_cross_site_fetch_rejected(settings: Settings, tmp_path) -> None:
    """Cross-site browser fetch on a random port keeps getting 403."""
    with _client_on_port(settings, 8931) as c:
        resp = c.post(
            "/api/projects/source-root",
            json={"path": str(tmp_path)},
            headers={
                "Origin": "https://evil.example.com",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        assert resp.status_code == 403

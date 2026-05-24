"""Unit tests for LocalTrustMiddleware in isolation.

Spec: ``docs/specs/2026-05-24-F-002-cors-and-auth-hardening.md`` slice 3.
Issue: ConcaveTrillion/pd-ocr-labeler-spa#407.
"""

from __future__ import annotations

from pd_ocr_labeler_spa.middleware.local_trust import (
    _LOCALHOST_ORIGINS,
    LOCAL_TRUST_ROUTES,
    LocalTrustMiddleware,
)


class TestLocalTrustConstants:
    """Module-level constants must contain the right paths and origins."""

    def test_fs_ls_in_local_trust_routes(self) -> None:
        assert "/api/fs/ls" in LOCAL_TRUST_ROUTES

    def test_source_root_in_local_trust_routes(self) -> None:
        assert "/api/projects/source-root" in LOCAL_TRUST_ROUTES

    def test_localhost_origins_include_vite_dev(self) -> None:
        assert "http://localhost:5173" in _LOCALHOST_ORIGINS
        assert "http://127.0.0.1:5173" in _LOCALHOST_ORIGINS

    def test_localhost_origins_include_production_port(self) -> None:
        assert "http://localhost:8080" in _LOCALHOST_ORIGINS
        assert "http://127.0.0.1:8080" in _LOCALHOST_ORIGINS

    def test_localhost_origins_no_https(self) -> None:
        """https:// localhost should not be in the allowlist (self-signed certs)."""
        for origin in _LOCALHOST_ORIGINS:
            assert not origin.startswith("https://"), f"Unexpected https:// origin in allowlist: {origin}"

    def test_evil_origin_not_in_allowlist(self) -> None:
        assert "https://evil.example.com" not in _LOCALHOST_ORIGINS

    def test_middleware_is_subclass_of_base(self) -> None:
        from starlette.middleware.base import BaseHTTPMiddleware

        assert issubclass(LocalTrustMiddleware, BaseHTTPMiddleware)

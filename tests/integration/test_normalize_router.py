"""Integration tests for api/normalize.py — normalize availability probe (#261).

Spec: docs/specs/2026-05-12-text-normalization-design.md §Toggle UI
Issue #261 acceptance: route registered, returns 200 JSON payload.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


def test_normalize_available_route_in_openapi(tmp_path: Path) -> None:
    """GET /api/normalize/available is registered in the OpenAPI spec."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
        path = "/api/normalize/available"
        assert path in spec["paths"]
        assert "get" in spec["paths"][path]


def test_normalize_available_returns_200(tmp_path: Path) -> None:
    """GET /api/normalize/available returns 200."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as client:
        resp = client.get("/api/normalize/available")
        assert resp.status_code == 200


def test_normalize_available_returns_bool(tmp_path: Path) -> None:
    """GET /api/normalize/available returns JSON with boolean 'available' key."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as client:
        resp = client.get("/api/normalize/available")
        body = resp.json()
        assert "available" in body
        assert isinstance(body["available"], bool)


def test_normalize_available_reflects_is_available(tmp_path: Path, monkeypatch) -> None:
    """GET /api/normalize/available returns the result of core.text_normalize.is_available."""
    import pd_ocr_labeler_spa.api.normalize as normalize_mod

    monkeypatch.setattr(normalize_mod, "is_available", lambda: True)

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as client:
        resp = client.get("/api/normalize/available")
        assert resp.json()["available"] is True

    monkeypatch.setattr(normalize_mod, "is_available", lambda: False)
    app2 = build_app(settings)
    with TestClient(app2) as client2:
        resp2 = client2.get("/api/normalize/available")
        assert resp2.json()["available"] is False

"""GET /healthz contract.

Spec: ``specs/02-backend.md §5.1`` — ``{"status": "ok", "version": "..."}``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_returns_status_ok_and_version(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # version is an importlib-metadata-derived string; we don't pin a
    # value (hatch-vcs) but it must be present and a string.
    assert isinstance(body["version"], str)
    assert body["version"]


def test_healthz_is_unauthenticated(client: TestClient) -> None:
    # No Authorization header is sent — must still return 200.
    # Probes carry no creds; auth gates must not apply to /healthz.
    resp = client.get("/healthz")
    assert resp.status_code == 200


def test_healthz_excluded_from_openapi_schema(client: TestClient) -> None:
    # /healthz uses include_in_schema=False so it doesn't pollute the
    # generated TS types — the SPA never calls it.
    schema = client.get("/openapi.json").json()
    assert "/healthz" not in schema.get("paths", {})


def test_env_js_returns_window_env_assignment(client: TestClient) -> None:
    resp = client.get("/env.js")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/javascript")
    # M0 contract from specs/02-backend.md §5.1:
    #     window.__ENV__ = {"API_BASE": "", "API_TOKEN": null};
    body = resp.text
    assert body.startswith("window.__ENV__ = ")
    assert '"API_BASE": ""' in body
    assert '"API_TOKEN": null' in body

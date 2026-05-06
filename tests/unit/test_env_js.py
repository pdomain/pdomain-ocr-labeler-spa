"""``GET /env.js`` contract — parametrised across ``Settings.mode``.

Per ``specs/02-backend.md §2`` step 12, ``/env.js`` (and the future
``/image-cache`` mount + SPA fallback) is only installed when
``settings.mode != "api_only"``. ``api_only`` is the
OpenAPI-export / pure-API integration shape — the SPA bootstrap shim
has no business existing there.

Per ``specs/02-backend.md §5.1`` the body shape is exactly::

    window.__ENV__ = {"API_BASE": "", "API_TOKEN": null};

Regression for B-01.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _make_client(tmp_path: Path, mode: str) -> TestClient:
    s = Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode=mode,  # type: ignore[arg-type]
    )
    return TestClient(build_app(s))


@pytest.mark.parametrize("mode", ["normal"])
def test_env_js_present_in_non_api_only_modes(tmp_path: Path, mode: str) -> None:
    with _make_client(tmp_path, mode) as client:
        resp = client.get("/env.js")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/javascript")

    body = resp.text
    # Spec §5.1 contract — exact assignment shape.
    assert body.startswith("window.__ENV__ = ")
    assert body.rstrip().endswith(";")

    # Extract the JSON literal between "window.__ENV__ = " and the
    # trailing ";" so we can assert on keys precisely.
    m = re.match(r"window\.__ENV__ = (?P<obj>\{.*\});\s*\Z", body, re.DOTALL)
    assert m, f"unexpected /env.js body: {body!r}"
    payload = json.loads(m.group("obj"))

    # Spec-pinned keys + values: M0 has no auth, so API_TOKEN is null
    # and API_BASE is the same-origin empty string.
    assert set(payload.keys()) == {"API_BASE", "API_TOKEN"}
    assert payload["API_BASE"] == ""
    assert payload["API_TOKEN"] is None


def test_env_js_not_registered_in_api_only_mode(tmp_path: Path) -> None:
    with _make_client(tmp_path, "api_only") as client:
        resp = client.get("/env.js")
    # Route must not be registered → 404 (not, e.g., 200-with-empty body).
    assert resp.status_code == 404


def test_env_js_route_absent_from_router_table_in_api_only(tmp_path: Path) -> None:
    # Belt-and-suspenders: confirm the route literally isn't on the app
    # in api_only mode, so any future middleware that returns 404s for
    # other reasons can't mask the gate regressing.
    s = Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )
    app = build_app(s)
    paths = {getattr(r, "path", None) for r in app.router.routes}
    assert "/env.js" not in paths


def test_env_js_route_present_in_router_table_in_normal(tmp_path: Path) -> None:
    s = Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="normal",
    )
    app = build_app(s)
    paths = {getattr(r, "path", None) for r in app.router.routes}
    assert "/env.js" in paths


def test_build_env_helper_signature_has_no_unused_settings_param() -> None:
    """Regression for B-07.

    The prior shape was ``_build_env(settings: Settings) -> dict`` but
    the body never read ``settings``. Until M2 (auth seam) wires an
    actual consumer (e.g. ``settings.api_key``), the parameter is a
    misleading promise: static-analysis (ruff ``ARG``) and human readers
    are told the function depends on settings when it does not.

    Pin the cleaned-up signature so a future contributor doesn't quietly
    re-introduce the dead parameter ahead of an actual consumer.
    """
    import inspect

    from pd_ocr_labeler_spa.api.env_js import _build_env

    sig = inspect.signature(_build_env)
    assert list(sig.parameters) == [], (
        "_build_env should take no parameters until M2 reintroduces a "
        f"settings consumer; got {list(sig.parameters)}"
    )

"""``build_app(settings)`` smoke tests — M0 surface.

Spec: ``docs/architecture/02-backend.md §2``. M0 only verifies that the factory
returns a real FastAPI app with /healthz and /env.js wired and that
``app.state.settings`` is the same object that was passed in.
"""

from __future__ import annotations

from fastapi import FastAPI

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def test_build_app_returns_fastapi_with_settings_stashed() -> None:
    s = Settings(mode="api_only")
    app = build_app(s)
    assert isinstance(app, FastAPI)
    assert app.state.settings is s


def test_build_app_with_no_settings_constructs_default() -> None:
    # Convenient for ``uvicorn --factory`` which calls build_app() with
    # no args.
    app = build_app(None)
    assert isinstance(app, FastAPI)
    assert isinstance(app.state.settings, Settings)


def test_build_app_is_pure_same_settings_same_routes() -> None:
    # Spec: "The factory is pure — same Settings always produces the
    # same wired graph."
    # Use mode="normal" so /env.js IS expected on the route table —
    # api_only intentionally drops it (docs/architecture/02-backend.md §2 step 12).
    s = Settings(mode="normal")
    app1 = build_app(s)
    app2 = build_app(s)
    paths_1 = {route.path for route in app1.routes if hasattr(route, "path")}
    paths_2 = {route.path for route in app2.routes if hasattr(route, "path")}
    assert paths_1 == paths_2
    assert "/healthz" in paths_1
    assert "/env.js" in paths_1


def test_build_app_api_only_mode_omits_env_js() -> None:
    # Spec §2 step 12: /env.js is only installed when mode != "api_only".
    # Regression for B-01.
    s = Settings(mode="api_only")
    app = build_app(s)
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/healthz" in paths
    assert "/env.js" not in paths

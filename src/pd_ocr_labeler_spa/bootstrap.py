"""``build_app(settings)`` — FastAPI app factory.

M0 scope: mount ``/healthz`` and ``/env.js`` against a fresh ``FastAPI``
instance. CORS middleware mirrors ``pd-prep-for-pgdp`` so Vite-dev
(5173 → 8080) works out of the box.

Per ``specs/02-backend.md §2`` the full factory order is

    1. configure_logging
    2. build adapters (storage / auth / ocr)
    3. build job runner + broker
    4. build AppState
    5. lifespan
    6. FastAPI(...)
    7. CORSMiddleware
    8. RequestIdMiddleware (outermost)
    9. stash adapters on app.state
    10. install error handlers + routers
    11. install /healthz BEFORE the SPA mount
    12. install /env.js + image-cache + SPA fallback (skipped when
        mode == "api_only")

Steps 1-4 and 7-12 (beyond /healthz, /env.js, settings stashing) land in
M1+. The factory is pure: same ``Settings`` always produces the same
wired graph.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.env_js import install_env_js
from .api.healthz import install_healthz
from .settings import Settings

log = logging.getLogger(__name__)


def build_app(settings: Settings | None = None) -> FastAPI:
    """Build a fresh FastAPI app from ``settings``.

    Passing ``None`` constructs a default ``Settings()`` — convenient for
    ``uvicorn --factory`` and for the OpenAPI export entrypoint that
    needs a minimal app graph.
    """
    if settings is None:
        settings = Settings()

    app = FastAPI(title="pd-ocr-labeler-spa")

    # CORS: same shape as pgdp-prep. Acceptable because the SPA serves
    # from the same origin in production; wide setting unblocks
    # Vite-dev (5173 → 8080).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    # Stash settings on app.state so dependencies / routes can read it.
    app.state.settings = settings

    # /healthz BEFORE SPA mount so the catch-all fallback can't shadow it.
    install_healthz(app)
    install_env_js(app)

    # M0: no SPA static mount yet — frontend bundle lands in M0 part 2.
    # In api_only mode we'd skip the mount anyway; record the intent.
    if settings.mode == "api_only":
        log.debug("api_only mode: skipping SPA static mount")

    return app

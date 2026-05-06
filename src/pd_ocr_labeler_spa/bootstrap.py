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
from .api.middleware.error_handler import install_error_handlers
from .api.middleware.request_id import RequestIdMiddleware
from .api.static_mounts import install_image_cache, install_spa_fallback
from .core.app_state import build_app_state
from .core.logging_config import configure_logging
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

    # Spec §2 step 1: configure logging first so the rest of the
    # factory (and the lifespan tasks queued from here) emit through
    # the configured root handler.
    configure_logging(settings.log_format)

    app = FastAPI(title="pd-ocr-labeler-spa")

    # CORS: same shape as pgdp-prep. Acceptable because the SPA serves
    # from the same origin in production; wide setting unblocks
    # Vite-dev (5173 → 8080).
    #
    # NOTE: ``allow_credentials`` is intentionally omitted. Per the CORS
    # spec, browsers reject ``Access-Control-Allow-Origin: *`` paired
    # with ``Access-Control-Allow-Credentials: true``. Matches
    # pd-prep-for-pgdp/src/pd_prep_for_pgdp/bootstrap.py and
    # specs/02-backend.md §step-7. Auth (M2+) will switch to a concrete
    # origin list and may then re-enable credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Spec §2 step 8 + §12: RequestIdMiddleware is added LAST so it
    # becomes the OUTERMOST layer. Starlette's ``add_middleware``
    # prepends to the user_middleware stack — so "last added =
    # outermost" — meaning every log line emitted from inside CORS,
    # routers, exception handlers, and the SPA fallback all see the
    # request-id contextvar.
    app.add_middleware(RequestIdMiddleware, header_name=settings.request_id_header)

    # Stash settings on app.state so dependencies / routes can read it.
    app.state.settings = settings

    # Spec §2 step 4 + step 9: build the AppState (adapter wiring graph)
    # and stash both the singleton and each adapter on ``app.state`` so
    # ``api/dependencies.py`` providers can read them by name. Wiring
    # errors (e.g. ``storage_backend = "s3"``) raise here, at app-build
    # time — not on first request — per the loud-at-wire-time policy in
    # spec §2.
    app_state = build_app_state(settings)
    app.state.app_state = app_state
    app.state.storage = app_state.storage
    app.state.auth = app_state.auth
    app.state.ocr_engine = app_state.ocr_engine

    # Spec §2 step 10: install error handlers AFTER middleware (CORS +
    # RequestId) so a 500 still passes back through both on the way
    # out — the response keeps its CORS headers AND its X-Request-ID
    # echo. FastAPI exception handlers register one-per-class, so this
    # is idempotent under repeated build_app calls.
    install_error_handlers(app)

    # /healthz BEFORE SPA mount so the catch-all fallback can't shadow it.
    install_healthz(app)

    # Per specs/02-backend.md §2 step 12: /env.js, /image-cache, and the
    # SPA fallback only land in non-api_only modes. api_only is the
    # OpenAPI-export / pure-API integration shape — the SPA bootstrap
    # shim has no business existing there.
    if settings.mode != "api_only":
        # Order matters:
        # 1. /env.js — concrete route, registered first so the SPA
        #    catch-all can't shadow it.
        # 2. /image-cache/{key:path} — concrete route through IStorage
        #    (D-019); also concrete so the catch-all can't shadow.
        # 3. SPA fallback `/{full_path:path}` — registered LAST so every
        #    real route wins ahead of the catch-all. Spec §10.
        install_env_js(app)
        install_image_cache(app)
        install_spa_fallback(app)
    else:
        log.debug("api_only mode: skipping /env.js + /image-cache + SPA fallback")

    return app

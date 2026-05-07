"""``build_app(settings)`` — FastAPI app factory.

CORS middleware mirrors ``pd-prep-for-pgdp`` so Vite-dev (5173 → 8080)
works out of the box.

Per ``specs/02-backend.md §2`` the full factory order is

    1. configure_logging                                    [done]
    2. build adapters (storage / auth / ocr)                [done — via build_app_state]
    3. build job runner + broker                            [deferred to M3]
    4. build AppState                                       [done]
    5. lifespan                                             [done — startup hook calls
                                                              resolve_initial_project +
                                                              ActiveProjectCarrier
                                                              .set_active_project; M2 slice 3]
    6. FastAPI(...)                                         [done]
    7. CORSMiddleware                                       [done]
    8. RequestIdMiddleware (outermost)                      [done]
    9. stash adapters on app.state                          [done]
    10. install error handlers + routers                    [error handlers done; routers M2-M9]
    11. install /healthz BEFORE the SPA mount               [done]
    12. install /env.js + image-cache + SPA fallback        [done; skipped when mode == "api_only"]
        (skipped when mode == "api_only")

The factory is pure: same ``Settings`` always produces the same
wired graph. Only the lifespan startup hook touches the filesystem,
and it does so behind ``with TestClient(app) as c`` — i.e. lazily,
not at construction.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.env_js import install_env_js
from .api.healthz import install_healthz
from .api.middleware.error_handler import install_error_handlers
from .api.middleware.request_id import RequestIdMiddleware
from .api.projects import install_projects_router
from .api.static_mounts import install_image_cache, install_spa_fallback
from .core.active_project import (
    ActiveProjectCarrier,
    InvalidProjectDirError,
)
from .core.app_state import build_app_state
from .core.logging_config import configure_logging
from .core.persistence.session_state import load_session_state
from .core.project_state import ProjectState
from .core.startup_discovery import resolve_initial_project
from .settings import Settings

log = logging.getLogger(__name__)


def _make_lifespan(
    settings: Settings,
    carrier: ActiveProjectCarrier,
):
    """Build the FastAPI ``lifespan`` async context manager.

    Spec authority: ``specs/02-backend.md §2`` step 5 (lifespan) +
    ``§13`` (background discovery + restoration). M2 slice 3 wires
    the startup half; the shutdown half is a no-op for now (the
    JobRunner background task arrives in M3).

    Startup order:

    1. Read ``session_state.json`` from ``settings.data_root`` via
       ``load_session_state`` — returns ``None`` on every failure
       path (missing / malformed / pydantic-rejected). No raises.
    2. Resolve the initial project via
       ``resolve_initial_project(settings, session_state=...)`` —
       CLI overrides session per spec §13 step 4; invalid CLI falls
       through to session; stale session returns ``None``.
    3. If a resolution exists, call
       ``carrier.set_active_project(path)``. The carrier
       re-validates internally (defensive belt-and-suspenders) and
       raises ``InvalidProjectDirError`` only if the dir vanished
       between the resolver's check and the carrier's check —
       that's a TOCTOU race we treat as "no project" rather than
       "refuse to boot", matching the legacy parity contract from
       slice 1's docstring.

    The factory pattern (closure over ``settings`` + ``carrier``)
    keeps the lifespan dependency-free of module-global state, so
    each ``build_app`` call gets its own startup hook bound to its
    own carrier — pinned by
    ``test_lifespan_startup_hook_is_idempotent_across_app_builds``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
        # Step 1: read session_state (best-effort, never raises).
        session = load_session_state(settings.data_root)

        # Step 2: resolve initial project (pure; logs WARNING/DEBUG).
        resolved = resolve_initial_project(settings, session_state=session)

        # Step 3: feed into the carrier if a candidate exists.
        if resolved is not None:
            try:
                carrier.set_active_project(resolved.path)
            except InvalidProjectDirError:
                # TOCTOU: dir vanished between resolver-validate and
                # carrier-validate. Boot to "no project loaded" rather
                # than crash; user can pick from the discovery dropdown
                # once M2-proper lands.
                log.warning(
                    "Active project dir vanished between resolve and set; booting with no project loaded.",
                    extra={
                        "initial_project_path": str(resolved.path),
                        "initial_project_source": resolved.source,
                    },
                )

        try:
            yield
        finally:
            # No shutdown work yet; M3's JobRunner will land here.
            pass

    return lifespan


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

    # Spec §2 step 5 + §13: construct the active-project carrier and
    # the lifespan closure BEFORE ``FastAPI(...)`` so the lifespan can
    # be passed in at construction. The carrier is later re-stashed on
    # ``app.state.active_project_carrier`` (step 9) so DI can resolve
    # it; the same instance is referenced by both the startup hook
    # closure and the request-time provider.
    carrier = ActiveProjectCarrier()
    lifespan = _make_lifespan(settings, carrier)

    app = FastAPI(title="pd-ocr-labeler-spa", lifespan=lifespan)

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

    # Spec §13 + §00 "State model" lines 179-201: the active-project
    # pointer is mutable and lives separately from the frozen
    # ``AppState``. The carrier was constructed above so the lifespan
    # closure could capture it; here we expose it on ``app.state`` so
    # the DI provider ``get_active_project_carrier`` can resolve it.
    # Slice 3 wired the lifespan startup hook (calls
    # ``resolve_initial_project()`` and feeds the result into
    # ``carrier.set_active_project``); slice 4 will add
    # ``POST /api/projects/load`` to mutate it from the request path.
    app.state.active_project_carrier = carrier

    # Spec ``§00-overview.md`` lines 185-187: ``ProjectState`` is the
    # per-project graph (loaded ``Project`` + per-page state), separate
    # from the ``ActiveProjectCarrier`` pointer. M2 slice 5 wires it so
    # ``POST /api/projects/load`` can call
    # ``state.set_loaded_project(project)`` after the persistence layer
    # builds the model. A fresh ``ProjectState`` per ``build_app`` —
    # like ``ActiveProjectCarrier`` it's process-scoped, not module-
    # global, so multiple ``build_app(...)`` calls in the same test
    # process get isolated state.
    app.state.project_state = ProjectState()

    # Spec §2 step 10: install error handlers AFTER middleware (CORS +
    # RequestId) so a 500 still passes back through both on the way
    # out — the response keeps its CORS headers AND its X-Request-ID
    # echo. FastAPI exception handlers register one-per-class, so this
    # is idempotent under repeated build_app calls.
    install_error_handlers(app)

    # /healthz BEFORE SPA mount so the catch-all fallback can't shadow it.
    install_healthz(app)

    # /api/projects router — M2 slice 4. Concrete prefix (/api/...) so
    # ordering vs. the SPA catch-all is unambiguous; included alongside
    # /healthz for symmetry. M2-proper will add /api/pages, /api/words,
    # etc.
    install_projects_router(app)

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

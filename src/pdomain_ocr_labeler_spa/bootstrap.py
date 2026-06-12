"""``build_app(settings)`` — FastAPI app factory.

CORS middleware mirrors ``pdomain-prep-for-pgdp`` so Vite-dev (5173 → 8080)
works out of the box.

Per ``docs/architecture/02-backend.md §2`` the full factory order is

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

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pdomain_ops.suite.routes import mount_routes as mount_suite_routes
from pdomain_ops.suite.shared_paths import publish_shared_path
from pdomain_ops.suite.types import InstalledApp

from .api.env_js import install_env_js
from .api.export import install_export_router
from .api.fs import install_fs_router
from .api.healthz import install_healthz
from .api.history import install_history_router
from .api.jobs import install_jobs_router
from .api.label_vocabulary import install_label_vocabulary_router
from .api.lines_paragraphs import install_lines_paragraphs_router
from .api.middleware.error_handler import install_error_handlers
from .api.middleware.request_id import RequestIdMiddleware
from .api.normalize import install_normalize_router
from .api.notifications import install_notifications_router
from .api.ocr_config import _resolve_local_models_root, install_ocr_config_router
from .api.pages import install_pages_router
from .api.projects import install_projects_router
from .api.refine import install_refine_router
from .api.session_state import install_session_state_router
from .api.static_mounts import install_blob_route, install_spa_fallback
from .api.words import install_words_router
from .core.active_project import (
    ActiveProjectCarrier,
    InvalidProjectDirError,
)
from .core.app_state import build_app_state
from .core.jobs import JobEventBroker, JobRunner
from .core.logging_config import configure_logging
from .core.notifications import NotificationQueue
from .core.ocr.predictor import PredictorCache
from .core.ocr.weights_resolver import build_weights_resolver
from .core.ocr_config_state import OCRConfigCarrier
from .core.persistence.config_yaml import load_config
from .core.persistence.ocr_config import load_ocr_config
from .core.persistence.page_store import LabelerPageStore
from .core.persistence.pidfile import check_and_write_pidfile, release_pidfile
from .core.persistence.session_state import load_session_state
from .core.project_state import ProjectState
from .core.source_root_state import SourceRootCarrier
from .core.startup_discovery import resolve_initial_project
from .middleware.local_trust import LocalTrustMiddleware
from .settings import Settings

log = logging.getLogger(__name__)


def _suite_app_metadata(settings: Settings) -> InstalledApp:
    try:
        package_version = version("pdomain-ocr-labeler-spa")
    except PackageNotFoundError:
        package_version = "0.0.0"

    return InstalledApp(
        app_id="pdomain-ocr-labeler-spa",
        package="pdomain-ocr-labeler-spa",
        version=package_version,
        binary=sys.executable,
        default_port=settings.port,
        icon="/static/icon.svg",
        display_name="OCR Labeler",
        description="OCR correction and labeling workspace.",
    )


def _make_lifespan(
    settings: Settings,
    carrier: ActiveProjectCarrier,
    ocr_carrier: OCRConfigCarrier,
    runner: JobRunner,
):
    """Build the FastAPI ``lifespan`` async context manager.

    Spec authority: ``docs/architecture/02-backend.md §2`` step 5 (lifespan) +
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
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Issue #223 — pidfile check: warn if another live process holds
        # the cache root; write our own PID regardless.  Advisory-only;
        # does not prevent startup.
        check_and_write_pidfile(settings.cache_root)

        # M3 slice 8c-iv-b: seed the OCRConfigCarrier from the
        # ``ocr_config.json`` sidecar (if present + valid). A missing
        # / corrupt sidecar returns ``None`` and the carrier keeps its
        # construction-time defaults (``stock``, ``stock``, None) —
        # matching the carrier's natural cold-start state. Done BEFORE
        # session_state to keep the order stable for log readers
        # (carrier-state logged first, project-resolution second).
        persisted = load_ocr_config(settings.data_root)
        if persisted is not None:
            ocr_carrier.set_models(
                detection_key=persisted.selected_detection_key,
                recognition_key=persisted.selected_recognition_key,
                hf_pinned_revision=persisted.hf_pinned_revision,
            )
            # M9.2: restore auto-rotate settings from sidecar.
            ocr_carrier.set_auto_rotate(
                auto_rotate_on_load=persisted.auto_rotate_on_load,
                auto_rotate_method=persisted.auto_rotate_method,
            )

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

        # Track C: publish export root as a suite shared path so sibling
        # apps (e.g. pdomain-ocr-trainer-spa) can discover labeled exports.
        # Best-effort: a missing/unwritable suite dir must not abort startup.
        _export_root = Path(settings.data_root) / "doctr-export"
        try:
            publish_shared_path(
                "doctr-export-root",
                _export_root,
                app="pdomain-ocr-labeler-spa",
            )
            log.debug("published shared path: doctr-export-root → %s", _export_root)
        except Exception:  # noqa: BLE001
            log.warning("publish_shared_path failed; continuing startup", exc_info=True)

        runner_task = asyncio.create_task(runner.run_forever())
        try:
            yield
        finally:
            await runner.stop()
            runner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await runner_task
            # Issue #223 — release pidfile on clean shutdown.
            release_pidfile(settings.cache_root)

    return lifespan


def _install_legacy_redirects(app: FastAPI) -> None:
    """Register 301 redirects for the legacy single-word SPA paths.

    Spec §4 / issue #185 bullet 3. Legacy paths:

    - ``/project/{id}`` → ``/projects/{id}``
    - ``/project/{id}/page/{n}`` → ``/projects/{id}/pages/pageno/{n}``

    Registered with ``include_in_schema=False`` so they don't pollute
    the OpenAPI schema. They're SPA routes (not API routes) so they
    don't need a schema entry.
    """
    from fastapi.responses import RedirectResponse

    @app.get("/project/{project_id}", include_in_schema=False)
    def legacy_project_redirect(project_id: str) -> RedirectResponse:
        return RedirectResponse(url=f"/projects/{project_id}", status_code=301)

    @app.get("/project/{project_id}/page/{page_number}", include_in_schema=False)
    def legacy_page_redirect(project_id: str, page_number: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"/projects/{project_id}/pages/pageno/{page_number}",
            status_code=301,
        )


def _suppress_ops_schema_violations(app: FastAPI) -> None:
    """Hide pdomain-ops library routes that cannot satisfy our response_model rule.

    ``pdomain_ops.suite.routes.mount_routes`` registers several routes whose
    return types are ``dict[str, object]`` or bare ``Response`` — patterns our
    CONVENTIONS.md §Rule prohibits for first-party routes, but which we cannot
    fix upstream without a library release.  We suppress them from the OpenAPI
    schema so:

    1. ``test_healthz_excluded_from_openapi_schema`` keeps passing — ops mounts
       a second ``/healthz`` without ``include_in_schema=False``; our local copy
       (registered first, wins routing) already has it, but ops' copy would
       pollute the schema if left visible.
    2. ``test_all_json_routes_have_typed_response_model`` keeps passing — the
       ops routes that return ``dict[str, object]`` or binary ``Response`` would
       fail the typed-schema check.
    3. ``test_every_schema_route_has_explicit_response_model`` keeps passing —
       ``GET /api/icons/{size}`` has ``response_model=None`` with a default
       response class, which looks like a missing ``response_model=`` declaration.

    Routes suppressed (all library-owned, not first-party):
    - ``/healthz`` (second registration, ops duplicate of our include_in_schema=False copy)
    - ``POST /api/suite/launch``  (returns dict; launch-result shape not Pydantic)
    - ``GET  /api/suite/prefs``   (returns dict; prefs blob not typed here)
    - ``GET  /api/icons/{size}``  (returns binary PNG Response; not JSON)
    - ``POST /api/suite/update``  (returns dict; restart_required blob)

    Cross-repo recommendation
      Target: pdomain-ops
      Reason: suite routes use dict[str, object] return types and mount /healthz
        without include_in_schema=False; typed Pydantic response models +
        include_in_schema=False on /healthz would let consumers drop this patch.
    """
    from fastapi.routing import APIRoute

    # Paths whose ops-mounted routes cannot provide a typed response_model.
    # Keyed by (method, path) pairs matching the APIRoute attributes.
    ops_suppress: frozenset[tuple[str, str]] = frozenset(
        {
            ("GET", "/healthz"),  # ops duplicate; our include_in_schema=False copy already registered
            ("POST", "/api/suite/launch"),  # returns dict[str, object]
            ("GET", "/api/suite/prefs"),  # returns dict[str, object]
            ("GET", "/api/icons/{size}"),  # returns binary PNG Response
            ("POST", "/api/suite/update"),  # returns dict[str, object]
        }
    )

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not getattr(route, "include_in_schema", True):
            continue  # already suppressed
        methods = route.methods or set()
        for method, path in ops_suppress:
            if route.path == path and method in methods:
                route.include_in_schema = False
                break


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
    # the configured root handler. Use the log_level from settings
    # (set by --verbose CLI flag or PDLABELER_LOG_LEVEL env).
    configure_logging(settings.log_format, level=settings.log_level)

    # Spec §2 step 5 + §13: construct the active-project carrier and
    # the lifespan closure BEFORE ``FastAPI(...)`` so the lifespan can
    # be passed in at construction. The carrier is later re-stashed on
    # ``app.state.active_project_carrier`` (step 9) so DI can resolve
    # it; the same instance is referenced by both the startup hook
    # closure and the request-time provider.
    carrier = ActiveProjectCarrier()
    # M3 slice 8c-iv-b: build the OCRConfigCarrier here too so the
    # lifespan can capture it via closure and seed it from the
    # ``ocr_config.json`` sidecar before any request arrives. Per-
    # ``build_app`` instance so test isolation holds (no module-global
    # state).
    ocr_carrier = OCRConfigCarrier()
    # Spec §2 step 3 + §11: build the JobEventBroker and JobRunner before
    # the lifespan so the runner can be started in the lifespan task and
    # stashed on ``app.state`` for DI. Per-``build_app`` for test isolation.
    broker = JobEventBroker()
    runner = JobRunner(broker, context={"settings": settings})
    lifespan = _make_lifespan(settings, carrier, ocr_carrier, runner)

    app = FastAPI(title="pdomain-ocr-labeler-spa", lifespan=lifespan)

    # CORS: restrict to explicit localhost origins (F-002 hardening).
    # The SPA is served from the same origin as the API in production,
    # so only the Vite dev-server origins need to be listed here.
    # Operators can override via PDLABELER_CORS_ALLOWED_ORIGINS env var.
    #
    # NOTE: ``allow_credentials`` is intentionally omitted — browsers
    # reject ``Access-Control-Allow-Origin: *`` paired with credentials,
    # and auth is deferred (D-042). See docs/architecture/02-backend.md §step-7.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )

    # F-002: LocalTrustMiddleware blocks cross-origin requests to
    # designated local-trust-required routes (/api/fs/ls,
    # /api/projects/source-root). Added AFTER CORSMiddleware so it runs
    # inside CORS — CORS preflight OPTIONS requests are already handled
    # before this middleware fires. Requests without an Origin header
    # (curl, TestClient) are passed through unchanged.
    app.add_middleware(LocalTrustMiddleware)

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

    # Spec §9 §7 + spec §5.2 ``POST /api/projects/source-root``: the
    # effective projects root may be mutated at runtime by the source-root
    # route.  ``Settings.source_projects_root`` is the CLI/env-var seed;
    # ``config.yaml`` is the persistent fallback.  The carrier holds the
    # runtime-effective value so list/discover routes always read from
    # one place. Seed order: CLI/env (Settings) > config.yaml > None.
    # Always load the full ``AppConfig`` so routes can read fields like
    # ``fuzz_threshold`` (GAP-5) via the ``get_app_config`` DI provider
    # without re-reading the file on every request.
    _app_config = load_config(settings.config_root)
    app.state.app_config = _app_config
    _initial_root = settings.source_projects_root or _app_config.source_projects_root
    source_root_carrier = SourceRootCarrier(initial=_initial_root)
    app.state.source_root_carrier = source_root_carrier

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

    # M9: LabelerPageStore factory — creates a per-project store when called.
    # Route handlers call this when a project is loaded to create the store
    # and stash it on app.state.page_store.
    app.state.page_store_factory = LabelerPageStore

    # M3 slice 8c-iv-a + 8c-iv-b: ``OCRConfigCarrier`` holds the
    # user-selected OCR detection + recognition model keys +
    # ``hf_pinned_revision``. Slice 8c-iv-a wired the in-process
    # carrier so a POST persists into a subsequent GET within one
    # server process. Slice 8c-iv-b adds the ``ocr_config.json``
    # sidecar (spec §7a) so the selection survives a restart — the
    # carrier instance is constructed above (so the lifespan closure
    # can capture it) and seeded from disk by the lifespan startup
    # hook before any request arrives. Per-``build_app`` for test
    # isolation, same as ``ProjectState``.
    app.state.ocr_config_carrier = ocr_carrier

    # Spec §2 step 3 + §11: stash the job runner + event broker so DI
    # providers ``get_job_runner`` / ``get_job_events`` can resolve them.
    # Both are per-``build_app`` instances (no module-global state).
    app.state.job_runner = runner
    app.state.job_events = broker

    # Spec §5.11 + §11-notifications.md: ``NotificationQueue`` holds the
    # ring buffer of server-pushed notifications. One queue per
    # ``build_app`` — no module-global state. The SSE route reads from it
    # via ``get_notification_queue``; back-end code (autosave, OCR, export)
    # injects it to queue events. ``app.state.notification_queue`` is the
    # canonical slot per the ``_state_attr`` DI contract.
    notification_queue = NotificationQueue()
    app.state.notification_queue = notification_queue

    # Spec-23-B1 (issue #307): the ``reload_ocr`` job handler reads
    # ``project_state`` / ``notification_queue`` (and an optional
    # ``page_loader``) from ``runner.context`` to mutate state + queue
    # notifications without a request-time DI graph.  Wire them now
    # that both carriers exist — the runner instance was built earlier
    # so the lifespan closure could capture it; ``context`` is a
    # mutable dict so post-hoc population is safe.
    runner.context["project_state"] = app.state.project_state
    runner.context["notification_queue"] = notification_queue
    # Spec-23-B1 production wiring: the reload_ocr handler builds a
    # LocalDoctrPageLoader on-demand from these three context keys when
    # no explicit ``page_loader`` has been injected (test/route-layer
    # path). ``ocr_carrier`` is the same instance captured by the
    # lifespan closure so snapshot() reads current user selection.
    runner.context["predictor_cache"] = PredictorCache(
        weights_resolver=build_weights_resolver(_resolve_local_models_root())
    )
    runner.context["ocr_config_carrier"] = ocr_carrier
    runner.context["settings"] = settings

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

    # /api/fs/ls — directory-listing helper for the source-folder picker.
    # Issue #294 (spec 22 §10).
    install_fs_router(app)

    # /api/projects/{id}/pages/* router — issue #185.
    install_pages_router(app)

    # /api/projects/{id}/pages/{idx}/undo|redo — event-store undo
    # (docs/specs/2026-06-12-event-store-undo.md, slice H-B).
    install_history_router(app)

    # /api/jobs/* router — issue #185 (SSE for long-running operations).
    install_jobs_router(app)

    install_export_router(app)
    install_refine_router(app)
    install_words_router(app)
    install_lines_paragraphs_router(app)

    # Legacy SPA path redirects — spec §4 / issue #185 bullet 3.
    # /project/{id} → /projects/{id} (and /project/{id}/page/{n}
    # → /projects/{id}/pages/pageno/{n}) as 301 Moved Permanently.
    _install_legacy_redirects(app)

    # /api/notifications router — spec §5.11.
    install_notifications_router(app)

    # /api/ocr-config router — M3 slice 8a. Read-only stock-fallback
    # skeleton composed from the iter-7 OCR config DTOs; spec §5.8
    # lines 317-322. Wired alongside /api/projects so the SPA's
    # OCRConfigModal can fetch its initial state from the OpenAPI-
    # generated client without conditional gating. Slice 8b+ will add
    # the POST mutate / rescan routes against this same prefix.
    install_ocr_config_router(app)

    # GET /api/session-state — returns last-loaded project path for RootPage
    # redirect-on-mount logic. Issue #274.
    install_session_state_router(app)

    # GET /api/normalize/available — probe for pdomain_book_tools.text.normalize.
    # Used by OCRConfigModal to gate normalize UI toggles. Issue #261.
    install_normalize_router(app)

    # GET /api/label-vocabulary — canonical text-style + word-component vocab
    # sourced from pdomain_book_tools so the frontend can never drift.
    # Q-B2-STYLE-LABELS option (b). Issue resolved in this slice.
    install_label_vocabulary_router(app)

    # pdomain-ops suite plumbing for shared settings panels. The compute panel
    # uses /api/suite/device on startup and when opened to report CPU/CUDA/NVIDIA
    # state and persist app-scoped compute overrides.
    mount_suite_routes(app, suite_app=_suite_app_metadata(settings))
    _suppress_ops_schema_violations(app)

    # Per docs/architecture/02-backend.md §2 step 12: /env.js, /image-cache, and the
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
        install_blob_route(app)
        install_spa_fallback(app)
    else:
        log.debug("api_only mode: skipping /env.js + /image-cache + SPA fallback")

    return app

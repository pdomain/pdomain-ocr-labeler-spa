"""FastAPI ``Depends`` providers — surface ``AppState`` to route handlers.

Spec: ``docs/architecture/02-backend.md §6``. Each provider reads from
``request.app.state.<name>`` directly rather than chaining through
``Depends(get_app_state)`` — this matches the spec snippet literally
and keeps dependency-resolution flat (FastAPI doesn't dedupe two
``Depends(get_app_state)`` calls in the same request graph if they
type-resolve through different aliases, so flat reads are cheaper).

The providers fail-fast with a ``RuntimeError`` if the wiring step in
``bootstrap.build_app`` was skipped (e.g. someone constructed a bare
``FastAPI()`` for a unit test and forgot to stash adapters). The
message names the missing attribute so the failure mode is
self-explanatory at the test boundary, not a downstream ``AttributeError``
inside a route body.

Job-runner / event-broker / ``get_user`` providers ship with M3+
(spec ``§11``, ``§5.10``); adding their stubs here now would lie
about wiring the spec doesn't yet describe.
"""

from __future__ import annotations

from fastapi import Request

from ..adapters.auth import IAuth
from ..adapters.ocr import IOCREngine
from ..adapters.storage import IStorage
from ..core.active_project import ActiveProject, ActiveProjectCarrier
from ..core.app_state import AppState
from ..core.jobs import JobEventBroker, JobRunner
from ..core.notifications import NotificationQueue
from ..core.ocr_config_state import OCRConfigCarrier
from ..core.persistence.config_yaml import AppConfig
from ..core.project_state import ProjectState
from ..core.source_root_state import SourceRootCarrier
from ..settings import Settings


def _state_attr(request: Request, name: str) -> object:
    """Read ``request.app.state.<name>`` or raise a wiring-clear error."""
    state = request.app.state
    try:
        return getattr(state, name)
    except AttributeError as exc:
        # ``app.state`` raises ``AttributeError`` on a missing key. The
        # message names the missing attr + the wiring step so a test
        # author can find the gap fast. (B-52: dropped the
        # ``pragma: no cover`` — this branch IS exercised by
        # ``test_provider_raises_runtime_error_on_unwired_app``.)
        msg = (
            f"app.state.{name} not set — call bootstrap.build_app(settings) "
            f"to wire the dependency graph (docs/architecture/02-backend.md §2 step 9)."
        )
        raise RuntimeError(msg) from exc


def get_settings(request: Request) -> Settings:
    """The hermetic, frozen ``Settings`` instance the app booted with."""
    settings = _state_attr(request, "settings")
    if not isinstance(settings, Settings):
        raise RuntimeError(
            f"app.state.settings is {type(settings)!r}, expected Settings — bootstrap misconfigured"
        )
    return settings


def get_app_config(request: Request) -> AppConfig:
    """The ``AppConfig`` loaded from ``config.yaml`` at boot.

    Provides access to runtime-configurable settings (e.g.
    ``fuzz_threshold``, ``normalize_for_gt_matching``) without
    re-reading ``config.yaml`` per request.  The instance on
    ``app.state`` is set by ``bootstrap.build_app`` and is frozen for
    the process lifetime; a server restart is required to pick up
    config-file changes.

    Callers that need user-adjustable config (distinct from the
    ``PDLABELER_*``-env-var ``Settings``) should prefer this provider.
    """
    cfg = _state_attr(request, "app_config")
    if not isinstance(cfg, AppConfig):
        raise RuntimeError(
            f"app.state.app_config is {type(cfg)!r}, expected AppConfig — bootstrap misconfigured"
        )
    return cfg


def get_app_state(request: Request) -> AppState:
    """The full ``AppState`` singleton — settings + every adapter."""
    state = _state_attr(request, "app_state")
    if not isinstance(state, AppState):
        raise RuntimeError(
            f"app.state.app_state is {type(state)!r}, expected AppState — bootstrap misconfigured"
        )
    return state


def get_storage(request: Request) -> IStorage:
    """The configured ``IStorage`` impl (``filesystem`` in v1)."""
    storage = _state_attr(request, "storage")
    return storage  # type: ignore[return-value]  # pyright: ignore[reportReturnType]


def get_auth(request: Request) -> IAuth:
    """The configured ``IAuth`` impl (``NoneAuth`` in v1)."""
    auth = _state_attr(request, "auth")
    return auth  # type: ignore[return-value]  # pyright: ignore[reportReturnType]


def get_ocr_engine(request: Request) -> IOCREngine:
    """The configured ``IOCREngine`` impl (``LocalDoctrOCR`` in v1)."""
    ocr = _state_attr(request, "ocr_engine")
    return ocr  # type: ignore[return-value]  # pyright: ignore[reportReturnType]


def get_active_project_carrier(request: Request) -> ActiveProjectCarrier:
    """The mutable ``ActiveProjectCarrier`` — the swap-handle.

    Most read-side handlers want ``get_active_project`` (the snapshot)
    instead. Reach for this provider only from endpoints that mutate
    the active project — i.e. ``POST /api/projects/load`` and
    ``DELETE /api/projects/{id}`` (spec §5.2). Wiring lands in M2
    slice 4; the provider exists now so the dependency type is
    importable from route modules under construction.
    """
    carrier = _state_attr(request, "active_project_carrier")
    if not isinstance(carrier, ActiveProjectCarrier):
        raise RuntimeError(
            f"app.state.active_project_carrier is {type(carrier)!r}, "
            "expected ActiveProjectCarrier — bootstrap misconfigured"
        )
    return carrier


def get_active_project(request: Request) -> ActiveProject | None:
    """The current ``ActiveProject`` snapshot, or ``None`` if no project loaded.

    Read-only convenience over ``get_active_project_carrier`` — most
    handlers only need to know "what's active right now" and shouldn't
    be reaching for the swap method.
    """
    carrier = get_active_project_carrier(request)
    return carrier.snapshot()


def get_project_state(request: Request) -> ProjectState:
    """The mutable ``ProjectState`` carrier — loaded ``Project`` + per-page graph.

    Spec authority: ``docs/architecture/00-overview.md`` lines 185-187 (the
    per-project state container) + ``specs/16-milestones.md`` line 158
    (M2 backend bullet 1). Distinct from ``ActiveProjectCarrier``:

    - ``ActiveProjectCarrier`` (slice 2) holds the *pointer* — which
      project root is active.
    - ``ProjectState`` (this module) holds the *graph* — the
      reconstituted ``Project`` model + per-page state.

    Slice 5 wires this carrier so ``POST /api/projects/load`` can call
    ``state.set_loaded_project(project)`` after the persistence layer
    builds the model. The provider exists at slice 5 so the wiring is
    exercised end-to-end; future routes that read the loaded project
    (the M2-proper ``GET /api/projects/{id}``, every page-route in M3)
    will reach for the same provider.
    """
    state = _state_attr(request, "project_state")
    if not isinstance(state, ProjectState):
        raise RuntimeError(
            f"app.state.project_state is {type(state)!r}, expected ProjectState — bootstrap misconfigured"
        )
    return state


def get_job_runner(request: Request) -> JobRunner:
    """The in-process ``JobRunner`` — spec §5.10 / §11."""
    runner = _state_attr(request, "job_runner")
    if not isinstance(runner, JobRunner):
        raise RuntimeError(
            f"app.state.job_runner is {type(runner)!r}, expected JobRunner — bootstrap misconfigured"
        )
    return runner


def get_job_events(request: Request) -> JobEventBroker:
    """The ``JobEventBroker`` for SSE fan-out — spec §11."""
    broker = _state_attr(request, "job_events")
    if not isinstance(broker, JobEventBroker):
        raise RuntimeError(
            f"app.state.job_events is {type(broker)!r}, expected JobEventBroker — bootstrap misconfigured"
        )
    return broker


def get_notification_queue(request: Request) -> NotificationQueue:
    """The ``NotificationQueue`` — in-process ring buffer + SSE fan-out.

    Spec authority: ``docs/architecture/02-backend.md §5.11`` + ``docs/architecture/11-notifications.md``.
    One ``NotificationQueue`` per ``build_app`` instance (no module-global state).
    """
    nq = _state_attr(request, "notification_queue")
    if not isinstance(nq, NotificationQueue):
        raise RuntimeError(
            f"app.state.notification_queue is {type(nq)!r}, "
            "expected NotificationQueue — bootstrap misconfigured"
        )
    return nq


def get_ocr_config_carrier(request: Request) -> OCRConfigCarrier:
    """The mutable ``OCRConfigCarrier`` — selected OCR detection + recognition
    model keys (M3 slice 8c-iv-a).

    Spec authority: ``docs/architecture/02-backend.md §5.8`` lines 317-322 — ``GET
    /api/ocr-config`` returns the *currently selected* models; ``POST
    /api/ocr-config/models`` updates the selection. The carrier is the
    in-process state that lets a POST persist into a subsequent GET
    within one process lifetime. Disk-side persistence is slice
    8c-iv-b (``ocr_config.json`` sidecar).
    """
    carrier = _state_attr(request, "ocr_config_carrier")
    if not isinstance(carrier, OCRConfigCarrier):
        raise RuntimeError(
            f"app.state.ocr_config_carrier is {type(carrier)!r}, "
            "expected OCRConfigCarrier — bootstrap misconfigured"
        )
    return carrier


def get_source_root_carrier(request: Request) -> SourceRootCarrier:
    """The mutable ``SourceRootCarrier`` — runtime-effective source projects root.

    Spec authority: ``docs/architecture/09-persistence.md §7`` (config.yaml) +
    ``docs/architecture/02-backend.md §5.2`` (``POST /api/projects/source-root``).

    The carrier holds the effective ``source_projects_root`` as mutated
    by ``POST /api/projects/source-root`` at runtime.  It is seeded at
    boot from ``Settings.source_projects_root`` (CLI/env) > ``config.yaml``
    > ``None`` (``bootstrap.build_app`` step 9).
    """
    carrier = _state_attr(request, "source_root_carrier")
    if not isinstance(carrier, SourceRootCarrier):
        raise RuntimeError(
            f"app.state.source_root_carrier is {type(carrier)!r}, "
            "expected SourceRootCarrier — bootstrap misconfigured"
        )
    return carrier


__all__ = [
    "get_active_project",
    "get_active_project_carrier",
    "get_app_config",
    "get_app_state",
    "get_auth",
    "get_job_events",
    "get_job_runner",
    "get_notification_queue",
    "get_ocr_config_carrier",
    "get_ocr_engine",
    "get_project_state",
    "get_settings",
    "get_source_root_carrier",
    "get_storage",
]

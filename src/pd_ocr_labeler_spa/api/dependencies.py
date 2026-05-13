"""FastAPI ``Depends`` providers — surface ``AppState`` to route handlers.

Spec: ``specs/02-backend.md §6``. Each provider reads from
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
from ..core.ocr_config_state import OCRConfigCarrier
from ..core.project_state import ProjectState
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
            f"to wire the dependency graph (specs/02-backend.md §2 step 9)."
        )
        raise RuntimeError(msg) from exc


def get_settings(request: Request) -> Settings:
    """The hermetic, frozen ``Settings`` instance the app booted with."""
    settings = _state_attr(request, "settings")
    assert isinstance(settings, Settings)
    return settings


def get_app_state(request: Request) -> AppState:
    """The full ``AppState`` singleton — settings + every adapter."""
    state = _state_attr(request, "app_state")
    assert isinstance(state, AppState)
    return state


def get_storage(request: Request) -> IStorage:
    """The configured ``IStorage`` impl (``filesystem`` in v1)."""
    storage = _state_attr(request, "storage")
    return storage  # type: ignore[return-value]


def get_auth(request: Request) -> IAuth:
    """The configured ``IAuth`` impl (``NoneAuth`` in v1)."""
    auth = _state_attr(request, "auth")
    return auth  # type: ignore[return-value]


def get_ocr_engine(request: Request) -> IOCREngine:
    """The configured ``IOCREngine`` impl (``LocalDoctrOCR`` in v1)."""
    ocr = _state_attr(request, "ocr_engine")
    return ocr  # type: ignore[return-value]


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
    assert isinstance(carrier, ActiveProjectCarrier)
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

    Spec authority: ``specs/00-overview.md`` lines 185-187 (the
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
    assert isinstance(state, ProjectState)
    return state


def get_job_runner(request: Request) -> JobRunner:
    """The in-process ``JobRunner`` — submit + track long-running jobs.

    Spec §5.10 / §11. Wired in ``bootstrap.build_app`` alongside the
    lifespan hook that calls ``runner.run_forever()``.
    """
    runner = _state_attr(request, "job_runner")
    assert isinstance(runner, JobRunner)
    return runner


def get_job_events(request: Request) -> JobEventBroker:
    """The ``JobEventBroker`` for SSE fan-out.

    Spec §11: per-job ``asyncio.Queue`` fan-out. Wired alongside
    ``job_runner`` in ``bootstrap.build_app``.
    """
    broker = _state_attr(request, "job_events")
    assert isinstance(broker, JobEventBroker)
    return broker


def get_ocr_config_carrier(request: Request) -> OCRConfigCarrier:
    """The mutable ``OCRConfigCarrier`` — selected OCR detection + recognition
    model keys (M3 slice 8c-iv-a).

    Spec authority: ``specs/02-backend.md §5.8`` lines 317-322 — ``GET
    /api/ocr-config`` returns the *currently selected* models; ``POST
    /api/ocr-config/models`` updates the selection. The carrier is the
    in-process state that lets a POST persist into a subsequent GET
    within one process lifetime. Disk-side persistence is slice
    8c-iv-b (``ocr_config.json`` sidecar).
    """
    carrier = _state_attr(request, "ocr_config_carrier")
    assert isinstance(carrier, OCRConfigCarrier)
    return carrier


__all__ = [
    "get_active_project",
    "get_active_project_carrier",
    "get_app_state",
    "get_auth",
    "get_job_events",
    "get_job_runner",
    "get_ocr_config_carrier",
    "get_ocr_engine",
    "get_project_state",
    "get_settings",
    "get_storage",
]

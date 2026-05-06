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
from ..core.app_state import AppState
from ..settings import Settings


def _state_attr(request: Request, name: str) -> object:
    """Read ``request.app.state.<name>`` or raise a wiring-clear error."""
    state = request.app.state
    try:
        return getattr(state, name)
    except AttributeError as exc:  # pragma: no cover - defensive
        # ``app.state`` raises ``AttributeError`` on a missing key. The
        # message names the missing attr + the wiring step so a test
        # author can find the gap fast.
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


__all__ = [
    "get_settings",
    "get_app_state",
    "get_storage",
    "get_auth",
    "get_ocr_engine",
]

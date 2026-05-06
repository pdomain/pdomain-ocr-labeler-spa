"""``AppState`` — the typed singleton container for adapters + settings.

Spec: ``specs/02-backend.md §2 step 4`` ("Build ``AppState(settings,
storage, auth, ocr_engine, broker, runner)``") and ``§6`` (the
``api/dependencies.py`` providers read ``request.app.state.app_state``
to surface this object to route handlers).

Why a frozen dataclass and not a ``BaseModel``:
- The fields are runtime objects (Protocol implementations, not wire
  shapes). Pydantic would try to validate / serialise them; we want
  identity-preserving by-reference storage instead.
- ``frozen=True`` makes it a wiring error to mutate ``state.storage``
  post-construction — the same hard-frozen contract ``Settings``
  enforces (``settings.py`` ``frozen=True``).

Why ``broker`` / ``runner`` are absent in the M1.d shape:
- They land in M3 with the job runner (spec ``§11``). Adding them now
  forces a placeholder type that the spec doesn't yet sanction. The
  ``AppState`` constructor signature widens additively in M3 — no
  existing call sites break, since they all pass kwargs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..adapters.auth import IAuth, NoneAuth
from ..adapters.ocr import IOCREngine, LocalDoctrOCR, ModalOCR, SharedContainerOCR
from ..adapters.storage import FilesystemStorage, IStorage
from ..settings import Settings
from .exceptions import NotImplementedYet


@dataclass(frozen=True)
class AppState:
    """Singleton wiring graph: settings + the three adapter Protocol impls.

    One instance per ``FastAPI`` app — built at ``build_app(settings)``
    time, stashed on ``app.state.app_state``, surfaced to route
    handlers via ``api.dependencies.get_app_state``. Same identity for
    every request in the process; **never** rebuilt mid-request.

    Construct via ``build_app_state(settings)`` — direct instantiation
    is fine in tests but production wiring goes through the builder so
    backend selection lives in exactly one place.
    """

    settings: Settings
    storage: IStorage
    auth: IAuth
    ocr_engine: IOCREngine


def build_app_state(settings: Settings) -> AppState:
    """Construct ``AppState`` from ``Settings`` per spec §2 step 2-4.

    Each adapter axis is selected by its ``Settings`` field:

    - ``storage_backend`` → ``IStorage`` impl. Filesystem mode roots
      under ``settings.cache_root / "page-images"`` to match the
      ``/image-cache/{key}`` mount described in spec ``§10``. ``s3``
      raises ``NotImplementedYet`` (D-019).
    - ``auth_mode`` → ``IAuth`` impl. Only ``none`` is wired in v1
      (D-005).
    - ``ocr_engine`` → ``IOCREngine`` impl. All three impls are
      *constructed* (the seam exists per D-018); the ``modal`` /
      ``shared_container`` impls raise ``NotImplementedYet`` from
      ``ocr_page`` rather than from their constructors so the wiring
      itself stays cheap and testable.

    Loud-at-wire-time policy: a misconfigured ``storage_backend = "s3"``
    fails immediately during ``build_app(settings)`` — not at first
    request — so deployments using a not-yet-wired backend can't boot
    silently into a broken state.
    """
    storage = _build_storage(settings)
    auth = _build_auth(settings)
    ocr_engine = _build_ocr_engine(settings)

    return AppState(
        settings=settings,
        storage=storage,
        auth=auth,
        ocr_engine=ocr_engine,
    )


# ── per-axis builders (private, kept short — one ``match`` each) ───────────


def _build_storage(settings: Settings) -> IStorage:
    backend = settings.storage_backend
    if backend == "filesystem":
        # Spec §10: ``/image-cache`` is read-only over HTTP and rooted
        # at ``<cache_root>/page-images/`` under the filesystem adapter.
        # M1.d roots the *adapter* there too — every storage key is
        # forward-slash-relative under that root.
        root: Path = settings.cache_root / "page-images"
        return FilesystemStorage(root)
    if backend == "s3":  # pragma: no cover - guarded by NotImplementedYet
        raise NotImplementedYet("s3 storage backend not yet wired (D-019)")
    raise ValueError(f"unknown storage_backend: {backend!r}")


def _build_auth(settings: Settings) -> IAuth:
    mode = settings.auth_mode
    if mode == "none":
        return NoneAuth()
    raise ValueError(f"unknown auth_mode: {mode!r}")


def _build_ocr_engine(settings: Settings) -> IOCREngine:
    engine = settings.ocr_engine
    if engine == "local_doctr":
        return LocalDoctrOCR()
    if engine == "modal":
        return ModalOCR()
    if engine == "shared_container":
        return SharedContainerOCR()
    raise ValueError(f"unknown ocr_engine: {engine!r}")


__all__ = ["AppState", "build_app_state"]

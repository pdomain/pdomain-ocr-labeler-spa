"""``core.app_state`` shape pins (spec ``02-backend.md §2 step 4`` + ``§3``).

These tests pin:

- The ``AppState`` field set + types (``Settings`` + three Protocol impls).
- ``frozen=True`` — assignment to ``state.<field>`` after construction
  raises (the same hard-frozen contract ``Settings`` enforces, so a
  future regression to a mutable container fails loudly).
- ``build_app_state(settings)`` constructs the right impl for each
  ``Settings`` Literal value, including the two NotImplementedYet OCR
  engines (constructor succeeds; the seam is real per D-018 — only
  ``ocr_page`` raises).
- The s3 storage backend raises ``NotImplementedYet`` at wire-time
  (D-019; loud-at-wire-time policy in spec §2).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.adapters.auth import IAuth, NoneAuth, UserContext
from pd_ocr_labeler_spa.adapters.ocr import (
    IOCREngine,
    LocalDoctrOCR,
    ModalOCR,
    SharedContainerOCR,
)
from pd_ocr_labeler_spa.adapters.storage import FilesystemStorage, IStorage
from pd_ocr_labeler_spa.core.app_state import AppState, build_app_state
from pd_ocr_labeler_spa.core.exceptions import NotImplementedYet
from pd_ocr_labeler_spa.settings import Settings


def _settings(tmp_path: Path, **over: object) -> Settings:
    base: dict[str, object] = dict(
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


# ── shape ──────────────────────────────────────────────────────────────────


def test_app_state_is_frozen_dataclass() -> None:
    assert is_dataclass(AppState)
    # ``dataclass(frozen=True)`` flips ``__hash__`` to a real method and
    # blocks attr assignment. We don't need to assert the flag literal
    # — exercising the FrozenInstanceError below is the load-bearing
    # check. Here we just pin the field set so a future drift fails.
    field_names = {f.name for f in fields(AppState)}
    assert field_names == {"settings", "storage", "auth", "ocr_engine"}


def test_app_state_assignment_raises(tmp_path: Path) -> None:
    state = build_app_state(_settings(tmp_path))
    with pytest.raises(FrozenInstanceError):
        state.storage = FilesystemStorage(tmp_path / "other")  # type: ignore[misc]


# ── builder selects the right impls ────────────────────────────────────────


def test_build_app_state_filesystem_storage_default(tmp_path: Path) -> None:
    state = build_app_state(_settings(tmp_path))

    assert isinstance(state.storage, FilesystemStorage)
    # IStorage Protocol conformance — runtime_checkable + structural.
    assert isinstance(state.storage, IStorage)


def test_build_app_state_filesystem_root_under_cache_page_images(tmp_path: Path) -> None:
    """Spec §10: ``/image-cache`` mount roots at ``<cache_root>/page-images/``."""
    settings = _settings(tmp_path)
    state = build_app_state(settings)

    expected = (settings.cache_root / "page-images").resolve()
    # ``FilesystemStorage._root`` is private; but it's the load-bearing
    # invariant the spec describes, so reach in.
    assert state.storage._root.resolve() == expected  # type: ignore[attr-defined]


def test_build_app_state_none_auth(tmp_path: Path) -> None:
    state = build_app_state(_settings(tmp_path))

    assert isinstance(state.auth, NoneAuth)
    assert isinstance(state.auth, IAuth)


def test_build_app_state_local_doctr_default(tmp_path: Path) -> None:
    state = build_app_state(_settings(tmp_path))

    assert isinstance(state.ocr_engine, LocalDoctrOCR)
    assert isinstance(state.ocr_engine, IOCREngine)


@pytest.mark.parametrize(
    ("engine_setting", "expected_cls"),
    [
        ("local_doctr", LocalDoctrOCR),
        ("modal", ModalOCR),
        ("shared_container", SharedContainerOCR),
    ],
)
def test_build_app_state_ocr_engine_axis(
    tmp_path: Path,
    engine_setting: str,
    expected_cls: type,
) -> None:
    """All three OCR engines construct cleanly — the seam is real (D-018).

    Only ``ocr_page`` raises ``NotImplementedYet``; the constructors
    themselves are cheap so a misconfigured engine can still boot the
    server (errors at request time, with a recognisable message).
    """
    state = build_app_state(_settings(tmp_path, ocr_engine=engine_setting))
    assert isinstance(state.ocr_engine, expected_cls)


def test_build_app_state_settings_passthrough_identity(tmp_path: Path) -> None:
    """``state.settings`` is the same object passed to ``build_app_state``."""
    settings = _settings(tmp_path)
    state = build_app_state(settings)
    assert state.settings is settings


# ── NotImplementedYet wiring (D-019: s3 storage) ───────────────────────────


def test_build_app_state_s3_storage_raises_not_implemented_yet(tmp_path: Path) -> None:
    """``storage_backend="s3"`` fails LOUDLY at wire-time, not at request-time."""
    settings = _settings(tmp_path, storage_backend="s3")

    with pytest.raises(NotImplementedYet) as exc:
        build_app_state(settings)

    # The message names the seam so the failure mode is self-explanatory.
    assert "s3" in str(exc.value).lower()


# ── NoneAuth round-trip — sanity that the wired adapter actually works ─────


@pytest.mark.anyio
async def test_build_app_state_none_auth_returns_local_user(tmp_path: Path) -> None:
    state = build_app_state(_settings(tmp_path))
    user = await state.auth.verify(None)
    assert isinstance(user, UserContext)
    assert user.user_id == "local"
    assert user.display_name == "Local User"


@pytest.fixture
def anyio_backend() -> str:
    # NoneAuth.verify is async; pin asyncio backend so we don't pull in trio.
    return "asyncio"

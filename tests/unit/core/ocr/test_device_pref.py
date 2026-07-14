"""Unit tests for ``core.ocr.device_pref``.

``resolve_ocr_device_override`` is best-effort: it must never raise,
since it runs both on the request-time predictor-cache path and the
CLI startup-banner path. Uses a fake ``PrefsAdapter`` (real
``pdomain_ops.suite.types`` models) rather than mocking internals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pdomain_ops.suite import device_prefs as device_prefs_mod
from pdomain_ops.suite.types import CommonUIPrefs, UIPrefs

from pdomain_ocr_labeler_spa.core.ocr import device_pref

if TYPE_CHECKING:
    from pdomain_ops.suite.types import UIPrefs as _UIPrefs

_APP_ID = "pdomain-ocr-labeler-spa"


class _FakePrefs:
    """Minimal ``PrefsAdapter`` stand-in — ``read()`` only, per protocol usage here."""

    def __init__(self, snapshot: _UIPrefs | None = None, *, error: Exception | None = None) -> None:
        self._snapshot = snapshot if snapshot is not None else UIPrefs()
        self._error = error

    def read(self) -> _UIPrefs:
        if self._error is not None:
            raise self._error
        return self._snapshot

    def write_common(self, common: CommonUIPrefs) -> None:
        raise NotImplementedError

    def write_app(self, app_id: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError


def test_app_override_wins() -> None:
    prefs = _FakePrefs(UIPrefs(apps={_APP_ID: {"compute_device": "cpu"}}))

    assert device_pref.resolve_ocr_device_override(prefs) == "cpu"


def test_app_override_cuda_index_passes_through() -> None:
    prefs = _FakePrefs(UIPrefs(apps={_APP_ID: {"compute_device": "cuda:1"}}))

    assert device_pref.resolve_ocr_device_override(prefs) == "cuda:1"


def test_auto_detect_sentinel_local_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """``pick_device()`` returning ``"local"`` (its CUDA auto-detect sentinel,
    not a torch device string) means no override — keep the existing
    ``describe_device`` / predictor auto-detect path."""
    monkeypatch.setattr(device_prefs_mod, "pick_device", lambda: "local")
    prefs = _FakePrefs(UIPrefs())

    assert device_pref.resolve_ocr_device_override(prefs) is None


def test_suite_default_wins_even_when_cuda_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device_prefs_mod, "pick_device", lambda: "local")
    prefs = _FakePrefs(UIPrefs(common=CommonUIPrefs(compute_device_default="cpu")))

    assert device_pref.resolve_ocr_device_override(prefs) == "cpu"


def test_prefs_read_failure_returns_none() -> None:
    prefs = _FakePrefs(error=RuntimeError("prefs file corrupt"))

    assert device_pref.resolve_ocr_device_override(prefs) is None


def test_no_prefs_argument_constructs_local_file_prefs(monkeypatch: pytest.MonkeyPatch) -> None:
    """``prefs=None`` falls back to a fresh ``LocalFilePrefs()`` instance."""
    sentinel = _FakePrefs(UIPrefs(apps={_APP_ID: {"compute_device": "cpu"}}))
    monkeypatch.setattr(device_pref, "LocalFilePrefs", lambda: sentinel)

    assert device_pref.resolve_ocr_device_override() == "cpu"

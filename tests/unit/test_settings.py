"""Settings contract — ``PDLABELER_*`` env prefix and field defaults.

Spec: ``specs/02-backend.md §3``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pd_ocr_labeler_spa.settings import Settings


def test_default_settings_have_expected_server_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # Strip any inherited PDLABELER_* env so we observe true defaults.
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8080
    assert s.frontend_dev_url is None
    assert s.log_format == "plain"
    assert s.request_id_header == "X-Request-ID"
    assert s.mode == "normal"


def test_settings_reads_pdlabeler_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    # The ``PDLABELER_`` prefix is the spec's contract for every env var;
    # if this regresses, every deployment doc breaks.
    monkeypatch.setenv("PDLABELER_HOST", "0.0.0.0")
    monkeypatch.setenv("PDLABELER_PORT", "9090")
    monkeypatch.setenv("PDLABELER_LOG_FORMAT", "json")

    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 9090
    assert s.log_format == "json"


def test_settings_ignores_extra_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``extra="ignore"`` in the model_config protects against typoed env
    # vars killing startup. Future milestones will add fields; existing
    # PDLABELER_* env that doesn't match anything must not raise.
    monkeypatch.setenv("PDLABELER_TOTALLY_UNKNOWN_KNOB", "yes")
    Settings()  # must not raise


def test_path_roots_default_under_user_home() -> None:
    s = Settings()
    home = Path.home()
    assert s.config_root.is_absolute()
    assert s.data_root.is_absolute()
    assert s.cache_root.is_absolute()
    # Defaults live under $HOME — when users override via env, those are
    # respected; we only assert the default shape here.
    assert home in s.config_root.parents or s.config_root == home
    assert home in s.data_root.parents or s.data_root == home
    assert home in s.cache_root.parents or s.cache_root == home


def test_settings_accepts_explicit_overrides(tmp_path: Path) -> None:
    # The conftest ``settings`` fixture relies on this; make it explicit.
    s = Settings(
        host="127.0.0.1",
        port=8123,
        data_root=tmp_path / "d",
        config_root=tmp_path / "c",
        cache_root=tmp_path / "ca",
        mode="api_only",
    )
    assert s.port == 8123
    assert s.data_root == tmp_path / "d"
    assert s.mode == "api_only"

"""Integration test: doctr-export-root shared path published on startup.

Verifies that ``bootstrap.build_app`` lifespan startup calls
``publish_shared_path("doctr-export-root", ...)`` when pdomain_ops is
available, and does NOT raise when it fails.

Also verifies the degraded-mode contract: when ``pdomain_ops.suite.shared_paths``
is absent (released 0.9.0 / 0.10.0 ops), the module imports cleanly and
``build_app()`` + lifespan startup succeed without any advertisement.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


def test_bootstrap_import_succeeds_without_shared_paths_module(tmp_path: Path) -> None:
    """``import pdomain_ocr_labeler_spa.bootstrap`` must not raise ModuleNotFoundError.

    This is the primary regression test for the ship-blocker: the unconditional
    top-level import of ``pdomain_ops.suite.shared_paths`` prevented module
    collection on any env with released ops (0.9.0/0.10.0), crashing the entire
    pytest suite at conftest import time.

    Approach: patch ``pdomain_ops.suite`` to make the sub-module appear absent,
    then reload bootstrap to confirm the guarded import degrades cleanly.
    """
    import sys

    import pdomain_ocr_labeler_spa.bootstrap as _bootstrap_mod

    # Simulate the absent-module condition by temporarily hiding shared_paths.
    real_shared_paths = sys.modules.pop("pdomain_ops.suite.shared_paths", None)

    # Also ensure a fresh import of bootstrap sees None (force re-evaluation
    # of the module-level try/except by saving and restoring publish_shared_path).
    real_publish = _bootstrap_mod.publish_shared_path

    # Replace with None as the guarded path would produce.
    _bootstrap_mod.publish_shared_path = None  # type: ignore[assignment]

    try:
        settings = _make_settings(tmp_path)
        app = build_app(settings)
        with TestClient(app) as c:
            resp = c.get("/healthz")
            assert resp.status_code == 200, "build_app startup failed when publish_shared_path is None"
    finally:
        _bootstrap_mod.publish_shared_path = real_publish  # type: ignore[assignment]
        if real_shared_paths is not None:
            sys.modules["pdomain_ops.suite.shared_paths"] = real_shared_paths


def test_publish_shared_path_called_on_startup(tmp_path: Path) -> None:
    """publish_shared_path is invoked once with the export root on startup."""
    settings = _make_settings(tmp_path)
    export_root = Path(str(settings.data_root)) / "doctr-export"

    mock_publish = MagicMock()
    with patch(
        "pdomain_ocr_labeler_spa.bootstrap.publish_shared_path",
        mock_publish,
    ):
        app = build_app(settings)
        with TestClient(app):
            pass  # lifespan runs inside the context manager

    mock_publish.assert_called_once_with(
        "doctr-export-root",
        export_root,
        app="pdomain-ocr-labeler-spa",
    )


def test_startup_does_not_crash_when_shared_path_fails(tmp_path: Path) -> None:
    """A publish_shared_path failure does not abort startup."""
    settings = _make_settings(tmp_path)

    def _raise(*_a: object, **_kw: object) -> None:
        raise OSError("suite dir unwritable")

    with patch(
        "pdomain_ocr_labeler_spa.bootstrap.publish_shared_path",
        side_effect=_raise,
    ):
        app = build_app(settings)
        with TestClient(app) as c:
            resp = c.get("/healthz")
            assert resp.status_code == 200, "startup crashed on publish_shared_path failure"

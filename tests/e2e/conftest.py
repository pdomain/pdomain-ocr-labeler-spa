"""Session-scoped fixtures for Playwright E2E tests.

Mirrors ``pd-prep-for-pgdp/tests/e2e/conftest.py``:

- ``live_server`` builds + serves the SPA and FastAPI together on a free
  port, yields the base URL and settings, and tears the server down at
  session end.
- Pre-built SPA is assumed (``make e2e`` runs ``make frontend-build`` first).

Per-test isolation comes from ``data_root`` being a tmp directory unique
to the session; we do not reset between tests in a single session.

``exercise_server`` is re-exported here so that any test module that runs
alone (e.g. ``pytest tests/e2e/test_ui_coverage.py``) can discover it
without needing ``exercise_real_project.py`` to be collected first.

Spec: docs/specs/2026-05-12-testing-design.md §E2E conftest
Issue #247
"""

from __future__ import annotations

import shutil
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import uvicorn

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings

# Path to the bundled fixtures for the tiny-fixture project.
_TINY_FIXTURE_SRC = Path(__file__).parent / "fixtures" / "projects" / "tiny-fixture"


@dataclass
class LiveServer:
    """Holds the running server's base URL and its settings."""

    base_url: str
    settings: Settings
    source_root: Path


def _pick_free_port() -> int:
    """Return an unbound TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spa_built() -> bool:
    """Return True if the SPA static bundle exists.

    ``make e2e`` runs ``frontend-build`` first; this is the safety net
    that prints a clear skip message instead of a cryptic 404.
    """
    static = Path(__file__).resolve().parents[2] / "src" / "pd_ocr_labeler_spa" / "static"
    return static.is_dir() and any(static.iterdir())


def _wait_until(url: str, timeout: float = 10.0) -> None:
    """Poll ``url`` until it returns HTTP 200 or ``timeout`` seconds elapse.

    Raises ``RuntimeError`` on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready at {url!r} within {timeout}s")


def _install_tiny_fixture(source_root: Path) -> None:
    """Copy the tiny-fixture project into ``source_root``.

    Creates ``<source_root>/tiny-fixture/`` with the PNG pages, pages.json,
    and ``page-images/`` envelope files so load_project can open it.
    """
    dest = source_root / "tiny-fixture"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(_TINY_FIXTURE_SRC, dest)


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveServer]:
    """Start a live uvicorn + FastAPI server for the session.

    Skips the test session when the SPA bundle is not present; run
    ``make frontend-build`` (or ``make e2e``) first.
    """
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) before E2E tests")

    data_root = tmp_path_factory.mktemp("e2e-data")
    cache_root = tmp_path_factory.mktemp("e2e-cache")
    config_root = tmp_path_factory.mktemp("e2e-config")
    source_root = tmp_path_factory.mktemp("e2e-source")

    # Populate the tiny-fixture source project so load_project works.
    _install_tiny_fixture(source_root)

    port = _pick_free_port()
    settings = Settings(
        host="127.0.0.1",
        port=port,
        data_root=data_root,
        cache_root=cache_root,
        config_root=config_root,
        source_projects_root=source_root,
        mode="normal",
    )

    app = build_app(settings)
    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{settings.host}:{settings.port}"
    try:
        _wait_until(f"{base_url}/healthz")
    except RuntimeError:
        server.should_exit = True
        thread.join(timeout=2)
        raise

    yield LiveServer(base_url=base_url, settings=settings, source_root=source_root)

    server.should_exit = True
    thread.join(timeout=5)


# Re-export so that test modules collected alone (e.g. test_ui_coverage.py)
# can discover this module-scoped fixture without requiring
# exercise_real_project.py to be collected in the same run.
from tests.e2e.exercise_real_project import exercise_server as exercise_server  # noqa: E402

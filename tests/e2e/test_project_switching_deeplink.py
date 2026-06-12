"""E2E — project switching (P4.1) + deep-link auto-load (P4.3).

Parity-audit fixes (docs/research/parity-audit/PARITY-GAP.md):

- F12 (A-02 / C13): the "Projects" home link must reach the RootPage grid
  even while a session exists, and opening another project from the grid
  must work while one is already loaded.
- F14 (C57): a deep link to a not-yet-loaded project must auto-load it
  (legacy ``_initialize_from_url`` parity) instead of bouncing to the grid.

Uses a module-scoped server with TWO copies of the tiny-fixture project so
switching has a second target. Each test seeds its own state via httpx so
it is self-sufficient under pytest-xdist distribution.
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
from playwright.sync_api import Page

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import SEED_TIMEOUT, wait_for_page_loaded

pytestmark = pytest.mark.e2e

_TINY_FIXTURE_SRC = Path(__file__).parent / "fixtures" / "projects" / "tiny-fixture"

_PROJECT_A = "tiny-fixture"
_PROJECT_B = "tiny-fixture-b"


@dataclass
class SwitchServer:
    """Running server with two installed source projects."""

    base_url: str
    source_root: Path


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spa_built() -> bool:
    static = Path(__file__).resolve().parents[2] / "src" / "pdomain_ocr_labeler_spa" / "static"
    return static.is_dir() and any(static.iterdir())


@pytest.fixture(scope="module")
def switch_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SwitchServer]:
    """Live server whose source root contains tiny-fixture AND tiny-fixture-b.

    No project is pre-loaded — the deep-link test depends on a fresh
    (nothing-in-memory) server state for its first navigation.
    """
    if not _spa_built():
        pytest.skip("SPA not built — run `make frontend-build` (or `make e2e`) before E2E tests")

    data_root = tmp_path_factory.mktemp("switch-data")
    cache_root = tmp_path_factory.mktemp("switch-cache")
    config_root = tmp_path_factory.mktemp("switch-config")
    source_root = tmp_path_factory.mktemp("switch-source")

    for project_id in (_PROJECT_A, _PROJECT_B):
        shutil.copytree(_TINY_FIXTURE_SRC, source_root / project_id)

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
    deadline = 50  # 50 polls x 0.2s = 10s
    for _ in range(deadline):
        try:
            if httpx.get(f"{base_url}/healthz", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    else:
        server.should_exit = True
        thread.join(timeout=2)
        raise RuntimeError(f"server did not become ready at {base_url}")

    yield SwitchServer(base_url=base_url, source_root=source_root)

    server.should_exit = True
    thread.join(timeout=5)


def _seed_load(server: SwitchServer, project_id: str) -> None:
    """POST /api/projects/load for ``project_id`` (by absolute source path)."""
    r = httpx.post(
        f"{server.base_url}/api/projects/load",
        json={"project_root": str(server.source_root / project_id)},
        timeout=SEED_TIMEOUT,
    )
    assert r.status_code == 200, f"seed load of {project_id} failed: {r.status_code} {r.text}"


# ---------------------------------------------------------------------------
# P4.1 — project switching reachable (F12 / A-02 / C13)
# ---------------------------------------------------------------------------


def test_home_link_reaches_grid_and_switches_project(switch_server: SwitchServer, page: Page) -> None:
    """From a loaded project, the Projects link reaches the grid and a second
    project can be opened from its card — the full A-02/C13 switch loop."""
    _seed_load(switch_server, _PROJECT_A)

    page.goto(f"{switch_server.base_url}/projects/{_PROJECT_A}/pages/pageno/1", timeout=30_000)
    wait_for_page_loaded(page, switch_server.base_url, timeout=30_000)

    # Click the "Projects" home link — must land on the RootPage grid, not
    # bounce back to the loaded project (the pre-fix session-redirect bug).
    page.click('[data-testid="projects-home-link"]')
    page.wait_for_selector('[data-testid="root-projects-grid"]', timeout=15_000)
    assert "/projects/" not in page.url, f"bounced back to a project route: {page.url}"

    # Both project cards are present; open the OTHER project.
    page.wait_for_selector(f'[data-testid="project-card-{_PROJECT_B}"]', timeout=10_000)
    page.click(f'[data-testid="project-card-open-{_PROJECT_B}"]')

    page.wait_for_url(f"**/projects/{_PROJECT_B}/pages/pageno/1", timeout=60_000)
    wait_for_page_loaded(page, switch_server.base_url, timeout=60_000)
    assert f"/projects/{_PROJECT_B}/" in page.url


# ---------------------------------------------------------------------------
# P4.2 — project delete from the grid (F13 / C14)
# ---------------------------------------------------------------------------


def _goto_grid(server: SwitchServer, page: Page) -> None:
    """Navigate to the RootPage grid, riding through a session redirect if one
    fires (other tests in this module may have left a session behind)."""
    page.goto(f"{server.base_url}/", timeout=30_000)
    try:
        page.wait_for_selector('[data-testid="root-projects-grid"]', timeout=5_000)
        return
    except Exception:
        # Session redirect landed us on a project page — use the home link
        # (P4.1) to reach the grid.
        page.click('[data-testid="projects-home-link"]')
        page.wait_for_selector('[data-testid="root-projects-grid"]', timeout=15_000)


def test_delete_project_from_grid(switch_server: SwitchServer, page: Page) -> None:
    """Card menu Delete: confirm dialog -> DELETE -> card gone + dir gone."""
    doomed = "tiny-fixture-del"
    dest = switch_server.source_root / doomed
    if not dest.exists():
        shutil.copytree(_TINY_FIXTURE_SRC, dest)

    _goto_grid(switch_server, page)
    page.wait_for_selector(f'[data-testid="project-card-{doomed}"]', timeout=10_000)

    page.click(f'[data-testid="project-card-menu-{doomed}"]')
    page.click(f'[data-testid="project-card-delete-{doomed}"]')

    page.wait_for_selector('[data-testid="confirm-dialog"]', timeout=10_000)
    page.click('[data-testid="confirm-dialog-confirm"]')

    # The card leaves the grid and the project directory is removed from disk.
    page.wait_for_selector(f'[data-testid="project-card-{doomed}"]', state="detached", timeout=15_000)
    assert not dest.exists(), "project source dir survived the grid Delete action"

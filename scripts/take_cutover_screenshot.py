"""Standalone script to capture a cut-over reference screenshot.

Usage:
    uv run --group e2e python scripts/take_cutover_screenshot.py

Starts a live server with the exercise-fixture project, navigates to
page 1, waits for the full shell (header, rail, drawer, canvas, right
panel) to render, then saves a 1920x1080 PNG to
``docs/Screenshot-hifi-gaps-closed.png``.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve project root (works whether script is run from repo root or
# scripts/ subdirectory).
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# Lightweight helpers with no heavy deps (importable by unit tests).
# _screenshot_utils lives in the same scripts/ directory.
sys.path.insert(0, str(_SCRIPT_DIR))
import uvicorn  # noqa: E402
from _screenshot_utils import pick_free_port as _pick_free_port  # noqa: E402
from _screenshot_utils import require_http_url as _require_http_url  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from pd_ocr_labeler_spa.bootstrap import build_app  # noqa: E402
from pd_ocr_labeler_spa.settings import Settings  # noqa: E402

_FIXTURE_SRC = _REPO_ROOT / "tests" / "e2e" / "fixtures" / "projects" / "exercise-fixture"
_OUT_PNG = _REPO_ROOT / "docs" / "Screenshot-hifi-gaps-closed.png"


def _wait_until(url: str, timeout: float = 30.0) -> None:
    _require_http_url(url)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)  # noqa: S310  # scheme validated above
        except OSError:
            time.sleep(0.3)
        else:
            return
    raise RuntimeError(f"Server did not come up at {url} within {timeout}s")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="screenshot-") as tmp:
        tmp_path = Path(tmp)
        data_root = tmp_path / "data"
        cache_root = tmp_path / "cache"
        config_root = tmp_path / "config"
        source_root = tmp_path / "source"
        for d in (data_root, cache_root, config_root, source_root):
            d.mkdir()

        # Install the exercise fixture as the source project
        dest = source_root / _FIXTURE_SRC.name
        shutil.copytree(_FIXTURE_SRC, dest)
        print(f"Fixture installed: {dest}")

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
        config = uvicorn.Config(
            app,
            host=settings.host,
            port=settings.port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        base_url = f"http://{settings.host}:{settings.port}"
        print(f"Waiting for server at {base_url} …")
        _wait_until(f"{base_url}/healthz")
        print("Server up.")

        try:
            _take_screenshot(base_url)
        finally:
            server.should_exit = True
            thread.join(timeout=5)

    print(f"Screenshot saved to: {_OUT_PNG}")


def _take_screenshot(base_url: str) -> None:
    """Load the project list, open the exercise fixture, navigate to page 1."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Navigate to the app home page
        print(f"Navigating to {base_url} …")
        page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # Try to find a project link and click it
        project_link = page.locator("[data-testid='project-card']").first
        if project_link.count() > 0:
            print("Found project card — clicking …")
            project_link.click()
            page.wait_for_timeout(2000)
        else:
            print("No project-card found; trying direct navigation …")

        # GET /api/projects to find the project ID, then navigate directly
        api_url = f"{base_url}/api/projects"
        _require_http_url(api_url)
        with urllib.request.urlopen(api_url) as resp:  # noqa: S310  # scheme validated above
            projects = json.loads(resp.read())
        print(f"Projects API: {projects!r}")

        # API returns {"projects": [...], ...}
        project_list = projects.get("projects", projects) if isinstance(projects, dict) else projects
        if project_list:
            project_id = project_list[0].get("id") or project_list[0].get("project_id")
            if project_id:
                url = f"{base_url}/project/{project_id}/page/1"
                print(f"Navigating to project page: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)

                # Wait for key shell elements (header, rail, canvas, right panel)
                try:
                    page.wait_for_selector("[data-testid='app-shell']", timeout=10000)
                    print("app-shell present")
                except TimeoutError:
                    print("app-shell selector timed out — screenshotting anyway")

                # Extra wait for Konva canvas to paint
                page.wait_for_timeout(2000)

        # Take the screenshot
        _OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(_OUT_PNG), full_page=False)
        print(f"Screenshot captured ({_OUT_PNG.stat().st_size} bytes)")

        browser.close()


if __name__ == "__main__":
    main()

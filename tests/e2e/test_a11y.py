"""Accessibility audit via axe-core (WCAG AA) — issue #238.

Uses Playwright to load each key page and injects axe-core from the
bundled ``frontend/node_modules/axe-core/axe.min.js``.

Pages checked:
- Root page  (/)
- Project page (/projects/<id>/pages/pageno/1)  — requires tiny-fixture loaded

Any WCAG AA violation causes the test to fail with a detailed report.

Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md
Issue: #238

Run:
    make e2e
    # or targeted:
    uv run pytest tests/e2e/test_a11y.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer
from tests.e2e.helpers import wait_for_app_ready

# Path to the axe-core bundle shipped with frontend devDeps.
_AXE_BUNDLE = Path(__file__).resolve().parents[2] / "frontend" / "node_modules" / "axe-core" / "axe.min.js"


def _inject_axe(page: Page) -> None:
    """Inject axe-core into the current page context."""
    if not _AXE_BUNDLE.exists():
        pytest.skip(
            f"axe-core bundle not found — run `make frontend-install` first (expected: {_AXE_BUNDLE})"
        )
    page.add_script_tag(path=str(_AXE_BUNDLE))


def _run_axe(page: Page, context_selector: str | None = None) -> list[dict]:
    """Run axe.run() and return any WCAG AA violations.

    ``context_selector``: optional CSS selector to scope the scan;
    defaults to the full page (``document``).
    """
    _inject_axe(page)

    options_js = json.dumps(
        {
            "runOnly": {
                "type": "tag",
                "values": ["wcag2aa", "wcag21aa", "best-practice"],
            }
        }
    )
    context_js = f"'{context_selector}'" if context_selector else "document"

    result = page.evaluate(
        f"""async () => {{
            const results = await axe.run({context_js}, {options_js});
            return results.violations;
        }}"""
    )
    return result or []  # type: ignore[return-value]


def _format_violations(violations: list[dict]) -> str:
    """Format axe violations into a human-readable string."""
    lines = [f"{len(violations)} axe violation(s) found:"]
    for v in violations:
        lines.append(f"\n  [{v.get('impact', '?').upper()}] {v.get('id')} — {v.get('description')}")
        for node in v.get("nodes", [])[:3]:
            html = node.get("html", "")[:120]
            lines.append(f"    • {html}")
            for fix in node.get("failureSummary", "").splitlines()[:2]:
                lines.append(f"      {fix}")
    return "\n".join(lines)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _load_tiny_fixture(base_url: str) -> str:
    """Load the tiny-fixture project via the API; return its project_id."""
    r = httpx.get(f"{base_url}/api/projects", timeout=5)
    r.raise_for_status()
    projects = r.json().get("projects", [])
    tiny = next((p for p in projects if p.get("project_id") == "tiny-fixture"), None)
    if tiny is None:
        pytest.skip("tiny-fixture project not available — check conftest fixture install")
    # Load the project so session state is set.
    load_r = httpx.post(
        f"{base_url}/api/projects/load",
        json={"project_root": tiny["project_root"], "initial_page_index": 0},
        timeout=10,
    )
    if load_r.status_code not in (200, 409):
        pytest.skip(f"Failed to load tiny-fixture: {load_r.status_code}")
    return tiny["project_id"]


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.e2e
def test_a11y_root_page_no_violations(live_server: LiveServer, page: Page) -> None:
    """Root page (/) passes axe-core WCAG AA audit with zero violations."""
    wait_for_app_ready(live_server.base_url)
    page.goto(live_server.base_url, timeout=15_000)
    page.wait_for_selector("[data-testid='app-shell']", timeout=10_000)

    violations = _run_axe(page)
    assert not violations, _format_violations(violations)


@pytest.mark.e2e
def test_a11y_project_page_no_violations(live_server: LiveServer, page: Page) -> None:
    """Project page passes axe-core WCAG AA audit with zero violations.

    Loads the tiny-fixture project and navigates to page 1.
    """
    wait_for_app_ready(live_server.base_url)
    project_id = _load_tiny_fixture(live_server.base_url)

    url = f"{live_server.base_url}/projects/{project_id}/pages/pageno/1"
    page.goto(url, timeout=15_000)
    page.wait_for_selector("[data-testid='app-shell']", timeout=10_000)
    # Wait for the page content to settle.
    page.wait_for_timeout(1000)

    violations = _run_axe(page)
    assert not violations, _format_violations(violations)


@pytest.mark.e2e
def test_a11y_live_regions_present(live_server: LiveServer, page: Page) -> None:
    """App shell contains the required ARIA live regions (status + alert)."""
    wait_for_app_ready(live_server.base_url)
    page.goto(live_server.base_url, timeout=15_000)
    page.wait_for_selector("[data-testid='app-shell']", timeout=10_000)

    # status-announcer: role="status" aria-live="polite"
    status_el = page.query_selector("#status-announcer")
    assert status_el is not None, "Missing #status-announcer element"
    assert status_el.get_attribute("role") == "status", "status-announcer must have role=status"
    assert status_el.get_attribute("aria-live") == "polite", "status-announcer must have aria-live=polite"

    # error-announcer: role="alert" aria-live="assertive"
    error_el = page.query_selector("#error-announcer")
    assert error_el is not None, "Missing #error-announcer element"
    assert error_el.get_attribute("role") == "alert", "error-announcer must have role=alert"
    assert error_el.get_attribute("aria-live") == "assertive", "error-announcer must have aria-live=assertive"


@pytest.mark.e2e
def test_a11y_word_match_region_role(live_server: LiveServer, page: Page) -> None:
    """Word matches container has role=region and aria-label."""
    wait_for_app_ready(live_server.base_url)
    project_id = _load_tiny_fixture(live_server.base_url)

    url = f"{live_server.base_url}/projects/{project_id}/pages/pageno/1"
    page.goto(url, timeout=15_000)
    # word-match-view lives in a display:none stub wrapper (IS-4) for
    # driver-contract testid preservation — use state="attached" not visible.
    page.wait_for_selector("[data-testid='word-match-view']", state="attached", timeout=15_000)

    view = page.query_selector("[data-testid='word-match-view']")
    assert view is not None, "word-match-view not found"
    assert view.get_attribute("role") == "region", "word-match-view must have role=region"
    assert view.get_attribute("aria-label") == "Word matches", (
        "word-match-view must have aria-label='Word matches'"
    )

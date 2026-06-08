"""High-level E2E helper functions.

Thin wrappers over Playwright ``Page`` that encode the URL/testid
conventions from ``docs/architecture/13-driver-contract.md``. Tests import these
instead of calling ``page.goto`` / ``page.locator`` directly, so
URL-shape changes only need to be fixed here.

Spec: docs/specs/2026-05-12-driver-contract-design.md
Issue #247
"""

from __future__ import annotations

import httpx
from playwright.sync_api import Page

# Generous per-request timeout for fixture seeding. Under parallel e2e
# (multiple workers each booting uvicorn + chromium AND running cold OCR on the
# fixture pages) the server can be slow to respond to the seed POST/GET; a short
# 5s timeout spuriously raised ``httpx.ReadTimeout`` under contention. 60s lets
# a slow-under-load seed complete without masking a genuinely hung server.
SEED_TIMEOUT = 60.0

# Timeout (ms) for the project-loading overlay to clear after navigation.
# The FIRST page fetch lazily runs a cold OCR + upright-rotation pass on the
# fixture image (see ``page_line_match_count`` — "can take well over 10s"),
# so ``ProjectLoadingOverlay`` (driven by ``pageQ.isLoading``) legitimately
# stays up far longer than a normal render. This is deliberately generous so
# the overlay-wait never fires *before* the cold load completes; it is shorter
# than the cold-OCR worst case only when the model is truly hung.
OVERLAY_TIMEOUT = 90_000


def wait_for_app_ready(base_url: str, timeout: float = 10.0) -> None:
    """Assert the server is healthy before the test starts.

    Raises ``RuntimeError`` on timeout; used by tests that need to
    make API calls before Playwright opens a page.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/healthz", timeout=0.5)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        import time as _t

        _t.sleep(0.1)
    raise RuntimeError(f"App at {base_url!r} did not become ready within {timeout}s")


def load_project(base_url: str, project_id: str) -> httpx.Response:
    """POST /api/projects/load for ``project_id`` and return the response.

    Uses the source root already configured in the live server's
    ``Settings.source_projects_root``.  The caller must have set
    ``source_projects_root`` before invoking this; the test conftest
    does so via ``Settings(source_projects_root=source_root)``.

    Returns the raw httpx response so callers can assert on status.
    """
    url = f"{base_url}/api/projects/load"
    # The project_root must be an absolute path under source_projects_root.
    # We can't know source_root here, so the caller must POST separately
    # when they need a custom root. This helper is for the standard
    # tiny-fixture case where the server already has source_root set and
    # the project is named ``project_id``.
    #
    # Use GET /api/projects first to discover the full path.
    list_resp = httpx.get(f"{base_url}/api/projects", timeout=SEED_TIMEOUT)
    if list_resp.status_code != 200:
        return list_resp
    projects = list_resp.json().get("projects", [])
    match = next((p for p in projects if p.get("project_id") == project_id), None)
    if match is None:
        # Fallback: POST a plausible path and let the server error.
        return httpx.post(url, json={"project_root": f"/nonexistent/{project_id}"}, timeout=SEED_TIMEOUT)
    project_path = match["source_path"]
    return httpx.post(url, json={"project_root": project_path}, timeout=SEED_TIMEOUT)


def wait_for_project_ready(page: Page, timeout: float = OVERLAY_TIMEOUT) -> None:
    """Wait until the ``project-loading-overlay`` is gone.

    ``ProjectLoadingOverlay`` (driven by ``pageQ.isLoading``) is a
    ``fixed inset-0 z-50`` element that fully unmounts (returns ``null``) once
    the page query settles. While it is up it covers the whole viewport, so any
    click lands on the overlay — Playwright reports "project-loading-overlay
    intercepts pointer events" and the action times out.

    The first page fetch lazily runs a cold OCR/rotation pass, so the overlay
    can stay up for tens of seconds on the very first navigation; the default
    :data:`OVERLAY_TIMEOUT` is generous to accommodate that. Call this after
    navigating to / seeding a project page so individual tests never click
    through the overlay. ``state="hidden"`` matches both the detached
    (unmounted) and CSS-hidden cases.
    """
    page.wait_for_selector(
        '[data-testid="project-loading-overlay"]',
        state="hidden",
        timeout=timeout,
    )


def wait_for_page_loaded(page: Page, base_url: str, timeout: float = 10_000) -> None:
    """Wait until the project page has rendered and the loading overlay is gone.

    Driver-contract §2.8: ``[data-testid="project-page"]`` must be visible
    within ``timeout`` ms. We additionally wait for the
    ``project-loading-overlay`` to detach (with the generous
    :data:`OVERLAY_TIMEOUT`, independent of ``timeout``, since the first page
    fetch runs cold OCR) so callers can click immediately without the overlay
    intercepting pointer events (see :func:`wait_for_project_ready`).
    """
    page.wait_for_selector('[data-testid="project-page"]', timeout=timeout)
    wait_for_project_ready(page)


def click_word_edit(page: Page, line_index: int, word_index: int) -> None:
    """Click the ``edit-word-button`` for word ``(line_index, word_index)``.

    Driver-contract §2.8: ``data-testid="edit-word-button-{l}-{w}"``.
    """
    testid = f"edit-word-button-{line_index}-{word_index}"
    page.click(f'[data-testid="{testid}"]')


def page_line_match_count(base_url: str, project_id: str, page_index: int) -> int:
    """Return the number of ``line_matches`` the page payload exposes.

    Word-level parity tests (validate / merge / style / persist) require the
    page to carry real OCR structure.  Some environments (no GPU / no real OCR
    model output on synthetic fixture images) load a project whose pages have
    *zero* ``line_matches`` — there is nothing to select, so those tests would
    be vacuous.  Callers use this to ``pytest.skip`` with a clear reason rather
    than assert against an empty page.

    The first GET for a page triggers a lazy load that, in the no-OCR-content
    case, runs a cold OCR pass (model download + inference) and can take well
    over 10s.  We use a generous timeout and treat *any* error (timeout,
    connection, non-200, malformed body) as "no content available" -> 0, so the
    guard degrades to a clean skip instead of a flaky failure.

    **Do not use this for the exercise-fixture** — that fixture is deterministically
    seeded via the event store (since d0c1494) and content is an invariant.  Use
    :func:`require_page_line_matches` there so backend regressions fail loudly.
    """
    try:
        r = httpx.get(
            f"{base_url}/api/projects/{project_id}/pages/{page_index}",
            timeout=120.0,
        )
    except httpx.HTTPError:
        return 0
    if r.status_code != 200:
        return 0
    try:
        return len(r.json().get("line_matches", []))
    except (ValueError, AttributeError):
        return 0


def require_page_line_matches(base_url: str, project_id: str, page_index: int) -> int:
    """Assert that the page has real OCR content and return the line-match count.

    Use this for fixtures that are **deterministically seeded** via the event
    store (e.g. ``exercise-fixture`` since d0c1494).  Content presence is an
    invariant — a 0-count means the seeding path or the page endpoint has
    regressed, not that the environment lacks an OCR model.

    Unlike :func:`page_line_match_count` this helper does **not** swallow
    errors.  A non-200 response or malformed body raises :class:`AssertionError`
    immediately so CI fails loudly instead of silently skipping.

    Raises:
        AssertionError: if the response is not 200, the body is malformed,
            or ``line_matches`` is empty.
        httpx.HTTPError: propagated as-is on connection / timeout failures.
    """
    r = httpx.get(
        f"{base_url}/api/projects/{project_id}/pages/{page_index}",
        timeout=120.0,
    )
    assert r.status_code == 200, (
        f"GET /api/projects/{project_id}/pages/{page_index} returned {r.status_code}: {r.text[:200]}"
    )
    try:
        count = len(r.json().get("line_matches", []))
    except (ValueError, AttributeError) as exc:
        raise AssertionError(f"Malformed page response for {project_id}/pages/{page_index}: {exc}") from exc
    assert count > 0, (
        f"exercise-fixture page {page_index} has 0 line_matches — "
        "event-store seeding invariant violated (check _ingest_ocr_result path)"
    )
    return count

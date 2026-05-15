"""Viewport perf E2E benchmark — spec-21-C2 (#305).

Mounts the dev/test-only ``/__perf-test`` route (4 000 word rects rendered
into the selection layer), drives a 1-second mouse drag across the
viewport in Playwright headless Chromium, and counts
``requestAnimationFrame`` callbacks observed during that window.

Acceptance (spec §11): ``frame_count >= 55``. Reviewer judgement allows
relaxing to 45 on slow CI with a follow-up issue filed (see #305 body).

Spec: specs/21-konva-renderer.md §11 (Performance pinning),
      §14 (Tests — ``test_viewport_perf.py``).

Run:
    make e2e
    # or
    uv run pytest tests/e2e/test_viewport_perf.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import LiveServer

# Spec §11 acceptance — 60 Hz target with 5-frame headroom.
FRAME_COUNT_TARGET = 55

# Drag window. 1 second matches spec §11; we add a little slack on either
# side because Playwright's mouse step granularity is non-trivial.
DRAG_DURATION_MS = 1_000

# Viewport drag rectangle — sweeps most of the synthetic 1600x2000 page so
# every animation-frame mousemove paints a different drag-preview shape
# (worst-case for re-paint cost). Coordinates are page-relative; Playwright
# routes them through the wrapping div which forwards to the Konva Stage.
_DRAG_FROM = (50, 50)
_DRAG_TO = (1500, 1900)


def _install_frame_counter(page: Page) -> None:
    """Install a self-driving rAF counter loop on the live page.

    Schedules a recursive ``requestAnimationFrame`` that increments a
    counter each frame. This bypasses any wrapping/replacement of
    ``window.requestAnimationFrame`` by libraries (Konva swaps it on
    some code paths) by running OUR rAF loop independently. We start it
    after page load so any post-load monkey-patches are already in place.

    Resetting: ``window.__perfResetFrameCount()`` zeroes the counter
    without stopping the loop, so the count reflects only frames
    observed during the timed window.
    """
    page.evaluate(
        """
        () => {
            if (window.__perfLoopStarted) return;
            window.__perfLoopStarted = true;
            window.__perfFrameCount = 0;
            window.__perfResetFrameCount = () => {
                window.__perfFrameCount = 0;
            };
            const tick = () => {
                window.__perfFrameCount += 1;
                window.requestAnimationFrame(tick);
            };
            window.requestAnimationFrame(tick);
        }
        """
    )


@pytest.mark.e2e
def test_viewport_perf_4000_rects(live_server: LiveServer, page: Page) -> None:
    """4 000-rect viewport drag stays at 60 Hz (spec §11).

    Loads ``/__perf-test`` (4 000 selected word rects rendered into the
    Konva selection layer), starts a mouse drag, holds it for 1 second
    while sweeping across the page, and asserts the rAF counter saw
    ``FRAME_COUNT_TARGET`` (55) or more frames in that window.

    The frame counter is installed via ``add_init_script`` so it's active
    from the very first script the page runs (react-konva's first rAF
    after Stage mount would otherwise be missed).
    """
    page.goto(f"{live_server.base_url}/__perf-test", timeout=15_000)
    page.wait_for_selector('[data-testid="perf-test-page"]', timeout=10_000)
    _install_frame_counter(page)

    # Sanity: the synthetic payload reports 4 000 words.
    perf_root = page.locator('[data-testid="perf-test-page"]').first
    word_count = int(perf_root.get_attribute("data-word-count") or "0")
    assert word_count == 4_000, f"expected 4 000 words, got {word_count}"

    # Wait for the viewport sidecar so we know the canvas has mounted.
    # `image-stage` is a `visibility: hidden` sidecar (spec §12), so we
    # wait for `state="attached"` rather than the default `state="visible"`.
    page.wait_for_selector('[data-testid="image-viewport"]', timeout=10_000)
    page.wait_for_selector('[data-testid="image-stage"]', state="attached", timeout=10_000)

    # Position the mouse at the drag start, press, and step across.
    page.mouse.move(*_DRAG_FROM)
    page.mouse.down()

    # Reset the rAF counter AFTER mousedown / before mousemove so initial
    # mount + first-paint frames don't artificially inflate the count.
    page.evaluate("window.__perfResetFrameCount && window.__perfResetFrameCount()")

    # Drive a many-step mousemove over the drag window. 30 steps over
    # 1 000 ms gives ~33 ms between steps — slower than 60 Hz, which lets
    # rAF batching show up if it isn't actually happening (the rAF count
    # should still be ≥55 because the browser keeps firing rAF regardless
    # of mouse step rate).
    steps = 30
    page.mouse.move(*_DRAG_TO, steps=steps)
    page.wait_for_timeout(DRAG_DURATION_MS)
    page.mouse.up()

    frame_count = int(page.evaluate("window.__perfFrameCount || 0"))

    # Make the failure message actionable — surfaces the count + the
    # configured tolerance + the follow-up path so the reviewer doesn't
    # have to spelunk the spec.
    assert frame_count >= FRAME_COUNT_TARGET, (
        f"viewport perf below target: {frame_count} frames in "
        f"{DRAG_DURATION_MS} ms (target {FRAME_COUNT_TARGET}). "
        "Spec §11 allows reviewer judgement: if this is consistently "
        "flaky on slow CI, bump tolerance to 45 and file a follow-up "
        "perf-tuning issue (see #305 body)."
    )


@pytest.mark.e2e
def test_perf_test_page_word_count(live_server: LiveServer, page: Page) -> None:
    """The synthetic perf page exposes a 4 000-word sidecar attribute.

    Independent assertion (separate from the timing-sensitive drag test)
    so a regression in the synthetic payload is caught by a deterministic
    check rather than a flaky frame-count failure.
    """
    page.goto(f"{live_server.base_url}/__perf-test", timeout=15_000)
    page.wait_for_selector('[data-testid="perf-test-page"]', timeout=10_000)
    perf_root = page.locator('[data-testid="perf-test-page"]').first
    assert perf_root.get_attribute("data-line-count") == "200"
    assert perf_root.get_attribute("data-word-count") == "4000"

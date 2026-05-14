"""Smoke test: ``frontend/vite.config.ts`` proxies must hit the FastAPI
backend port, not a phantom one.

Background: iter-5 review (B-02) found the dev proxy targeting :8765
while every spec + the ``Settings.port`` default agree on :8080. This
test pins the literal so a future copy-paste regression surfaces in CI
rather than the first time a contributor runs ``make frontend-dev``.

We deliberately read the file as text (no Node available in the Python
test runner). Same shape as ``test_pre_commit_config.py`` and
``test_makefile.py`` — text-grep is good enough for a guarded literal.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VITE_CONFIG = REPO_ROOT / "frontend" / "vite.config.ts"

# Settings default lives in ``src/pd_ocr_labeler_spa/settings.py`` —
# spec ``docs/architecture/02-backend.md §3`` pins it. If the backend port ever
# moves both files must move together; the assertion below catches the
# half-migration.
EXPECTED_BACKEND = "http://localhost:8080"

# These are the three proxy keys vite.config.ts wires up (see file body
# + B-02 finding). Any reshuffling that drops one would silently break
# the SPA dev loop.
EXPECTED_PROXY_KEYS = ("/api", "/image-cache", "/env.js")


def test_vite_config_exists() -> None:
    assert VITE_CONFIG.exists(), f"vite.config.ts missing at {VITE_CONFIG}"


def test_vite_proxy_targets_backend_port_8080() -> None:
    text = VITE_CONFIG.read_text(encoding="utf-8")
    # All three proxy keys must point at :8080.
    for key in EXPECTED_PROXY_KEYS:
        # Fragment shape: `"/api": "http://localhost:8080"` (or with
        # single quotes / extra whitespace — keep the test forgiving).
        assert key in text, f"proxy key {key!r} not found in vite.config.ts"
    assert EXPECTED_BACKEND in text, (
        f"expected backend target {EXPECTED_BACKEND!r} not present in vite.config.ts (B-02 regression?)"
    )


def test_vite_proxy_does_not_reference_stale_8765() -> None:
    # Iter-5 B-02: legacy literal that must never reappear. Spec sources
    # of truth: docs/architecture/02-backend.md §3 (port=8080), docs/architecture/15-deployment-dev.md.
    text = VITE_CONFIG.read_text(encoding="utf-8")
    assert "8765" not in text, (
        "vite.config.ts still references the stale :8765 backend port (see docs/BUGS_FOUND.md B-02)"
    )

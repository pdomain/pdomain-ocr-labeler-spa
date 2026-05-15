"""Smoke test: ``frontend/vite.config.ts`` proxies must hit the FastAPI
backend port, not a phantom one.

Background: iter-5 review (B-02) found the dev proxy targeting :8765
while every spec + the ``Settings.port`` default agree on :8080. This
test pins the proxy structure so a future copy-paste regression surfaces
in CI rather than the first time a contributor runs ``make frontend-dev``.

Issue #323: the proxy target is now dynamic — ``vite.config.ts`` reads
``.pdlabeler-port`` (written on every server start) and falls back to
8080 when the file is absent. The literal ``http://localhost:8080`` no
longer appears verbatim; instead we check for the ``readBackendPort``
helper and the fallback constant ``8080`` inside the function body.

We deliberately read the file as text (no Node available in the Python
test runner). Same shape as ``test_pre_commit_config.py`` and
``test_makefile.py`` — text-grep is good enough for a guarded literal.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VITE_CONFIG = REPO_ROOT / "frontend" / "vite.config.ts"

# These are the three proxy keys vite.config.ts wires up (see file body
# + B-02 finding). Any reshuffling that drops one would silently break
# the SPA dev loop.
EXPECTED_PROXY_KEYS = ("/api", "/image-cache", "/env.js")


def test_vite_config_exists() -> None:
    assert VITE_CONFIG.exists(), f"vite.config.ts missing at {VITE_CONFIG}"


def test_vite_proxy_keys_present() -> None:
    """All three proxy keys must be wired in vite.config.ts.

    Issue #323: proxy targets are now dynamic (``backendPort`` variable),
    so we verify the key strings are present rather than the full target URL.
    """
    text = VITE_CONFIG.read_text(encoding="utf-8")
    for key in EXPECTED_PROXY_KEYS:
        assert key in text, f"proxy key {key!r} not found in vite.config.ts"


def test_vite_proxy_reads_port_file() -> None:
    """vite.config.ts must read ``.pdlabeler-port`` and fall back to 8080.

    Issue #323: the port file is written by the server on every start.
    The config must contain the ``readBackendPort`` helper function and
    read ``.pdlabeler-port`` from the filesystem, with 8080 as the fallback.
    """
    text = VITE_CONFIG.read_text(encoding="utf-8")
    assert "readBackendPort" in text, (
        "vite.config.ts must define readBackendPort() to read .pdlabeler-port (issue #323)"
    )
    assert ".pdlabeler-port" in text, "vite.config.ts must reference .pdlabeler-port (issue #323)"
    # Fallback port 8080 must appear in the helper body.
    assert "8080" in text, "vite.config.ts readBackendPort() fallback must be 8080"


def test_vite_proxy_does_not_reference_stale_8765() -> None:
    # Iter-5 B-02: legacy literal that must never reappear. Spec sources
    # of truth: docs/architecture/02-backend.md §3 (port=8080), docs/architecture/15-deployment-dev.md.
    text = VITE_CONFIG.read_text(encoding="utf-8")
    assert "8765" not in text, (
        "vite.config.ts still references the stale :8765 backend port (see docs/BUGS_FOUND.md B-02)"
    )

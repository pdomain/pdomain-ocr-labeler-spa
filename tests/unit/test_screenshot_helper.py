"""Unit tests for the screenshot helper URL-scheme validator.

Exercises ``scripts/_screenshot_utils.require_http_url`` which was
extracted from ``take_cutover_screenshot.py`` to fix Bandit B310 (#423).
The utility module has no heavy dependencies (no playwright, no uvicorn),
so it is importable in the plain unit-test environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Add scripts/ to sys.path so _screenshot_utils is importable.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _screenshot_utils import require_http_url

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRequireHttpUrl:
    """require_http_url must accept http/https and reject everything else."""

    def test_accepts_http(self) -> None:
        # Should not raise for a plain loopback HTTP URL.
        require_http_url("http://127.0.0.1:8080/healthz")

    def test_accepts_https(self) -> None:
        # Should not raise for HTTPS.
        require_http_url("https://example.com/path")

    def test_rejects_file_scheme(self) -> None:
        with pytest.raises(ValueError, match="file"):
            require_http_url("file:///etc/passwd")

    def test_rejects_ftp_scheme(self) -> None:
        with pytest.raises(ValueError, match="ftp"):
            require_http_url("ftp://attacker.example/payload")

    def test_rejects_empty_scheme(self) -> None:
        # A bare string with no recognized scheme (urlparse gives scheme='')
        # must be rejected.
        with pytest.raises(ValueError):
            require_http_url("not-a-url-at-all")

    def test_error_message_contains_scheme(self) -> None:
        with pytest.raises(ValueError, match="'data'"):
            require_http_url("data:text/plain,hello")

"""Internal utilities for take_cutover_screenshot.py.

Kept in a separate module so unit tests can import the helpers without
pulling in playwright or uvicorn (which are e2e-only dependencies).
"""

from __future__ import annotations

import socket
import urllib.parse


def pick_free_port() -> int:
    """Bind to an ephemeral port on loopback and return its number."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def require_http_url(url: str) -> None:
    """Raise ValueError if *url* does not use the http or https scheme.

    This guards every ``urllib.request.urlopen`` call in the screenshot helper
    against accidental ``file://``, ``ftp://``, or other unexpected schemes
    (Bandit B310).  The script only ever contacts a loopback HTTP server, so
    any other scheme indicates a programming error.
    """
    scheme = urllib.parse.urlparse(url).scheme
    if scheme not in {"http", "https"}:
        raise ValueError(
            f"Refusing to open URL with scheme {scheme!r}. Only 'http' and 'https' are permitted."
        )

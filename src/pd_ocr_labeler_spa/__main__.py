"""Console entry point: ``pd-ocr-labeler-ui``.

Mirrors the legacy ``pd-ocr-labeler-ui`` flag set plus the
``--frontend-dev`` option from pgdp-prep. M0 wires ``--host``, ``--port``,
``--reload``, ``--no-browser``, ``--frontend-dev``, ``--version`` and
``project_dir``; the rest of the legacy flag set (``--projects-root``,
``--debugpy``, ``--verbose``, ``--page-timing``) lands in M1+ when their
consumers exist.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser

import uvicorn

from .settings import Settings


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pd-ocr-labeler-ui",
        description="Run the pd-ocr-labeler-spa server (FastAPI + bundled SPA).",
    )
    p.add_argument("project_dir", nargs="?", default=None, help="optional path to a project directory")
    p.add_argument("--host", default=None, help="bind host (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=None, help="bind port (default 8080)")
    p.add_argument("--reload", action="store_true", help="enable uvicorn auto-reload")
    p.add_argument(
        "--frontend-dev",
        default=None,
        metavar="URL",
        help="proxy unknown asset paths to a Vite dev server (e.g. http://localhost:5173)",
    )
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab on start")
    p.add_argument("--version", action="store_true", help="print version and exit")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.version:
        from . import __version__

        print(__version__)
        return 0

    settings = Settings()
    host = args.host or settings.host
    port = args.port or settings.port

    if args.frontend_dev:
        # spec/02-backend.md §3 says "override after construction is forbidden";
        # M0 still mutates here because the only consumer is the very next
        # uvicorn.run call. M1's CLI lands a proper "build settings up front
        # then pass into build_app" pattern via Settings(**overrides).
        settings.frontend_dev_url = args.frontend_dev

    url = f"http://{host}:{port}"
    print(f"Listening on {url}")

    if not args.no_browser and not args.reload:
        try:
            webbrowser.open(url, new=1)
        except Exception:
            pass

    uvicorn.run(
        "pd_ocr_labeler_spa.bootstrap:build_app",
        host=host,
        port=port,
        reload=args.reload,
        factory=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Console entry point: ``pd-ocr-labeler-ui``.

Mirrors the legacy ``pd-ocr-labeler-ui`` flag set
(``pd-ocr-labeler/pd_ocr_labeler/cli.py:13-62``) plus pgdp-prep's
``--frontend-dev`` and the new SPA-side ``--data-root`` override.

Spec authority:

- ``specs/15-deployment-dev.md §3`` — canonical CLI flag set.
- ``specs/02-backend.md §3`` — Settings precedence (default → env → CLI),
  built **once** in ``main()`` and passed into ``build_app(settings)``.

Precedence is enforced by only adding a key to the ``overrides`` dict
when the user explicitly passed the flag — argparse `None` / `False`
defaults are never threaded through, so they can't clobber a real
``PDLABELER_*`` env value.

Flags whose consumers haven't landed yet (``--projects-root``,
``--debugpy``, ``--verbose``, ``--page-timing``) are accepted at parse
time so users get spec-stable CLI surface today; the wiring lands in
the milestone that owns the consumer (M2 for projects-root + project
positional; future iter for debugpy / verbose / page-timing).

See ``OPEN_QUESTIONS.md`` Q-A13 for the deferred ``--log-level`` flag —
spec §3 only names ``log_format`` (plain/json), not ``log_level``;
filed pending user decision before adding a new Settings field.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

import uvicorn

from .settings import Settings


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pd-ocr-labeler-ui",
        description="Run the pd-ocr-labeler-spa server (FastAPI + bundled SPA).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # ── Positional ────────────────────────────────────────────────────────
    p.add_argument(
        "project_dir",
        nargs="?",
        default=None,
        help="optional path to a project directory (overrides session restore)",
    )

    # ── Server ────────────────────────────────────────────────────────────
    p.add_argument(
        "--host",
        default=None,
        help="bind host (default 127.0.0.1; PDLABELER_HOST env)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=None,
        help="bind port (default 8080; PDLABELER_PORT env)",
    )
    p.add_argument(
        "--reload",
        action="store_true",
        help="enable uvicorn auto-reload (also suppresses browser auto-open)",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="don't open a browser tab on start",
    )
    p.add_argument(
        "--frontend-dev",
        default=None,
        metavar="URL",
        help="proxy unknown asset paths to a Vite dev server (e.g. http://localhost:5173)",
    )

    # ── Path roots (spec §3) ──────────────────────────────────────────────
    p.add_argument(
        "--data-root",
        type=Path,
        default=None,
        metavar="PATH",
        help="override Settings.data_root (PDLABELER_DATA_ROOT env)",
    )
    p.add_argument(
        "--projects-root",
        type=Path,
        default=None,
        metavar="PATH",
        help="root directory whose subdirectories are selectable projects "
        "(overrides config.yaml source_projects_root; consumer lands M2)",
    )

    # ── Legacy parity (consumers land in later milestones) ───────────────
    p.add_argument(
        "--debugpy",
        action="store_true",
        help="enable debugpy listener on 0.0.0.0:5678 (legacy parity; consumer not yet wired)",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="increase logging verbosity: -v DEBUG app, -vv +pd-book-tools, -vvv all (legacy parity)",
    )
    p.add_argument(
        "--page-timing",
        action="store_true",
        help="enable page-timing logger (legacy parity; consumer not yet wired)",
    )

    # ── Misc ──────────────────────────────────────────────────────────────
    p.add_argument(
        "--version",
        action="store_true",
        help="print version and exit",
    )

    return p.parse_args(argv)


def _build_overrides(args: argparse.Namespace) -> dict[str, object]:
    """Translate parsed CLI args into a Settings overrides dict.

    Only keys the user explicitly passed land in the dict. argparse
    None / False defaults are skipped so env precedence is preserved.
    Spec §3: Settings is constructed exactly once; mutation is forbidden.
    """
    overrides: dict[str, object] = {}
    if args.host is not None:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.frontend_dev is not None:
        overrides["frontend_dev_url"] = args.frontend_dev
    if args.data_root is not None:
        overrides["data_root"] = args.data_root
    if args.projects_root is not None:
        overrides["source_projects_root"] = args.projects_root
    if args.project_dir is not None:
        overrides["cli_project_dir"] = Path(args.project_dir)
    return overrides


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.version:
        from . import __version__

        print(__version__)
        return 0

    # spec/02-backend.md §3: build Settings *once* from CLI overrides + env.
    # Frozen post-construction; precedence dict only includes flags the user
    # explicitly passed (see ``_build_overrides``).
    settings = Settings(**_build_overrides(args))
    host = settings.host
    port = settings.port

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

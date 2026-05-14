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
import contextlib
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn

from .settings import Settings

# ── B-70: argparse type validators that reject degenerate inputs ─────────


def _nonempty_str(name: str):
    """Return an argparse `type=` callable that rejects empty strings.

    B-70 — `--host ""` previously landed `host=""` in Settings; the
    shell expansion of `--host "$UNSET"` is the common path. Empty
    strings here mean "user accidentally passed nothing"; the right
    response is a clean parse-time error, not a silent re-bind to "".
    """

    def _check(value: str) -> str:
        if value == "":
            raise argparse.ArgumentTypeError(f"{name} cannot be empty")
        return value

    return _check


def _nonempty_path(name: str):
    """Return an argparse `type=` callable that rejects empty-string paths.

    B-70 — `--data-root ""` would yield `Path("")` which equals CWD;
    a stale labeler dir in the user's CWD then gets silently
    re-rooted into. Reject up-front so the failure is loud.
    """

    def _check(value: str) -> Path:
        if value == "":
            raise argparse.ArgumentTypeError(f"{name} cannot be empty")
        return Path(value)

    return _check


def _tcp_port(value: str) -> int:
    """B-70 — TCP ports are in `[1, 65535]`. Zero, negatives, > 65535 rejected.

    `--port 0` previously made the printed `Listening on http://...:0`
    line factually false (uvicorn picks an ephemeral port and the
    browser-open call hits `:0` and refuses).
    """
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--port must be an integer, got {value!r}") from None
    if not (1 <= port <= 65535):
        raise argparse.ArgumentTypeError(f"--port must be in [1, 65535], got {port}")
    return port


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
        type=_nonempty_str("project_dir"),  # B-70
        default=None,
        help="optional path to a project directory (overrides session restore)",
    )

    # ── Server ────────────────────────────────────────────────────────────
    p.add_argument(
        "--host",
        type=_nonempty_str("--host"),  # B-70
        default=None,
        help="bind host (default 127.0.0.1; PDLABELER_HOST env)",
    )
    p.add_argument(
        "--port",
        type=_tcp_port,  # B-70
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
        type=_nonempty_path("--data-root"),  # B-70
        default=None,
        metavar="PATH",
        help="override Settings.data_root (PDLABELER_DATA_ROOT env)",
    )
    p.add_argument(
        "--projects-root",
        type=_nonempty_path("--projects-root"),  # B-70
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


def _build_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Translate parsed CLI args into a Settings overrides dict.

    Only keys the user explicitly passed land in the dict. argparse
    None / False defaults are skipped so env precedence is preserved.
    Spec §3: Settings is constructed exactly once; mutation is forbidden.
    """
    import logging

    overrides: dict[str, Any] = {}
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
    if args.verbose >= 2:
        # -vv enables DEBUG; -v is INFO (default), omitted here to preserve env precedence.
        overrides["log_level"] = logging.DEBUG
    return overrides


# B-68: bound on how long the browser-open thread will poll for the
# uvicorn listener before giving up. 10s comfortably covers the SPA
# factory's import + adapter wiring (sub-second on warm caches) while
# still bounding the daemon thread's lifetime if startup wedges.
_BROWSER_OPEN_DEADLINE_S: float = 10.0
_BROWSER_OPEN_POLL_S: float = 0.1


def _open_when_ready(
    url: str,
    host: str,
    port: int,
    *,
    deadline_s: float = _BROWSER_OPEN_DEADLINE_S,
    poll_s: float = _BROWSER_OPEN_POLL_S,
) -> None:
    """Poll ``host:port`` until something accepts a TCP connection, then
    call ``webbrowser.open(url)``.

    Per B-68: ``webbrowser.open`` returns immediately after handing the
    URL to the OS-level launcher. If we call it *before* uvicorn binds
    the port, the spawned tab can race the still-importing app factory
    and either (a) hit ``ECONNREFUSED`` (browsers cache that for ~30s
    on some platforms), or (b) hit a stale prior listener still in
    ``TIME_WAIT``. Polling the port first eliminates both.

    Bounded by ``deadline_s`` so a startup wedge never leaks this
    daemon thread indefinitely. Swallows all exceptions
    (``webbrowser.open`` itself raises on some headless platforms) —
    failing to open the browser must never crash the server, matching
    the prior ``try / except Exception: pass`` semantics.
    """
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(poll_s)
    else:
        # Deadline hit without a successful connection — give up
        # silently. The server itself may still come up later; the
        # user can navigate manually.
        return
    with contextlib.suppress(Exception):
        webbrowser.open(url, new=1)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.version:
        from . import __version__

        print(__version__)  # noqa: T201  # intentional CLI output — not a debug print
        return 0

    # spec/02-backend.md §3: build Settings *once* from CLI overrides + env.
    # Frozen post-construction; precedence dict only includes flags the user
    # explicitly passed (see ``_build_overrides``).
    settings = Settings(**_build_overrides(args))
    host = settings.host
    port = settings.port

    # Surface the resolved torch device so operators running `make run`
    # can see whether the local GPU was picked up before the OCR
    # pipeline starts pulling models. ``describe_device()`` never raises
    # and lazily imports torch, so the cost is bounded and a torch-less
    # env still boots cleanly. Printed BEFORE the URL so a `tail -1` of
    # the boot log still surfaces the listen address.
    from .core.device_info import describe_device

    print(describe_device())  # noqa: T201  # intentional CLI boot banner

    url = f"http://{host}:{port}"
    print(f"Listening on {url}")  # noqa: T201  # intentional CLI boot banner

    if not args.no_browser and not args.reload:
        # B-68 fix: do not open the browser before uvicorn binds the port.
        # Spawn a daemon thread that polls ``host:port`` and opens the URL
        # once the listener is up. Bounded by ``_BROWSER_OPEN_DEADLINE_S``
        # so a startup failure can't leak the thread; ``daemon=True`` so a
        # parent ``SystemExit`` from uvicorn cleanly tears it down.
        threading.Thread(
            target=_open_when_ready,
            args=(url, host, port),
            name="pd-ocr-labeler-browser-opener",
            daemon=True,
        ).start()

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

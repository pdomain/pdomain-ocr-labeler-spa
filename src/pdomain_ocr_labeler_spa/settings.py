"""Runtime configuration for ``pdomain-ocr-labeler-spa``.

Reads ``PDLABELER_*`` env vars. Read **once** in
``pdomain_ocr_labeler_spa.__main__.main()`` and passed into ``build_app(settings)``.

The Settings shape mirrors ``docs/architecture/02-backend.md §3`` verbatim — every
field listed there must exist here, even if its consumer is M2 / M3
deferred. The "lean stub" policy from earlier milestones was retired
in iter 51 (B-63) after the iter-47 M1.g work added pre-emptive fields
for `--projects-root` / positional `project_dir`: keeping some
no-consumer-yet fields and rejecting others created spec-vs-impl drift
that was harder to reason about than just declaring the full shape.
Fields with deferred consumers are tagged ``M{n}-deferred consumer``
in their docstring so future readers know which milestone wires them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["plain", "json"]
Mode = Literal["normal", "api_only"]
StorageBackend = Literal["filesystem", "s3"]
AuthMode = Literal["none"]
OCREngine = Literal["local_doctr", "modal", "shared_container"]

# The app-name leaf used under every OS-aware root (config_root / data_root /
# cache_root) — matches the distribution name, per
# ``docs/architecture/01-data-models.md §5``.
_APP_DIRNAME = "pdomain-ocr-labeler-spa"


def _legacy_data_root() -> Path:
    """The pre-XDG default (``~/pdomain-ocr-labeler-spa``).

    BUG-SMOKE-3: kept only as a fallback for installs that predate this app
    adopting OS-aware paths (see :func:`default_data_root`). Never write new
    installs here. A function (not a module-level constant) so it re-reads
    ``Path.home()`` on every call — tests that monkeypatch ``HOME`` would
    otherwise observe a value cached from import time.
    """
    return Path.home() / _APP_DIRNAME


def _os_aware_root(
    *,
    xdg_env: str,
    xdg_default_parts: tuple[str, ...],
    macos_parts: tuple[str, ...],
    windows_env: str,
    windows_default_parts: tuple[str, ...],
    windows_extra_parts: tuple[str, ...] = (),
) -> Path:
    """Resolve one OS-aware root, shared by the ``config_root`` / ``data_root``
    / ``cache_root`` branches in :func:`_xdg_config_root`, :func:`_xdg_data_root`
    and :func:`_xdg_cache_root`.

    Spec: ``docs/architecture/01-data-models.md §5``. The three roots share
    the same three-way branch (Linux honours an ``XDG_*`` env var with a
    ``~``-relative fallback; macOS and Windows use a fixed OS convention) but
    disagree on which env var / OS directory applies — callers supply that
    difference:

    - ``xdg_env`` / ``xdg_default_parts``: the Linux (and other POSIX)
      env var and its ``~``-relative fallback parts.
    - ``macos_parts``: the ``~``-relative parts of the macOS directory.
      config_root and data_root pass the same value here — Apple has no
      config/data distinction, both collapse onto
      ``~/Library/Application Support``.
    - ``windows_env`` / ``windows_default_parts``: the Windows env var and
      its ``~``-relative fallback parts. data_root and cache_root pass
      ``LOCALAPPDATA`` (non-roaming); config_root passes ``APPDATA``
      (roaming) — Windows roams small user-authored settings files but not
      bulk/cache data.
    - ``windows_extra_parts``: path parts appended after ``_APP_DIRNAME`` on
      Windows only. Only cache_root uses this (a nested ``cache`` leaf) —
      on Windows, data_root and cache_root would otherwise resolve to the
      exact same directory.

    Every branch appends ``_APP_DIRNAME`` as the leaf (before
    ``windows_extra_parts``, if any).
    """
    home = Path.home()
    if sys.platform == "win32":
        env_value = os.environ.get(windows_env)
        base = Path(env_value) if env_value else home.joinpath(*windows_default_parts)
        return base.joinpath(_APP_DIRNAME, *windows_extra_parts)
    if sys.platform == "darwin":
        return home.joinpath(*macos_parts, _APP_DIRNAME)
    xdg_value = os.environ.get(xdg_env)
    base = Path(xdg_value) if xdg_value else home.joinpath(*xdg_default_parts)
    return base / _APP_DIRNAME


def _xdg_data_root() -> Path:
    """The OS-aware default ``data_root`` for the current platform.

    Spec: ``docs/architecture/01-data-models.md §5`` (``data_root`` row):

    - Linux / other POSIX: ``$XDG_DATA_HOME`` (default ``~/.local/share``).
    - macOS: ``~/Library/Application Support`` — Apple's per-user data
      convention; ``XDG_DATA_HOME`` has no meaning there.
    - Windows: ``%LOCALAPPDATA%`` (default ``~/AppData/Local``) — the
      per-user, non-roaming data location.

    Every branch appends ``_APP_DIRNAME`` as the leaf.
    """
    return _os_aware_root(
        xdg_env="XDG_DATA_HOME",
        xdg_default_parts=(".local", "share"),
        macos_parts=("Library", "Application Support"),
        windows_env="LOCALAPPDATA",
        windows_default_parts=("AppData", "Local"),
    )


def _xdg_config_root() -> Path:
    """The OS-aware default ``config_root`` for the current platform.

    Spec: ``docs/architecture/01-data-models.md §5`` (``config_root`` row):

    - Linux / other POSIX: ``$XDG_CONFIG_HOME`` (default ``~/.config``).
    - macOS: ``~/Library/Application Support`` — identical to
      :func:`_xdg_data_root`'s macOS branch. Apple has no per-user *config*
      convention distinct from *data*; both XDG categories collapse onto the
      same directory there, so ``config_root == data_root`` on macOS. That's
      harmless here: the two roots never write files with the same name
      (``config.yaml`` vs. ``session_state.json`` / ``ocr_config.json`` /
      etc.), so nothing collides.
    - Windows: ``%APPDATA%`` (default ``~/AppData/Roaming``) — the
      *roaming* profile directory, distinct from data/cache's
      ``%LOCALAPPDATA%``. Windows roams small user-authored settings files
      (``config.yaml`` is one); it does not roam bulk or cache data.

    Every branch appends ``_APP_DIRNAME`` as the leaf.
    """
    return _os_aware_root(
        xdg_env="XDG_CONFIG_HOME",
        xdg_default_parts=(".config",),
        macos_parts=("Library", "Application Support"),
        windows_env="APPDATA",
        windows_default_parts=("AppData", "Roaming"),
    )


def _xdg_cache_root() -> Path:
    """The OS-aware default ``cache_root`` for the current platform.

    Spec: ``docs/architecture/01-data-models.md §5`` (``cache_root`` row):

    - Linux / other POSIX: ``$XDG_CACHE_HOME`` (default ``~/.cache``).
    - macOS: ``~/Library/Caches`` — Apple's per-user cache convention.
      Unlike config_root, this does *not* collapse onto Application
      Support; caches get their own directory on macOS.
    - Windows: ``%LOCALAPPDATA%/pdomain-ocr-labeler-spa/cache`` — the same
      base directory as :func:`_xdg_data_root`'s Windows branch, with a
      nested ``cache`` leaf so the two roots don't share a directory.

    Every branch appends ``_APP_DIRNAME`` as the leaf (plus the extra
    ``cache`` leaf on Windows).
    """
    return _os_aware_root(
        xdg_env="XDG_CACHE_HOME",
        xdg_default_parts=(".cache",),
        macos_parts=("Library", "Caches"),
        windows_env="LOCALAPPDATA",
        windows_default_parts=("AppData", "Local"),
        windows_extra_parts=("cache",),
    )


def default_data_root() -> Path:
    """Resolve ``Settings.data_root``'s default.

    BUG-SMOKE-3 ruling: default to the OS-aware data directory
    (:func:`_xdg_data_root`), but if a pre-XDG install already has data at
    the legacy location (:func:`_legacy_data_root`, i.e. ``~/pdomain-ocr-labeler-spa``)
    and the new location doesn't exist yet, keep using the legacy directory —
    a person who has been using this app must not open it and find it empty.

    Deliberately does **not** look for the legacy NiceGUI app's directory
    (``~/.local/share/pd-ocr-labeler/``) — that is a different application's
    data; silently adopting it would be exactly the invisible behaviour this
    policy exists to avoid. Point ``PDLABELER_DATA_ROOT`` / ``--data-root`` at
    it explicitly to use it.
    """
    legacy = _legacy_data_root()
    xdg = _xdg_data_root()
    if legacy.exists() and not xdg.exists():
        return legacy
    return xdg


def describe_data_root(data_root: Path) -> str:
    """Startup line naming the data directory actually in use.

    Describes the resolved value you pass in — never recomputes it — so it
    stays true regardless of whether ``data_root`` came from the default, an
    env var, a config file, or ``--data-root``.
    """
    return f"Using data directory: {data_root}"


def data_root_legacy_note(data_root: Path) -> str | None:
    """A one-time compatibility note, or ``None`` if it doesn't apply.

    BUG-SMOKE-3: when the resolved ``data_root`` is the pre-XDG legacy
    directory and it exists while the OS-aware default does not, say so —
    silently keeping an old directory without telling anyone is the failure
    mode this policy exists to avoid.
    """
    xdg = _xdg_data_root()
    if data_root == _legacy_data_root() and data_root != xdg and data_root.exists() and not xdg.exists():
        return (
            f"{data_root} is the pre-XDG data directory and still has your data, so it's "
            f"still in use. The default is now {xdg} — move your files there and set "
            f"PDLABELER_DATA_ROOT={xdg} (or pass --data-root) to switch."
        )
    return None


def _legacy_config_root() -> Path:
    """The pre-XDG default (``~/.config/pdomain-ocr-labeler-spa``).

    Kept only as a fallback for installs that predate ``config_root``
    honouring ``XDG_CONFIG_HOME`` / the macOS / Windows equivalents (see
    :func:`default_config_root`). On Linux with ``XDG_CONFIG_HOME`` unset
    this is byte-identical to :func:`_xdg_config_root`'s result, so the
    fallback only changes behaviour when ``XDG_CONFIG_HOME`` was set (and
    previously ignored) or on macOS/Windows, where the old hardcoded
    ``~/.config`` path was never the OS-native location. A function (not a
    module-level constant) so it re-reads ``Path.home()`` on every call —
    see :func:`_legacy_data_root` for why.
    """
    return Path.home() / ".config" / _APP_DIRNAME


def default_config_root() -> Path:
    """Resolve ``Settings.config_root``'s default.

    Same compatibility ruling as :func:`default_data_root`, extending the
    BUG-SMOKE-3 policy to ``config_root``: default to the OS-aware config
    directory (:func:`_xdg_config_root`), but if a pre-XDG install already
    wrote ``config.yaml`` at the legacy location
    (:func:`_legacy_config_root`) and the new location doesn't exist yet,
    keep using the legacy directory.

    ``config.yaml`` holds settings a person set deliberately — most
    notably ``source_projects_root``, written by
    ``POST /api/projects/source-root`` (``api/projects.py``) whenever
    someone points the app at a different projects directory — so losing
    track of it silently is the same hazard :func:`default_data_root`
    exists to avoid. That's *not* true of ``cache_root``; see
    :func:`default_cache_root` for why that one has no such fallback.
    """
    legacy = _legacy_config_root()
    xdg = _xdg_config_root()
    if legacy.exists() and not xdg.exists():
        return legacy
    return xdg


def default_cache_root() -> Path:
    """Resolve ``Settings.cache_root``'s default.

    Deliberately **no** legacy-directory fallback, unlike
    :func:`default_data_root` / :func:`default_config_root`: everything
    under ``cache_root`` is disposable and regenerated on demand — the
    content-addressed page-image cache (``core/app_state.py``,
    ``core/persistence/paths.py::image_cache_root``, re-derived from
    project pages on a cache miss) and the per-run startup pidfile
    (``core/persistence/pidfile.py``, rewritten every launch). A stranded
    pre-XDG cache directory loses nothing a re-run can't recreate, so
    keeping it around — or warning that it's stranded — would be pure
    noise. This always resolves to the OS-aware default
    (:func:`_xdg_cache_root`).
    """
    return _xdg_cache_root()


def config_root_legacy_note(config_root: Path) -> str | None:
    """A one-time compatibility note, or ``None`` if it doesn't apply.

    Same "never migrate silently" contract as :func:`data_root_legacy_note`,
    for ``config_root``: when the resolved ``config_root`` is the pre-XDG
    legacy directory and it holds a config while the OS-aware default does
    not, say so.
    """
    xdg = _xdg_config_root()
    if (
        config_root == _legacy_config_root()
        and config_root != xdg
        and config_root.exists()
        and not xdg.exists()
    ):
        return (
            f"{config_root} is the pre-XDG config directory and still has your settings, so "
            f"it's still in use. The default is now {xdg} — move config.yaml there and set "
            f"PDLABELER_CONFIG_ROOT={xdg} to switch."
        )
    return None


class Settings(BaseSettings):
    """One process-wide settings instance. Chosen at startup; never mutated."""

    model_config = SettingsConfigDict(
        env_prefix="PDLABELER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Spec §3 (docs/architecture/02-backend.md:148-149): "override after construction
        # is forbidden." Enforce via pydantic frozen so any future regression
        # to mutate ``settings.<field> = …`` post-construction fails loudly
        # at the call-site instead of silently desyncing process state.
        frozen=True,
    )

    # ── Server ───────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8080
    frontend_dev_url: str | None = None
    """When set, the SPA mount falls through to this Vite dev server."""

    # ── Logging ──────────────────────────────────────────────────────────────
    log_format: LogFormat = "plain"
    log_level: int = 20  # logging.INFO
    """Logging level (10=DEBUG, 20=INFO, 30=WARNING, 40=ERROR, 50=CRITICAL).

    Set by --verbose count: -v enables INFO, -vv enables DEBUG, -vvv enables full DEBUG.
    Default is INFO (20). M1.g CLI feature."""

    request_id_header: str = "X-Request-ID"

    # ── OS-aware roots (docs/architecture/01-data-models.md §5) ──────────────────────────
    config_root: Path = Field(default_factory=default_config_root)
    data_root: Path = Field(default_factory=default_data_root)
    cache_root: Path = Field(default_factory=default_cache_root)

    # ── Project discovery (docs/architecture/02-backend.md §3 lines 130-132) ─────────────
    # Both fields are CLI-overridable seams; their consumers land in M2
    # (project discovery + load). Declared here so the M1.g ``__main__``
    # CLI can thread CLI args through ``Settings(**overrides)`` today.
    source_projects_root: Path | None = None
    """Root directory whose subdirectories are selectable projects.

    Set by ``--projects-root``; falls back to ``config.yaml``'s
    ``source_projects_root``. ``None`` until M2 wires the discovery
    layer.
    """

    cli_project_dir: Path | None = None
    """Optional positional ``project_dir`` from the CLI.

    When set, project discovery + restore overrides session_state's
    ``last_project_path`` and eagerly loads this dir. Same contract as
    legacy ``pdomain-ocr-labeler-ui [project_dir]`` (legacy
    ``cli.py:18-23``).
    """

    # ── Mode flag ────────────────────────────────────────────────────────────
    mode: Mode = "normal"
    """``api_only`` skips the SPA static mount — useful for tests and headless ops."""

    # ── Adapter axes (docs/architecture/02-backend.md §3) ────────────────────────────────
    # Wired by ``core.app_state.build_app_state`` (M1.d). Flipping these
    # fields is the only entry point for swapping backends; route code
    # never branches on adapter choice.
    storage_backend: StorageBackend = "filesystem"
    """``s3`` is ``NotImplementedYet`` (D-019); only ``filesystem`` is wired in v1."""

    auth_mode: AuthMode = "none"
    """``none`` returns a single anonymous ``UserContext`` for every request (D-005)."""

    ocr_engine: OCREngine = "local_doctr"
    """``modal`` / ``shared_container`` are ``NotImplementedYet`` (D-018); only ``local_doctr`` is wired."""

    # ── Job runner (docs/architecture/02-backend.md §3 line 138) ─────────────────────────
    # Consumer lands in M3 (JobRunner background loop). Declared now so
    # the Settings shape matches spec §3 verbatim — drift between spec
    # and impl is the failure mode B-63 was filed against, even though
    # no consumer is wired today.
    poll_interval_seconds: float = 0.5
    """Background JobRunner poll cadence — M3-deferred consumer."""

    max_concurrent_ocr_jobs: int = 1
    """Max number of OCR-heavy jobs (``reload_ocr`` / ``rotate_page`` /
    ``auto_rotate_all`` — every job type whose handler calls
    ``loader.run_ocr``) that ``JobRunner`` runs concurrently
    (``PDLABELER_MAX_CONCURRENT_OCR_JOBS``). ``<= 0`` disables the cap
    (unbounded, matching pre-Task-3 behavior). Other job types
    (``save_project``, ``export``, ``refine_bboxes``) are never gated by
    this semaphore."""

    # ── OCR (docs/architecture/02-backend.md §3 lines 141-142) ───────────────────────────
    # Consumers land in M3 (OCR predictor cache + model prefetch). The
    # `hf_repo` default mirrors legacy `pd-ocr-labeler/...` — see
    # spec §3 for the canonical name.
    hf_repo: str = "pdomain/pdomain-ocr-models"
    """HuggingFace repo for OCR model weights — M3-deferred consumer."""

    no_prefetch: bool = False
    """When True, skip the startup model-prefetch step — M3-deferred consumer."""

    ocr_timeout_s: float = 900.0
    """Wall-clock timeout in seconds for a single ``loader.run_ocr`` call
    inside ``reload_ocr`` / ``rotate_page`` / ``auto_rotate_all`` job
    handlers (``PDLABELER_OCR_TIMEOUT_S``). ``<= 0`` disables the timeout.

    Honest limitation: ``run_ocr`` executes on an ``asyncio.to_thread``
    worker thread. Cancelling the ``asyncio.wait_for`` await only stops
    the *coroutine* from waiting — Python threads are not preemptible,
    so the OS thread keeps running ``run_ocr`` to completion (or crash)
    in the background, holding whatever CPU/GPU/model resources it
    already acquired. This setting bounds how long a job can block the
    user-visible job status, not how long the underlying OCR call runs.
    """

    # ── CORS (docs/specs/2026-05-24-F-002-cors-and-auth-hardening.md) ────────────────────
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        description=(
            "CORS allow-origins list. In production the SPA is served from the same "
            "origin as the API, so this list only needs to cover the Vite dev server. "
            "Override with PDLABELER_CORS_ALLOWED_ORIGINS env var (JSON list). "
            "Set to [] for same-origin-only enforcement."
        ),
    )

    # ── Undo/redo (docs/specs/2026-06-12-event-store-undo.md, U-8) ───────────
    undo_depth: int = 50
    """Maximum number of per-page undo steps offered by the UI
    (``PDLABELER_UNDO_DEPTH``). Older versions remain in the event store but
    stop being reachable via the undo button. Default 50 (spec U-8)."""

    # ── Error-handler debug surface (docs/architecture/02-backend.md §8 / D-040) ─────────
    # Q-A11 (resolved 2026-05-07, option B): the unhandled-`Exception`
    # 500 envelope's ``details`` field surfaces the last 3 traceback
    # lines on a single-user laptop (default) but can be redacted on
    # any deployment that doesn't trust its clients. The full traceback
    # always reaches the server log via ``logger.exception`` — this
    # flag governs only what crosses the wire to the browser.
    debug_unhandled_traceback: bool = False
    """When True, the catch-all 500 envelope includes the last 3 traceback
    lines as ``details``. Default ``False`` (secure): ``details`` is
    ``None`` and the message is always the generic string "Internal server
    error" — operators must correlate via the ``X-Request-ID`` header
    against the server-side ``logger.exception`` line. See D-040 + spec §8.

    Set ``PDLABELER_DEBUG_UNHANDLED_TRACEBACK=true`` on a local dev
    instance to restore the diagnostic detail; never set True in any
    deployment that exposes the API to untrusted clients."""

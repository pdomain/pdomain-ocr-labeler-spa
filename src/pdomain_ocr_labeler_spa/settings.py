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

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["plain", "json"]
Mode = Literal["normal", "api_only"]
StorageBackend = Literal["filesystem", "s3"]
AuthMode = Literal["none"]
OCREngine = Literal["local_doctr", "modal", "shared_container"]


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
    config_root: Path = Field(default_factory=lambda: Path.home() / ".config" / "pdomain-ocr-labeler-spa")
    data_root: Path = Field(default_factory=lambda: Path.home() / "pdomain-ocr-labeler-spa")
    cache_root: Path = Field(default_factory=lambda: Path.home() / ".cache" / "pdomain-ocr-labeler-spa")

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

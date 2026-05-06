"""Runtime configuration for ``pd-ocr-labeler-spa``.

Reads ``PDLABELER_*`` env vars. Read **once** in
``pd_ocr_labeler_spa.__main__.main()`` and passed into ``build_app(settings)``.

This is the M0 stub: only the fields referenced by the M0 acceptance
tests are populated. Fields specified by ``specs/02-backend.md §3`` that
aren't yet exercised (storage_backend, ocr_engine, source_projects_root,
…) are added in M1 and later. Keep this file lean until the consuming
code lands — premature fields invite drift between spec and impl.
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
        # Spec §3 (specs/02-backend.md:148-149): "override after construction
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
    request_id_header: str = "X-Request-ID"

    # ── OS-aware roots (specs/01-data-models.md §5) ──────────────────────────
    config_root: Path = Field(default_factory=lambda: Path.home() / ".config" / "pd-ocr-labeler")
    data_root: Path = Field(default_factory=lambda: Path.home() / "pd-ocr-labeler")
    cache_root: Path = Field(default_factory=lambda: Path.home() / ".cache" / "pd-ocr-labeler")

    # ── Mode flag ────────────────────────────────────────────────────────────
    mode: Mode = "normal"
    """``api_only`` skips the SPA static mount — useful for tests and headless ops."""

    # ── Adapter axes (specs/02-backend.md §3) ────────────────────────────────
    # Wired by ``core.app_state.build_app_state`` (M1.d). Flipping these
    # fields is the only entry point for swapping backends; route code
    # never branches on adapter choice.
    storage_backend: StorageBackend = "filesystem"
    """``s3`` is ``NotImplementedYet`` (D-019); only ``filesystem`` is wired in v1."""

    auth_mode: AuthMode = "none"
    """``none`` returns a single anonymous ``UserContext`` for every request (D-005)."""

    ocr_engine: OCREngine = "local_doctr"
    """``modal`` / ``shared_container`` are ``NotImplementedYet`` (D-018); only ``local_doctr`` is wired."""

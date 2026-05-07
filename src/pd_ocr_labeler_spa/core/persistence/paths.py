"""Pure path-derivation helpers (no I/O).

Spec: ``specs/01-data-models.md §5`` (OS-aware paths) +
``specs/09-persistence.md §1`` (the three on-disk lanes) + ``§5-§7``
(per-purpose files: ``project.json``, ``session_state.json``,
``config.yaml``).

Why a module of pure functions instead of the legacy class-based
``PersistencePathsOperations``: the SPA's ``Settings``
(``settings.py``) already owns the **three OS-aware roots**
(``config_root`` / ``data_root`` / ``cache_root``) — including the
override path through ``PDLABELER_DATA_ROOT`` etc. These helpers just
derive the per-purpose sub-paths from those roots, so they're trivially
testable with synthetic paths and don't read ``platform.system()`` /
``os.getenv``. The OS-awareness lives at one layer (Settings'
defaults), not two.

Every helper here is a **string-arithmetic-only** transform: same
inputs → same outputs, no filesystem touch. ``mkdir`` lives at the
write site (the ``save_*`` helpers in sibling modules), never here, so
``build_app(Settings())`` continues to be a pure factory (B-54 invariant).

Spec mapping (from ``specs/01-data-models.md §5``):

- ``data_root`` (root)         → caller passes in
- ``cache_root`` (root)        → caller passes in
- ``config_root`` (root)       → caller passes in
- ``saved_projects_root``      → ``data_root / "labeled-projects"``
- ``project_backups_root``     → ``data_root / "project-backups"``
- ``logs_root``                → ``data_root / "logs"``
- ``session_state_path``       → ``data_root / "session_state.json"`` (§6)
- ``page_image_cache_root``    → ``cache_root / "page-images"``
- ``config_yaml_path``         → ``config_root / "config.yaml"`` (§7)

Note: the ``config_root`` argument to ``config_yaml_path`` is
**already** ``<os_default>/pd-ocr-labeler/`` (Settings handles the app-name
suffix). This module never re-applies the app-name — that would
double-suffix on every call.
"""

from __future__ import annotations

from pathlib import Path

# Filename constants. Lifted to module scope so tests can import them
# without re-typing the literal in two places (drift hazard).
SAVED_PROJECTS_DIRNAME = "labeled-projects"
PROJECT_BACKUPS_DIRNAME = "project-backups"
LOGS_DIRNAME = "logs"
PAGE_IMAGES_DIRNAME = "page-images"
CONFIG_YAML_FILENAME = "config.yaml"
SESSION_STATE_FILENAME = "session_state.json"
OCR_CONFIG_FILENAME = "ocr_config.json"


def labeled_projects_root(data_root: Path) -> Path:
    """``<data_root>/labeled-projects/`` — explicit user saves.

    Spec: ``specs/09-persistence.md §1`` ("Labeled lane") + §5 (where
    ``project.json`` lives). The labeler is the only writer; the legacy
    binary writes here too (D-003 shared-data-root contract).
    """
    return data_root / SAVED_PROJECTS_DIRNAME


def project_backups_root(data_root: Path) -> Path:
    """``<data_root>/project-backups/`` — reserved (spec §10, unused in v1)."""
    return data_root / PROJECT_BACKUPS_DIRNAME


def logs_root(data_root: Path) -> Path:
    """``<data_root>/logs/`` — application log files (per spec §5 table)."""
    return data_root / LOGS_DIRNAME


def session_state_path(data_root: Path) -> Path:
    """``<data_root>/session_state.json`` — last-loaded project + page (spec §6).

    Field-name compatibility (``last_project_path``, ``last_page_index``)
    is **mandatory** because both binaries share this file under D-003.
    See ``session_state.SessionState``.
    """
    return data_root / SESSION_STATE_FILENAME


def ocr_config_path(data_root: Path) -> Path:
    """``<data_root>/ocr_config.json`` — SPA-only OCR model selection sidecar (spec §7a).

    Sibling of ``session_state.json``. Unlike that file, this one is
    NOT shared with the legacy ``pd-ocr-labeler`` binary — legacy
    recomputes model selection on every launch. The sidecar persists
    the in-process ``OCRConfigCarrier`` triple across SPA restarts
    (M3 slice 8c-iv-b). Field shape + lifecycle in
    ``core/persistence/ocr_config.py``.
    """
    return data_root / OCR_CONFIG_FILENAME


def image_cache_root(cache_root: Path) -> Path:
    """``<cache_root>/page-images/`` — content-addressed image cache (spec §4).

    Filenames inside this dir follow
    ``<project>_<page:03d>_<image_type>_<sha>.{jpg,png}`` (legacy-shared,
    so two writers don't collide); the cached envelope is
    ``<project>_<page:03d>_envelope.json`` (spec §4.2).
    """
    return cache_root / PAGE_IMAGES_DIRNAME


def config_yaml_path(config_root: Path) -> Path:
    """``<config_root>/config.yaml`` — single-key user config (spec §7).

    ``config_root`` is expected to already include the app-name suffix
    (``Settings`` handles that via its OS defaults — see
    ``specs/01-data-models.md §5``).
    """
    return config_root / CONFIG_YAML_FILENAME

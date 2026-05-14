"""On-disk persistence helpers for ``pd-ocr-labeler-spa``.

Spec: ``docs/architecture/09-persistence.md`` (lanes, envelopes, atomic writes) +
``docs/architecture/01-data-models.md §5`` (OS-aware roots).

This package owns:

- ``paths`` — pure derivation of the labeler's per-purpose subdirs
  (saved projects, image cache, logs, session state file, …) from the
  three OS-aware root settings (``config_root`` / ``data_root`` /
  ``cache_root``). No I/O.
- ``session_state`` — read/write of ``<data_root>/session_state.json``
  (the legacy-compatible "where was I?" snapshot per spec §6).

Bigger pieces — ``user_page_envelope``, ``project_envelope``,
``ground_truth``, ``image_cache``, ``atomic`` — are landed in later
M1+ sub-tasks per ``specs/16-milestones.md``.
"""

from __future__ import annotations

from pd_ocr_labeler_spa.core.persistence.paths import (
    config_yaml_path,
    image_cache_root,
    labeled_projects_root,
    logs_root,
    project_backups_root,
    session_state_path,
)
from pd_ocr_labeler_spa.core.persistence.session_state import (
    SESSION_STATE_FILENAME,
    SESSION_STATE_SCHEMA_VERSION,
    SessionState,
    load_session_state,
    save_session_state,
)

__all__ = [
    "SESSION_STATE_FILENAME",
    "SESSION_STATE_SCHEMA_VERSION",
    "SessionState",
    "config_yaml_path",
    "image_cache_root",
    "labeled_projects_root",
    "load_session_state",
    "logs_root",
    "project_backups_root",
    "save_session_state",
    "session_state_path",
]

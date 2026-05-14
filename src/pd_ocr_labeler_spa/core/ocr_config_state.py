"""``OCRConfigCarrier`` — in-process holder for the user-selected OCR
detection / recognition model keys (M3 slice 8c-iv-a).

Spec authority:

- ``specs/02-backend.md §5.8`` lines 317-322 — ``GET /api/ocr-config``
  must return the *currently selected* models, and
  ``POST /api/ocr-config/models`` must update that selection. Today
  (pre-8c-iv) the POST is stateless echo: a subsequent GET still
  reports the stock defaults. This carrier is the in-process state
  that closes the gap.
- ``specs/01-data-models.md`` lines 374-400 — the wire DTOs the
  carrier surfaces (``selected_detection``, ``selected_recognition``,
  ``hf_pinned_revision``).
- ``specs/17-decisions.md`` D-042 — local-mode persistence is the
  active path; this slice ships the in-process holder, slice 8c-iv-b
  will add the ``ocr_config.json`` filesystem sidecar so the
  selection survives a server restart. The split is deliberate: the
  carrier shape is independent of disk-persistence shape, and shipping
  them as one slice would couple two contracts that should be tested
  separately.

Pattern parity:

- Same shape as ``ProjectState`` (``core/project_state.py``) and
  ``ActiveProjectCarrier`` (``core/active_project.py``) — ``threading.Lock``
  (not ``asyncio.Lock``) because route handlers may be either sync
  (threadpool worker) or async (event loop), and a thread-lock is safe
  to hold from both. Mutation bumps a ``generation`` counter so future
  SSE / cache-invalidation code can detect changes without diffing.
- One instance per ``build_app(...)`` call; lives at
  ``app.state.ocr_config_carrier``. Module-global state is forbidden
  (test isolation requires per-build_app instances).

What this slice deliberately does NOT do (deferred to 8c-iv-b):

- **Disk persistence.** No ``ocr_config.json`` read/write. The carrier
  is process-scoped; restarting the server resets to defaults. The
  filesystem sidecar (atomic-rename + spec §7-style ``config_root``
  derivation) lands as a separate slice with its own tests.
- **Surfacing HF / local options.** ``detection_options`` /
  ``recognition_options`` stay stock-only in the response (per
  router-level contract); the carrier doesn't validate the keys it
  holds against any option list — that's the route's job.
- **Persisting ``hf_pinned_revision`` per-project vs globally.** This
  is a config-yaml question deferred to slice 8c-iv-b when the on-disk
  layout question is forced.
"""

from __future__ import annotations

import threading
from typing import Literal

#: Valid auto-rotate method values.  ``"auto"`` lets the engine pick the
#: best available method (GT-best-match if GT present, layout otherwise).
AutoRotateMethod = Literal["gt-best-match", "layout", "auto"]


class OCRConfigCarrier:
    """In-process holder for the active OCR model selection + auto-rotate config.

    Default state matches the slice-8a stock-only options
    (``selected_detection_key="stock"``,
    ``selected_recognition_key="stock"``, ``hf_pinned_revision=None``).
    Mutation goes through ``set_models`` / ``set_auto_rotate``, which are
    idempotent (storing the same values does not bump generation) so
    callers can re-apply a selection without forcing SSE / cache
    invalidation downstream.

    Thread-safety: all reads + writes hold ``self._lock``. Snapshot
    accessors copy primitive values out under the lock so the caller
    sees a consistent tuple even if a concurrent mutation lands mid-read.
    ``generation`` is monotonically non-decreasing.
    """

    def __init__(
        self,
        *,
        detection_key: str = "stock",
        recognition_key: str = "stock",
        hf_pinned_revision: str | None = None,
        auto_rotate_on_load: bool = True,
        auto_rotate_method: AutoRotateMethod = "auto",
    ) -> None:
        self._lock = threading.Lock()
        self._detection_key = detection_key
        self._recognition_key = recognition_key
        self._hf_pinned_revision = hf_pinned_revision
        self._auto_rotate_on_load = auto_rotate_on_load
        self._auto_rotate_method: AutoRotateMethod = auto_rotate_method
        self._generation = 0

    # ── read-only views ──────────────────────────────────────────────────

    @property
    def detection_key(self) -> str:
        with self._lock:
            return self._detection_key

    @property
    def recognition_key(self) -> str:
        with self._lock:
            return self._recognition_key

    @property
    def hf_pinned_revision(self) -> str | None:
        with self._lock:
            return self._hf_pinned_revision

    @property
    def auto_rotate_on_load(self) -> bool:
        with self._lock:
            return self._auto_rotate_on_load

    @property
    def auto_rotate_method(self) -> AutoRotateMethod:
        with self._lock:
            return self._auto_rotate_method

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def snapshot(self) -> tuple[str, str, str | None]:
        """Return a consistent ``(detection, recognition, revision)`` triple
        under the lock. Use this when reading more than one field —
        property-by-property reads can interleave with a writer.
        """
        with self._lock:
            return (
                self._detection_key,
                self._recognition_key,
                self._hf_pinned_revision,
            )

    # ── mutators ─────────────────────────────────────────────────────────

    def set_models(
        self,
        *,
        detection_key: str,
        recognition_key: str,
        hf_pinned_revision: str | None,
    ) -> bool:
        """Update the selection; return ``True`` iff the state changed.

        Idempotent: storing the exact same triple is a no-op and does
        not bump ``generation``. Validation (e.g. "is this key in the
        currently-exposed option list?") is the route's responsibility,
        not the carrier's — the carrier holds whatever string the
        caller hands it. The router's slice-8c-i validation gate stays
        in place.
        """
        with self._lock:
            unchanged = (
                self._detection_key == detection_key
                and self._recognition_key == recognition_key
                and self._hf_pinned_revision == hf_pinned_revision
            )
            if unchanged:
                return False
            self._detection_key = detection_key
            self._recognition_key = recognition_key
            self._hf_pinned_revision = hf_pinned_revision
            self._generation += 1
            return True

    def set_auto_rotate(
        self,
        *,
        auto_rotate_on_load: bool,
        auto_rotate_method: AutoRotateMethod,
    ) -> bool:
        """Update auto-rotate settings; return ``True`` iff the state changed.

        Idempotent: storing the same values is a no-op and does not bump
        ``generation``.
        """
        with self._lock:
            unchanged = (
                self._auto_rotate_on_load == auto_rotate_on_load
                and self._auto_rotate_method == auto_rotate_method
            )
            if unchanged:
                return False
            self._auto_rotate_on_load = auto_rotate_on_load
            self._auto_rotate_method = auto_rotate_method
            self._generation += 1
            return True


__all__ = ["AutoRotateMethod", "OCRConfigCarrier"]

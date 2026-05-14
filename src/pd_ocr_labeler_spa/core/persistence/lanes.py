"""Three on-disk persistence lanes + read-precedence resolver.

Spec authority:

- ``specs/09-persistence.md §1`` lines 18–40 — lane definitions:
  source (read-only), labeled (explicit user saves), cached (auto-save
  after every mutation). Read precedence: labeled → cached → OCR →
  fallback.
- ``specs/01-data-models.md §1`` lines 55–59 — ``PageSource`` enum.
- Issue #221 acceptance criteria.

### Three lanes

1. **Source lane** — ``<source_root>/<project>/<image>.png`` + pages
   JSON. Read-only; writes raise ``SourceLaneReadOnlyError``.
2. **Labeled lane** — ``<data_root>/labeled-projects/<project_id>/
   <project_id>_<page:03d>.json``. Written only on explicit "Save Page"
   or "Save Project" (not on every mutation). Shared with the legacy
   labeler under D-003.
3. **Cached lane** — ``<cache_root>/page-images/<project_id>_<page:03d>_
   envelope.json``. Auto-written after every mutation. SPA-specific
   suffix avoids collision with legacy cache files (D-003).

### Read-precedence resolver

``LaneResolver.load_page_from_disk(page_index)`` probes:

1. Labeled lane — most authoritative (user explicitly saved).
2. Cached lane — recent auto-save (last mutation's snapshot).
3. Returns ``None`` — OCR or fallback are handled by
   ``ensure_page_model`` in ``core/page_state.py`` at the call site;
   this module only owns the on-disk reads.

### Auto-cache-write

``write_cached(page_index, envelope)`` writes a ``UserPageEnvelope``
to the cached lane atomically (tmp + os.replace). Called after every
mutation in the route handlers. Never raises on I/O errors — emits a
WARNING and continues, because a failed cache-write must not turn a
successful mutation into a 500 (per spec §4.2 last paragraph).

### Source-lane write guard

``SourceLaneReadOnlyError(PermissionError)`` is raised by
``write_labeled`` when the caller accidentally targets the source root.
The labeled lane uses its own directory tree (``labeled-projects/``),
so in practice this guard is belt-and-suspenders. Subclasses
``PermissionError`` so generic write-error handling catches it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .atomic import write_json_atomic
from .user_page_envelope import (
    UserPageEnvelope,
    cached_envelope_path,
    envelope_to_dict,
    labeled_envelope_path,
    read_envelope_file,
)

logger = logging.getLogger(__name__)


class SourceLaneReadOnlyError(PermissionError):
    """Raised when a caller attempts to write to the source (read-only) lane.

    Spec: issue #221 acceptance — "Source lane is read-only; writes raise".
    Subclasses ``PermissionError`` so generic error handlers catch it.
    """


@dataclass(frozen=True)
class LaneReadResult:
    """Result of a lane read, pairing the envelope with its source lane.

    ``source`` is one of ``"labeled"``, ``"cached"``, or ``"none"``
    (for callers that want to know which lane satisfied the read).
    """

    envelope: UserPageEnvelope
    source: str


class LaneResolver:
    """On-disk lane reader/writer for a single loaded project.

    Constructed with the three roots from ``Settings``
    (``data_root``, ``cache_root``) plus the ``project_id`` of the
    currently loaded project.

    Instances are cheap to create (no I/O on __init__) — they can be
    constructed per-request or once per project load.

    Spec: ``specs/09-persistence.md §1`` + issue #221.
    """

    def __init__(
        self,
        *,
        data_root: Path,
        cache_root: Path,
        project_id: str,
    ) -> None:
        self._data_root = data_root
        self._cache_root = cache_root
        self._project_id = project_id

    # ── Read-precedence resolver ───────────────────────────────────────────

    def load_page_from_disk(self, page_index: int) -> LaneReadResult | None:
        """Probe labeled → cached lanes; return first hit or ``None``.

        Spec: ``specs/09-persistence.md §1`` lines 32–40.

        - Labeled lane checked first (highest authority — explicit user
          save; shared with legacy labeler under D-003).
        - Cached lane checked second (recent auto-save; SPA-only suffix).
        - Returns ``None`` when both lanes miss — the caller
          (``ensure_page_model``) will fall through to OCR or fallback.

        Failures on individual reads are swallowed (``read_envelope_file``
        is already tolerant); a corrupt/missing file in one lane silently
        falls through to the next.
        """
        # 1. Labeled lane
        labeled_path = labeled_envelope_path(self._data_root, self._project_id, page_index)
        labeled = read_envelope_file(labeled_path)
        if labeled is not None:
            logger.debug(
                "LaneResolver: loaded page %d from labeled lane (%s)",
                page_index,
                labeled_path,
            )
            return LaneReadResult(envelope=labeled, source="labeled")

        # 2. Cached lane
        cached_path = cached_envelope_path(self._cache_root, self._project_id, page_index)
        cached = read_envelope_file(cached_path)
        if cached is not None:
            logger.debug(
                "LaneResolver: loaded page %d from cached lane (%s)",
                page_index,
                cached_path,
            )
            return LaneReadResult(envelope=cached, source="cached")

        # 3. Miss on both lanes — OCR / fallback handled by caller
        return None

    # ── Labeled lane writer ────────────────────────────────────────────────

    def write_labeled(self, page_index: int, envelope: UserPageEnvelope) -> Path:
        """Write envelope to the labeled lane atomically.

        Spec: issue #221 — "Labeled lane written only on explicit Save
        Page / Save Project". The labeled-lane directory is created on
        first write. Returns the path written.

        Raises ``SourceLaneReadOnlyError`` if (somehow) the caller
        attempts to write to a path inside the source root instead of
        the labeled-projects tree.  In practice the labeled-lane path
        is always under ``data_root/labeled-projects/``, so this guard
        is belt-and-suspenders (issue #221: "Source lane is read-only;
        writes raise").
        """
        path = labeled_envelope_path(self._data_root, self._project_id, page_index)
        # Belt-and-suspenders guard: labeled path must NOT be under source root.
        # (The source root is a different directory entirely, but we validate
        # the written path is under labeled-projects/ as a safety net.)
        labeled_root = self._data_root / "labeled-projects"
        try:
            path.relative_to(labeled_root)
        except ValueError as exc:
            raise SourceLaneReadOnlyError(
                f"write_labeled path {path!r} is not under labeled-projects root "
                f"{labeled_root!r} — refusing to write"
            ) from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, envelope_to_dict(envelope))
        logger.info(
            "LaneResolver: wrote labeled lane page %d → %s",
            page_index,
            path,
        )
        return path

    # ── Cached lane writer (auto-save after every mutation) ────────────────

    def write_cached(self, page_index: int, envelope: UserPageEnvelope) -> None:
        """Write envelope to the cached lane atomically.

        Spec: issue #221 — "Cached lane written after every mutation".
        Legacy parity: ``project_state.py:780-797 (_auto_save_to_cache)``.

        Never raises — I/O errors are logged as WARNING and swallowed
        so a failed cache-write does not turn a successful mutation into
        a 500.  Spec: ``specs/09-persistence.md §4.2`` last paragraph.
        """
        path = cached_envelope_path(self._cache_root, self._project_id, page_index)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(path, envelope_to_dict(envelope))
            logger.debug(
                "LaneResolver: wrote cached lane page %d → %s",
                page_index,
                path,
            )
        except OSError as exc:
            logger.warning(
                "LaneResolver: cached lane write failed for page %d (%s): %s — continuing",
                page_index,
                path,
                exc,
            )


__all__ = [
    "LaneReadResult",
    "LaneResolver",
    "SourceLaneReadOnlyError",
]

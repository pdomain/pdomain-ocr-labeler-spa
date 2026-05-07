"""Domain models — the typed in-memory shapes shared by adapters + wire.

Spec authority:
- ``specs/01-data-models.md §1`` lines 21-44 — ``Project`` model.
- ``specs/01-data-models.md`` opening lines 7-12 — convention: domain
  models live here and are reused by both the ``IStorage`` /
  ``IOCREngine`` Protocols AND the wire (no separate DTO layer).

What this iter-4 (M2 skeleton) ships:

- ``Project`` — minimal slice-5-ready shape: all spec-§1 fields, but
  no ``from_dict`` / ``to_dict`` round-trip yet (slice 5 lands the
  ``UserPageEnvelope``-bytes-compatible persistence layer per spec
  ``§09-persistence.md``).

What this iter-4 deliberately does NOT do:

- Ship the M3+ models (``PageRecord``, ``WordMatch``, ``LineMatch``,
  ``BBox``, ``Selection``, ``LineFilter``, ``EncodedDims``, etc.).
  They land milestone-by-milestone as the routes that need them ship.
- Ship persistence ``from_dict`` / ``to_dict``. The legacy
  ``UserPageEnvelope`` v2.1 contract is a hard one (see workspace
  memory ``project_d003_extras_tolerance.md``) and deserves its own
  round-trip test suite — slice 5.

Adding new models: append; never reorder. Generated TS via
``make openapi-export`` keys on field name + position.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Project(BaseModel):
    """One labeler project — ``specs/01-data-models.md §1`` lines 28-44.

    Mirrors legacy ``pd_ocr_labeler/models/project_model.py:9``.

    Field semantics:

    - ``project_id``: derived from ``project_root.name``. The legacy
      labeler treats this as the URL-stable identifier (M2-proper's
      ``GET /api/projects/{id}`` keys on it).
    - ``project_root``: absolute path to the project directory.
    - ``image_paths``: sorted list of page image files. Order is
      authoritative — ``page_index`` indexes into this list.
    - ``ground_truth_map``: normalized ``{stem -> text}`` mapping read
      from per-image GT sidecars.
    - ``version`` / ``source_lib``: provenance fields written into
      ``project.json`` for legacy round-trip; defaults match the
      legacy labeler's defaults so a round-trip of an unsaved project
      doesn't churn these fields.
    - ``total_pages``: == ``len(image_paths)``. Carried as a separate
      field (and not just a property) so the JSON envelope keeps the
      legacy v2.1 shape.
    - ``saved_pages`` / ``current_page_index``: persisted UI state.
    - ``include_images`` / ``copied_images``: legacy export-bundle
      flags; M2 carries them through unchanged for round-trip parity.

    Validation: top-level envelope so ``extra="forbid"`` per
    ``specs/01-data-models.md`` line 15. (Per workspace memory
    ``project_d003_extras_tolerance.md``, ``extra="forbid"`` is
    correct for ``UserPageEnvelope`` and project-level envelopes; the
    extras-tolerance carve-out applies to *session_state.json* and
    other D-003-shared sidecar files.)
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str
    project_root: Path
    image_paths: list[Path]
    ground_truth_map: dict[str, str]
    version: str = "1.0"
    source_lib: str = "doctr-pd-labeled"
    total_pages: int
    saved_pages: int = 0
    current_page_index: int = 0
    include_images: bool = True
    copied_images: bool = False

    @property
    def page_count(self) -> int:
        """``== len(image_paths)`` per spec §1 line 43.

        Computed (not stored) so callers always see the live count even
        if a future code path mutates ``image_paths`` in place.
        """
        return len(self.image_paths)


__all__ = ["Project"]

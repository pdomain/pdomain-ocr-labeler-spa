"""``project.json`` reader/writer + the ``Project`` builder.

Spec authority:

- ``specs/09-persistence.md §5`` — ``project.json`` shape (per the
  labeled-projects lane: ``<labeled-projects>/<project_id>/project.json``).
- ``specs/01-data-models.md §1`` lines 28-44 — ``Project`` model.
- ``specs/16-milestones.md`` line 159 — slice 5 scope.

Three responsibilities in this module:

1. ``project_to_dict(project) -> dict`` — serialize the persisted
   metadata slice of a ``Project`` for ``project.json``. Mirrors
   legacy ``project_model.py::to_dict`` (line 42-54).

2. ``project_from_dict(data, image_paths, ground_truth_map) -> Project`` —
   reconstitute a ``Project`` from persisted metadata + caller-supplied
   filesystem-derived fields. The dict-side is byte-compatible with
   legacy ``project_model.py::from_dict`` (line 56-71).

3. ``read_project_metadata(project_root) -> dict | None`` — open the
   ``project.json`` file and return the parsed dict. Returns ``None``
   on any failure (missing/malformed/wrong-shape) — the caller falls
   back to defaults.

4. ``build_project_from_directory(project_root, ground_truth_map) -> Project`` —
   the integration helper called by ``POST /api/projects/load``:
   scans for image files (sorted, three exts), reads optional
   ``project.json`` for saved metadata, constructs the ``Project``.

D-003 byte-compat with legacy:

The legacy ``Project`` dataclass and the SPA ``Project`` Pydantic
model differ in two field types:

- ``copied_images``: legacy ``int`` (count) vs SPA ``bool`` (gate).
- ``project_root`` vs legacy ``source_path``: SPA carries an absolute
  ``Path`` object; legacy persists a string under the key
  ``"source_path"``. Wire-side both serialize as a string at the
  ``"source_path"`` key — the field rename is local to the in-memory
  model.

Both differences are handled at the to_dict/from_dict boundary so the
on-disk shape stays identical to legacy.

Slice-5 deliberately does NOT ship:

- ``write_project_json`` (atomic write of ``project.json``). That's
  the **save** side; M5 lands it together with the rest of the
  Save Project flow. Reading is what M2 needs.
- The full ``UserPageEnvelope`` v2.1 reader/writer
  (``user_page_envelope.py``). That's per-page, M3 territory.
- Multi-project state. M2 ships single-project load; future iters
  will support having multiple ``Project`` instances cached at once.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pd_ocr_labeler_spa.core.models import Project

logger = logging.getLogger(__name__)

# Legacy filename pin — ``project_operations.py:162``.
PROJECT_JSON_FILENAME = "project.json"

# Image extensions, mirrored from legacy ``constants.py:15``. Same set
# as ``ground_truth.py`` keeps; defined per-module so each is
# self-contained for testing.
_IMAGE_EXTS = (".png", ".jpg", ".jpeg")

# Legacy default for ``copied_images`` when reading a half-populated
# dict. The legacy default is int 0; we coerce to bool below, so the
# default we read is False.
_LEGACY_DEFAULTS: dict[str, Any] = {
    "version": "1.0",
    "source_lib": "doctr-pd-labeled",
    "saved_pages": 0,
    "current_page_index": 0,
    "include_images": True,
    "copied_images": False,
}

__all__ = [
    "PROJECT_JSON_FILENAME",
    "build_project_from_directory",
    "project_from_dict",
    "project_to_dict",
    "read_project_metadata",
]


# ── to_dict / from_dict ──────────────────────────────────────────────────


def project_to_dict(project: Project) -> dict[str, Any]:
    """Serialize the persisted-metadata slice of ``project`` to a dict.

    The output is **byte-compatible** with legacy
    ``project_model.py::to_dict`` — same nine keys, same value types
    (modulo ``copied_images: bool`` per the SPA spec; legacy reads
    JSON ``true`` as Python ``bool`` which ``isinstance``-checks as
    ``int`` so its consumer doesn't crash).

    Field mapping:

    - ``project.project_root`` → ``"source_path"`` (string-encoded;
      legacy uses string).
    - All other fields pass through under their canonical names.

    NOT serialized (because they're filesystem-derived and re-built on
    every load):

    - ``image_paths`` — re-scanned from disk.
    - ``ground_truth_map`` — re-loaded from ``pages.json`` / manifest.
    """
    return {
        "version": project.version,
        "source_lib": project.source_lib,
        "project_id": project.project_id,
        # Legacy persists the project root under "source_path"; honor
        # the legacy key name so cross-binary reads work.
        "source_path": str(project.project_root),
        "total_pages": project.total_pages,
        "saved_pages": project.saved_pages,
        "current_page_index": project.current_page_index,
        "include_images": project.include_images,
        "copied_images": project.copied_images,
    }


def project_from_dict(
    data: dict[str, Any],
    *,
    image_paths: list[Path],
    ground_truth_map: dict[str, str],
) -> Project:
    """Reconstitute a ``Project`` from persisted-metadata dict + filesystem.

    Reads the persisted metadata (with legacy-default fallbacks for
    missing keys, mirroring legacy ``project_model.py:60-69`` —
    ``data.get(key, default)`` pattern), then composes with the
    caller-supplied ``image_paths`` (filesystem-derived) and
    ``ground_truth_map`` (from the GT loader).

    Coercions:

    - ``copied_images``: int (legacy) → bool (SPA). ``0 → False``,
      any non-zero → ``True``. Pin matches the legacy semantics
      ("did we copy any?") without preserving the count (which the
      SPA spec dropped intentionally).

    The ``image_paths`` and ``ground_truth_map`` kwargs are
    keyword-only because they're not in the dict — this prevents
    accidental positional-arg confusion at the call site.
    """
    # The persisted source path lives under "source_path" (legacy key).
    # If absent, fall back to the empty string — the resulting
    # Path("") will fail Pydantic if image_paths is non-empty (because
    # caller-side typically resolves project_root themselves), but the
    # builder always passes project_root through the resolved-path code
    # path so this fallback is only hit when callers construct a
    # ``Project`` purely from a dict (round-trip tests).
    source_path = data.get("source_path", "")

    copied_raw = data.get("copied_images", _LEGACY_DEFAULTS["copied_images"])
    # bool isinstance(int) is True in Python, so we must check bool
    # FIRST — otherwise an explicit True/False would slip through the
    # int-coercion branch. Both branches converge on the same bool.
    if isinstance(copied_raw, bool):
        copied_bool = copied_raw
    elif isinstance(copied_raw, int):
        copied_bool = copied_raw != 0
    else:
        # Pydantic would reject a non-int/non-bool here; surface the
        # legacy-friendly default so a malformed value doesn't crash
        # an otherwise-valid project load.
        logger.warning("Unexpected copied_images value %r; defaulting to False", copied_raw)
        copied_bool = False

    return Project(
        version=data.get("version", _LEGACY_DEFAULTS["version"]),
        source_lib=data.get("source_lib", _LEGACY_DEFAULTS["source_lib"]),
        project_id=data.get("project_id", ""),
        project_root=Path(source_path) if source_path else Path(""),
        image_paths=image_paths,
        ground_truth_map=ground_truth_map,
        total_pages=data.get("total_pages", len(image_paths)),
        saved_pages=data.get("saved_pages", _LEGACY_DEFAULTS["saved_pages"]),
        current_page_index=data.get("current_page_index", _LEGACY_DEFAULTS["current_page_index"]),
        include_images=data.get("include_images", _LEGACY_DEFAULTS["include_images"]),
        copied_images=copied_bool,
    )


# ── read_project_metadata ────────────────────────────────────────────────


def read_project_metadata(project_root: Path) -> dict[str, Any] | None:
    """Read ``project.json`` from ``project_root`` and return parsed dict.

    Returns ``None`` (not raises) on:

    - Missing file (the common "never-saved" case).
    - Malformed JSON (defensive — a hand-edited file shouldn't crash).
    - Non-object root (``[]``, ``"string"``, etc).
    - I/O error (permissions, etc).

    Returning ``None`` on every failure mode mirrors legacy
    ``project_operations.py:152-187`` ("don't break existing projects").
    The builder treats ``None`` as "use legacy defaults" via
    ``project_from_dict({}, ...)``.

    Rationale for not validating with ``project_from_dict`` here: the
    builder applies its own clamps / fallbacks downstream, and errors
    that surface in this read step would be losing information about
    *why* the read failed (file vs json vs shape). Logging at this
    layer keeps the diagnostic visible.
    """
    project_json_path = project_root / PROJECT_JSON_FILENAME
    if not project_json_path.exists():
        return None

    try:
        with open(project_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001  (we WANT to swallow on read)
        logger.warning("Failed to read %s: %s", project_json_path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning(
            "Root of %s is not a JSON object: %r",
            project_json_path,
            type(data).__name__,
        )
        return None

    return data


# ── build_project_from_directory ─────────────────────────────────────────


def build_project_from_directory(
    project_root: Path,
    *,
    ground_truth_map: dict[str, str],
) -> Project:
    """Scan a project directory + read optional metadata → ``Project``.

    Composes the three pieces:

    1. ``_scan_image_paths`` — sorted list of ``.png/.jpg/.jpeg`` files.
    2. ``read_project_metadata`` — optional ``project.json`` dict.
    3. Caller-supplied ``ground_truth_map`` (the route layer composes
       ``ground_truth.load_ground_truth_from_directory`` separately so
       the same builder is reusable from places that already have GT
       in hand — e.g. cached invalidation paths).

    Then constructs a ``Project`` with on-disk truths winning over
    persisted metadata where they conflict:

    - ``project_id`` always derived from ``project_root.name`` (URL
      stability — never let a stale ``project.json`` override).
    - ``project_root`` always the resolved input (caller control).
    - ``image_paths`` always from disk scan.
    - ``total_pages`` always ``== len(image_paths)`` (resilient against
      stale persisted ``total_pages``).
    - ``current_page_index`` clamped to ``[0, total_pages-1]`` (or 0
      if ``total_pages == 0``) so a stale-cursor save doesn't crash
      ``ProjectState.set_current_page_index``'s upper-bound check.
    - All other persisted fields pass through with legacy defaults
      when missing.

    Filesystem-error semantics: if ``project_root`` doesn't exist or
    isn't a directory, ``_scan_image_paths`` raises (route layer
    surfaces as ``project_not_found`` / ``invalid_project_dir``).
    Beyond that, an empty project dir is loadable with
    ``image_paths=[]``, ``total_pages=0`` — the route layer gets to
    decide if that's worth a user-facing message.
    """
    resolved_root = project_root.resolve()
    image_paths = _scan_image_paths(resolved_root)
    metadata = read_project_metadata(resolved_root) or {}

    # Apply on-disk overrides + clamps. We can't just call
    # ``project_from_dict`` then mutate — the model is immutable from
    # the outside, and we want the constructor to see correct values.
    overrides = dict(metadata)
    overrides["project_id"] = resolved_root.name
    overrides["source_path"] = str(resolved_root)
    overrides["total_pages"] = len(image_paths)

    persisted_cursor = metadata.get("current_page_index", 0)
    if not isinstance(persisted_cursor, int):
        persisted_cursor = 0
    if image_paths:
        clamped_cursor = max(0, min(persisted_cursor, len(image_paths) - 1))
    else:
        clamped_cursor = 0
    overrides["current_page_index"] = clamped_cursor

    return project_from_dict(
        overrides,
        image_paths=image_paths,
        ground_truth_map=ground_truth_map,
    )


def _scan_image_paths(directory: Path) -> list[Path]:
    """Return sorted list of image files in ``directory``.

    Mirrors legacy ``project_operations.py:43-77`` (``scan_project_directory``).

    Accepts ``.png/.jpg/.jpeg`` (case-insensitive). Sorted by name for
    consistent ordering — the page index is the index into this list.

    Raises ``FileNotFoundError`` if the directory doesn't exist;
    ``NotADirectoryError`` (via ``ValueError`` upstream — legacy raises
    ``ValueError`` but ``NotADirectoryError`` is the more specific
    Python idiom). The route layer catches both and surfaces a
    user-friendly error tag.
    """
    if not directory.exists():
        raise FileNotFoundError(f"directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"path is not a directory: {directory}")

    # Case-insensitive extension check. ``Path.suffix`` preserves case,
    # so we lowercase both sides — a ``001.PNG`` file is a valid image.
    images = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_EXTS]
    return sorted(images)

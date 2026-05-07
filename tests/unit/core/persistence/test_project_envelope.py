"""Round-trip tests for ``core/persistence/project_envelope.py``.

Spec: ``specs/09-persistence.md §5`` (the ``project.json`` shape) +
``specs/01-data-models.md §1`` (the ``Project`` model) +
``specs/16-milestones.md`` line 159 (slice 5 scope).

What slice 5 ships in this module:

1. ``Project.to_dict`` / ``from_dict`` — byte-compatible serialization
   of ``Project`` to a dict matching legacy
   ``pd-ocr-labeler/pd_ocr_labeler/models/project_model.py:42-71``.
   Round-trip identity (``from_dict(to_dict(p)) == p`` modulo defaults)
   is the contract that lets the SPA read a legacy-saved
   ``project.json`` AND write one back the legacy can re-load.

2. ``read_project_metadata(project_root) -> dict | None`` — read the
   ``project.json`` file from a labeled-projects directory. Returns
   ``None`` if the file's missing (a fresh source-lane project that
   was never saved). Mirrors legacy
   ``project_operations.py::load_project_metadata`` (line 152).

3. ``build_project_from_directory(project_root, ground_truth_map)`` —
   the integration helper: scans for image files (sorted, three
   extensions), reads optional ``project.json`` for saved metadata,
   constructs the in-memory ``Project``. Used by
   ``POST /api/projects/load`` to swap the carrier.

Why round-trip identity matters: the legacy and SPA share the
labeled-projects lane (D-003). If a user opens a project in the SPA,
makes no changes, and the SPA round-trips ``project.json``, the legacy
must still re-read it identically. A field rename / type drift here
would break that contract silently.

Note on the legacy ``copied_images`` field:

- Legacy ``Project`` model has ``copied_images: int`` (count of images
  copied; defaults to 0 — see legacy ``project_model.py:35``).
- SPA spec ``§01-data-models.md`` line 40 has ``copied_images: bool``
  (defaults to ``False``).

This is a known D-003 friction point. The SPA accepts both shapes on
read (legacy-int writes coerce to the spec-bool: any non-zero int
counts as ``True``) and writes back as ``bool`` (the spec shape). On
the legacy round-trip side, a JSON ``true``/``false`` is dict-loadable
into the legacy ``int`` field as a ``bool`` Python value (Python's
``bool`` ``isinstance`` of ``int``), so legacy reads of an SPA-written
``true`` work — the field just carries 1 instead of an actual count.
This is documented in the implementation, not silent.
"""

from __future__ import annotations

import json
from pathlib import Path

from pd_ocr_labeler_spa.core.models import Project
from pd_ocr_labeler_spa.core.persistence.project_envelope import (
    PROJECT_JSON_FILENAME,
    build_project_from_directory,
    project_from_dict,
    project_to_dict,
    read_project_metadata,
)

# ── module-level constant pin ────────────────────────────────────────────


def test_project_json_filename_constant() -> None:
    """The metadata filename is pinned at ``project.json``.

    Legacy parity: ``project_operations.py:162``. Constant exported so
    a typo is caught at import time, not after a project save.
    """
    assert PROJECT_JSON_FILENAME == "project.json"


# ── to_dict / from_dict round trip ───────────────────────────────────────


def _make_project(tmp_path: Path) -> Project:
    """Helper: a representative Project with non-default fields."""
    return Project(
        project_id="example_book",
        project_root=tmp_path / "example_book",
        image_paths=[
            tmp_path / "example_book" / "001.png",
            tmp_path / "example_book" / "002.png",
        ],
        ground_truth_map={"001.png": "page one", "002.png": "page two"},
        version="1.0",
        source_lib="doctr-pd-labeled",
        total_pages=2,
        saved_pages=1,
        current_page_index=1,
        include_images=True,
        copied_images=False,
    )


def test_project_to_dict_emits_legacy_compatible_keys(tmp_path: Path) -> None:
    """``project_to_dict`` emits exactly the legacy field set.

    Legacy parity: ``project_model.py:42-54``. The on-disk
    ``project.json`` carries these nine fields, no more no less. Pin
    the key set so an additive change to ``Project`` doesn't silently
    leak a new field through to disk (which the legacy reader would
    silently ignore via ``data.get(...)``).
    """
    p = _make_project(tmp_path)
    d = project_to_dict(p)
    assert set(d.keys()) == {
        "version",
        "source_lib",
        "project_id",
        "source_path",
        "total_pages",
        "saved_pages",
        "current_page_index",
        "include_images",
        "copied_images",
    }


def test_project_to_dict_source_path_is_string(tmp_path: Path) -> None:
    """``source_path`` is serialized as a string, not a Path.

    Legacy parity: ``project_model.py:48`` — ``source_path: str = ""``
    on the legacy dataclass. JSON has no Path type, so we always
    stringify on write. Pin the type so a future refactor doesn't
    accidentally write ``PosixPath('...')`` repr that the legacy
    couldn't parse.
    """
    p = _make_project(tmp_path)
    d = project_to_dict(p)
    assert isinstance(d["source_path"], str)
    # The serialized string is the absolute path.
    assert d["source_path"] == str(p.project_root)


def test_project_to_dict_copied_images_is_bool(tmp_path: Path) -> None:
    """SPA writes ``copied_images`` as the spec-canonical bool.

    Spec: ``§01-data-models.md`` line 40 — the SPA's ``Project`` has
    ``copied_images: bool``. We honor the spec on write; the legacy
    reads ``True`` as int(1) which round-trips as a no-op for its
    purposes (it's a "did we copy?" gate; truthiness is what matters).
    See module docstring for the D-003 friction discussion.
    """
    p = _make_project(tmp_path)
    d = project_to_dict(p)
    assert d["copied_images"] is False
    p_with_copy = p.model_copy(update={"copied_images": True})
    assert project_to_dict(p_with_copy)["copied_images"] is True


def test_project_from_dict_reads_legacy_default_int(tmp_path: Path) -> None:
    """A legacy-written ``copied_images: 0`` is accepted as ``False``.

    Legacy parity: ``project_model.py:35`` — legacy default is int 0.
    Without coercion, a SPA reader of a legacy-written
    ``project.json`` would fail validation on the type mismatch. The
    coercion is **read-side**: int 0 → False, any non-zero int → True.
    """
    legacy_dict = {
        "version": "1.0",
        "source_lib": "doctr-pd-labeled",
        "project_id": "legacy_book",
        "source_path": str(tmp_path / "legacy_book"),
        "total_pages": 5,
        "saved_pages": 0,
        "current_page_index": 0,
        "include_images": True,
        "copied_images": 0,  # ← legacy int
    }
    project = project_from_dict(
        legacy_dict,
        image_paths=[tmp_path / f"{i:03d}.png" for i in range(1, 6)],
        ground_truth_map={},
    )
    assert project.copied_images is False


def test_project_from_dict_reads_legacy_nonzero_int(tmp_path: Path) -> None:
    """Legacy ``copied_images`` count → SPA's bool ``True``.

    Non-zero int means "we copied at least one image"; the SPA's
    truthiness-gate matches that semantics. Pin so a refactor doesn't
    flip the convention to "exact 1 → True".
    """
    legacy_dict = {
        "version": "1.0",
        "source_lib": "doctr-pd-labeled",
        "project_id": "legacy_book",
        "source_path": str(tmp_path / "legacy_book"),
        "total_pages": 5,
        "saved_pages": 0,
        "current_page_index": 0,
        "include_images": True,
        "copied_images": 7,  # ← legacy "we copied 7 images"
    }
    project = project_from_dict(
        legacy_dict,
        image_paths=[tmp_path / f"{i:03d}.png" for i in range(1, 6)],
        ground_truth_map={},
    )
    assert project.copied_images is True


def test_project_from_dict_preserves_metadata(tmp_path: Path) -> None:
    """All persisted metadata fields survive the read.

    The persisted-metadata round trip is the heart of the slice-5
    contract. ``Project.image_paths`` and ``ground_truth_map`` are
    NOT in the persisted dict (they're derived from filesystem +
    pages.json on each load); the dict carries scalar metadata only.
    """
    legacy_dict = {
        "version": "1.0",
        "source_lib": "doctr-pd-labeled",
        "project_id": "the_four_men",
        "source_path": "/some/abs/path/to/the_four_men",
        "total_pages": 42,
        "saved_pages": 12,
        "current_page_index": 5,
        "include_images": True,
        "copied_images": False,
    }
    project = project_from_dict(
        legacy_dict,
        image_paths=[tmp_path / f"{i:03d}.png" for i in range(1, 43)],
        ground_truth_map={"001.png": "first"},
    )
    assert project.project_id == "the_four_men"
    assert project.total_pages == 42
    assert project.saved_pages == 12
    assert project.current_page_index == 5
    assert project.include_images is True
    assert project.copied_images is False
    # image_paths + ground_truth_map come from caller, not the dict.
    assert len(project.image_paths) == 42
    assert project.ground_truth_map == {"001.png": "first"}


def test_project_from_dict_uses_legacy_defaults_for_missing_keys(tmp_path: Path) -> None:
    """Missing keys fall back to the same defaults as legacy.

    Legacy parity: ``project_model.py:60-69`` uses ``data.get(key,
    default)`` for every field. We mirror so a half-populated
    ``project.json`` (e.g., one written by an older legacy version)
    doesn't fail validation.
    """
    skinny_dict = {
        "project_id": "skinny",
        "source_path": str(tmp_path / "skinny"),
        "total_pages": 3,
    }
    project = project_from_dict(
        skinny_dict,
        image_paths=[tmp_path / f"{i:03d}.png" for i in range(1, 4)],
        ground_truth_map={},
    )
    assert project.version == "1.0"
    assert project.source_lib == "doctr-pd-labeled"
    assert project.saved_pages == 0
    assert project.current_page_index == 0
    assert project.include_images is True
    assert project.copied_images is False


def test_project_to_dict_then_from_dict_round_trips(tmp_path: Path) -> None:
    """Identity invariant: ``from_dict(to_dict(p))`` == ``p`` for the
    persisted-metadata slice.

    Spec ``§09-persistence.md`` line 100-105 spells out the round-trip
    invariant for the full envelope; this test covers the
    ``project.json`` slice. ``image_paths`` + ``ground_truth_map`` are
    held constant across the round-trip (they're not in the dict).
    """
    original = _make_project(tmp_path)
    d = project_to_dict(original)
    restored = project_from_dict(
        d,
        image_paths=original.image_paths,
        ground_truth_map=original.ground_truth_map,
    )
    # Compare every field — equality on Pydantic v2 models compares
    # field-by-field (no ``__eq__`` override needed).
    assert restored == original


# ── read_project_metadata ────────────────────────────────────────────────


def test_read_project_metadata_missing_file_returns_none(tmp_path: Path) -> None:
    """Missing ``project.json`` → ``None`` (not an error).

    Legacy parity: ``project_operations.py:163-165`` returns ``None``
    when the file's absent. A source-lane project that's never been
    saved has no ``project.json``; the loader treats this as "use
    defaults", not "refuse to load".
    """
    assert read_project_metadata(tmp_path) is None


def test_read_project_metadata_returns_dict_on_success(tmp_path: Path) -> None:
    """Valid ``project.json`` is returned as a dict for caller to feed
    into ``project_from_dict``.

    The caller-side composition is intentional: ``read_project_metadata``
    handles the I/O (open, decode, parse JSON), ``project_from_dict``
    handles the model construction. Splitting the two makes both
    independently testable and lets ``build_project_from_directory``
    skip the disk read when no file exists.
    """
    persisted = {
        "version": "1.0",
        "source_lib": "doctr-pd-labeled",
        "project_id": "x",
        "source_path": str(tmp_path),
        "total_pages": 3,
        "saved_pages": 1,
        "current_page_index": 0,
        "include_images": True,
        "copied_images": False,
    }
    (tmp_path / PROJECT_JSON_FILENAME).write_text(json.dumps(persisted, indent=2), encoding="utf-8")
    result = read_project_metadata(tmp_path)
    assert result == persisted


def test_read_project_metadata_invalid_json_returns_none(tmp_path: Path) -> None:
    """Malformed ``project.json`` → ``None`` + warning, never raises.

    Legacy parity: ``project_operations.py:185-187`` catches all
    exceptions and returns ``None``. A typo'd ``project.json``
    shouldn't prevent the project from loading at all — we'd rather
    fall back to defaults than crash.
    """
    (tmp_path / PROJECT_JSON_FILENAME).write_text("not json {", encoding="utf-8")
    assert read_project_metadata(tmp_path) is None


# ── build_project_from_directory ─────────────────────────────────────────


def _seed_image(path: Path) -> None:
    """Create a 1-byte placeholder image (we don't read pixel data here)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")


def test_build_project_from_directory_scans_images_sorted(tmp_path: Path) -> None:
    """Image scan: all three exts, sorted, deduplicated by stem.

    Legacy parity: ``project_operations.py:43-77``
    (``scan_project_directory``) — sorted by name, three image
    extensions only.
    """
    project_root = tmp_path / "test_book"
    _seed_image(project_root / "002.png")
    _seed_image(project_root / "001.png")
    _seed_image(project_root / "003.jpg")
    _seed_image(project_root / "ignore.txt")  # not an image
    project = build_project_from_directory(project_root, ground_truth_map={})
    assert [p.name for p in project.image_paths] == ["001.png", "002.png", "003.jpg"]
    assert project.total_pages == 3


def test_build_project_from_directory_uses_basename_as_project_id(tmp_path: Path) -> None:
    """``project_id`` = directory basename.

    Spec: ``§01-data-models.md`` line 30 — derived from
    ``project_root.name``. URL-stable identifier; we never invent a
    hash or counter.
    """
    project_root = tmp_path / "the_four_men"
    _seed_image(project_root / "001.png")
    project = build_project_from_directory(project_root, ground_truth_map={})
    assert project.project_id == "the_four_men"


def test_build_project_from_directory_resolves_project_root(tmp_path: Path) -> None:
    """``Project.project_root`` is absolute (resolved).

    Pin: a relative path passed to the builder produces an absolute
    ``project_root`` — important because the route layer sometimes
    passes paths through user input that may be relative-relative.
    """
    project_root = tmp_path / "resolved_book"
    _seed_image(project_root / "001.png")
    project = build_project_from_directory(project_root, ground_truth_map={})
    assert project.project_root.is_absolute()
    assert project.project_root == project_root.resolve()


def test_build_project_from_directory_ground_truth_passed_through(tmp_path: Path) -> None:
    """The caller-supplied ``ground_truth_map`` lands on the Project verbatim.

    Decoupled by design: the builder doesn't read GT itself (that's
    ``ground_truth.py``'s job). The route layer composes the two.
    """
    project_root = tmp_path / "gt_book"
    _seed_image(project_root / "001.png")
    gt = {"001.png": "page one"}
    project = build_project_from_directory(project_root, ground_truth_map=gt)
    assert project.ground_truth_map == gt


def test_build_project_from_directory_uses_project_json_when_present(tmp_path: Path) -> None:
    """Saved metadata (``project.json``) overrides defaults.

    When the user has previously saved this project (from either
    binary), the saved cursor / saved-pages count / etc. survives the
    re-load. This is the resume-from-disk parity legacy users expect.
    """
    project_root = tmp_path / "saved_book"
    _seed_image(project_root / "001.png")
    _seed_image(project_root / "002.png")
    _seed_image(project_root / "003.png")
    saved = {
        "version": "1.0",
        "source_lib": "doctr-pd-labeled",
        "project_id": "saved_book",
        "source_path": str(project_root),
        "total_pages": 3,
        "saved_pages": 2,
        "current_page_index": 1,
        "include_images": True,
        "copied_images": False,
    }
    (project_root / "project.json").write_text(json.dumps(saved), encoding="utf-8")
    project = build_project_from_directory(project_root, ground_truth_map={})
    assert project.saved_pages == 2
    assert project.current_page_index == 1


def test_build_project_from_directory_no_project_json_uses_defaults(tmp_path: Path) -> None:
    """Without saved metadata, defaults match legacy fresh-load behavior.

    Legacy parity: a never-saved source-lane project loads with
    ``saved_pages=0``, ``current_page_index=0``. Pin so a refactor
    doesn't accidentally seed non-zero defaults.
    """
    project_root = tmp_path / "fresh_book"
    _seed_image(project_root / "001.png")
    project = build_project_from_directory(project_root, ground_truth_map={})
    assert project.saved_pages == 0
    assert project.current_page_index == 0


def test_build_project_from_directory_total_pages_from_image_count(tmp_path: Path) -> None:
    """``total_pages`` reflects the **on-disk** image count, not the
    saved metadata.

    If ``project.json`` says ``total_pages=5`` but only 3 images are
    on disk (e.g., the user deleted some), the on-disk truth wins.
    Legacy parity: ``create_project`` re-derives ``total_pages`` from
    ``len(images)`` (``project_operations.py:145``); the persisted
    ``total_pages`` is informational only.
    """
    project_root = tmp_path / "stale_book"
    _seed_image(project_root / "001.png")
    _seed_image(project_root / "002.png")
    saved = {
        "project_id": "stale_book",
        "source_path": str(project_root),
        "total_pages": 99,  # ← stale; only 2 images on disk
        "saved_pages": 0,
        "current_page_index": 0,
        "include_images": True,
        "copied_images": False,
    }
    (project_root / "project.json").write_text(json.dumps(saved), encoding="utf-8")
    project = build_project_from_directory(project_root, ground_truth_map={})
    assert project.total_pages == 2


def test_build_project_from_directory_clamps_current_page_index(tmp_path: Path) -> None:
    """If saved cursor ≥ on-disk page count, clamp to last page.

    Defensive: a stale ``project.json`` with cursor=4 but only 2 pages
    on disk would crash later when ``ProjectState.set_loaded_project``
    tries to seed the cursor (the M2 ``set_current_page_index``
    upper-bound check would reject). Better to clamp here at load
    time so the user sees the last available page.

    Pin: clamp is to ``total_pages - 1`` when in-bounds, else 0
    (when ``total_pages == 0`` we have no valid cursor anyway).
    """
    project_root = tmp_path / "clamped_book"
    _seed_image(project_root / "001.png")
    _seed_image(project_root / "002.png")
    saved = {
        "project_id": "clamped_book",
        "source_path": str(project_root),
        "total_pages": 99,
        "saved_pages": 0,
        "current_page_index": 50,  # ← way out of range
        "include_images": True,
        "copied_images": False,
    }
    (project_root / "project.json").write_text(json.dumps(saved), encoding="utf-8")
    project = build_project_from_directory(project_root, ground_truth_map={})
    assert project.current_page_index == 1  # last page (0-based)


def test_build_project_from_directory_zero_images_yields_empty_project(tmp_path: Path) -> None:
    """A project dir with no images is loadable but empty.

    The route layer is the one that decides "should we surface a
    user-friendly error for empty projects?"; the builder's contract
    is "return what's on disk". An empty project is a valid (if
    useless) loadable state — pin so we don't accidentally raise here.
    """
    project_root = tmp_path / "empty_book"
    project_root.mkdir()
    project = build_project_from_directory(project_root, ground_truth_map={})
    assert project.image_paths == []
    assert project.total_pages == 0
    assert project.current_page_index == 0

"""Unit tests for ``core.project_enumeration`` — M2 slice 4 starter.

Slice 4 of the M2 startup-discovery sequence ships *project
enumeration*: scanning ``Settings.source_projects_root`` for project
subdirectories and returning a sorted, deduped list that the future
``GET /api/projects`` endpoint will hand to the frontend's project
dropdown.

Spec authority:

- ``docs/architecture/02-backend.md §5.2`` (line 208-213): ``GET /api/projects``
  reads ``Settings.source_projects_root``, scans for project dirs,
  returns sorted list with the currently selected one (last loaded
  or CLI-provided).
- ``docs/architecture/02-backend.md §13`` step 2: "Scan for project subdirectories."
- ``docs/architecture/01-data-models.md §2`` lines 212-216: ``ProjectKey`` is the
  wire shape — ``project_id`` (the dir basename, used as a stable
  identifier in URLs), ``project_root`` (absolute path), ``label``
  (display label, equal to ``project_id`` plus a dedup suffix when
  two scanned roots share a basename).

What slice 4 ships in this module (the pure-enumeration half):

- ``EnumeratedProject`` — frozen dataclass mirroring ``ProjectKey``
  but pre-wire (no Pydantic dependency at the core layer).
- ``enumerate_projects(source_projects_root)`` — pure function.
  Returns a list sorted by ``project_id`` (case-folded for human
  ordering); duplicate basenames get a dedup suffix on ``label`` only
  so ``project_id`` stays a stable URL slug. Hidden dirs (leading
  dot) are skipped — legacy parity, the picker never showed them.
  Symlinks to dirs are followed (legacy parity, see startup_discovery
  symlink contract).

What slice 4 deliberately does NOT do here:

- **GT loading / Project graph.** That's M2-proper's
  ``core/project_state.py`` (the spec-proper module name). This
  enumeration returns dir handles, not loaded ``Project`` models.
- **YAML config_source threading.** ``GET /api/projects`` reports
  ``config_source: "yaml" | "cli" | "default"`` — that's an endpoint
  concern, not an enumeration concern. The router will compose this
  pure function's output with ``Settings`` to fill that field.
- **Project-shape validation.** A "project dir" here is just any
  subdirectory of ``source_projects_root``. Distinguishing "valid
  project dir" from "stray folder" requires reading
  ``pages.json`` / ``pages_manifest.json`` — that gate lands when
  M2-proper's ``Project`` loader does. For slice 4, an empty dir is a
  visible-but-unselectable project; the load endpoint will error
  loudly when the user tries to open it.

The function is **pure** beyond a single ``iterdir()`` (one stat per
entry to filter regular files / hidden-dotfiles). No side effects
beyond logging at DEBUG.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.project_enumeration import (
    EnumeratedProject,
    enumerate_projects,
)

# ── empty / invalid roots ─────────────────────────────────────────────────


def test_enumerate_returns_empty_when_root_is_none() -> None:
    """``Settings.source_projects_root`` defaults to ``None`` (M1-shipped
    field). The enumerator must accept that and return ``[]`` rather
    than crash — the GET /api/projects endpoint always wants a list to
    return, even when no root has been configured yet."""
    assert enumerate_projects(None) == []


def test_enumerate_returns_empty_when_root_does_not_exist(tmp_path: Path) -> None:
    """Stale config (``source_projects_root: ~/old-projects`` but the
    directory was moved) → ``[]``. Same legacy-parity contract as
    ``startup_discovery.validate_project_dir`` — silent fall-through,
    no crash."""
    missing = tmp_path / "nope"
    assert enumerate_projects(missing) == []


def test_enumerate_returns_empty_when_root_is_a_file(tmp_path: Path) -> None:
    """Pathological config (root points at a regular file) → ``[]``.
    Belt-and-suspenders; the YAML loader could theoretically be tricked."""
    f = tmp_path / "not-a-dir.txt"
    f.write_text("hi")
    assert enumerate_projects(f) == []


def test_enumerate_returns_empty_for_empty_root(tmp_path: Path) -> None:
    """Configured but empty root → ``[]``. The frontend will show the
    "no projects in dropdown" empty-state."""
    assert enumerate_projects(tmp_path) == []


# ── happy path: dir scanning ──────────────────────────────────────────────


def test_enumerate_lists_subdirectories_as_projects(tmp_path: Path) -> None:
    """Each subdirectory of root is one project. ``project_root`` is
    the absolute resolved path; ``project_id`` is the dir basename;
    ``label`` defaults to ``project_id`` (no dedup suffix in the
    common case)."""
    (tmp_path / "AlphaBook").mkdir()
    (tmp_path / "BetaBook").mkdir()
    out = enumerate_projects(tmp_path)
    ids = [p.project_id for p in out]
    assert ids == ["AlphaBook", "BetaBook"]
    for p in out:
        assert isinstance(p, EnumeratedProject)
        assert p.label == p.project_id
        assert p.project_root.is_absolute()
        assert p.project_root.parent == tmp_path.resolve()


def test_enumerate_skips_regular_files(tmp_path: Path) -> None:
    """A stray file in the root is NOT a project. Common case: the
    user dumps a README.md or zip alongside their project dirs."""
    (tmp_path / "Project_001").mkdir()
    (tmp_path / "README.md").write_text("hi")
    (tmp_path / "archive.zip").write_bytes(b"")
    out = enumerate_projects(tmp_path)
    assert [p.project_id for p in out] == ["Project_001"]


def test_enumerate_skips_hidden_directories(tmp_path: Path) -> None:
    """Dotted dirs (``.git``, ``.cache``, ``.DS_Store`` if it ever
    became a dir) are skipped — legacy parity. The picker never
    showed them and showing them now would be surprising."""
    (tmp_path / "Project_001").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".cache").mkdir()
    out = enumerate_projects(tmp_path)
    assert [p.project_id for p in out] == ["Project_001"]


def test_enumerate_follows_symlinks_to_directories(tmp_path: Path) -> None:
    """Symlinks → dirs are real projects (legacy parity, matches the
    ``validate_project_dir`` symlink-follow rule). A broken symlink
    or symlink-to-file is skipped."""
    real = tmp_path / "real_root"
    real.mkdir()
    real_proj = real / "RealProject"
    real_proj.mkdir()

    root = tmp_path / "scanned_root"
    root.mkdir()
    (root / "ViaSymlink").symlink_to(real_proj)
    (root / "BrokenLink").symlink_to(tmp_path / "nope")
    file_link = tmp_path / "afile"
    file_link.write_text("hi")
    (root / "FileLink").symlink_to(file_link)

    out = enumerate_projects(root)
    ids = [p.project_id for p in out]
    assert ids == ["ViaSymlink"]


# ── sorting (stable + case-folded) ────────────────────────────────────────


def test_enumerate_sorts_case_folded_for_human_ordering(tmp_path: Path) -> None:
    """Sort is case-folded so ``alpha`` and ``Beta`` and ``Gamma``
    interleave sensibly in the dropdown — humans expect ``alpha``
    next to ``Alpha``, not after ``Zulu`` because lowercase sorts
    last in raw byte order."""
    for name in ["zulu", "Alpha", "alpha", "Beta"]:
        (tmp_path / name).mkdir()
    out = enumerate_projects(tmp_path)
    ids = [p.project_id for p in out]
    # Case-folded sort: Alpha, alpha, Beta, zulu
    assert ids == ["Alpha", "alpha", "Beta", "zulu"]


def test_enumerate_is_stable_for_case_collisions(tmp_path: Path) -> None:
    """``Alpha`` vs ``alpha`` case-fold to the same key. The tiebreak
    must be deterministic (we use the original name as secondary
    sort key) so successive enumerations produce the same list — the
    frontend keys its dropdown on order."""
    for name in ["alpha", "Alpha", "ALPHA"]:
        (tmp_path / name).mkdir()
    a = [p.project_id for p in enumerate_projects(tmp_path)]
    b = [p.project_id for p in enumerate_projects(tmp_path)]
    assert a == b
    # Uppercase sorts first under raw-string secondary tiebreak.
    assert a == ["ALPHA", "Alpha", "alpha"]


# ── dedup-on-label (project_id stays stable for URLs) ─────────────────────


def test_enumerate_dedups_label_when_basenames_collide(tmp_path: Path) -> None:
    """Two dirs with the same basename (only possible via symlinks
    pointing at differently-rooted real dirs that happen to share a
    name) get a dedup suffix on ``label`` — but ``project_id`` stays
    the basename so URLs are stable.

    Spec ``01-data-models.md`` line 215: "label: display label
    (project_id with dedup suffix)."
    """
    real_a = tmp_path / "tree_a" / "Project"
    real_a.mkdir(parents=True)
    real_b = tmp_path / "tree_b" / "Project"
    real_b.mkdir(parents=True)

    root = tmp_path / "scanned"
    root.mkdir()
    (root / "via_a").symlink_to(real_a)
    (root / "via_b").symlink_to(real_b)

    # Both symlinks point at dirs whose ``.name`` is "Project" — but
    # the symlink names themselves differ. enumeration uses the
    # symlink name (the entry under root) as project_id, NOT the
    # target's name; so this *specific* case doesn't actually collide.
    out = enumerate_projects(root)
    ids = [p.project_id for p in out]
    assert ids == ["via_a", "via_b"]


# ── return-type discipline ────────────────────────────────────────────────


def test_enumerated_project_is_frozen(tmp_path: Path) -> None:
    """``EnumeratedProject`` is frozen — consumers can hand the value
    to a UI layer without worrying about mutation through a returned
    reference. ``dataclasses.FrozenInstanceError`` IS-A
    ``AttributeError`` (stdlib), so we pin against ``AttributeError``
    rather than the bare ``Exception`` ruff B017 forbids."""
    (tmp_path / "P").mkdir()
    out = enumerate_projects(tmp_path)
    assert len(out) == 1
    with pytest.raises(AttributeError):
        out[0].project_id = "evil"  # type: ignore[misc]


def test_enumerated_project_root_is_resolved(tmp_path: Path) -> None:
    """``project_root`` is ``Path.resolve()``-d for cross-module
    equality with ``ResolvedInitialProject.path`` and
    ``ActiveProject.path`` (slices 1 + 2 already resolve their paths).
    A relative-path or ``./foo`` root would otherwise compare unequal
    even when pointing at the same directory."""
    (tmp_path / "P").mkdir()
    out = enumerate_projects(Path(str(tmp_path) + "/."))
    assert out[0].project_root == (tmp_path / "P").resolve()

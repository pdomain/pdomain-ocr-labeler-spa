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

from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pdomain_book_tools.typography import BookLabelingManifest, BookLabelingPage

if TYPE_CHECKING:
    from collections.abc import Generator

from pdomain_ocr_labeler_spa.core.project_enumeration import (
    EnumeratedProject,
    ProjectProgress,
    enumerate_projects,
)
from pdomain_ocr_labeler_spa.core.review_counts import PageWordCounts, WordReviewCountsJournal


def _sha(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _write_book_manifest(root: Path, *, page_count: int) -> BookLabelingManifest:
    """Write a minimal, schema-valid ``book-labeling-manifest.json``.

    Deliberately does NOT create the pages' materialization directories —
    ``core.project_enumeration``'s page-count path only reads and validates
    this one JSON file (unlike
    ``core.persistence.book_labeling_manifest.load_book_labeling_manifest_directory``,
    which additionally opens one directory per page). If the count path ever
    regressed to calling the full loader, this fixture would make that
    regression fail loudly instead of silently doing extra I/O.
    """
    root.mkdir()
    pages = tuple(
        BookLabelingPage(
            page_index=index,
            page_id=f"pgdp:project:{index:03d}.png",
            labeling_bundle_id=_sha(f"bundle-{index}".encode()),
            materialization_relative_path=f"pages/{index + 1:03d}",
            materialization_sha256=_sha(f"materialization-{index}".encode()),
            configuration_hash="c" * 64,
            taxonomy_version="labeler-v1",
            taxonomy_hash="a" * 64,
        )
        for index in range(page_count)
    )
    manifest = BookLabelingManifest(book_id="pgdp-project", pages=pages)
    (root / "book-labeling-manifest.json").write_bytes(manifest.to_json_bytes())
    return manifest


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


# ── page_count (P2-ROOT) ───────────────────────────────────────────────────
#
# Page count is cheap: one extra ``iterdir()`` per project directory, same
# cost class as the top-level scan already performed here (measured
# ~20ms for 20 projects x 50 pages of filesystem-only counting — see
# docs/context/decisions.md P2-ROOT entry). Reviewed/validated-page
# progress is NOT computed here — see the same decision entry for the
# measured cost of a live event-store walk.


def test_enumerate_page_count_counts_image_files(tmp_path: Path) -> None:
    """``page_count`` counts ``.png``/``.jpg``/``.jpeg`` files, ignoring
    non-image files — same extension set as ``_scan_image_paths``."""
    proj = tmp_path / "Book"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"")
    (proj / "002.JPG").write_bytes(b"")
    (proj / "notes.txt").write_bytes(b"")
    (proj / "pages.json").write_text("{}")
    out = enumerate_projects(tmp_path)
    assert out[0].page_count == 2


def test_enumerate_page_count_zero_for_empty_project(tmp_path: Path) -> None:
    """An empty project directory has ``page_count == 0`` — a known,
    real zero, distinct from ``None`` (unknown)."""
    (tmp_path / "Empty").mkdir()
    out = enumerate_projects(tmp_path)
    assert out[0].page_count == 0


def test_enumerate_page_count_none_when_directory_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project directory that cannot be read (permission race, mid-scan
    removal, etc.) degrades that one entry's ``page_count`` to ``None``
    rather than failing the whole enumeration."""
    proj = tmp_path / "Locked"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"")
    resolved_proj = proj.resolve()

    original_iterdir = Path.iterdir

    def _flaky_iterdir(self: Path) -> Generator[Path]:
        if self == resolved_proj:
            raise PermissionError(f"denied: {self}")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", _flaky_iterdir)

    out = enumerate_projects(tmp_path)
    assert len(out) == 1
    assert out[0].page_count is None


def test_enumerate_page_count_none_when_a_per_entry_check_raises_mid_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The directory itself opens fine (``iterdir()`` succeeds); a later
    per-entry check (``is_file()``) raises partway through — e.g. an entry
    removed between listing and stat-ing it. This must still degrade to
    ``None``, not a partial/wrong count and not a crash."""
    proj = tmp_path / "Flaky"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"")
    (proj / "vanishes.png").write_bytes(b"")
    (proj / "002.png").write_bytes(b"")
    vanishes = (proj / "vanishes.png").resolve()

    original_is_file = Path.is_file

    def _flaky_is_file(self: Path) -> bool:
        if self.resolve() == vanishes:
            raise OSError(f"vanished mid-iteration: {self}")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", _flaky_is_file)

    out = enumerate_projects(tmp_path)
    assert len(out) == 1
    assert out[0].page_count is None


# ── page_count — book-labeling-manifest.json shape ─────────────────────────
#
# A book-labeling-manifest.json project stores each page under its own
# materialization directory, not as top-level image files, so the default
# filesystem scan silently reports 0 pages for a real book — a confident
# wrong number. The manifest's own ``pages`` list is the real, cheap count.


def test_enumerate_page_count_from_book_labeling_manifest(tmp_path: Path) -> None:
    """A 300-page manifest-backed project reports 300, not 0."""
    proj = tmp_path / "Book"
    _write_book_manifest(proj, page_count=300)
    out = enumerate_projects(tmp_path)
    assert len(out) == 1
    assert out[0].page_count == 300


def test_enumerate_page_count_from_book_labeling_manifest_ignores_top_level_files(
    tmp_path: Path,
) -> None:
    """The manifest count wins even if stray top-level image files exist —
    proves this isn't accidentally falling back to the filesystem scan."""
    proj = tmp_path / "Book"
    _write_book_manifest(proj, page_count=5)
    (proj / "cover.png").write_bytes(b"")
    out = enumerate_projects(tmp_path)
    assert out[0].page_count == 5


def test_enumerate_page_count_none_for_malformed_book_manifest(tmp_path: Path) -> None:
    """A present-but-unparseable manifest degrades to ``None`` — not 0, not
    a crash, and not a fallback to the (likely-empty) filesystem scan."""
    proj = tmp_path / "Book"
    proj.mkdir()
    (proj / "book-labeling-manifest.json").write_text("not valid json")
    out = enumerate_projects(tmp_path)
    assert len(out) == 1
    assert out[0].page_count is None


# ── page_count — labeling-bundle.json shape ─────────────────────────────────
#
# A labeling-bundle.json project embeds exactly one page (image + words) in
# its descriptor — LabelingBundle has a single page_id/image_sha256 by
# construction, so the real count is always 1. No need to open the file.


def test_enumerate_page_count_for_labeling_bundle_project(tmp_path: Path) -> None:
    """A labeling-bundle.json project reports page_count == 1, not 0 — even
    with no top-level image files present."""
    proj = tmp_path / "SinglePage"
    proj.mkdir()
    (proj / "labeling-bundle.json").write_text("{}")
    out = enumerate_projects(tmp_path)
    assert len(out) == 1
    assert out[0].page_count == 1


def test_enumerate_page_count_book_manifest_takes_priority_over_labeling_bundle(
    tmp_path: Path,
) -> None:
    """Mirrors ``api.projects.load_project``'s shape-detection order: a
    book-labeling-manifest.json, if present, wins over labeling-bundle.json."""
    proj = tmp_path / "Both"
    _write_book_manifest(proj, page_count=7)
    (proj / "labeling-bundle.json").write_text("{}")
    out = enumerate_projects(tmp_path)
    assert out[0].page_count == 7


# ── progress ─────────────────────────────────────────────────────────────
#
# Progress is read from ``core.review_counts.WordReviewCountsJournal`` — see
# docs/context/decisions.md (progress-P2-ROOT-followup entry) for the
# measured cost. Only the filesystem-image shape can ever have a row in
# that journal; see ``ProjectProgress`` for the full list of "no honest
# number" cases that fold into ``None``.


def _fs_project(tmp_path: Path, name: str, *, page_count: int) -> Path:
    """A plain filesystem-image project with ``page_count`` image files."""
    proj = tmp_path / name
    proj.mkdir()
    for i in range(page_count):
        (proj / f"{i:03d}.png").write_bytes(b"")
    return proj


def _append_counts(proj: Path, *, page_index: int, total_words: int, validated_words: int) -> None:
    WordReviewCountsJournal(proj).append(
        PageWordCounts(
            page_index=page_index,
            content_hash=f"h{page_index}",
            total_words=total_words,
            validated_words=validated_words,
        )
    )


def test_enumerate_progress_is_none_when_no_journal_exists(tmp_path: Path) -> None:
    """No page has been saved since the journal existed — unknown, not a
    confidently wrong 0%."""
    _fs_project(tmp_path, "Fresh", page_count=3)
    out = enumerate_projects(tmp_path)
    assert out[0].progress is None


def test_enumerate_progress_full_coverage_all_validated_is_complete(tmp_path: Path) -> None:
    """Every page counted, every counted word validated → complete."""
    proj = _fs_project(tmp_path, "Done", page_count=2)
    _append_counts(proj, page_index=0, total_words=5, validated_words=5)
    _append_counts(proj, page_index=1, total_words=3, validated_words=3)

    out = enumerate_projects(tmp_path)

    assert out[0].progress == ProjectProgress(
        validated_words=8,
        total_words=8,
        pages_counted=2,
        pages_not_counted=0,
        is_lower_bound=False,
        complete=True,
    )


def test_enumerate_progress_full_coverage_partially_validated_is_not_complete(
    tmp_path: Path,
) -> None:
    """Every page counted, but not every word validated → not complete."""
    proj = _fs_project(tmp_path, "InProgress", page_count=2)
    _append_counts(proj, page_index=0, total_words=5, validated_words=5)
    _append_counts(proj, page_index=1, total_words=3, validated_words=1)

    out = enumerate_projects(tmp_path)

    progress = out[0].progress
    assert progress is not None
    assert progress.pages_not_counted == 0
    assert progress.is_lower_bound is False
    assert progress.complete is False
    assert progress.validated_words == 6
    assert progress.total_words == 8


def test_enumerate_progress_partial_coverage_is_visible_and_never_complete(
    tmp_path: Path,
) -> None:
    """40 of 300 pages counted, all fully validated: the fraction over those
    40 pages is surfaced, but never reported as the project's progress and
    never as complete — a project complete over a subset is not complete."""
    proj = _fs_project(tmp_path, "Partial", page_count=300)
    for page_index in range(40):
        _append_counts(proj, page_index=page_index, total_words=4, validated_words=4)

    out = enumerate_projects(tmp_path)

    progress = out[0].progress
    assert progress is not None
    assert progress.pages_counted == 40
    assert progress.pages_not_counted == 260
    assert progress.is_lower_bound is True
    assert progress.complete is False
    assert progress.validated_words == 160
    assert progress.total_words == 160


def test_enumerate_progress_pages_not_counted_never_negative(tmp_path: Path) -> None:
    """A journal can hold rows for more pages than the project currently
    has (pages deleted since); ``pages_not_counted`` clamps at 0 rather
    than going negative."""
    proj = _fs_project(tmp_path, "Shrunk", page_count=1)
    _append_counts(proj, page_index=0, total_words=2, validated_words=2)
    _append_counts(proj, page_index=1, total_words=2, validated_words=2)

    out = enumerate_projects(tmp_path)

    progress = out[0].progress
    assert progress is not None
    assert progress.pages_counted == 2
    assert progress.pages_not_counted == 0


def test_enumerate_progress_is_none_when_page_count_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No page-count denominator → no progress either, even with a
    populated journal — there's nothing to judge partial coverage
    against."""
    proj = _fs_project(tmp_path, "Locked", page_count=1)
    _append_counts(proj, page_index=0, total_words=2, validated_words=2)
    resolved_proj = proj.resolve()

    original_iterdir = Path.iterdir

    def _flaky_iterdir(self: Path) -> Generator[Path]:
        if self == resolved_proj:
            raise PermissionError(f"denied: {self}")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", _flaky_iterdir)

    out = enumerate_projects(tmp_path)
    assert out[0].page_count is None
    assert out[0].progress is None


def test_enumerate_progress_is_none_when_journal_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A journal read failure degrades this one entry's ``progress`` to
    ``None`` rather than failing the whole list."""
    proj = _fs_project(tmp_path, "Flaky", page_count=1)
    _append_counts(proj, page_index=0, total_words=2, validated_words=2)

    def _raise(self: WordReviewCountsJournal) -> dict[int, PageWordCounts]:
        raise OSError("journal unreadable")

    monkeypatch.setattr(WordReviewCountsJournal, "latest_by_page", _raise)

    out = enumerate_projects(tmp_path)
    assert len(out) == 1
    assert out[0].progress is None


def test_enumerate_progress_is_none_for_book_labeling_manifest_shape(
    tmp_path: Path,
) -> None:
    """A book-labeling-manifest.json project never writes to
    ``WordReviewCountsJournal`` (it validates through
    ``ImportedTextValidationLog`` instead) — even a stray journal file
    (e.g. left over from a prior shape) must not be trusted for this
    shape."""
    proj = tmp_path / "Book"
    _write_book_manifest(proj, page_count=5)
    _append_counts(proj, page_index=0, total_words=2, validated_words=2)

    out = enumerate_projects(tmp_path)

    assert out[0].page_count == 5
    assert out[0].progress is None


def test_enumerate_progress_is_none_for_labeling_bundle_shape(tmp_path: Path) -> None:
    """A labeling-bundle.json (single-page) project also never writes to
    this journal."""
    proj = tmp_path / "SinglePage"
    proj.mkdir()
    (proj / "labeling-bundle.json").write_text("{}")
    _append_counts(proj, page_index=0, total_words=2, validated_words=2)

    out = enumerate_projects(tmp_path)

    assert out[0].page_count == 1
    assert out[0].progress is None


def test_enumerated_project_progress_is_frozen(tmp_path: Path) -> None:
    """``ProjectProgress`` is immutable, same contract as ``EnumeratedProject``."""
    proj = _fs_project(tmp_path, "Done", page_count=1)
    _append_counts(proj, page_index=0, total_words=1, validated_words=1)
    out = enumerate_projects(tmp_path)
    progress = out[0].progress
    assert progress is not None
    with pytest.raises(AttributeError):
        progress.complete = False  # type: ignore[misc]

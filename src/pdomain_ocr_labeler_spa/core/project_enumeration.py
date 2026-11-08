"""Project enumeration — scan ``Settings.source_projects_root`` for projects.

Spec authority:

- ``docs/architecture/02-backend.md §5.2`` (line 208-213): ``GET /api/projects``
  reads ``Settings.source_projects_root``, scans for project dirs,
  returns sorted list with the currently selected one.
- ``docs/architecture/02-backend.md §13`` step 2: "Scan for project subdirectories."
- ``docs/architecture/01-data-models.md §2`` lines 212-216: ``ProjectKey`` wire
  shape — ``project_id`` (the loaded project's URL-stable identity),
  ``project_root`` (absolute path), ``label`` (display label = project_id + dedup
  suffix on collision).

This module is **slice 4** of the M2 startup-discovery sequence. It
ships the *pure-enumeration* half: a function that takes a root and
returns a sorted list of dir handles. The future ``GET /api/projects``
endpoint composes this with ``Settings`` (for ``config_source``) and
the ``ActiveProjectCarrier`` (for ``selected``). The full ``Project``
graph (with GT loading, page envelopes, etc.) lands in M2-proper's
``core/project_state.py``.

Design notes:

- **Reads-mostly, with one documented exception.** One ``iterdir()`` plus
  one ``stat()`` per entry for the enumeration walk itself, plus — per
  project, for ``page_count`` (P2-ROOT) — either one more ``iterdir()``
  (filesystem-image shape) or one small JSON file read + parse
  (``book-labeling-manifest.json`` shape); see ``_count_pages``. A parsed
  book manifest also supplies its loaded project identity. Plus, for
  ``progress``, one read of ``WordReviewCountsJournal`` per
  filesystem-image project; see ``_compute_progress``. That journal's
  reader can rewrite (compact) its own file once it has grown past its own
  threshold — see ``core.review_counts.WordReviewCountsJournal`` — so this
  module is no longer purely read-only once ``progress`` is in the
  response; it inherits that one documented mutating side effect, already
  accepted for the same journal read by ``api.review_queue``.
- **Idempotent + stable**. Repeated calls produce the same list (case-
  folded primary sort key, raw-name secondary tiebreak). The frontend
  dropdown keys on order.
- **Legacy parity** on three filtering rules: hidden dirs (leading
  dot) skipped, regular files skipped, broken symlinks / symlink-to-
  files skipped.
- **No project-shape validation**. An empty subdirectory is a
  visible-but-unselectable project here; the future load endpoint
  will error loudly when a user tries to open one. Splitting that
  validation gate into M2-proper keeps this module a pure scan.
- **Uncached, cost scales with total files/pages, not project count**
  (P2-ROOT). Every ``GET /api/projects`` call re-scans every project
  from scratch; there's no memoization across requests. Because
  ``page_count`` for the filesystem-image shape is an ``iterdir()`` per
  project, the aggregate cost of one list call is roughly proportional
  to the total number of files across every discovered project, not to
  the number of projects — one project with 10,000 loose files costs
  about the same as 200 projects of 50 files each. Fine at today's
  scale (measured ~22ms for 20 projects x 50 files — see
  ``docs/context/decisions.md`` P2-ROOT entry); revisit if a source
  root's total file count grows much larger, or if ``GET /api/projects``
  starts getting called often enough for per-call cost to matter (e.g.
  polling).
- **``progress``'s added cost, measured** (docs/context/decisions.md,
  progress-P2-ROOT-followup entry): reading one compacted
  ``word-review-counts.jsonl`` (one row per page, the steady state between
  saves) costs about the same order of magnitude as the ``page_count``
  scan it sits next to — measured ~2.6ms/project for 20 projects of 300
  pages each (~51ms total), ~2.3ms/project at 200 projects (~454ms total).
  A journal sitting right at its own pre-compaction ceiling (up to 10 rows
  per page before ``WordReviewCountsJournal`` compacts it) costs
  substantially more per project — measured ~37ms/project for the same
  20-project fixture at that ceiling (~738ms total) — because every extra
  row is parsed and discarded on every read until the next append triggers
  compaction. Acceptable at today's scale; revisit together with
  ``page_count`` if either the per-call cost or the compaction ceiling
  becomes a problem in practice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pdomain_book_tools.typography import BookLabelingManifest, LabelingBundle
from pydantic import ValidationError

from .review_counts import WordReviewCountsJournal

logger = logging.getLogger(__name__)

_ProjectShape = Literal["book_manifest", "labeling_bundle", "filesystem_images"]

# Image extensions counted for ``page_count`` on the plain filesystem-image
# project shape. Mirrors the set pinned in
# ``core/persistence/ground_truth.py`` and ``core/persistence/project_envelope.py``
# (each module keeps its own copy per the existing per-module convention here —
# see those modules' docstrings).
_IMAGE_EXTS = (".png", ".jpg", ".jpeg")

# Shape-marker filenames. Mirrors the detection order in
# ``api.projects.load_project`` — book-labeling-manifest.json wins over
# labeling-bundle.json, which wins over the plain filesystem-image shape.
_BOOK_MANIFEST_FILENAME = "book-labeling-manifest.json"
_LABELING_BUNDLE_FILENAME = "labeling-bundle.json"


@dataclass(frozen=True)
class ProjectProgress:
    """One project's word-validation progress, from its word-review-counts
    journal (``core.review_counts.WordReviewCountsJournal``).

    ``EnumeratedProject.progress`` is ``None`` — not an instance of this
    type with zeros — whenever there is no honest number to report at all:

    - The project's shape never writes to this journal.
      ``book-labeling-manifest.json`` and ``labeling-bundle.json`` projects
      validate text through ``ImportedTextValidationLog`` instead of
      ``save_page_content_to_store``, so the journal never gets a row for
      them (see ``api.review_queue``'s ``_word_entry``, which draws the same
      line for the same reason).
    - ``page_count`` itself is ``None``. Without a total page count there is
      no denominator to judge partial coverage against.
    - The journal can't be read (permission error, removed mid-scan) —
      degrades this one entry, never the whole list, same as ``page_count``.
    - The journal has no rows at all. A project with no journal has not had
      a page saved since the journal existed — that is not zero progress,
      it is unknown, so it is modeled the same as an unavailable page count
      rather than as 0%.

    When this type IS present, ``pages_counted`` is always greater than
    zero, and ``validated_words`` / ``total_words`` are summed ONLY over
    those counted pages — never inferred for ``pages_not_counted`` pages.
    ``is_lower_bound`` is ``True`` whenever ``pages_not_counted > 0``: the
    percentage this implies is a lower bound on the whole project's true
    progress, not the project's real progress, because an uncounted page
    could be anywhere from untouched to fully validated.

    ``complete`` defines "complete" as every page counted
    (``pages_not_counted == 0``) AND every counted word validated AND at
    least one word counted — never ``True`` over a subset. A project
    complete over 40 of its 300 pages is not complete.
    """

    validated_words: int
    total_words: int
    pages_counted: int
    pages_not_counted: int
    is_lower_bound: bool
    complete: bool


@dataclass(frozen=True)
class EnumeratedProject:
    """Frozen handle to one project found by ``enumerate_projects``.

    Mirrors the wire-side ``ProjectKey`` (spec §2 lines 212-216) but
    pre-Pydantic so the core layer doesn't depend on the wire schema:

    - ``project_id``: the loaded project's stable URL slug. Plain
      filesystem projects use the directory basename. Prepared books
      and standalone PGDP bundles use the source identity that their
      loaders assign, so navigation targets the loaded project. A
      malformed descriptor falls back to the basename.
    - ``project_root``: absolute, ``Path.resolve()``-d directory. Same
      canonicalization as ``ResolvedInitialProject.path`` (slice 1)
      and ``ActiveProject.path`` (slice 2) so cross-module equality
      just works.
    - ``label``: human-readable display name. Defaults to
      ``project_id``; gets a dedup suffix on case-insensitive project
      identity collisions (spec §2 line 215). Exact identity collisions
      are not listed, because their ID-only actions would be ambiguous.
    - ``page_count``: the project's real page count, or ``None`` when it
      can't be determined cheaply — P2-ROOT
      (``docs/issues/2026-07-21-project-list-metadata-filters-noop.md``).
      This repo supports three project shapes (mirrors the detection
      order in ``api.projects.load_project``), and each has a different
      cheap source of truth — see ``_count_pages`` for the per-shape
      logic:

      1. ``book-labeling-manifest.json`` present: the manifest's own
         ``pages`` list length. A book stores each page under its own
         materialization directory, not as top-level image files, so
         counting top-level files would silently report 0 for a real
         book — a confident wrong number, worse than "unknown".
      2. ``labeling-bundle.json`` present: always 1 — this shape embeds
         exactly one page (image + words) in its descriptor by
         construction (single ``page_id`` / ``image_sha256``).
      3. Neither present: count of ``.png``/``.jpg``/``.jpeg`` files
         directly under ``project_root`` (one extra ``iterdir()`` per
         project, same cost class as the top-level enumeration scan
         already performed by this module).

      Cost: measured on this repo's dev fixtures at ~1ms for 20
      filesystem-image projects of 50 files each — see
      ``docs/context/decisions.md`` P2-ROOT entry for the full
      measurement.
    - ``progress``: word-validation progress, or ``None`` when there is no
      honest number to report — see ``ProjectProgress`` for exactly which
      cases fold into ``None``. Read from
      ``core.review_counts.WordReviewCountsJournal``, the per-page counts
      journal that made this affordable where the original P2-ROOT
      measurement (a live per-page event-store walk, ~200ms for a
      20-project fixture) ruled it out. See ``docs/context/decisions.md``
      for the follow-up measurement of this journal-based read.
    """

    project_id: str
    project_root: Path
    label: str
    page_count: int | None
    progress: ProjectProgress | None


def enumerate_projects(source_projects_root: Path | None) -> list[EnumeratedProject]:
    """Return sorted ``EnumeratedProject`` list under ``source_projects_root``.

    Returns ``[]`` (not raises) for every "no projects to enumerate"
    branch:

    - ``source_projects_root`` is ``None`` (default Settings value).
    - The path doesn't exist (stale config; user moved their root).
    - The path is a regular file (pathological config).
    - The path is empty (configured but no projects yet).

    Filtering rules (per dir entry):

    - Regular files: skipped.
    - Hidden dirs (leading ``.``): skipped — legacy parity, the
      picker never showed ``.git`` / ``.cache``.
    - Symlinks → dirs: included (legacy + slice-1 parity on symlink
      handling).
    - Broken symlinks / symlinks → files: skipped (``is_dir()``
      returns False, which catches both).

    Sort order:

    - Primary: ``casefold()`` of ``project_id`` (case-insensitive
      human ordering — ``alpha`` next to ``Alpha``, not at the end).
    - Secondary: ``project_id`` raw (for case-collision stability;
      uppercase sorts first under raw byte order, which is fine
      because the order just has to be deterministic, not aesthetic).

    Exact duplicate project identities are excluded. The API has ID-only
    routes, including delete, so listing either duplicate would make that
    action target-dependent. Distinct identities that only collide after
    ``casefold()`` remain listed and get suffixed labels ``"<id> (2)"``,
    ``"<id> (3)"``, etc. ``project_id`` itself is NOT suffixed because
    routes use the canonical loaded identity.

    Args:
        source_projects_root: The configured root, or ``None``.

    Returns:
        A list of ``EnumeratedProject``, possibly empty, sorted as
        described.
    """
    if source_projects_root is None:
        logger.debug("enumerate_projects: no source_projects_root configured.")
        return []

    if not source_projects_root.is_dir():
        # Covers missing path, regular file, broken symlink — all the
        # "stale config" branches return empty.
        logger.debug(
            "enumerate_projects: %s is not a directory; returning [].",
            source_projects_root,
        )
        return []

    resolved_root = source_projects_root.resolve()
    entries: list[EnumeratedProject] = []
    for entry in resolved_root.iterdir():
        # Skip hidden + non-dir (regular files, broken symlinks,
        # symlinks-to-files) in one ``is_dir()`` call. ``is_dir()``
        # follows symlinks by default; for broken symlinks it
        # returns False; for symlinks-to-files it also returns False.
        if entry.name.startswith("."):
            continue
        if not entry.is_dir():
            continue
        # ``project_root`` = the resolved absolute path (follows
        # symlinks so consumers get a real on-disk dir).
        project_root = entry.resolve()
        # Detected once and shared: ``page_count`` needs it to pick a
        # counting strategy, ``progress`` needs it to know whether
        # ``WordReviewCountsJournal`` can answer anything at all for this
        # project (see ``ProjectProgress``).
        shape = _detect_shape(project_root)
        manifest = _read_book_manifest(project_root) if shape == "book_manifest" else None
        project_id = _project_id(
            project_root,
            shape=shape,
            fallback=entry.name,
            manifest=manifest,
        )
        page_count = _count_pages(project_root, shape=shape, manifest=manifest)
        entries.append(
            EnumeratedProject(
                project_id=project_id,
                project_root=project_root,
                label=project_id,
                page_count=page_count,
                progress=_compute_progress(project_root, shape=shape, page_count=page_count),
            )
        )

    # Sort: case-folded primary, raw-name secondary tiebreak.
    entries.sort(key=lambda p: (p.project_id.casefold(), p.project_id))

    exact_duplicates = _exact_duplicate_project_ids(entries)
    if exact_duplicates:
        duplicate_roots = [
            str(project.project_root) for project in entries if project.project_id in exact_duplicates
        ]
        logger.warning(
            "enumerate_projects: excluding duplicate loaded identities %s at roots %s",
            ", ".join(sorted(exact_duplicates)),
            ", ".join(duplicate_roots),
        )
        entries = [project for project in entries if project.project_id not in exact_duplicates]

    # Dedup-on-label: any case-folded project identity that appears more than
    # once gets a 1-based suffix ``" (n)"`` on its label. ``project_id``
    # is NOT touched — URLs key on the canonical loaded identity.
    seen: dict[str, int] = {}
    deduped: list[EnumeratedProject] = []
    for p in entries:
        key = p.project_id.casefold()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            deduped.append(
                EnumeratedProject(
                    project_id=p.project_id,
                    project_root=p.project_root,
                    label=f"{p.label} ({seen[key]})",
                    page_count=p.page_count,
                    progress=p.progress,
                )
            )
        else:
            deduped.append(p)

    logger.debug(
        "enumerate_projects: scanned %s, found %d project(s).",
        resolved_root,
        len(deduped),
    )
    return deduped


def _detect_shape(project_root: Path) -> _ProjectShape | None:
    """Which of the three project shapes ``project_root`` is, or ``None`` on
    I/O failure.

    Mirrors the detection order in ``api.projects.load_project``:
    ``book-labeling-manifest.json`` wins over ``labeling-bundle.json``,
    which wins over the plain filesystem-image shape. Shared by
    ``_count_pages`` (which needs the shape to pick a counting strategy)
    and ``_compute_progress`` (which needs it to know whether
    ``WordReviewCountsJournal`` can answer anything for this project at
    all — see ``ProjectProgress``).
    """
    try:
        if (project_root / _BOOK_MANIFEST_FILENAME).is_file():
            return "book_manifest"
        if (project_root / _LABELING_BUNDLE_FILENAME).is_file():
            return "labeling_bundle"
    except OSError:
        logger.debug("enumerate_projects: shape detection failed for %s", project_root, exc_info=True)
        return None
    return "filesystem_images"


def _count_pages(
    project_root: Path,
    *,
    shape: _ProjectShape | None,
    manifest: BookLabelingManifest | None,
) -> int | None:
    """Return this project's page count, or ``None`` when it can't be
    determined cheaply.

    Reads each shape's cheapest real source of truth:

    1. ``book_manifest`` → ``len(manifest.pages)``. Only this one JSON file
       is read and parsed — NOT ``load_book_labeling_manifest_directory``,
       which additionally opens one directory per page and hashes every
       match-graph file (O(pages) filesystem opens that would defeat the
       point of a cheap list scan).
    2. ``labeling_bundle`` → always 1 (this shape is a single-page format
       by construction; no need to open the file).
    3. ``filesystem_images`` → count of top-level image files.
    4. ``None`` (shape detection itself failed) → ``None``.

    Any failure along the way (unreadable directory, malformed manifest
    JSON) degrades to ``None`` — "unknown" — rather than a wrong number
    (e.g. 0 for a 300-page book whose pages live in per-page
    materialization directories, not as top-level files) or a crash.
    """
    if shape is None:
        return None
    if shape == "book_manifest":
        return None if manifest is None else len(manifest.pages)
    if shape == "labeling_bundle":
        return 1
    return _count_image_files(project_root)


def _project_id(
    project_root: Path,
    *,
    shape: _ProjectShape | None,
    fallback: str,
    manifest: BookLabelingManifest | None,
) -> str:
    """Return the URL identity that the matching loader will assign.

    Prepared books and standalone labeling bundles can live in opaque working
    directories. Their loaders use the source identifier inside the manifest
    or bundle, so the project list must use that same identifier. Invalid or
    unreadable descriptors retain the directory basename: listing remains
    resilient and loading still reports the descriptor error.
    """
    if shape == "book_manifest":
        return _book_manifest_project_id(manifest, fallback=fallback)
    if shape == "labeling_bundle":
        return _labeling_bundle_project_id(project_root / _LABELING_BUNDLE_FILENAME, fallback=fallback)
    return fallback


def _book_manifest_project_id(manifest: BookLabelingManifest | None, *, fallback: str) -> str:
    """Return a prepared book's canonical project ID, or ``fallback``."""
    if manifest is None:
        return fallback
    project_id = manifest.book_id.split(":")[-1]
    return project_id or fallback


def _read_book_manifest(project_root: Path) -> BookLabelingManifest | None:
    """Read and validate a prepared-book manifest once for list metadata."""
    manifest_path = project_root / _BOOK_MANIFEST_FILENAME
    try:
        return BookLabelingManifest.model_validate_json(manifest_path.read_bytes())
    except (OSError, ValidationError, ValueError):
        logger.debug("enumerate_projects: metadata unavailable for manifest %s", manifest_path, exc_info=True)
        return None


def _labeling_bundle_project_id(bundle_path: Path, *, fallback: str) -> str:
    """Read the canonical project id from a standalone labeling bundle."""
    try:
        bundle = LabelingBundle.model_validate_json(bundle_path.read_bytes())
    except (OSError, ValidationError, ValueError):
        logger.debug("enumerate_projects: project id unavailable for bundle %s", bundle_path, exc_info=True)
        return fallback
    page_id_parts = bundle.page_id.split(":")
    if len(page_id_parts) == 3 and page_id_parts[0] == "pgdp" and page_id_parts[1]:
        return page_id_parts[1]
    return fallback


def _compute_progress(
    project_root: Path, *, shape: _ProjectShape | None, page_count: int | None
) -> ProjectProgress | None:
    """This project's word-validation progress, or ``None`` — see
    ``ProjectProgress`` for exactly which cases fold into ``None``.

    Only the ``filesystem_images`` shape ever has rows in
    ``WordReviewCountsJournal``: a ``book_manifest`` or ``labeling_bundle``
    project validates text through ``ImportedTextValidationLog`` instead of
    ``save_page_content_to_store``, so the journal never gets a row for it
    (``api.review_queue``'s ``_word_entry`` draws the same line for the
    same reason). Without ``page_count`` there is also no denominator to
    judge partial coverage against, so an unknown ``page_count`` forces
    ``None`` here too, even for a ``filesystem_images`` project.
    """
    if page_count is None or shape != "filesystem_images":
        return None
    try:
        latest = WordReviewCountsJournal(project_root).latest_by_page()
    except OSError:
        logger.debug("enumerate_projects: progress unavailable for %s", project_root, exc_info=True)
        return None

    pages_counted = len(latest)
    if pages_counted == 0:
        # No page has been saved since the journal existed — unknown, not
        # zero progress (see ``ProjectProgress``).
        return None

    total_words = sum(counts.total_words for counts in latest.values())
    validated_words = sum(counts.validated_words for counts in latest.values())
    # ``max(..., 0)``: a project whose page count shrank since some of
    # these rows were written (pages deleted) could otherwise go negative.
    pages_not_counted = max(page_count - pages_counted, 0)

    return ProjectProgress(
        validated_words=validated_words,
        total_words=total_words,
        pages_counted=pages_counted,
        pages_not_counted=pages_not_counted,
        is_lower_bound=pages_not_counted > 0,
        complete=pages_not_counted == 0 and total_words > 0 and validated_words == total_words,
    )


def _exact_duplicate_project_ids(projects: list[EnumeratedProject]) -> set[str]:
    """Return loaded identities shared by more than one project root.

    ``DELETE /api/projects/{project_id}`` identifies its target only by ID.
    Keeping exact duplicates in the list would therefore make a card's
    destructive action depend on enumeration order.
    """
    seen: set[str] = set()
    duplicates: set[str] = set()
    for project in projects:
        if project.project_id in seen:
            duplicates.add(project.project_id)
        else:
            seen.add(project.project_id)
    return duplicates


def _count_image_files(project_root: Path) -> int | None:
    """Count image files directly under ``project_root``, or ``None`` on error.

    Cheap: one ``iterdir()`` plus a suffix check per file, the same cost
    class as the enumeration scan above. Any ``OSError`` (permission
    denied, directory removed between the caller's ``is_dir()`` check and
    this call, a per-entry stat racing a concurrent delete, etc.) degrades
    to ``None`` — "unknown" — rather than raising or returning a partial
    count, so one unreadable project never fails the whole list.
    """
    try:
        return sum(1 for f in project_root.iterdir() if f.is_file() and f.suffix.lower() in _IMAGE_EXTS)
    except OSError:
        logger.debug("enumerate_projects: page_count unavailable for %s", project_root, exc_info=True)
        return None


__all__ = [
    "EnumeratedProject",
    "ProjectProgress",
    "enumerate_projects",
]

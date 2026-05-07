"""Project enumeration — scan ``Settings.source_projects_root`` for projects.

Spec authority:

- ``specs/02-backend.md §5.2`` (line 208-213): ``GET /api/projects``
  reads ``Settings.source_projects_root``, scans for project dirs,
  returns sorted list with the currently selected one.
- ``specs/02-backend.md §13`` step 2: "Scan for project subdirectories."
- ``specs/01-data-models.md §2`` lines 212-216: ``ProjectKey`` wire
  shape — ``project_id`` (basename, URL-stable), ``project_root``
  (absolute path), ``label`` (display label = project_id + dedup
  suffix on collision).

This module is **slice 4** of the M2 startup-discovery sequence. It
ships the *pure-enumeration* half: a function that takes a root and
returns a sorted list of dir handles. The future ``GET /api/projects``
endpoint composes this with ``Settings`` (for ``config_source``) and
the ``ActiveProjectCarrier`` (for ``selected``). The full ``Project``
graph (with GT loading, page envelopes, etc.) lands in M2-proper's
``core/project_state.py``.

Design notes:

- **Pure**. No filesystem mutation. Only reads: one ``iterdir()`` plus
  one ``stat()`` per entry (via ``is_dir`` / ``is_symlink``).
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
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnumeratedProject:
    """Frozen handle to one project found by ``enumerate_projects``.

    Three fields, mirroring the wire-side ``ProjectKey`` (spec §2
    lines 212-216) but pre-Pydantic so the core layer doesn't depend
    on the wire schema:

    - ``project_id``: the directory basename. Used as a stable URL
      slug — the future ``/projects/{project_id}`` route keys on this.
      Symlink case: ``project_id`` is the symlink's *own* name (the
      entry under root), not the target's name. That keeps the
      identifier stable when the operator renames the symlink to
      disambiguate.
    - ``project_root``: absolute, ``Path.resolve()``-d directory. Same
      canonicalization as ``ResolvedInitialProject.path`` (slice 1)
      and ``ActiveProject.path`` (slice 2) so cross-module equality
      just works.
    - ``label``: human-readable display name. Defaults to
      ``project_id``; gets a dedup suffix on basename collisions
      (spec §2 line 215).
    """

    project_id: str
    project_root: Path
    label: str


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

    Dedup-on-label rule (spec §2 line 215): two entries with the same
    case-folded ``project_id`` get suffixed labels ``"<id> (2)"``,
    ``"<id> (3)"``, etc. ``project_id`` itself is NOT suffixed —
    URLs stay keyed on the original basename, which is fine because
    raw-name collisions are only possible on case-insensitive
    filesystems and the secondary sort already disambiguates them.

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
        # ``project_id`` = the basename of the entry under root (NOT
        # the symlink target's basename — keep identifiers stable
        # across operator-rename of symlinks).
        project_id = entry.name
        # ``project_root`` = the resolved absolute path (follows
        # symlinks so consumers get a real on-disk dir).
        project_root = entry.resolve()
        entries.append(
            EnumeratedProject(
                project_id=project_id,
                project_root=project_root,
                label=project_id,
            )
        )

    # Sort: case-folded primary, raw-name secondary tiebreak.
    entries.sort(key=lambda p: (p.project_id.casefold(), p.project_id))

    # Dedup-on-label: any case-folded basename that appears more than
    # once gets a 1-based suffix ``" (n)"`` on its label. ``project_id``
    # is NOT touched — URLs key on the basename and stay stable.
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


__all__ = [
    "EnumeratedProject",
    "enumerate_projects",
]

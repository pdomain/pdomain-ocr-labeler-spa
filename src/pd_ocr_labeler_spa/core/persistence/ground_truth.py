"""Read ``pages.json`` / ``pages_manifest.json`` ground-truth files.

Spec authority:

- ``specs/09-persistence.md §1`` — source-lane GT files (read-only to
  the labeler) live alongside the page images in
  ``<source_projects_root>/<project>/pages.json`` (or the multi-source
  ``pages_manifest.json``).
- ``specs/01-data-models.md §1`` line 33 — ``Project.ground_truth_map``
  is the post-load shape (``dict[str, str]`` keyed by image filename).
- ``specs/16-milestones.md`` line 159 — slice 5 scope.

D-003 byte-compat with legacy:

The legacy reader is
``pd-ocr-labeler/pd_ocr_labeler/operations/persistence/project_operations.py``
``load_ground_truth_from_directory`` (line 343). Both binaries share the
source lane (read-only), so this module is the **byte-compatible
re-implementation** — given the same on-disk inputs, the resulting
``ground_truth_map`` must be identical to what the legacy computes.

Why re-implement instead of import: the legacy operation lives in a
package that pulls in NiceGUI dependencies via sibling modules; the GT
loader itself is pure-functional. A local copy keeps the SPA's
backend free of UI-framework imports.

Reading rules (mirrored from legacy):

1. ``pages_manifest.json`` (if present + parseable) wins.
2. Manifest sources are merged in declaration order (later wins on
   collision).
3. ``offset`` is applied to the **numeric stem** of each key:
   ``"042.png"`` with offset 100 → ``"142.png"`` (zero-pad-3 format).
   Non-numeric keys pass through unchanged.
4. Single-file mode: ``pages.json`` parsed as ``dict[str, str]``.
5. Per-entry normalization via ``PGDPResults.processed_page_text``
   (markup, diacritics, dashes, quotes, proofer notes).
6. Lowercase-key alias + extension-less alias added via
   ``setdefault`` (so callers can lookup by canonical filename even
   when GT keys differ in case or omit the extension).
7. Any failure (missing file, malformed JSON, wrong root type) →
   warn + return ``{}``. A project with broken GT still loads.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pd_book_tools.pgdp.pgdp_results import PGDPResults

logger = logging.getLogger(__name__)

# Mirror legacy ``pd_ocr_labeler/constants.py:15``. Inlined so the SPA
# core/persistence package doesn't reach into the legacy package; the
# constant is small and stable.
_IMAGE_EXTS = (".png", ".jpg", ".jpeg")

# Legacy filename, pinned by ``test_pages_manifest_constant_matches_legacy``.
PAGES_MANIFEST_FILENAME = "pages_manifest.json"
_PAGES_JSON_FILENAME = "pages.json"

# Legacy regex from ``project_operations.py:483``. Matches a key whose
# stem is purely numeric, with optional extension (the optional group
# captures the extension including the dot, e.g. ``.png``).
_NUMERIC_STEM_RE = re.compile(r"^(\d+)(\.\w+)?$")


__all__ = [
    "PAGES_MANIFEST_FILENAME",
    "find_ground_truth_text",
    "load_ground_truth_from_directory",
]


def find_ground_truth_text(name: str, ground_truth_map: dict[str, str]) -> str | None:
    """Variant lookup of GT text for a page filename.

    Legacy parity: ``pd-ocr-labeler/pd_ocr_labeler/state/project_state.py``
    lines 1674-1722 (``ProjectState.find_ground_truth_text``). The
    ``ground_truth_map`` is the post-normalization dict produced by
    :func:`load_ground_truth_from_directory`, which already adds
    lowercase + extension-tolerant aliases via ``setdefault``. This
    helper still tries multiple variants in priority order so a caller
    holding an arbitrary path-or-filename can find the entry without
    pre-normalising.

    Variants attempted (first hit wins):

    1. ``name`` verbatim (after ``.strip()``)
    2. ``name.lower()``
    3. basename of ``name`` (Pathlib ``.name``)
    4. basename lowercase
    5. (if basename has a ``.``) bare stem
    6. bare stem lowercase

    Returns ``None`` if ``name`` is empty/whitespace, or no variant
    matches. Never raises.
    """
    if not name:
        return None
    normalized_name = str(name).strip()
    if not normalized_name:
        return None

    basename = Path(normalized_name).name
    candidates: list[str] = [
        normalized_name,
        normalized_name.lower(),
        basename,
        basename.lower(),
    ]
    if "." in basename:
        base = basename.rsplit(".", 1)[0]
        candidates.append(base)
        candidates.append(base.lower())

    seen: set[str] = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        if c in ground_truth_map:
            return ground_truth_map[c]
    return None


def load_ground_truth_from_directory(directory: Path) -> dict[str, str]:
    """Load + merge GT entries from a project directory.

    Manifest-first; falls back to single-file ``pages.json`` if the
    manifest is missing OR the manifest fails to parse (a typo'd
    manifest shouldn't shadow a perfectly-good single-file GT).

    Returns an empty dict when no GT file is present — a valid project
    state. The labeler renders empty GT cells; users can add GT later
    by dropping a ``pages.json`` next to the images.
    """
    manifest_path = directory / PAGES_MANIFEST_FILENAME
    if manifest_path.exists():
        try:
            merged = _load_from_manifest(manifest_path)
            logger.info(
                "Loaded %d ground-truth entries from manifest %s",
                len(merged),
                manifest_path,
            )
            return merged
        except Exception as exc:  # noqa: BLE001  (we WANT to fall through on any manifest error)
            logger.warning(
                "Failed to load %s (%s); falling back to %s: %s",
                PAGES_MANIFEST_FILENAME,
                manifest_path,
                _PAGES_JSON_FILENAME,
                exc,
            )

    pages_json = directory / _PAGES_JSON_FILENAME
    if not pages_json.exists():
        logger.info("No ground-truth file found in %s", directory)
        return {}
    try:
        raw = json.loads(pages_json.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse %s: %s", pages_json, exc)
        return {}
    if not isinstance(raw, dict):
        logger.warning("Root of %s is not a JSON object: %r", pages_json, type(raw).__name__)
        return {}
    norm = _normalize_entries(raw)
    logger.info("Loaded %d ground-truth entries from %s", len(norm), pages_json)
    return norm


# ── manifest mode ─────────────────────────────────────────────────────────


def _load_from_manifest(manifest_path: Path) -> dict[str, str]:
    """Parse + merge a ``pages_manifest.json``.

    Manifest schema (mirrored from legacy ``project_operations.py:400-409``)::

        {
            "schema": "pd_ocr_labeler.pages_manifest",   # informational
            "version": "1.0",                            # informational
            "sources": [
                {"file": "pages_r1.json", "offset": 0},
                {"file": "pages_r2.json", "offset": 100}
            ]
        }

    Per-source: read JSON, apply offset to numeric keys, normalize,
    merge into the running result with ``dict.update`` (last write wins).

    Raises ``ValueError`` (caught by caller and triggers fallback) when
    the root isn't a JSON object or ``sources`` isn't a list — those
    are structural errors a user can't have produced from a sensible
    edit, and warrant the fallback path.
    """
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{PAGES_MANIFEST_FILENAME} must be a JSON object")

    sources = raw.get("sources")
    if not isinstance(sources, list):
        raise ValueError(f"{PAGES_MANIFEST_FILENAME} must have a 'sources' list")

    base_dir = manifest_path.parent
    merged: dict[str, str] = {}

    for entry in sources:
        if not isinstance(entry, dict):
            logger.warning("Skipping invalid manifest entry: %r", entry)
            continue

        file_name = entry.get("file")
        if not isinstance(file_name, str) or not file_name:
            logger.warning("Skipping manifest entry with missing 'file': %r", entry)
            continue

        # Permissive int-coercion mirrors legacy ``int(entry.get("offset", 0))``
        # — a string offset like "100" is accepted; bad values raise here and
        # are caught by the outer try/except → fallback path.
        offset = int(entry.get("offset", 0))

        source_path = base_dir / file_name
        if not source_path.exists():
            logger.warning("Manifest source not found: %s", source_path)
            continue

        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse manifest source %s: %s", source_path, exc)
            continue

        if not isinstance(source_data, dict):
            logger.warning("Manifest source %s is not a JSON object; skipping", source_path)
            continue

        # Apply offset BEFORE normalization so the offset transform sees
        # the raw stem. Normalization's lowercase-alias + extension-alias
        # rules then operate on the post-offset key set.
        if offset != 0:
            source_data = _apply_page_index_offset(source_data, offset)

        partial = _normalize_entries(source_data)
        merged.update(partial)
        logger.debug("Merged %d entries from %s (offset=%d)", len(partial), source_path.name, offset)

    return merged


def _apply_page_index_offset(data: Mapping[str, Any], offset: int) -> dict[str, Any]:
    """Return a new dict with numeric-stem keys shifted by ``offset``.

    Mirrors legacy ``project_operations.py:485-517``. Non-numeric keys
    pass through verbatim; numeric stems get re-formatted with %03d
    zero-padding (so ``42`` + offset 100 → ``"142"``, not ``"00142"``).

    The output preserves the original extension (or absence thereof):
    ``"042.png"`` with offset 100 → ``"142.png"``;  ``"042"`` with
    offset 100 → ``"142"``.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            result[key] = value
            continue
        m = _NUMERIC_STEM_RE.match(key)
        if m:
            new_num = int(m.group(1)) + offset
            ext = m.group(2) or ""
            new_key = f"{new_num:03d}{ext}"
            result[new_key] = value
        else:
            result[key] = value
    return result


# ── normalization (the alias + PGDP-text-clean step) ──────────────────────


def _normalize_entries(data: Mapping[str, Any]) -> dict[str, str]:
    """Run every entry through PGDP normalization + alias generation.

    Three transforms per entry, in this order:

    1. Coerce non-string values to strings (``None`` short-circuits).
       Legacy ``project_operations.py:288-294``.
    2. Run the value through ``PGDPResults(key, value).processed_page_text``
       to convert PGDP markup (footnote brackets, ASCII dashes, etc.)
       into OCR-comparable Unicode. Legacy line 296.
    3. Register aliases via ``setdefault``:
       - lowercase form of the key (case-insensitive lookup).
       - if the key has no ``.``, register an alias for each of
         ``.png``/``.jpg``/``.jpeg`` (extension-tolerant lookup).

    ``setdefault`` (NOT direct assignment) means later entries don't
    overwrite earlier ones via aliases — only the original key write
    is unconditional.
    """
    normalized: dict[str, str] = {}

    for key, value in data.items():
        if not isinstance(key, str):
            continue

        text_value: str | None
        if isinstance(value, str):
            text_value = value
        elif value is None:
            continue
        else:
            text_value = str(value)

        # PGDP normalization. The result is the OCR-comparable form of
        # the proofreader's text — diacritics + special chars resolved.
        text_value = PGDPResults(key, text_value).processed_page_text

        # Original key always wins.
        normalized[key] = text_value

        # Lowercase alias.
        lower_key = key.lower()
        normalized.setdefault(lower_key, text_value)

        # Extension-less stem → register aliases for all three image exts.
        if "." not in key:
            for ext in _IMAGE_EXTS:
                normalized.setdefault(f"{key}{ext}", text_value)
                normalized.setdefault(f"{key}{ext}".lower(), text_value)

    return normalized

"""Export job handler — DocTR training dataset export pipeline.

Spec authority:
- ``docs/specs/2026-05-12-export-design.md``
- Issue #226 acceptance criteria.

Handler entry-point: ``handle_export(runner, job)`` — registered in
``core/jobs/runner._HANDLERS["export"]``.

Output layout::

    <data_root>/doctr-export/<project_id>/<subfolder>/detection/
    <data_root>/doctr-export/<project_id>/<subfolder>/recognition/

``<subfolder>`` is ``"all"`` when no style filter is applied, or the
style label otherwise (e.g. ``"italics"``).  Multiple style filters
produce multiple subfolders in one run.

When recognition export runs, ``recognition/glyph_features.json`` sits next
to ``recognition/labels.json`` — the glyph-feature sidecar
``pdomain-ocr-training`` reads to slice CER/WER by ligature/long-s/swash
presence.  Only written when at least one exported word carries reviewed
glyph annotations; see ``glyph_sidecar.py``.

Cancel support: the handler checks ``runner.is_cancelled(job_id)`` (the
shared cancel-check helper on ``JobRunner``) between page iterations.  On
cancellation it ``shutil.rmtree``s the partial output dir and reports a
final progress message naming how many pages were exported before the
cancel landed.  The runner's ``request_cancel`` already emitted the
terminal CANCELLED SSE event and closed the broker; the extra
``update_progress`` call here only updates the in-memory ``Job.message``
for HTTP pollers — it does not reopen the SSE stream, so it also queues a
``NotificationKind.INFO`` toast (when a queue is wired) as the channel a
live client actually still has open.

### DocTRExportOperations

``DocTRExportOperations`` is an SPA-specific adaptation of the legacy
``pd_ocr_labeler.operations.export.doctr_export.DocTRExportOperations``.
Key differences:

- Reads pages from the **labeled lane** (``<data_root>/labeled-projects/
  <project_id>/<project_id>_<page:03d>.json``) via
  ``LaneResolver.load_page_from_disk()``.
- Uses ``UserPageEnvelope`` (parse_envelope) for envelope-format files;
  falls back to the legacy ``{"pages": [...]}`` shape.
- Runs as an async coroutine (yields control between pages) so the event
  loop stays alive for SSE and cancel checks.

### WordFilter

``WordFilter`` mirrors the legacy ``pd_ocr_labeler.operations.export.
doctr_export.WordFilter`` exactly (frozenset, matches method).

### Page resolution (store-first — PARITY-GAP P1.2)

Pages are resolved from the **event store** head (``ProjectAggregate``
index→page_id map, head provenance content blob — the content Save wrote
via ``save_page_content_to_store``), with the legacy
``<data_root>/labeled-projects/<project_id>/`` envelope as a per-page
fallback ONLY when no store head exists for that index (C56 read-compat).
A page is considered validated when every word carries ``"validated"`` in
its ``word_labels`` list.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypedDict

from pdomain_book_contracts.layout.text_hints import LayoutStructure
from pdomain_book_tools.geometry.bounding_box import BoundingBox
from pdomain_book_tools.ocr.page import Page
from pdomain_book_tools.ocr.word import Word
from pydantic import BaseModel, ConfigDict, Field

from ...notifications import NotificationKind, NotificationQueue
from ...page_content_snapshot import restore_page_content, snapshot_page_content
from ...persistence.atomic import write_json_atomic
from ...project_state import ProjectState
from ...regions.block_adapter import confirmed_regions_from_page
from ...regions.layout_structure import refresh_structure_signatures

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WordFilter (mirrors legacy pd_ocr_labeler.operations.export.doctr_export)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WordFilter:
    """Predicate for selecting words in a labeled export.

    An empty filter (default) matches **all** words.
    Spec: ``docs/specs/2026-05-12-export-design.md §Backend shape``.
    """

    style_labels: frozenset[str] = field(default_factory=frozenset)
    word_components: frozenset[str] = field(default_factory=frozenset)

    def matches(self, word: Any) -> bool:
        if not self.style_labels and not self.word_components:
            return True

        if self.style_labels:
            word_styles = set(getattr(word, "text_style_labels", None) or [])
            if not word_styles & self.style_labels:
                return False

        if self.word_components:
            word_comps = set(getattr(word, "word_components", None) or [])
            if not word_comps & self.word_components:
                return False

        return True


# ---------------------------------------------------------------------------
# Helpers: envelope loading + page validation
# ---------------------------------------------------------------------------


def _load_page_from_envelope_file(json_path: Path) -> Page | None:
    """Load a ``Page`` from an envelope (or legacy pages-dict) JSON file.

    Returns ``None`` on any error.  Import of ``pdomain_book_tools`` is deferred
    to keep this module importable even in test environments that stub
    ``pdomain_book_tools``.
    """
    try:
        data = _object_dict(_json_value(json_path.read_text(encoding="utf-8")), "page file")

        # Try envelope format first.
        schema = _object_dict(data.get("schema", {}), "page schema")
        if schema.get("name") == "pd_ocr_labeler.user_page":
            payload = _object_dict(data.get("payload", {}), "page payload")
            page_dict = _object_dict(payload.get("page"), "page content")
            return restore_page_content(page_dict)

        # Legacy {"pages": [...]} format.
        pages = _object_list(data.get("pages", []), "legacy pages")
        if pages:
            return restore_page_content(_object_dict(pages[0], "legacy page content"))

        return None
    except Exception:
        log.debug("Failed to load page from %s", json_path, exc_info=True)
        return None


def _page_is_validated(page: Any) -> bool:
    """Return True when ALL words in ``page`` carry ``'validated'`` in ``word_labels``."""
    words = getattr(page, "words", []) or []
    return all("validated" in (getattr(w, "word_labels", None) or []) for w in words)


def freeze_export_page(
    *,
    page: Page,
    image_path: Path,
    page_index: int,
    prefix: str,
    blob_project_dir: Path,
) -> dict[str, object]:
    """Persist content-addressed page and image bytes for one reviewed export head."""
    from pdomain_ops.blob_store import BlobStore

    page_payload = json.dumps(
        snapshot_page_content(page), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    image_payload = image_path.read_bytes()
    blobs = BlobStore(blob_project_dir)
    page_sha256 = blobs.write(page_payload)
    image_sha256 = blobs.write(image_payload)
    return {
        "page_index": page_index,
        "prefix": prefix,
        "blob_project_dir": str(blob_project_dir),
        "page_sha256": page_sha256,
        "image_sha256": image_sha256,
    }


def load_frozen_export_page(snapshot: dict[str, object]) -> tuple[Page, Path]:
    """Reload and verify an immutable page/image snapshot from its declared hashes."""
    import hashlib

    from pdomain_ops.blob_store import BlobStore

    blob_project_dir = Path(str(snapshot["blob_project_dir"]))
    page_sha256 = str(snapshot["page_sha256"])
    image_sha256 = str(snapshot["image_sha256"])
    for digest in (page_sha256, image_sha256):
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("invalid frozen export content hash")
    blobs = BlobStore(blob_project_dir)
    page_payload = blobs.read(page_sha256)
    image_payload = blobs.read(image_sha256)
    if hashlib.sha256(page_payload).hexdigest() != page_sha256:
        raise ValueError("frozen export page hash mismatch")
    if hashlib.sha256(image_payload).hexdigest() != image_sha256:
        raise ValueError("frozen export image hash mismatch")
    return restore_page_content(page_payload), blob_project_dir / "blobs" / image_sha256


def _prepare_page_gt_first(page: Any) -> None:
    """Set GT-first text/bbox on every word in place."""
    for word in getattr(page, "words", []) or []:
        if not getattr(word, "ground_truth_text", None):
            word.ground_truth_text = getattr(word, "text", "") or ""
        gt_bbox = getattr(word, "ground_truth_bounding_box", None)
        if gt_bbox is not None:
            word.bounding_box = gt_bbox


# ---------------------------------------------------------------------------
# Page scanning helpers
# ---------------------------------------------------------------------------


def _labeled_project_dir(data_root: Path, project_id: str) -> Path:
    """``<data_root>/labeled-projects/<project_id>/``."""
    return data_root / "labeled-projects" / project_id


def _scan_labeled_pages(data_root: Path, project_id: str) -> list[Path]:
    """Return sorted list of labeled envelope JSON files for ``project_id``."""
    project_dir = _labeled_project_dir(data_root, project_id)
    if not project_dir.exists():
        return []
    return sorted(project_dir.glob("*.json"))


def _resolve_image_path(json_path: Path) -> Path | None:
    """Find the PNG/JPG image alongside a JSON label file."""
    for ext in (".png", ".jpg", ".jpeg"):
        candidate = json_path.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Store-first page resolution (PARITY-GAP P1.2 — sweep C35/C36/C37)
# ---------------------------------------------------------------------------
#
# Save writes ONLY the event store (``save_page_content_to_store``); the
# ``labeled-projects/`` lane is retired. Export therefore resolves pages
# **store-first**: the project's ``ProjectAggregate`` (same ``uuid5``
# resolution as ``LocalDoctrPageLoader.load_labeled``) yields the
# index→page_id map, and each page's content is the head provenance blob.
# A legacy ``labeled-projects/`` envelope is consumed ONLY for pages with
# no store head (C56 read-compat for pre-migration data).


@dataclass(frozen=True)
class ExportPageRef:
    """One exportable page: store head (preferred) and/or legacy envelope.

    ``page_index`` is ``-1`` for legacy files whose stem doesn't carry a
    parsable index (they are still exported, matching the old glob scan).
    """

    page_index: int
    prefix: str
    page_id: Any | None = None  # UUID of the store head (preferred lane)
    json_path: Path | None = None  # legacy envelope fallback (C56)


def _store_page_ids(store: Any, project_id: str) -> dict[int, Any]:
    """index → page_id map from the project's ``ProjectAggregate``.

    Returns ``{}`` on ANY failure (no store, no aggregate, import error) so
    callers fall through to the legacy scan — mirrors ``load_labeled``'s
    never-raise contract. NIL-uuid gap slots (reserved, never OCR'd) are
    filtered out.
    """
    if store is None:
        return {}
    try:
        from ....adapters.ocr.local_doctr import _NIL_PAGE_ID, _project_uuid_for

        proj_agg = store.get_project(_project_uuid_for(project_id))
        return {
            idx: page_id for idx, page_id in enumerate(proj_agg.record.page_ids) if page_id != _NIL_PAGE_ID
        }
    except Exception as exc:
        log.debug("export: store page-id resolution failed for %s: %s", project_id, exc)
        return {}


def resolve_export_page_refs(
    data_root: Path,
    project_id: str,
    store: Any,
    *,
    page_index: int | None = None,
) -> list[ExportPageRef]:
    """Resolve the pages an export should consider, store-first.

    Union of the event-store index→page_id map and the legacy
    ``labeled-projects/`` scan; when both lanes have the same index the
    store head wins (the legacy file is stale — Save no longer writes it).
    ``page_index`` restricts the result to that single index (scope
    ``current``).
    """
    store_map = _store_page_ids(store, project_id)

    legacy_map: dict[int, Path] = {}
    legacy_unindexed: list[Path] = []
    for json_path in _scan_labeled_pages(data_root, project_id):
        try:
            idx = int(json_path.stem.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            legacy_unindexed.append(json_path)
            continue
        legacy_map[idx] = json_path

    refs: list[ExportPageRef] = []
    for idx in sorted(set(store_map) | set(legacy_map)):
        if page_index is not None and idx != page_index:
            continue
        json_path = legacy_map.get(idx)
        prefix = json_path.stem if json_path is not None else f"{project_id}_{idx:03d}"
        refs.append(
            ExportPageRef(
                page_index=idx,
                prefix=prefix,
                page_id=store_map.get(idx),
                json_path=json_path,
            )
        )

    if page_index is None:
        refs.extend(ExportPageRef(page_index=-1, prefix=p.stem, json_path=p) for p in legacy_unindexed)
    return refs


def load_export_page(ref: ExportPageRef, store: Any) -> Page | None:
    """Load the ``Page`` for a ref: store head first, legacy envelope fallback."""
    if ref.page_id is not None and store is not None:
        from ....api._page_content import load_page_from_store

        page = load_page_from_store(store, ref.page_id)
        if page is not None:
            return page
        log.warning(
            "export: store head unreadable for page_index=%d (page_id=%s) — trying legacy fallback",
            ref.page_index,
            ref.page_id,
        )
    if ref.json_path is not None:
        return _load_page_from_envelope_file(ref.json_path)
    return None


def _resolve_ref_image(ref: ExportPageRef, image_paths: list[Path]) -> Path | None:
    """Resolve the page image: project source image first, legacy sibling second."""
    if 0 <= ref.page_index < len(image_paths) and image_paths[ref.page_index].exists():
        return image_paths[ref.page_index]
    if ref.json_path is not None:
        return _resolve_image_path(ref.json_path)
    return None


# ---------------------------------------------------------------------------
# Manifest write helper (Track C — export manifest)
# ---------------------------------------------------------------------------


def _write_export_manifest(
    export_root: Path,
    project_id: str,
    exported_at: str,
    page_count: int,
    task_stats: list[Any],
) -> None:
    """Merge-update the doctr-export manifest.json after a successful export.

    ``export_root`` is the doctr-export ROOT DIRECTORY (e.g.
    ``<data_root>/doctr-export/``).  Both ``read_manifest`` and
    ``write_manifest`` from ``pdomain_ops.schemas.doctr_export`` accept
    this directory and resolve ``<export_root>/manifest.json`` internally —
    do NOT pass the manifest file path directly.

    Imports Track-B helpers at call time so the handler stays importable
    when pdomain_ops is absent (CI, stub environments).  Any failure is
    logged and swallowed — a manifest write must never abort an otherwise
    successful export.

    JSON contract (schema: "pdomain.doctr-export-manifest", version 1):

        {
            "schema": "pdomain.doctr-export-manifest",
            "version": 1,
            "generated_at": "<ISO-8601>",
            "app": "pdomain-ocr-labeler-spa",
            "projects": {
                "<project_id>": {
                    "exported_at": "<ISO-8601>",
                    "page_count": <int>,
                    "tasks": {
                        "<task>": {"item_count": <int>}
                    }
                }
            }
        }

    Merge semantics: re-exporting a project replaces that project's entry;
    other projects are preserved.  ``generated_at`` is refreshed on every write.
    """
    try:
        from datetime import UTC, datetime

        from pdomain_ops.schemas.doctr_export import (  # pyright: ignore[reportMissingImports]
            DoctrExportManifest,
            DoctrExportProject,
            DoctrExportTaskStats,
            read_manifest,
            write_manifest,
        )
    except ImportError:
        log.debug("pdomain_ops.schemas.doctr_export not available; skipping manifest write")
        return

    try:
        existing = read_manifest(export_root)

        existing_projects: dict[str, DoctrExportProject] = (
            dict(existing.projects) if existing is not None else {}
        )

        # task_stats items carry .task (name) and .item_count; build the
        # dict[str, DoctrExportTaskStats] expected by DoctrExportProject.
        task_map: dict[str, DoctrExportTaskStats] = {
            ts.task: DoctrExportTaskStats(item_count=ts.item_count) for ts in task_stats
        }
        # exported_at is an ISO-8601 string; DoctrExportProject expects a datetime.
        exported_at_dt = datetime.fromisoformat(exported_at.replace("Z", "+00:00"))
        existing_projects[project_id] = DoctrExportProject(
            exported_at=exported_at_dt,
            page_count=page_count,
            tasks=task_map,
        )

        # Construct via model_validate (dict) to avoid the alias/field-name
        # ambiguity that strict pyright flags when schema_id is used as a kwarg.
        manifest = DoctrExportManifest.model_validate(
            {
                "schema": "pdomain.doctr-export-manifest",
                "version": 1,
                "generated_at": datetime.now(UTC),
                "app": "pdomain-ocr-labeler-spa",
                "projects": existing_projects,
            }
        )
        write_manifest(export_root, manifest)
        log.debug("manifest updated: %s/manifest.json (project=%s)", export_root, project_id)
    except Exception:
        log.warning("manifest write failed for project=%s", project_id, exc_info=True)


# ---------------------------------------------------------------------------
# Export output helpers
# ---------------------------------------------------------------------------

_DOCTR_EXPORT_DIRNAME = "doctr-export"


def export_output_dir(data_root: Path, project_id: str, subfolder: str) -> Path:
    """``<data_root>/doctr-export/<project_id>/<subfolder>/``.

    Raises ``ValueError`` if the resolved path is not strictly under the
    project export root.  This is a defence-in-depth guard; the API layer
    should have already rejected unsafe strings via ``ExportRequest``
    validators.

    The function is pure (no I/O side-effects) so it can be tested in
    isolation.  ``Path.resolve()`` fully normalises the path without
    requiring the paths to exist (Python 3.6+).

    Spec: ``docs/specs/2026-05-24-F-001-export-path-traversal.md``.
    """
    export_root = (data_root / _DOCTR_EXPORT_DIRNAME / project_id).resolve()
    candidate = (data_root / _DOCTR_EXPORT_DIRNAME / project_id / subfolder).resolve()
    # Accept paths that are strict descendants of export_root OR equal to it.
    if not str(candidate).startswith(str(export_root) + "/") and candidate != export_root:
        raise ValueError(
            f"Export subfolder {subfolder!r} resolves outside the project"
            f" export root: {candidate} is not under {export_root}"
        )
    return candidate


def _subfolder_for_style(style_filter: str | None) -> str:
    """Return the subfolder name for a given style filter."""
    return style_filter if style_filter else "all"


# ---------------------------------------------------------------------------
# Confirmed layout regions, written beside detection/ and recognition/
# ---------------------------------------------------------------------------

_LAYOUT_REGIONS_SCHEMA = "pdomain.layout-regions"
_LAYOUT_REGIONS_VERSION = 1


class LayoutRegionBox(TypedDict):
    x: int
    y: int
    width: int
    height: int


class LayoutRegionRecord(TypedDict):
    region_id: str
    role: str
    box: LayoutRegionBox
    member_word_signatures: list[list[float | bool | None]]


class LayoutRegionPage(TypedDict):
    prefix: str
    page_index: int
    regions: list[LayoutRegionRecord]


class LayoutRegionsFile(TypedDict):
    schema: str
    version: int
    pages: list[LayoutRegionPage]


def _json_value(text: str) -> object:
    # json.loads is typed as Any. The parsers below check every field.
    return json.loads(text)  # pyright: ignore[reportAny]


def _object_dict(value: object, label: str) -> dict[str, object]:
    """Copy a JSON object into ``dict[str, object]``.

    ``isinstance(value, dict)`` leaves the key and value parameters unknown
    under basedpyright, so the copy is the one place that names that fact.
    """
    if not isinstance(value, dict):
        raise ValueError(f"layout regions {label} must be an object")
    raw: dict[object, object] = value  # pyright: ignore[reportUnknownVariableType]
    mapping: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise ValueError(f"layout regions {label} has a non-string key")
        mapping[key] = item
    return mapping


def _object_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"layout regions {label} must be a list")
    raw: list[object] = value  # pyright: ignore[reportUnknownVariableType]
    return list(raw)


def _required(mapping: dict[str, object], key: str, label: str) -> object:
    if key not in mapping:
        raise ValueError(f"layout regions {label} is missing")
    return mapping[key]


def _layout_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"layout regions {label} must be a string")
    return value


def _layout_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"layout regions {label} must be an integer")
    return value


def _parse_layout_box(value: object) -> LayoutRegionBox:
    mapping = _object_dict(value, "box")
    return {
        "x": _layout_int(_required(mapping, "x", "box.x"), "box.x"),
        "y": _layout_int(_required(mapping, "y", "box.y"), "box.y"),
        "width": _layout_int(_required(mapping, "width", "box.width"), "box.width"),
        "height": _layout_int(_required(mapping, "height", "box.height"), "box.height"),
    }


def _parse_layout_signature(value: object) -> list[float | bool | None]:
    items = _object_list(value, "word signature")
    if len(items) != 5:
        raise ValueError("layout region word signature must have 5 entries")
    parsed: list[float | bool | None] = []
    for index, item in enumerate(items):
        if index < 4:
            if isinstance(item, bool) or not isinstance(item, int | float):
                raise ValueError("layout region word signature coordinate must be a number")
            parsed.append(float(item))
            continue
        if item is not None and not isinstance(item, bool):
            raise ValueError("layout region word signature flag must be a boolean or null")
        parsed.append(item)
    return parsed


def _parse_layout_region(value: object) -> LayoutRegionRecord:
    mapping = _object_dict(value, "region")
    signatures = _object_list(
        _required(mapping, "member_word_signatures", "member_word_signatures"),
        "member_word_signatures",
    )
    return {
        "region_id": _layout_str(_required(mapping, "region_id", "region_id"), "region_id"),
        "role": _layout_str(_required(mapping, "role", "role"), "role"),
        "box": _parse_layout_box(_required(mapping, "box", "box")),
        "member_word_signatures": [_parse_layout_signature(item) for item in signatures],
    }


def _parse_layout_page(value: object) -> LayoutRegionPage:
    mapping = _object_dict(value, "page")
    regions = _object_list(_required(mapping, "regions", "regions"), "regions")
    return {
        "prefix": _layout_str(_required(mapping, "prefix", "prefix"), "prefix"),
        "page_index": _layout_int(_required(mapping, "page_index", "page_index"), "page_index"),
        "regions": [_parse_layout_region(item) for item in regions],
    }


def _load_layout_regions(path: Path) -> LayoutRegionsFile:
    raw = _object_dict(_json_value(path.read_text(encoding="utf-8")), "file")
    if raw.get("schema") != _LAYOUT_REGIONS_SCHEMA or raw.get("version") != _LAYOUT_REGIONS_VERSION:
        raise ValueError("layout regions file has an unexpected schema")
    try:
        pages = _object_list(raw.get("pages"), "pages")
    except ValueError as exc:
        raise ValueError("layout regions file has an unexpected schema") from exc
    return {
        "schema": _LAYOUT_REGIONS_SCHEMA,
        "version": _LAYOUT_REGIONS_VERSION,
        "pages": [_parse_layout_page(item) for item in pages],
    }


def _signature_list(
    signature: tuple[float, float, float, float, bool | None],
) -> list[float | bool | None]:
    return [signature[0], signature[1], signature[2], signature[3], signature[4]]


class LayoutStructureEntry(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    prefix: str
    page_index: int
    region_id: str
    structure: LayoutStructure


class LayoutStructureFile(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    schema_name: Literal["pdomain.layout-structure"] = Field(
        default="pdomain.layout-structure", alias="schema"
    )
    version: Literal[1] = 1
    regions: list[LayoutStructureEntry] = Field(default_factory=list)


def _reviewed_structure_document(
    page: Page, path: Path, *, prefix: str
) -> tuple[LayoutStructureFile | None, int]:
    """Validate existing and new structure before publishing either export file."""
    entries = [
        LayoutStructureEntry(
            prefix=prefix,
            page_index=page.page_index,
            region_id=region.region_id,
            structure=refresh_structure_signatures(region.layout_structure, page=page),
        )
        for region in confirmed_regions_from_page(page)
        if region.region_id is not None and region.layout_structure is not None
    ]
    if not entries and not path.exists():
        return None, 0
    document = (
        LayoutStructureFile.model_validate_json(path.read_bytes()) if path.exists() else LayoutStructureFile()
    )
    document.regions = [
        entry for entry in document.regions if (entry.prefix, entry.page_index) != (prefix, page.page_index)
    ] + entries
    return document, len(entries)


def append_reviewed_structure(page: Page, output_dir: Path, *, prefix: str) -> int:
    """Replace this page's current reviewed structure, including deletions."""
    path = output_dir / "regions" / "structure.json"
    document, count = _reviewed_structure_document(page, path, prefix=prefix)
    if document is None:
        return count
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, document.model_dump(mode="json", exclude_none=True, by_alias=True))
    return count


def append_confirmed_regions(page: Page, output_dir: Path, *, prefix: str) -> int:
    """Write this page's confirmed regions into ``output_dir/regions/labels.json``.

    Schema ``pdomain.layout-regions`` version 1. A later export of the same
    prefix replaces that page's entry, including when the page no longer has
    any confirmed regions.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    regions_dir = output_dir / "regions"
    regions_dir.mkdir(parents=True, exist_ok=True)
    path = regions_dir / "labels.json"
    empty_document: LayoutRegionsFile = {
        "schema": _LAYOUT_REGIONS_SCHEMA,
        "version": _LAYOUT_REGIONS_VERSION,
        "pages": [],
    }
    document = _load_layout_regions(path) if path.is_file() else empty_document
    records: list[LayoutRegionRecord] = []
    for resolved in confirmed_regions_from_page(page):
        if resolved.region_id is None:
            continue
        left, top, right, bottom = resolved.box
        records.append(
            {
                "region_id": resolved.region_id,
                "role": resolved.role.value,
                "box": {"x": left, "y": top, "width": right - left, "height": bottom - top},
                "member_word_signatures": [
                    _signature_list(signature) for signature in resolved.member_word_signatures
                ],
            }
        )
    document["pages"] = [item for item in document["pages"] if item["prefix"] != prefix]
    document["pages"].append({"prefix": prefix, "page_index": page.page_index, "regions": records})
    structure_path = regions_dir / "structure.json"
    structure, _count = _reviewed_structure_document(page, structure_path, prefix=prefix)
    write_json_atomic(path, document)
    if structure is not None:
        write_json_atomic(structure_path, structure.model_dump(mode="json", exclude_none=True, by_alias=True))
    return len(records)


def _snapshot_word_boxes(page: Page) -> list[tuple[Word, BoundingBox]]:
    """Word boxes before export replaces them with ground-truth boxes."""
    return [(word, word.bounding_box) for word in page.words]


def _restore_word_boxes(snapshot: list[tuple[Word, BoundingBox]]) -> None:
    for word, box in snapshot:
        word.bounding_box = box


def _export_page_to_output_roots(
    page: Any,
    image_path: Path,
    output_roots: dict[str, Path],
    *,
    prefix: str,
    style_filters: list[str],
    component_filter: str | None,
    detection: bool,
    recognition: bool,
    classification: bool,
) -> None:
    """Export one page into every style folder.

    ``_export_page`` replaces word boxes with ground-truth boxes in place.
    Region signatures are read from those boxes, so each folder is exported
    from the same pre-swap snapshot. The page is left in the swapped state
    the word counters already expect.
    """
    snapshot = _snapshot_word_boxes(page) if isinstance(page, Page) else None
    for subfolder, output_root in output_roots.items():
        if snapshot is not None:
            _restore_word_boxes(snapshot)
        word_filter: WordFilter | None = None
        if style_filters and subfolder != "all":
            word_filter = WordFilter(style_labels=frozenset([subfolder]))
        elif component_filter:
            word_filter = WordFilter(word_components=frozenset([component_filter]))
        _export_page(
            page,
            image_path,
            output_root,
            word_filter=word_filter,
            detection=detection,
            recognition=recognition,
            classification=classification,
            prefix=prefix,
        )


# ---------------------------------------------------------------------------
# Single-page export (sync, wraps pdomain-book-tools)
# ---------------------------------------------------------------------------


def _export_page(
    page: Any,
    image_path: Path,
    output_dir: Path,
    *,
    word_filter: WordFilter | None,
    detection: bool,
    recognition: bool,
    classification: bool,
    prefix: str,
) -> None:
    """Export a single validated page to DocTR training format.

    Thin wrapper around ``Page.generate_doctr_detection_training_set``
    and ``Page.generate_doctr_recognition_training_set``.  Image loading
    (cv2_imread) is performed here rather than at caller level so failures
    are isolated per page.

    Confirmed layout regions are written before the image is read, so a
    missing OpenCV install or a missing image still leaves the region file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(page, Page):
        raise TypeError("export page must be a book-tools Page")
    _ = append_confirmed_regions(page, output_dir, prefix=prefix)
    try:
        from cv2 import imread as cv2_imread
    except ImportError:
        log.warning("cv2 not available; skipping image export for %s", image_path)
        return

    cv2_image = cv2_imread(str(image_path))
    if cv2_image is None:
        log.warning("cv2 failed to load image: %s", image_path)
        return

    page.cv2_numpy_page_image = cv2_image
    _prepare_page_gt_first(page)
    output_dir.mkdir(parents=True, exist_ok=True)

    wf_callable = word_filter.matches if word_filter else None

    if detection:
        page.generate_doctr_detection_training_set(
            output_path=output_dir,
            prefix=prefix,
            word_filter=wf_callable,
        )

    if recognition:
        label_formatter = _classification_label_formatter if classification else None
        page.generate_doctr_recognition_training_set(
            output_path=output_dir,
            prefix=prefix,
            word_filter=wf_callable,
            label_formatter=label_formatter,
        )
        _write_page_glyph_sidecar(
            page,
            output_dir=output_dir,
            prefix=prefix,
            word_filter=wf_callable,
            has_label_formatter=label_formatter is not None,
        )


def _classification_label_formatter(word: Any) -> dict[str, Any]:
    """Label formatter for classification export mode."""
    word_styles = set(getattr(word, "text_style_labels", None) or [])
    word_comps = set(getattr(word, "word_components", None) or [])
    return {
        "text": getattr(word, "ground_truth_text", None) or getattr(word, "text", "") or "",
        "labels": {
            label: (label in word_styles)
            for label in (
                "italics",
                "small caps",
                "blackletter",
                "bold",
                "all caps",
                "underline",
                "strikethrough",
                "monospace",
                "handwritten",
            )
        }
        | {
            comp: (comp in word_comps) for comp in ("superscript", "subscript", "footnote marker", "drop cap")
        },
    }


# ---------------------------------------------------------------------------
# Glyph-feature sidecar (issue #8/#9 join — see glyph_sidecar.py)
# ---------------------------------------------------------------------------


def _write_page_glyph_sidecar(
    page: Any,
    *,
    output_dir: Path,
    prefix: str,
    word_filter: Callable[[Any], bool] | None,
    has_label_formatter: bool,
) -> None:
    """Write this page's contribution to the recognition glyph-feature sidecar.

    Runs immediately after ``generate_doctr_recognition_training_set`` so it
    sees the same GT-first ``word.bounding_box`` state that call used
    (``_prepare_page_gt_first`` already ran earlier in ``_export_page``) —
    the crop ids computed here must match the keys that call just wrote to
    ``recognition/labels.json``. See ``glyph_sidecar.py`` for the crop-id
    formula and the reviewed-vs-never-reviewed distinction.
    """
    from .glyph_sidecar import build_glyph_feature_entries, write_glyph_feature_sidecar

    if page.cv2_numpy_page_image is None:
        return
    img_height, img_width = page.cv2_numpy_page_image.shape[:2]

    entries = build_glyph_feature_entries(
        page,
        prefix=prefix,
        img_width=img_width,
        img_height=img_height,
        word_filter=word_filter,
        has_label_formatter=has_label_formatter,
    )
    write_glyph_feature_sidecar(
        output_dir / "recognition",
        prefix=prefix,
        page_index=page.page_index,
        new_entries=entries,
    )


# ---------------------------------------------------------------------------
# Stats accounting (Lane E3)
# ---------------------------------------------------------------------------


def _word_has_bbox(word: Any) -> bool:
    """True when a word carries a usable bounding box for detection export."""
    gt_bbox = getattr(word, "ground_truth_bounding_box", None)
    return gt_bbox is not None or getattr(word, "bounding_box", None) is not None


def _word_has_text(word: Any) -> bool:
    """True when a word carries non-empty ground-truth/text for recognition export."""
    text = getattr(word, "ground_truth_text", None) or getattr(word, "text", None) or ""
    return bool(str(text).strip())


def _count_exported_words(page: Any, word_filter: WordFilter | None) -> tuple[int, int]:
    """Return ``(detection_words, recognition_words)`` for a page+filter.

    Mirrors the per-word inclusion the DocTR training-set generators apply:
    detection needs a bounding box, recognition needs non-empty text. Words
    are filtered by ``word_filter`` first (``None`` matches all).
    """
    detection_words = 0
    recognition_words = 0
    for word in getattr(page, "words", []) or []:
        if word_filter is not None and not word_filter.matches(word):
            continue
        if _word_has_bbox(word):
            detection_words += 1
        if _word_has_text(word):
            recognition_words += 1
    return detection_words, recognition_words


# ---------------------------------------------------------------------------
# Task-stats builder (plain objects, no pdomain_ops dependency)
# ---------------------------------------------------------------------------


def _build_task_stats(
    *,
    detection: bool,
    recognition: bool,
    classification: bool,
    words_detection: int,
    words_recognition: int,
) -> list[Any]:
    """Build a list of task-stats objects for the manifest helper.

    Uses plain objects (SimpleNamespace) so the handler remains importable
    without pdomain_ops.  ``_write_export_manifest`` converts these to
    ``DoctrExportTaskStats`` instances internally using the ``.task`` and
    ``.item_count`` attributes.
    """
    from types import SimpleNamespace

    stats: list[Any] = []
    if detection:
        stats.append(SimpleNamespace(task="detection", item_count=words_detection))
    if recognition:
        stats.append(SimpleNamespace(task="recognition", item_count=words_recognition))
    if classification:
        # Classification re-uses the recognition word count (same words, different labels).
        stats.append(SimpleNamespace(task="classification", item_count=words_recognition))
    return stats


# ---------------------------------------------------------------------------
# Main async handler
# ---------------------------------------------------------------------------


async def handle_export(runner: JobRunner, job: Job) -> None:
    """Async export handler — registered as ``_HANDLERS["export"]``.

    Reads ``job.payload`` for export parameters, iterates labeled pages,
    calls ``_export_page`` per page, emits SSE progress events.  On
    cancellation, ``shutil.rmtree``s partial output and returns early.

    Spec: ``docs/specs/2026-05-12-export-design.md §Export flow``.
    """
    payload = job.payload
    if payload.get("regions_only") is True:
        from .region_export import handle_region_export

        await handle_region_export(runner, job)
        return
    project_id = job.project_id or ""
    scope = payload.get("scope", "all_validated")
    style_filters: list[str] = payload.get("style_filters") or []
    component_filter: str | None = payload.get("component_filter")
    include_classification: bool = bool(payload.get("include_classification", False))
    detection_only: bool = bool(payload.get("detection_only", False))
    recognition_only: bool = bool(payload.get("recognition_only", False))
    page_index: int | None = payload.get("page_index")
    frozen_pages = payload.get("frozen_pages")

    detection = not recognition_only
    recognition = not detection_only

    settings = runner.context.get("settings")
    if settings is None:
        raise RuntimeError("export handler: settings not in runner.context")

    data_root: Path = Path(settings.data_root)

    # --- resolve pages to export (store-first, P1.2) ---
    # The runner context's page_store belongs to the *loaded* project; only
    # trust it (and the loaded project's image paths) when the ids match —
    # otherwise an export for project A would read project B's store.
    store = runner.context.get("page_store")
    project_state = runner.context.get("project_state")
    loaded_project = getattr(project_state, "loaded_project", None) if project_state else None
    image_paths: list[Path] = []
    if loaded_project is not None and loaded_project.project_id == project_id:
        if isinstance(project_state, ProjectState) and project_state.has_book_labeling_session:
            raise RuntimeError("export: immutable book source pages are unsupported")
        image_paths = [Path(p) for p in loaded_project.image_paths]
    else:
        store = None

    pages_to_export: list[tuple[ExportPageRef, Path, Any]] = []
    if isinstance(frozen_pages, list):
        for raw_snapshot in frozen_pages:
            if not isinstance(raw_snapshot, dict):
                raise ValueError("invalid frozen export snapshot")
            page, image_path = load_frozen_export_page(raw_snapshot)
            pages_to_export.append(
                (
                    ExportPageRef(
                        page_index=int(raw_snapshot["page_index"]),
                        prefix=str(raw_snapshot["prefix"]),
                    ),
                    image_path,
                    page,
                )
            )
    else:
        refs = resolve_export_page_refs(
            data_root,
            project_id,
            store,
            page_index=page_index if scope == "current" else None,
        )
        for ref in refs:
            img = _resolve_ref_image(ref, image_paths)
            if img is not None:
                pages_to_export.append((ref, img, None))
            else:
                log.warning(
                    "export: no image resolvable for page_index=%d (prefix=%s) — skipping",
                    ref.page_index,
                    ref.prefix,
                )

    total_pages = len(pages_to_export)

    # --- determine output roots (one per style filter, or "all") ---
    subfolders = style_filters or ["all"]

    output_roots = {sf: export_output_dir(data_root, project_id, sf) for sf in subfolders}

    # --- iterate pages ---
    exported_count = 0
    skipped_count = 0
    words_exported_detection = 0
    words_exported_recognition = 0
    pages_skipped_not_validated = 0
    for page_num, (ref, image_path, frozen_page) in enumerate(pages_to_export):
        # Cooperative cancel check — shared helper, see JobRunner.is_cancelled.
        if runner.is_cancelled(job.job_id):
            # rmtree partial output for all subfolders.
            project_export_root = data_root / _DOCTR_EXPORT_DIRNAME / project_id
            if project_export_root.exists():
                shutil.rmtree(project_export_root, ignore_errors=True)
            cancel_message = (
                f"Cancelled after exporting {exported_count} of {total_pages} page(s); partial output removed"
            )
            notification_queue = runner.context.get("notification_queue")
            if isinstance(notification_queue, NotificationQueue):
                notification_queue.queue(NotificationKind.INFO, f"Export {cancel_message.lower()}")
            await runner.update_progress(
                job.job_id,
                current=exported_count,
                total=total_pages,
                message=cancel_message,
            )
            return

        page = frozen_page if frozen_page is not None else load_export_page(ref, store)
        if page is None:
            log.warning(
                "export: could not load page_index=%d (prefix=%s) — skipping", ref.page_index, ref.prefix
            )
            skipped_count += 1
            continue

        # Validation gate for all_validated scope.
        if scope != "current" and not _page_is_validated(page):
            log.debug("export: skipping non-validated page %s", ref.prefix)
            pages_skipped_not_validated += 1
            continue

        # Restore word boxes before each folder. The first successful export
        # swaps them to ground-truth boxes, and region signatures must stay
        # the boxes the page had before that swap.
        _export_page_to_output_roots(
            page,
            image_path,
            output_roots,
            prefix=ref.prefix,
            style_filters=style_filters,
            component_filter=component_filter,
            detection=detection,
            recognition=recognition,
            classification=include_classification,
        )

        # Count each page ONCE (not once per subfolder) — use None filter so
        # the total reflects all exported words on the page, independent of
        # how many style subfolders were selected.
        det_words, rec_words = _count_exported_words(page, None)
        if detection:
            words_exported_detection += det_words
        if recognition:
            words_exported_recognition += rec_words

        exported_count += 1

        await runner.update_progress(
            job.job_id,
            current=page_num + 1,
            total=total_pages,
            message=f"Exporting page {page_num + 1} of {total_pages}",
        )
        # Yield control so SSE events and cancel checks can propagate.
        await asyncio.sleep(0)

    log.info(
        "export complete: project=%s pages_exported=%d skipped=%d total=%d "
        "words_detection=%d words_recognition=%d pages_skipped_not_validated=%d",
        project_id,
        exported_count,
        skipped_count,
        total_pages,
        words_exported_detection,
        words_exported_recognition,
        pages_skipped_not_validated,
    )

    # Emit the terminal progress update so the completion message is surfaced
    # in the SSE "complete" event (runner reads job.message when emitting).
    # ``result`` carries the structured stats breakdown (Lane E3) so the
    # export dialog can render detection/recognition word counts and the
    # number of pages skipped because they were not fully validated.
    if skipped_count > 0:
        terminal_msg = f"Exported {exported_count} pages ({skipped_count} skipped due to load errors)"
    else:
        terminal_msg = f"Exported {exported_count} pages"

    await runner.update_progress(
        job.job_id,
        current=total_pages,
        total=total_pages,
        message=terminal_msg,
        result={
            "words_exported_detection": words_exported_detection,
            "words_exported_recognition": words_exported_recognition,
            "pages_skipped_not_validated": pages_skipped_not_validated,
        },
    )

    # --- Track C: write / update the export manifest ---
    # Runs after the terminal SSE event so a manifest failure never
    # prevents the "complete" event from reaching the frontend.
    from datetime import UTC
    from datetime import datetime as _dt

    _write_export_manifest(
        export_root=data_root / _DOCTR_EXPORT_DIRNAME,
        project_id=project_id,
        exported_at=_dt.now(UTC).isoformat(),
        page_count=exported_count,
        task_stats=_build_task_stats(
            detection=detection,
            recognition=recognition,
            classification=include_classification,
            words_detection=words_exported_detection,
            words_recognition=words_exported_recognition,
        ),
    )


__all__ = [
    "ExportPageRef",
    "WordFilter",
    "export_output_dir",
    "handle_export",
    "load_export_page",
    "resolve_export_page_refs",
]

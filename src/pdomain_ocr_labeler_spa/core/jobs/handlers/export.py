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

Cancel support: the handler checks ``runner._jobs[job_id].status`` between
page iterations.  On cancellation it ``shutil.rmtree``s the partial output
dir and emits nothing further (the runner's ``request_cancel`` already
emitted the CANCELLED event).

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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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


def _load_page_from_envelope_file(json_path: Path) -> Any | None:
    """Load a ``Page`` from an envelope (or legacy pages-dict) JSON file.

    Returns ``None`` on any error.  Import of ``pdomain_book_tools`` is deferred
    to keep this module importable even in test environments that stub
    ``pdomain_book_tools``.
    """
    try:
        from pdomain_book_tools.ocr.page import Page as PdPage

        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None

        # Try envelope format first.
        schema = data.get("schema", {})
        if isinstance(schema, dict) and schema.get("name") == "pd_ocr_labeler.user_page":
            payload = data.get("payload", {})
            if isinstance(payload, dict):
                page_dict = payload.get("page")
                if isinstance(page_dict, dict):
                    return PdPage.from_dict(page_dict)
            return None

        # Legacy {"pages": [...]} format.
        pages = data.get("pages")
        if isinstance(pages, list) and pages and isinstance(pages[0], dict):
            return PdPage.from_dict(pages[0])

        return None
    except Exception:
        log.debug("Failed to load page from %s", json_path, exc_info=True)
        return None


def _page_is_validated(page: Any) -> bool:
    """Return True when ALL words in ``page`` carry ``'validated'`` in ``word_labels``."""
    words = getattr(page, "words", []) or []
    if not words:
        return False
    return all("validated" in (getattr(w, "word_labels", None) or []) for w in words)


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


def load_export_page(ref: ExportPageRef, store: Any) -> Any | None:
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
    """
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
    from ..runner import JobStatus  # avoid circular at module level

    payload = job.payload
    project_id = job.project_id or ""
    scope = payload.get("scope", "all_validated")
    style_filters: list[str] = payload.get("style_filters") or []
    component_filter: str | None = payload.get("component_filter")
    include_classification: bool = bool(payload.get("include_classification", False))
    detection_only: bool = bool(payload.get("detection_only", False))
    recognition_only: bool = bool(payload.get("recognition_only", False))
    page_index: int | None = payload.get("page_index")

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
        image_paths = [Path(p) for p in loaded_project.image_paths]
    else:
        store = None

    refs = resolve_export_page_refs(
        data_root,
        project_id,
        store,
        page_index=page_index if scope == "current" else None,
    )

    pages_to_export: list[tuple[ExportPageRef, Path]] = []  # (ref, image_path)
    for ref in refs:
        img = _resolve_ref_image(ref, image_paths)
        if img is not None:
            pages_to_export.append((ref, img))
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
    for page_num, (ref, image_path) in enumerate(pages_to_export):
        # Cooperative cancel check.
        current_job = runner._jobs.get(job.job_id)
        if current_job and current_job.status == JobStatus.CANCELLED:
            # rmtree partial output for all subfolders.
            project_export_root = data_root / _DOCTR_EXPORT_DIRNAME / project_id
            if project_export_root.exists():
                shutil.rmtree(project_export_root, ignore_errors=True)
            return

        page = load_export_page(ref, store)
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

        # Export to each subfolder.
        for subfolder, output_root in output_roots.items():
            wf: WordFilter | None = None
            if style_filters and subfolder != "all":
                wf = WordFilter(style_labels=frozenset([subfolder]))
            elif component_filter:
                wf = WordFilter(word_components=frozenset([component_filter]))

            _export_page(
                page,
                image_path,
                output_root,
                word_filter=wf,
                detection=detection,
                recognition=recognition,
                classification=include_classification,
                prefix=ref.prefix,
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

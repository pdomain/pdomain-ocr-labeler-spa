"""Headless CLI for DocTR training-data export.

Console script entry-point: ``pdomain-ocr-labeler-spa-export``.

Store-first (Wave 1.2 / P0-CLI-STORE): opens the project's event store when
a ``.pd-pages/`` directory is found (via ``--project-root`` or discovery),
reuses ``resolve_export_page_refs`` / ``load_export_page`` from the in-app
export path, and falls back to legacy ``labeled-projects/`` envelopes when
no store head exists.

No FastAPI boot required — this module imports nothing from FastAPI or
``pdomain_ocr_labeler_spa.api`` at module level (``load_export_page`` may
import ``api._page_content`` inside the function).

Spec: ``docs/specs/2026-05-12-export-design.md §Headless CLI``.
Issue: #228; deep-review Wave 1.2.

Usage example::

    pdomain-ocr-labeler-spa-export \\
        --data-root /data \\
        --project-id my-project \\
        --project-root /books/my-project \\
        --style italic bold \\
        --detection-only
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdomain-ocr-labeler-spa-export",
        description=(
            "Export DocTR training data from SPA event-store pages (store-first) "
            "or legacy labeled-project envelopes. No server required."
        ),
    )
    parser.add_argument(
        "--data-root",
        required=True,
        type=Path,
        help="Path to the data root directory (holds doctr-export/ and labeled-projects/).",
    )
    parser.add_argument("--project-id", required=True, help="Project identifier.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help=(
            "Source project directory containing images and optional .pd-pages/ "
            "event store (SPA Save path). When omitted, candidates under "
            "data-root are tried."
        ),
    )
    parser.add_argument(
        "--style",
        dest="style_filters",
        nargs="*",
        default=[],
        metavar="STYLE",
        help=(
            "Style label filter(s). When omitted, exports all words (subfolder 'all'). "
            "When provided, produces one subfolder per style label."
        ),
    )
    parser.add_argument(
        "--component",
        dest="component_filter",
        default=None,
        metavar="COMPONENT",
        help="Component filter (single label, e.g. 'footnote').",
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--detection-only",
        action="store_true",
        default=False,
        help="Export detection labels only (no recognition images).",
    )
    output_group.add_argument(
        "--recognition-only",
        action="store_true",
        default=False,
        help="Export recognition images only (no detection labels).",
    )
    output_group.add_argument(
        "--classification",
        action="store_true",
        default=False,
        help="Export recognition with multi-label classification formatter.",
    )

    parser.add_argument(
        "--page-index",
        type=int,
        default=None,
        metavar="N",
        help="Export a single page (0-based index). Default: all validated pages.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose logging.",
    )
    return parser


def _project_root_candidates(
    data_root: Path,
    project_id: str,
    project_root: Path | None,
) -> list[Path]:
    """Ordered paths that may hold ``.pd-pages/`` and source images."""
    candidates: list[Path] = []
    if project_root is not None:
        candidates.append(project_root)
    candidates.extend(
        [
            data_root / project_id,
            data_root / "projects" / project_id,
            data_root.parent / project_id,
            data_root / "labeled-projects" / project_id,
        ]
    )
    # De-dupe while preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def _open_store_and_images(
    data_root: Path,
    project_id: str,
    project_root: Path | None,
) -> tuple[object | None, list[Path], Path | None]:
    """Open LabelerPageStore when .pd-pages exists; scan image paths.

    Returns ``(store_or_None, image_paths, resolved_project_root)``.
    """
    from ...persistence.page_store import LabelerPageStore
    from ...persistence.project_envelope import _scan_image_paths

    for candidate in _project_root_candidates(data_root, project_id, project_root):
        if not candidate.is_dir():
            continue
        image_paths = _scan_image_paths(candidate) if candidate.is_dir() else []
        store: LabelerPageStore | None = None
        if (candidate / ".pd-pages").is_dir():
            try:
                store = LabelerPageStore(project_dir=candidate)
                log.info("Opened event store at %s/.pd-pages/", candidate)
            except Exception as exc:
                log.warning("Could not open store at %s: %s", candidate, exc)
                store = None
        if store is not None or image_paths or (candidate / ".pd-pages").is_dir():
            return store, image_paths, candidate
    return None, [], None


async def _run_export(
    data_root: Path,
    project_id: str,
    style_filters: list[str],
    component_filter: str | None,
    detection_only: bool,
    recognition_only: bool,
    classification: bool,
    page_index: int | None,
    project_root: Path | None = None,
) -> int:
    """Core async export logic — mirrors handle_export without the SSE layer.

    Returns the count of pages exported.
    """
    from datetime import UTC, datetime

    from .export import (
        _DOCTR_EXPORT_DIRNAME,
        ExportPageRef,
        WordFilter,
        _build_task_stats,
        _export_page,
        _page_is_validated,
        _resolve_ref_image,
        _write_export_manifest,
        export_output_dir,
        load_export_page,
        resolve_export_page_refs,
    )

    detection = not recognition_only
    recognition = not detection_only

    scope = "current" if page_index is not None else "all_validated"

    store, image_paths, resolved_root = _open_store_and_images(data_root, project_id, project_root)
    try:
        refs = resolve_export_page_refs(
            data_root,
            project_id,
            store,
            page_index=page_index if scope == "current" else None,
        )

        pages_to_export: list[tuple[ExportPageRef, Path]] = []
        for ref in refs:
            img = _resolve_ref_image(ref, image_paths)
            if img is not None:
                pages_to_export.append((ref, img))
            else:
                log.warning(
                    "No image for page_index=%s prefix=%s — skipping",
                    ref.page_index,
                    ref.prefix,
                )

        total_pages = len(pages_to_export)
        log.info(
            "Found %d page(s) to export for project '%s' (store=%s root=%s).",
            total_pages,
            project_id,
            "yes" if store is not None else "no",
            resolved_root,
        )

        if not pages_to_export:
            log.warning("No pages found. Nothing exported.")
            return 0

        subfolders = style_filters or ["all"]
        output_roots = {sf: export_output_dir(data_root, project_id, sf) for sf in subfolders}

        exported_count = 0
        words_det = 0
        words_rec = 0
        for page_num, (ref, image_path) in enumerate(pages_to_export):
            page = load_export_page(ref, store)
            if page is None:
                log.warning(
                    "Could not load page_index=%s; skipping.",
                    getattr(ref, "page_index", "?"),
                )
                continue

            if scope != "current" and not _page_is_validated(page):
                log.debug("Skipping non-validated page %s.", getattr(ref, "prefix", "?"))
                continue

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
                    classification=classification,
                    prefix=getattr(ref, "prefix", project_id),
                )

            # Approximate word counts for manifest (best-effort).
            n_words = len(getattr(page, "words", []) or [])
            if detection:
                words_det += n_words
            if recognition:
                words_rec += n_words

            exported_count += 1
            log.info(
                "[%d/%d] Exported page %s.",
                page_num + 1,
                total_pages,
                getattr(ref, "prefix", "?"),
            )
            await asyncio.sleep(0)

        if exported_count > 0:
            _write_export_manifest(
                export_root=data_root / _DOCTR_EXPORT_DIRNAME,
                project_id=project_id,
                exported_at=datetime.now(UTC).isoformat(),
                page_count=exported_count,
                task_stats=_build_task_stats(
                    detection=detection,
                    recognition=recognition,
                    classification=classification,
                    words_detection=words_det,
                    words_recognition=words_rec,
                ),
            )

        return exported_count
    finally:
        if store is not None:
            close = getattr(store, "close", None)
            if callable(close):
                close()


def main() -> None:
    """Entry-point for ``pdomain-ocr-labeler-spa-export`` console script."""
    parser = _build_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        format="%(levelname)s %(name)s %(message)s",
        level=log_level,
    )

    count = asyncio.run(
        _run_export(
            data_root=args.data_root,
            project_id=args.project_id,
            style_filters=args.style_filters or [],
            component_filter=args.component_filter,
            detection_only=args.detection_only,
            recognition_only=args.recognition_only,
            classification=args.classification,
            page_index=args.page_index,
            project_root=args.project_root,
        )
    )

    if count == 0:
        log.warning("No pages were exported.")
        sys.exit(1)

    print(f"Exported {count} page(s) to {args.data_root}/doctr-export/{args.project_id}/.")


__all__ = ["_run_export", "main"]

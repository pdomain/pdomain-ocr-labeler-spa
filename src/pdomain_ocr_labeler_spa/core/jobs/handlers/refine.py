"""Refine-bboxes job handler — Lane A / Task A1.

Audit finding: ``POST .../refine`` (and ``POST .../lines/refine-batch``)
enqueue job type ``refine_bboxes``, but the handler was never registered
in ``core/jobs/runner._HANDLERS`` so the job failed with
``NotImplementedError`` at run time. This module supplies the handler.

The handler runs over the live OCR ``Page`` already cached on
``ProjectState.page_states[idx].page_record.payload`` (the OCR lane stores
a ``pdomain_book_tools.ocr.page.Page`` directly — M5b event-store adoption).
It resolves the requested scope to a flat list of target words and, per the
requested ``mode``, expands and/or refines each word's bounding box against
the page's cv2 image.

Job payload keys (mirrors ``api/refine.RefineScopeRequest`` →
``runner.submit`` payload):

``page_index``        int  — 0-based page index.
``scope``             str  — ``"page" | "paragraph" | "line" | "word"``.
``mode``              str  — ``"refine" | "expand_then_refine" | "expand_only"``.
``padding_px``        int  — expansion / refine padding in pixels.
``paragraph_indices`` list[int]            — for scope=paragraph.
``line_indices``      list[int]            — for scope=line.
``word_indices``      list[(int, int)]     — for scope=word, (line, word).

Runner context keys (read-only) — same carriers ``reload_ocr`` uses:

``project_state``  ``ProjectState``  — required.
``page_store``     ``LabelerPageStore | None`` — optional; when present the
                    edited page content is persisted so refined bboxes
                    survive a fresh-store reload.

Returns ``{"refined": <count>}`` describing how many words were touched.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...project_state import ProjectState

if TYPE_CHECKING:
    from ..runner import Job, JobRunner

log = logging.getLogger(__name__)


def _resolve_scope_targets(page: Any, scope: str, payload: dict[str, Any]) -> list[Any]:
    """Resolve the refine scope to a flat list of target words.

    Out-of-range indices are skipped (the SPA may send stale indices from a
    re-OCRed page; the batch is best-effort by design).
    """
    targets: list[Any] = []
    if scope == "page":
        targets.extend(getattr(page, "words", []) or [])
        return targets
    if scope == "paragraph":
        paragraphs = getattr(page, "paragraphs", None) or []
        for pi in payload.get("paragraph_indices", []) or []:
            if 0 <= pi < len(paragraphs):
                targets.extend(getattr(paragraphs[pi], "words", []) or [])
        return targets
    if scope == "line":
        lines = getattr(page, "lines", None) or []
        for li in payload.get("line_indices", []) or []:
            if 0 <= li < len(lines):
                targets.extend(getattr(lines[li], "words", []) or [])
        return targets
    # Remaining branch: word scope — resolve each (line, word) pair.
    lines = getattr(page, "lines", None) or []
    for li, wi in payload.get("word_indices", []) or []:
        if 0 <= li < len(lines):
            words = getattr(lines[li], "words", None) or []
            if 0 <= wi < len(words):
                targets.append(words[wi])
    return targets


def _page_dimensions(page: Any) -> tuple[float, float]:
    """Best-effort (width, height) for ``expand_bbox`` clamping."""
    image = getattr(page, "cv2_numpy_page_image", None)
    shape = getattr(image, "shape", None)
    if shape is not None and len(shape) >= 2:
        return float(shape[1]), float(shape[0])
    return float(getattr(page, "width", 0) or 0), float(getattr(page, "height", 0) or 0)


def handle_refine_bboxes(runner: JobRunner, job: Job) -> None:
    """Refine / expand the bounding boxes for the requested scope.

    Synchronous body (no OCR engine call) — runs in-process under the job
    runner. Mutates the cached ``Page`` in place, bumps the page generation,
    and persists the edited content so the refined bboxes survive a reload.
    """
    payload: dict[str, Any] = job.payload
    page_index = int(payload.get("page_index", 0))
    scope = str(payload.get("scope", "page"))
    mode = str(payload.get("mode", "refine"))
    padding_px = int(payload.get("padding_px", 2))

    ctx: dict[str, Any] = runner.context
    project_state = ctx.get("project_state")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("refine_bboxes: runner.context['project_state'] is not wired")

    pstate = project_state.get_page_state(page_index)
    if pstate is None or pstate.page_record is None:
        raise RuntimeError(f"refine_bboxes: page {page_index} not loaded; run OCR / load first")
    page = getattr(pstate.page_record, "payload", None)
    if page is None or not hasattr(page, "lines"):
        raise RuntimeError(f"refine_bboxes: page {page_index} payload is not a Page")

    image = getattr(page, "cv2_numpy_page_image", None)
    width, height = _page_dimensions(page)

    page_lock = project_state.get_page_lock(page_index)
    refined = 0
    with page_lock:
        targets = _resolve_scope_targets(page, scope, payload)
        for word in targets:
            try:
                if mode == "expand_only":
                    word.expand_bbox(float(padding_px), width, height)
                elif mode == "expand_then_refine":
                    word.expand_then_refine_bbox(image)
                else:  # "refine"
                    word.refine_bbox(image, padding_px=padding_px)
            except Exception as exc:  # pragma: no cover - defensive per-word guard
                log.warning("refine_bboxes: word refine failed: %s", exc)
                continue
            refined += 1

        # Reset derived caches after bbox edits (legacy parity).
        finalize = getattr(page, "finalize_page_structure", None)
        if callable(finalize):
            finalize()
        pstate.generation += 1

        # Persist edited content so refined bboxes survive a fresh-store reload.
        store = ctx.get("page_store")
        if store is not None and pstate.page_id is not None and callable(getattr(page, "to_dict", None)):
            try:
                from ...page_state import save_page_content_to_store

                save_page_content_to_store(
                    page_id=pstate.page_id,
                    page=page,
                    store=store,
                    changes=[{"type": "refine_bboxes", "scope": scope, "mode": mode, "refined": refined}],
                )
            except Exception as exc:  # pragma: no cover - best-effort persistence
                log.warning("refine_bboxes: store write failed page_id=%s: %s", pstate.page_id, exc)

    job.payload["refined"] = refined
    log.info("refine_bboxes: page=%d scope=%s mode=%s refined=%d", page_index, scope, mode, refined)


__all__ = ["handle_refine_bboxes"]

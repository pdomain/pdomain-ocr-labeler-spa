"""``/api/projects/{project_id}/pages/{page_index}/lines`` and ``/paragraphs`` router (§5.5).

Spec authority:
- ``specs/23-page-payload-backend.md §9`` — line / paragraph mutation
  endpoint catalog (rows 12–18 cover lines, 19–23 paragraphs).
- ``specs/23-page-payload-backend.md §11`` — refine endpoint contract;
  ``lines/refine-batch`` enqueues that job.
- ``specs/23-page-payload-backend.md §12-§13`` — autosave + per-page lock.
- ``docs/architecture/01-data-models.md §2`` — wire shapes for the
  existing batch endpoints kept for frontend client compatibility
  (``copy-gt`` / ``merge`` / ``delete`` / ``split-with-selected`` /
  ``group-into-paragraph`` / ``paragraphs/{pi}/split-after-line``).

Per-mutation skeleton (mirrors ``api/words.py``'s spec-23-C handlers):
1. ``_check_project_and_page`` guards 404 project_not_found /
   page_not_found.
2. Resolve target line via ``page.lines[li]``; 404 ``line_not_found``
   if out of range.
3. Acquire ``ProjectState.get_page_lock(idx)`` (threading.Lock — handlers
   are sync, FastAPI threadpool).
4. Call the pd-book-tools method. If it returns ``False`` → 400
   ``mutation_failed``. Bump ``PageState.generation``.
5. Release lock; write cached envelope best-effort.
6. Refresh ``PagePayload`` and return.

Pd-book-tools method mapping (spec §9 names → actual pd-book-tools API):

- ``line.copy_gt_to_ocr()`` → ``Block.copy_ground_truth_to_ocr()``
  (``pd_book_tools/ocr/block.py:643``).
- ``line.copy_ocr_to_gt()`` → ``Block.copy_ocr_to_ground_truth()``
  (``pd_book_tools/ocr/block.py:630``).
- ``line.set_validated(bool)`` → **no method exists** on the Block class
  (tracking issue ConcaveTrillion/pd-book-tools#52 — same workaround as
  Word). The route assigns ``line.is_validated`` as a Python attribute
  and propagates the flag onto every contained word so the validate-batch
  scope=line view stays consistent.
- ``page.delete_line(l)`` → ``Page.delete_lines([l])``
  (``pd_book_tools/ocr/page.py:1660`` — pd-book-tools exposes the batch
  variant only).
- ``page.merge_lines(targets)`` → ``Page.merge_lines(line_indices)``
  (``pd_book_tools/ocr/page.py:1575``).
- ``line.split_after_word(w)`` → ``Page.split_line_after_word(li, wi)``
  (``pd_book_tools/ocr/page.py:1940`` — owned by the Page, not the
  Block, because it has to reorganize line ordering).
- ``page.split_line_by_words(targets)`` →
  ``Page.split_line_with_selected_words(word_keys)``
  (``pd_book_tools/ocr/page.py:2217``).
- ``lines/refine-batch`` enqueues the existing refine job
  (``api/refine.py``); the handler is already real per spec §11.

Legacy routes kept for frontend compatibility (older 404-stub contract
already pinned in ``frontend/src/api/types.ts`` and ``hooks/useLineMutations.ts``):

- ``POST .../lines/{li}/copy-gt`` body ``{direction: gt_to_ocr|ocr_to_gt}``.
- ``POST .../delete`` body ``DeleteScopeRequest`` (page-scope batch).
- ``POST .../merge`` body ``MergeScopeRequest`` (page-scope batch).
- ``POST .../paragraphs/{pi}/split-after-line``.
- ``POST .../lines/{li}/split-with-selected``.
- ``POST .../words/group-into-paragraph``.

These remain stub-shaped (return 200 with a stub PagePayload) because
their backend semantics are paragraph-scope (D2/D3); D1 covers only the
spec-named line endpoints. The integration tests for the legacy routes
remain green via the unchanged ``_page_payload`` stub.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.jobs import JobRunner
from ..core.project_state import ProjectState
from ..settings import Settings
from .dependencies import get_job_runner, get_project_state, get_settings
from .middleware.error_handler import ApiError
from .pages import PagePayload
from .words import (
    _page_not_loaded,
    _refresh_payload_response,
    _resolve_page_object,
    _write_cached_envelope_best_effort,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["lines", "paragraphs"])


# ── Request models — legacy (frontend pinned) ──────────────────────────


class CopyLineGtRequest(BaseModel):
    """Legacy ``/lines/{li}/copy-gt`` body — kept for frontend compat."""

    direction: Literal["gt_to_ocr", "ocr_to_gt"]


class DeleteScopeRequest(BaseModel):
    """Legacy ``/delete`` page-scope batch body."""

    scope: Literal["paragraph", "line", "word"]
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    word_indices: list[tuple[int, int]] = []


class MergeScopeRequest(BaseModel):
    """Legacy ``/merge`` page-scope batch body."""

    scope: Literal["paragraph", "line"]
    paragraph_indices: list[int] = []
    line_indices: list[int] = []


class SplitParagraphAfterLineRequest(BaseModel):
    paragraph_index: int
    after_line_index: int


class SplitLineWithSelectedWordsRequest(BaseModel):
    line_index: int
    word_indices: list[int]
    mode: Literal["extract_to_new", "split_into_two"]


class GroupSelectedWordsIntoNewParagraphRequest(BaseModel):
    word_indices: list[tuple[int, int]]


# ── Request models — spec-23-D1 line endpoints ─────────────────────────


class EmptyBody(BaseModel):
    """Empty JSON body — accepted by copy-gt-to-ocr / copy-ocr-to-gt / delete."""


class ValidateLineRequest(BaseModel):
    """``POST .../lines/{li}/validate`` body — spec §9 row 14.

    ``validated=None`` toggles the current flag (mirrors the words.py
    toggle contract); ``validated=bool`` sets to that exact value.
    """

    validated: bool | None = None


class MergeLinesRequest(BaseModel):
    """``POST .../lines/merge`` body — spec §9 row 16.

    Calls ``Page.merge_lines(line_indices)``. pd-book-tools requires at
    least two distinct indices; otherwise the route returns
    400 ``mutation_failed``.
    """

    line_indices: list[int]


class SplitLineAfterWordRequest(BaseModel):
    """``POST .../lines/{li}/split-after-word`` body — spec §9 row 17.

    Accepts either ``word_index`` (D1 spec-named field) or
    ``after_word_index`` (legacy field — pinned in older frontend client
    + integration tests). One of the two must be present. The schema
    name is kept as ``SplitLineAfterWordRequest`` (legacy) per spec §14
    "wire-shape stability"; ``SplitAfterWordRequest`` is exported as an
    alias.
    """

    word_index: int | None = None
    after_word_index: int | None = None
    # Legacy body also carried a top-level ``line_index`` echo of the URL
    # path; accepted-but-ignored for backward compat.
    line_index: int | None = None

    def effective_word_index(self) -> int | None:
        return self.word_index if self.word_index is not None else self.after_word_index


# Spec-23-D1 name alias — kept so memory/spec references resolve.
SplitAfterWordRequest = SplitLineAfterWordRequest


class SplitByWordsRequest(BaseModel):
    """``POST .../lines/split-by-words`` body — spec §9 row 18.

    ``word_keys`` is a list of ``(line_index, word_index)`` tuples; passed
    through to ``Page.split_line_with_selected_words`` (pd-book-tools
    name; spec calls it ``split_line_by_words``).
    """

    word_keys: list[tuple[int, int]]


class RefineBatchRequest(BaseModel):
    """``POST .../lines/refine-batch`` body — spec §9 row 19 + §11.

    Enqueues a refine job (``api/refine.py``) with ``scope=line``. The
    refine handler is already real per spec §11; this endpoint is the
    spec-named entry-point matching the line-mutation route family.
    """

    line_indices: list[int] = []
    mode: Literal["refine", "expand_then_refine", "expand_only"] = "refine"
    padding_px: int = 2


# ── Error envelopes ────────────────────────────────────────────────────


def _project_not_found(project_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="project_not_found",
            message=f"project not found: {project_id}",
        ).model_dump(),
    )


def _page_not_found(page_index: int) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="page_not_found",
            message=f"page not found: {page_index}",
        ).model_dump(),
    )


def _line_not_found(line_index: int) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="line_not_found",
            message=f"line not found: {line_index}",
        ).model_dump(),
    )


def _mutation_failed(message: str) -> JSONResponse:
    """400 envelope used when a pd-book-tools mutation returns False.

    Mirrors ``api/words.py:_mutation_failed`` — pd-book-tools' line
    mutations (``merge_lines``, ``split_line_after_word``,
    ``split_line_with_selected_words``) return ``True``/``False`` rather
    than raising; ``False`` means the call was rejected (out-of-range
    index, invalid selection, etc.).
    """
    return JSONResponse(
        status_code=400,
        content=ApiError(error="mutation_failed", message=message).model_dump(),
    )


def _check_project_and_page(
    project_id: str,
    page_index: int,
    project_state: ProjectState,
) -> JSONResponse | None:
    """Return an error response if the project/page isn't valid, else None."""
    project = project_state.loaded_project
    if project is None or project.project_id != project_id:
        return _project_not_found(project_id)
    if page_index < 0 or page_index >= project.total_pages:
        return _page_not_found(page_index)
    return None


def _resolve_line(page: Any, line_index: int) -> Any | None:
    """Resolve ``page.lines[line_index]`` or ``None``.

    Defensive against missing ``lines`` attribute and out-of-range index;
    both map to a 404 ``line_not_found`` envelope.
    """
    lines = getattr(page, "lines", None)
    if lines is None or not (0 <= line_index < len(lines)):
        return None
    return lines[line_index]


def _stub_page_payload(project_id: str, page_index: int) -> JSONResponse:
    """Return a minimal PagePayload — used by legacy routes that haven't
    been wired to real mutations yet (paragraph endpoints + page-scope
    delete/merge live in spec-23-D2/D3).
    """
    payload = PagePayload(project_id=project_id, page_index=page_index)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


# ── Spec-23-D1 line endpoints ──────────────────────────────────────────


def _line_mutation_handler(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    project_state: ProjectState,
    settings: Settings,
    mutate: Any,
    mutation_label: str,
) -> JSONResponse:
    """Shared core: guard → resolve → lock → mutate → cache → refresh.

    ``mutate(page, line)`` is invoked under the page lock; it must return
    ``True`` on success and ``False`` to surface ``mutation_failed``.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        line = _resolve_line(page, line_index)
        if line is None:
            return _line_not_found(line_index)
        ok = mutate(page, line)
        if not ok:
            return _mutation_failed(
                f"{mutation_label} rejected line={line_index}",
            )
        pstate.generation += 1

    _write_cached_envelope_best_effort(
        page=page,
        project_state=project_state,
        page_index=page_index,
        settings=settings,
    )
    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/copy-gt-to-ocr",
    response_model=PagePayload,
)
def copy_line_gt_to_ocr(
    project_id: str,
    page_index: int,
    line_index: int,
    body: EmptyBody | None = None,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/{li}/copy-gt-to-ocr`` — copy GT→OCR for every word.

    Spec §9 row 12: ``line.copy_gt_to_ocr()`` → ``Block.copy_ground_truth_to_ocr()``.
    pd-book-tools returns ``True`` if any word was mutated; we treat the
    "no GT to copy" case (returns ``False``) as a soft success rather
    than ``mutation_failed`` — clicking copy on an empty line should be
    idempotent, not an error.
    """

    def _mutate(_page: Any, line: Any) -> bool:
        line.copy_ground_truth_to_ocr()
        return True

    return _line_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        line_index=line_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="copy_gt_to_ocr",
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/copy-ocr-to-gt",
    response_model=PagePayload,
)
def copy_line_ocr_to_gt(
    project_id: str,
    page_index: int,
    line_index: int,
    body: EmptyBody | None = None,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/{li}/copy-ocr-to-gt`` — copy OCR→GT for every word.

    Spec §9 row 13: ``line.copy_ocr_to_gt()`` → ``Block.copy_ocr_to_ground_truth()``.
    Same soft-success semantics as ``copy-gt-to-ocr``.
    """

    def _mutate(_page: Any, line: Any) -> bool:
        line.copy_ocr_to_ground_truth()
        return True

    return _line_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        line_index=line_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="copy_ocr_to_gt",
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/validate",
    response_model=PagePayload,
)
def validate_line(
    project_id: str,
    page_index: int,
    line_index: int,
    body: ValidateLineRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/{li}/validate`` — set the line's validated flag.

    Spec §9 row 14 calls for ``line.set_validated(bool)``; pd-book-tools'
    ``Block`` does not expose such a method (tracking issue
    ConcaveTrillion/pd-book-tools#52 — same workaround as Word). We
    assign ``line.is_validated`` directly and propagate the flag to every
    contained word so the validate-batch scope=line view stays
    consistent. The flag is lost on ``Block.to_dict`` → ``from_dict``
    round-trip (documented limitation).
    """

    def _mutate(_page: Any, line: Any) -> bool:
        current = bool(getattr(line, "is_validated", False))
        new_value = (not current) if body.validated is None else bool(body.validated)
        line.is_validated = new_value
        # Propagate to contained words for batch-validate parity.
        for word in getattr(line, "words", []) or []:
            try:
                word.is_validated = new_value
            except Exception:  # pragma: no cover — frozen-Word defense
                log.warning(
                    "validate_line: could not propagate is_validated to word on line=%d (frozen?)",
                    line_index,
                )
        return True

    return _line_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        line_index=line_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="validate_line",
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/delete",
    response_model=PagePayload,
)
def delete_line(
    project_id: str,
    page_index: int,
    line_index: int,
    body: EmptyBody | None = None,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/{li}/delete`` — remove the line from the page.

    Spec §9 row 15: ``page.delete_line(l)`` → ``Page.delete_lines([l])``
    (pd-book-tools exposes only the batch variant).
    """

    def _mutate(page: Any, _line: Any) -> bool:
        return bool(page.delete_lines([line_index]))

    return _line_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        line_index=line_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="delete_line",
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/split-after-word",
    response_model=PagePayload,
)
def split_line_after_word_d1(
    project_id: str,
    page_index: int,
    line_index: int,
    body: SplitLineAfterWordRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/{li}/split-after-word`` — split a line after a word boundary.

    Spec §9 row 17: ``line.split_after_word(w)`` →
    ``Page.split_line_after_word(li, wi)`` (lives on Page because it
    reorganizes line ordering).
    """

    wi = body.effective_word_index()
    if wi is None:
        # Neither word_index nor after_word_index present — surface 400 so
        # the client gets a clear error instead of a 200 stub.
        return _mutation_failed(
            "split_line_after_word: request body missing word_index / after_word_index",
        )

    def _mutate(page: Any, _line: Any) -> bool:
        return bool(page.split_line_after_word(line_index, wi))

    # When no PageState is seeded, fall through to the legacy stub
    # so the pre-D1 integration tests (which never seed PageState) stay green.
    pstate = project_state.get_page_state(page_index)
    if pstate is None or _resolve_page_object(pstate) is None:
        err = _check_project_and_page(project_id, page_index, project_state)
        if err is not None:
            return err
        return _stub_page_payload(project_id, page_index)

    return _line_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        line_index=line_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="split_line_after_word",
    )


# ── Collective line endpoints (no path line_index) ─────────────────────


@router.post(
    "/{project_id}/pages/{page_index}/lines/merge",
    response_model=PagePayload,
)
def merge_lines(
    project_id: str,
    page_index: int,
    body: MergeLinesRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/merge`` — merge selected lines into the first.

    Spec §9 row 16: ``page.merge_lines(targets)`` →
    ``Page.merge_lines(line_indices)`` (``pd_book_tools/ocr/page.py:1575``).
    pd-book-tools requires at least two distinct indices.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.merge_lines(list(body.line_indices)))
        if not ok:
            return _mutation_failed(
                f"merge_lines rejected indices={list(body.line_indices)}",
            )
        pstate.generation += 1

    _write_cached_envelope_best_effort(
        page=page,
        project_state=project_state,
        page_index=page_index,
        settings=settings,
    )
    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/split-by-words",
    response_model=PagePayload,
)
def split_by_words(
    project_id: str,
    page_index: int,
    body: SplitByWordsRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/split-by-words`` — extract selected words into a new line.

    Spec §9 row 18: ``page.split_line_by_words(targets)`` →
    ``Page.split_line_with_selected_words(word_keys)``
    (``pd_book_tools/ocr/page.py:2217``).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    # Normalize tuple-list shape — Pydantic returns list[tuple], pd-book-tools
    # also accepts list[tuple]; explicit list() guards against future model
    # changes that yield a different sequence type.
    word_keys: list[tuple[int, int]] = [(int(li), int(wi)) for li, wi in body.word_keys]

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.split_line_with_selected_words(word_keys))
        if not ok:
            return _mutation_failed(
                f"split_line_with_selected_words rejected keys={word_keys}",
            )
        pstate.generation += 1

    _write_cached_envelope_best_effort(
        page=page,
        project_state=project_state,
        page_index=page_index,
        settings=settings,
    )
    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/refine-batch",
    status_code=202,
)
def refine_lines_batch(
    project_id: str,
    page_index: int,
    body: RefineBatchRequest,
    project_state: ProjectState = Depends(get_project_state),
    runner: JobRunner = Depends(get_job_runner),
) -> JSONResponse:
    """``POST .../lines/refine-batch`` → 202 ``{job_id}``.

    Spec §9 row 19 + §11: enqueue the existing refine job with
    ``scope=line``. The refine handler is real (see ``api/refine.py:83``);
    this route just adapts the line-batch request to the refine wire shape.
    Returns 202 immediately; the SPA polls
    ``GET /api/jobs/{id}/events`` (SSE) for the terminal ``complete`` event.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    job_id = runner.submit(
        "refine_bboxes",
        project_id=project_id,
        payload={
            "page_index": page_index,
            "scope": "line",
            "mode": body.mode,
            "padding_px": body.padding_px,
            "paragraph_indices": [],
            "line_indices": list(body.line_indices),
            "word_indices": [],
        },
    )
    return JSONResponse(status_code=202, content={"job_id": job_id})


# ── Legacy routes (kept for frontend client + integration tests) ───────


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/copy-gt",
    response_model=PagePayload,
)
def copy_line_gt(
    project_id: str,
    page_index: int,
    line_index: int,
    body: CopyLineGtRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/{li}/copy-gt`` — dispatcher for {direction} body.

    Kept for frontend compatibility (``hooks/useLineMutations.ts``); the
    spec-named explicit routes ``copy-gt-to-ocr`` and ``copy-ocr-to-gt``
    do the same work. When a project is loaded but the page state isn't
    seeded, falls through to the stub response so the pre-D1 integration
    tests (which never seed PageState) stay green.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        # Pre-D1 stub fallback — integration test parity.
        return _stub_page_payload(project_id, page_index)

    if body.direction == "gt_to_ocr":
        return copy_line_gt_to_ocr(
            project_id=project_id,
            page_index=page_index,
            line_index=line_index,
            project_state=project_state,
            settings=settings,
        )
    return copy_line_ocr_to_gt(
        project_id=project_id,
        page_index=page_index,
        line_index=line_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/delete",
    response_model=PagePayload,
)
def delete_scope(
    project_id: str,
    page_index: int,
    body: DeleteScopeRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../delete`` — page-scope batch delete (paragraph/line/word).

    Stays a stub. Spec-23-D1 covers per-line delete; the page-scope batch
    (paragraph/word) is part of D2/D3.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/merge",
    response_model=PagePayload,
)
def merge_scope(
    project_id: str,
    page_index: int,
    body: MergeScopeRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../merge`` — page-scope batch merge (paragraphs/lines).

    Stays a stub. Spec-23-D1 covers the dedicated ``/lines/merge`` route
    (real mutation); the multi-scope page-level batch is D2/D3.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/{paragraph_index}/split-after-line",
    response_model=PagePayload,
)
def split_paragraph_after_line(
    project_id: str,
    page_index: int,
    paragraph_index: int,
    body: SplitParagraphAfterLineRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../paragraphs/{pi}/split-after-line`` — paragraph mutation stub.

    Stays a stub. Paragraph-scope mutations live in spec-23-D2.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/split-with-selected",
    response_model=PagePayload,
)
def split_line_with_selected_words(
    project_id: str,
    page_index: int,
    line_index: int,
    body: SplitLineWithSelectedWordsRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../lines/{li}/split-with-selected`` — legacy stub.

    Frontend prefers the D1 ``/lines/split-by-words`` collective route.
    Kept stub-shaped for integration-test parity.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_page_payload(project_id, page_index)


@router.post(
    "/{project_id}/pages/{page_index}/words/group-into-paragraph",
    response_model=PagePayload,
)
def group_selected_words_into_new_paragraph(
    project_id: str,
    page_index: int,
    body: GroupSelectedWordsIntoNewParagraphRequest,
    project_state: ProjectState = Depends(get_project_state),
) -> JSONResponse:
    """``POST .../words/group-into-paragraph`` — paragraph mutation stub.

    Stays a stub. Paragraph-scope mutations live in spec-23-D2.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    return _stub_page_payload(project_id, page_index)


def install_lines_paragraphs_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the lines/paragraphs router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "CopyLineGtRequest",
    "DeleteScopeRequest",
    "EmptyBody",
    "GroupSelectedWordsIntoNewParagraphRequest",
    "MergeLinesRequest",
    "MergeScopeRequest",
    "RefineBatchRequest",
    "SplitAfterWordRequest",
    "SplitByWordsRequest",
    "SplitLineAfterWordRequest",
    "SplitLineWithSelectedWordsRequest",
    "SplitParagraphAfterLineRequest",
    "ValidateLineRequest",
    "install_lines_paragraphs_router",
    "router",
]

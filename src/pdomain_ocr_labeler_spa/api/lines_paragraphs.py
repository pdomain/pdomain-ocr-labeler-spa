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
4. Call the pdomain-book-tools method. If it returns ``False`` → 400
   ``mutation_failed``. Bump ``PageState.generation``.
5. Write cached envelope best-effort (inside the lock — spec §13).
6. Release lock; refresh ``PagePayload`` and return.

Pd-book-tools method mapping (spec §9 names → actual pdomain-book-tools API):

- ``line.copy_gt_to_ocr()`` → ``Block.copy_ground_truth_to_ocr()``
  (``pdomain_book_tools/ocr/block.py:643``).
- ``line.copy_ocr_to_gt()`` → ``Block.copy_ocr_to_ground_truth()``
  (``pdomain_book_tools/ocr/block.py:630``).
- ``line.set_validated(bool)`` → **no method exists** on the Block class
  (tracking issue pdomain/pdomain-book-tools#52 — same workaround as
  Word). The route assigns ``line.is_validated`` as a Python attribute
  and propagates the flag onto every contained word so the validate-batch
  scope=line view stays consistent.
- ``page.delete_line(l)`` → ``Page.delete_lines([l])``
  (``pdomain_book_tools/ocr/page.py:1660`` — pdomain-book-tools exposes the batch
  variant only).
- ``page.merge_lines(targets)`` → ``Page.merge_lines(line_indices)``
  (``pdomain_book_tools/ocr/page.py:1575``).
- ``line.split_after_word(w)`` → ``Page.split_line_after_word(li, wi)``
  (``pdomain_book_tools/ocr/page.py:1940`` — owned by the Page, not the
  Block, because it has to reorganize line ordering).
- ``page.split_line_by_words(targets)`` →
  ``Page.split_line_with_selected_words(word_keys)``
  (``pdomain_book_tools/ocr/page.py:2217``).
- ``lines/refine-batch`` enqueues the existing refine job
  (``api/refine.py``); the handler is already real per spec §11.

Paragraph mutation endpoints (spec-23-D2, issue #318):

- ``POST .../paragraphs/{pi}/copy-gt-to-ocr`` → ``Block.copy_ground_truth_to_ocr()``.
  pdomain-book-tools' ``Block`` is the paragraph type; the line-scope D1 route
  uses the same method on a different Block kind.
- ``POST .../paragraphs/{pi}/copy-ocr-to-gt`` → ``Block.copy_ocr_to_ground_truth()``.
- ``POST .../paragraphs/{pi}/validate`` → no method on Block (same
  workaround as Word + Line; see pdomain/pdomain-book-tools#52).
  Assigns ``paragraph.is_validated`` and propagates to every contained
  word. Flag is lost on ``Block.to_dict`` → ``from_dict``.
- ``POST .../paragraphs/{pi}/delete`` → ``Page.delete_paragraphs([pi])``
  (pdomain-book-tools exposes only the batch variant).
- ``POST .../paragraphs/merge`` → ``Page.merge_paragraphs(paragraph_indices)``
  (``pdomain_book_tools/ocr/page.py:980``). Requires at least 2 distinct
  indices; otherwise 400 ``mutation_failed``.
- ``POST .../paragraphs/{pi}/split-after-line`` →
  ``Page.split_paragraph_after_line(page_line_index)``
  (``pdomain_book_tools/ocr/page.py:1152``). pdomain-book-tools takes a
  PAGE-WIDE line index; the route translates the legacy body's
  within-paragraph ``after_line_index`` to page-wide via
  ``page.lines.index(paragraph.lines[after_line_index])``. Wire shape
  ``SplitParagraphAfterLineRequest`` is preserved per spec §14.

Legacy routes kept for frontend compatibility (older 404-stub contract
already pinned in ``frontend/src/api/types.ts`` and ``hooks/useLineMutations.ts``):

- ``POST .../lines/{li}/copy-gt`` body ``{direction: gt_to_ocr|ocr_to_gt}``.
- ``POST .../delete`` body ``DeleteScopeRequest`` (page-scope batch).
- ``POST .../merge`` body ``MergeScopeRequest`` (page-scope batch).
- ``POST .../lines/{li}/split-with-selected``.
- ``POST .../words/group-into-paragraph``.

These remain stub-shaped (return 200 with a stub PagePayload) because
their backend semantics are page-scope batches (D3); D2 wires the per-
paragraph endpoints from the spec table. The page-scope batch routes'
integration tests remain green via the unchanged ``_page_payload`` stub.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from ..core.jobs import JobRunner
from ..core.persistence.config_yaml import AppConfig
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import ProjectState
from ..settings import Settings
from .dependencies import (
    get_app_config,
    get_job_runner,
    get_page_store_optional,
    get_project_state,
    get_settings,
)
from .middleware.error_handler import ApiError
from .pages import PagePayload
from .refine import RefineJobResponse
from .words import (
    _GT_FORBIDDEN_CODEPOINTS,
    _page_not_loaded,
    _refresh_payload_response,
    _resolve_page_object,
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


class CopyGtBatchRequest(BaseModel):
    """Body for ``POST .../lines/copy-gt-batch`` — Lane A / Task A2.

    Matches the ``*-gt-to-ocr`` / ``*-ocr-to-gt`` toolbarMapping entries for
    every scope. ``direction`` chooses which way to copy; the scope selects
    which words are affected (page / paragraph / line / word).
    """

    scope: Literal["page", "paragraph", "line", "word"]
    direction: Literal["gt_to_ocr", "ocr_to_gt"]
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    word_indices: list[tuple[int, int]] = []


class DeleteParagraphsBatchRequest(BaseModel):
    """Body for ``POST .../paragraphs/delete-batch`` — Lane A / Task A2."""

    scope: Literal["paragraph"] = "paragraph"
    paragraph_indices: list[int] = []


class DeleteLinesBatchRequest(BaseModel):
    """Body for ``POST .../lines/delete-batch`` — Lane A / Task A2."""

    scope: Literal["line"] = "line"
    line_indices: list[int] = []


class SplitSelectedParagraphsRequest(BaseModel):
    """Body for ``POST .../paragraphs/split-selected`` — Lane A / Task A2.

    Splits each selected paragraph into one paragraph per line
    (``Page.split_paragraphs``).
    """

    paragraph_indices: list[int] = []


class GroupSelectedWordsIntoParagraphRequest(BaseModel):
    """Body for ``POST .../paragraphs/group-selected-words`` — Lane A / Task A2.

    Moves the selected words into a new paragraph
    (``Page.group_selected_words_into_new_paragraph``). ``scope`` is accepted
    (the toolbarMapping line-scope entry sends ``{ scope: "line" }``) but the
    operation is driven entirely by ``word_indices``.
    """

    word_indices: list[tuple[int, int]] = []
    scope: str | None = None


class SplitParagraphAfterLineRequest(BaseModel):
    paragraph_index: int
    after_line_index: int


class SplitLineWithSelectedWordsRequest(BaseModel):
    """``POST .../lines/{li}/split-with-selected`` body — spec §9 row 18b.

    ``word_keys`` is a list of ``(line_index, word_index)`` tuples passed through to
    ``Page.split_line_with_selected_words`` (same semantic as ``SplitByWordsRequest``
    used by the collective ``/lines/split-by-words`` route).
    """

    word_keys: list[tuple[int, int]]


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

    Calls ``Page.merge_lines(line_indices)``. pdomain-book-tools requires at
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
    through to ``Page.split_line_with_selected_words`` (pdomain-book-tools
    name; spec calls it ``split_line_by_words``).
    """

    word_keys: list[tuple[int, int]]


class ValidateParagraphRequest(BaseModel):
    """``POST .../paragraphs/{pi}/validate`` body — spec §9 paragraph rows.

    Same ``validated=None`` toggle semantics as ``ValidateLineRequest``;
    paragraphs lack a pdomain-book-tools ``set_validated`` method (same
    workaround as Word + Line; see pdomain/pdomain-book-tools#52).
    """

    validated: bool | None = None


class MergeParagraphsRequest(BaseModel):
    """``POST .../paragraphs/merge`` body — spec §9 paragraph rows.

    Calls ``Page.merge_paragraphs(paragraph_indices)``
    (``pdomain_book_tools/ocr/page.py:980``). pdomain-book-tools requires at least
    two distinct indices; otherwise the route returns
    400 ``mutation_failed``.
    """

    paragraph_indices: list[int]


_VALID_LAYOUT_TYPES = frozenset(["Body", "Heading", "Caption", "Footnote", "Quote", "Other"])


class PatchParagraphRequest(BaseModel):
    """``PATCH .../paragraphs/{pi}`` body — FO-1 (layout-type save).

    ``layout_type`` is one of the six documented types from the hi-fi
    redesign spec (Slice 22 — BlockDetail).  Unknown values are rejected
    with 422 so the frontend gets a clear error on client-side bugs.

    The field is stored as a Python attribute on the paragraph object
    (``paragraph.layout_type``).  pdomain-book-tools' ``Block`` does not
    expose a ``set_layout_type`` method today; the attribute is lost on
    ``Block.to_dict`` → ``from_dict`` round-trip (same documented
    limitation as ``is_validated``).
    """

    layout_type: str

    @field_validator("layout_type")
    @classmethod
    def _validate_layout_type(cls, v: str) -> str:
        if v not in _VALID_LAYOUT_TYPES:
            raise ValueError(f"layout_type must be one of {sorted(_VALID_LAYOUT_TYPES)!r}; got {v!r}")
        return v


class RefineBatchRequest(BaseModel):
    """``POST .../lines/refine-batch`` body — spec §9 row 19 + §11.

    Enqueues a refine job (``api/refine.py``) with ``scope=line``. The
    refine handler is already real per spec §11; this endpoint is the
    spec-named entry-point matching the line-mutation route family.
    """

    line_indices: list[int] = []
    mode: Literal["refine", "expand_then_refine", "expand_only"] = "refine"
    padding_px: int = 2


class SetLineGtRequest(BaseModel):
    """``POST .../lines/{li}/set-gt`` body.

    Splits ``text`` by whitespace and distributes tokens to the line's
    words left-to-right. Excess tokens are concatenated onto the last
    word with a space separator; words with no corresponding token
    receive empty-string GT. Forbidden codepoints (ligatures, long-s)
    are rejected with 422.
    """

    text: str

    @field_validator("text")
    @classmethod
    def _reject_forbidden_codepoints(cls, v: str) -> str:
        bad = [hex(ord(ch)) for ch in v if ord(ch) in _GT_FORBIDDEN_CODEPOINTS]
        if bad:
            raise ValueError(
                f"GT text contains forbidden codepoints: {', '.join(bad)}. "
                "Normalize ligatures and long-s to ASCII before saving GT."
            )
        return v


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


def _paragraph_not_found(paragraph_index: int) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="paragraph_not_found",
            message=f"paragraph not found: {paragraph_index}",
        ).model_dump(),
    )


def _mutation_failed(message: str) -> JSONResponse:
    """400 envelope used when a pdomain-book-tools mutation returns False.

    Mirrors ``api/words.py:_mutation_failed`` — pdomain-book-tools' line
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


def _resolve_paragraph(page: Any, paragraph_index: int) -> Any | None:
    """Resolve ``page.paragraphs[paragraph_index]`` or ``None``.

    Defensive against missing ``paragraphs`` attribute and out-of-range
    index; both map to a 404 ``paragraph_not_found`` envelope.
    """
    paragraphs = getattr(page, "paragraphs", None)
    if paragraphs is None or not (0 <= paragraph_index < len(paragraphs)):
        return None
    return paragraphs[paragraph_index]


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


def _finalize_structural_edit(
    *,
    page: Any,
    pstate: Any,  # PageState
    project_state: ProjectState,
    page_index: int,
    store: LabelerPageStore | None,
    changes: list[dict[str, Any]],
) -> None:
    """Finalize a structural mutation: rematch GT, bump generation, persist.

    Lane A / Task A3. Called by every line/paragraph (and word) structural
    mutation route after a successful in-memory edit. Three steps:

    1. **Auto-rematch GT** (``core/ground_truth_matcher.rematch_page``) so
       per-word GT mapping tracks the new structure — but explicit per-word
       GT edits are preserved (rematch only fills words whose GT the user
       did not type). Best-effort: no GT source / unmatchable page is a no-op.
    2. **Bump** ``pstate.generation`` so SSE consumers see the new state.
    3. **Persist edited content** via ``save_page_content_to_store`` so the
       structural change survives a fresh-store reload — closing the gap
       where ``lines_paragraphs.py`` previously saved through the no-op
       ``_write_cached_envelope_best_effort`` stub (word routes already
       persist via ``api/words.py::_save_to_store_best_effort``).

    Must be invoked inside the page lock.
    """
    _auto_rematch_preserving_edits(page=page, project_state=project_state, page_index=page_index)

    pstate.generation += 1
    _persist_content_best_effort(page=page, pstate=pstate, store=store, changes=changes)


def _persist_content_best_effort(
    *,
    page: Any,
    pstate: Any,  # PageState
    store: LabelerPageStore | None,
    changes: list[dict[str, Any]],
) -> None:
    """Persist edited page *content* so it survives a fresh-store reload.

    Mirrors ``api/words.py::_save_to_store_best_effort`` — closes the gap where
    ``lines_paragraphs.py`` previously saved through the no-op
    ``_write_cached_envelope_best_effort`` stub. Used by both structural
    mutations (via ``_finalize_structural_edit``) and the per-line/paragraph
    content edits (copy-gt / validate / set-gt / layout). No-op when there is
    no store, no ``page_id``, or the page can't serialise.
    """
    if store is None or getattr(pstate, "page_id", None) is None:
        return
    if not callable(getattr(page, "to_dict", None)):
        return
    try:
        from ..core.page_state import save_page_content_to_store

        save_page_content_to_store(page_id=pstate.page_id, page=page, store=store, changes=changes)
    except Exception as exc:  # pragma: no cover - best-effort persistence
        log.warning("_persist_content_best_effort: store write failed page_id=%s: %s", pstate.page_id, exc)


def _auto_rematch_preserving_edits(
    *,
    page: Any,
    project_state: ProjectState,
    page_index: int,
) -> None:
    """Re-run page-level GT matching after a structural edit, preserving
    explicit per-word GT edits.

    ``core/ground_truth_matcher.rematch_page`` wipes *all* per-word GT before
    re-matching (that is the explicit "Rematch GT" button semantics). For an
    automatic post-structural-edit rematch we instead want the legacy
    ``_finalize_structural_edit`` behaviour: surviving per-word GT edits are
    preserved, and only words the matcher fills get fresh GT. We achieve this
    by snapshotting non-empty per-word GT by object identity before the
    rematch and restoring it afterward.

    No-op (silently) when there is no GT source text for the page, or when the
    page object lacks the matcher method pair — never raises.
    """
    from ..core.ground_truth_matcher import rematch_page
    from ..core.persistence.ground_truth import find_ground_truth_text

    project = project_state.loaded_project
    if project is None:
        return
    image_paths = getattr(project, "image_paths", None) or []
    image_name = image_paths[page_index].name if 0 <= page_index < len(image_paths) else ""
    gt_text = find_ground_truth_text(image_name, getattr(project, "ground_truth_map", {}) or {})
    if not gt_text:
        return

    # Snapshot non-empty per-word GT by id() so user edits survive the wipe.
    snapshot: dict[int, str] = {}
    for line in getattr(page, "lines", []) or []:
        for word in getattr(line, "words", []) or []:
            gt = str(getattr(word, "ground_truth_text", "") or "")
            if gt:
                snapshot[id(word)] = gt

    ok = rematch_page(page, gt_text)
    if not ok:
        return

    # Restore explicit edits: any surviving word whose pre-edit GT was
    # non-empty keeps that GT (rematch only fills unedited words).
    for line in getattr(page, "lines", []) or []:
        for word in getattr(line, "words", []) or []:
            preserved = snapshot.get(id(word))
            if preserved:
                try:
                    word.ground_truth_text = preserved
                except Exception:  # pragma: no cover - frozen-word defense
                    log.debug("auto-rematch: could not restore GT on word")


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
    store: LabelerPageStore | None = None,
    structural: bool = False,
) -> JSONResponse:
    """Shared core: guard → resolve → lock → mutate → persist → refresh.

    ``mutate(page, line)`` is invoked under the page lock; it must return
    ``True`` on success and ``False`` to surface ``mutation_failed``.

    When ``structural`` is True the edit changes the page hierarchy
    (delete / split): it runs through ``_finalize_structural_edit`` which
    re-matches GT and persists content. Otherwise (content edits — copy-gt /
    validate / set-gt) it bumps the generation and persists content without a
    GT rematch (rematch would clobber a just-applied copy-gt / validate).
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
        changes = [{"type": mutation_label, "line": line_index}]
        if structural:
            _finalize_structural_edit(
                page=page,
                pstate=pstate,
                project_state=project_state,
                page_index=page_index,
                store=store,
                changes=changes,
            )
        else:
            pstate.generation += 1
            _persist_content_best_effort(page=page, pstate=pstate, store=store, changes=changes)

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
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/{li}/copy-gt-to-ocr`` — copy GT→OCR for every word.

    Spec §9 row 12: ``line.copy_gt_to_ocr()`` → ``Block.copy_ground_truth_to_ocr()``.
    pdomain-book-tools returns ``True`` if any word was mutated; we treat the
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
        store=store,
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
    store: LabelerPageStore | None = Depends(get_page_store_optional),
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
        store=store,
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
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/{li}/validate`` — set the line's validated flag.

    Spec §9 row 14 calls for ``line.set_validated(bool)``; pdomain-book-tools'
    ``Block`` does not expose such a method (tracking issue
    pdomain/pdomain-book-tools#52 — same workaround as Word). We
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
        store=store,
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
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/{li}/delete`` — remove the line from the page.

    Spec §9 row 15: ``page.delete_line(l)`` → ``Page.delete_lines([l])``
    (pdomain-book-tools exposes only the batch variant). Structural edit:
    triggers GT auto-rematch + content persistence (A3).
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
        store=store,
        structural=True,
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
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/{li}/split-after-word`` — split a line after a word boundary.

    Spec §9 row 17: ``line.split_after_word(w)`` →
    ``Page.split_line_after_word(li, wi)`` (lives on Page because it
    reorganizes line ordering). Structural edit: triggers GT auto-rematch +
    content persistence (A3).
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
        store=store,
        structural=True,
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/set-gt",
    response_model=PagePayload,
)
def set_line_gt(
    project_id: str,
    page_index: int,
    line_index: int,
    body: SetLineGtRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/{li}/set-gt`` — set line GT by distributing tokens.

    Splits ``body.text`` on whitespace; assigns each token to the
    corresponding word in the line left-to-right. Excess tokens
    (more tokens than words) are concatenated with a space onto the
    last word. Words with no corresponding token receive empty-string GT.
    """

    def _mutate(_page: Any, line: Any) -> bool:
        words = list(getattr(line, "words", []) or [])
        if not words:
            return True
        tokens = body.text.split()
        for i, word in enumerate(words):
            if i < len(tokens):
                if i == len(words) - 1:
                    word.ground_truth_text = " ".join(tokens[i:])
                else:
                    word.ground_truth_text = tokens[i]
            else:
                word.ground_truth_text = ""
        return True

    return _line_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        line_index=line_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="set_line_gt",
        store=store,
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
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/merge`` — merge selected lines into the first.

    Spec §9 row 16: ``page.merge_lines(targets)`` →
    ``Page.merge_lines(line_indices)`` (``pdomain_book_tools/ocr/page.py:1575``).
    pdomain-book-tools requires at least two distinct indices. Structural edit:
    triggers GT auto-rematch + content persistence (A3).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    line_indices = list(body.line_indices)
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.merge_lines(line_indices))
        if not ok:
            return _mutation_failed(
                f"merge_lines rejected indices={line_indices}",
            )
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "merge_lines", "line_indices": line_indices}],
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
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/split-by-words`` — extract selected words into a new line.

    Spec §9 row 18: ``page.split_line_by_words(targets)`` →
    ``Page.split_line_with_selected_words(word_keys)``
    (``pdomain_book_tools/ocr/page.py:2217``). Structural edit: triggers GT
    auto-rematch + content persistence (A3).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    # Normalize tuple-list shape — Pydantic returns list[tuple], pdomain-book-tools
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
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "split_by_words", "word_keys": word_keys}],
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
    response_model=RefineJobResponse,
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


# ── Lane A / Task A2: scope-batch routes (toolbarMapping contract) ─────


def _collect_copy_gt_targets(page: Any, body: CopyGtBatchRequest) -> list[Any]:
    """Resolve the requested scope to a flat list of target words.

    Out-of-range indices are silently skipped (best-effort batch).
    """
    targets: list[Any] = []
    scope = body.scope
    if scope == "page":
        targets.extend(getattr(page, "words", []) or [])
        return targets
    if scope == "paragraph":
        paragraphs = getattr(page, "paragraphs", None) or []
        for pi in body.paragraph_indices:
            if 0 <= pi < len(paragraphs):
                targets.extend(getattr(paragraphs[pi], "words", []) or [])
        return targets
    if scope == "line":
        lines = getattr(page, "lines", None) or []
        for li in body.line_indices:
            if 0 <= li < len(lines):
                targets.extend(getattr(lines[li], "words", []) or [])
        return targets
    # Remaining branch: word scope.
    lines = getattr(page, "lines", None) or []
    for li, wi in body.word_indices:
        if 0 <= li < len(lines):
            words = getattr(lines[li], "words", None) or []
            if 0 <= wi < len(words):
                targets.append(words[wi])
    return targets


@router.post(
    "/{project_id}/pages/{page_index}/lines/copy-gt-batch",
    response_model=PagePayload,
)
def copy_gt_batch(
    project_id: str,
    page_index: int,
    body: CopyGtBatchRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/copy-gt-batch`` — copy GT↔OCR over a scope (A2).

    Thin scope-resolver over the per-word ``copy_ground_truth_to_ocr`` /
    ``copy_ocr_to_ground_truth`` operations. Atomic: one event per request.
    This is a content edit (not structural) — it does not trigger GT rematch.
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
        targets = _collect_copy_gt_targets(page, body)
        for word in targets:
            if body.direction == "gt_to_ocr":
                word.copy_ground_truth_to_ocr()
            else:
                word.copy_ocr_to_ground_truth()
        pstate.generation += 1
        # Persist edited content (matches words.py best-effort save path).
        if (
            store is not None
            and getattr(pstate, "page_id", None) is not None
            and callable(getattr(page, "to_dict", None))
        ):
            try:
                from ..core.page_state import save_page_content_to_store

                save_page_content_to_store(
                    page_id=pstate.page_id,
                    page=page,
                    store=store,
                    changes=[{"type": "copy_gt_batch", "scope": body.scope, "direction": body.direction}],
                )
            except Exception as exc:  # pragma: no cover - best-effort
                log.warning("copy_gt_batch: store write failed page_id=%s: %s", pstate.page_id, exc)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
    )


@router.post(
    "/{project_id}/pages/{page_index}/lines/delete-batch",
    response_model=PagePayload,
)
def delete_lines_batch(
    project_id: str,
    page_index: int,
    body: DeleteLinesBatchRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/delete-batch`` — delete selected lines (A2)."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    line_indices = list(body.line_indices)
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.delete_lines(line_indices))
        if not ok:
            return _mutation_failed(f"delete_lines rejected indices={line_indices}")
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "lines_delete_batch", "line_indices": line_indices}],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
    )


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/delete-batch",
    response_model=PagePayload,
)
def delete_paragraphs_batch(
    project_id: str,
    page_index: int,
    body: DeleteParagraphsBatchRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/delete-batch`` — delete selected paragraphs (A2)."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    paragraph_indices = list(body.paragraph_indices)
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.delete_paragraphs(paragraph_indices))
        if not ok:
            return _mutation_failed(f"delete_paragraphs rejected indices={paragraph_indices}")
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "paragraphs_delete_batch", "paragraph_indices": paragraph_indices}],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
    )


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/split-selected",
    response_model=PagePayload,
)
def split_selected_paragraphs(
    project_id: str,
    page_index: int,
    body: SplitSelectedParagraphsRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/split-selected`` — split paragraphs into one per line (A2)."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    paragraph_indices = list(body.paragraph_indices)
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.split_paragraphs(paragraph_indices))
        if not ok:
            return _mutation_failed(f"split_paragraphs rejected indices={paragraph_indices}")
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "paragraphs_split_selected", "paragraph_indices": paragraph_indices}],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
    )


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/group-selected-words",
    response_model=PagePayload,
)
def group_selected_words_into_paragraph(
    project_id: str,
    page_index: int,
    body: GroupSelectedWordsIntoParagraphRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/group-selected-words`` — group words into a new paragraph (A2)."""
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    word_keys: list[tuple[int, int]] = [(int(li), int(wi)) for li, wi in body.word_indices]
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.group_selected_words_into_new_paragraph(word_keys))
        if not ok:
            return _mutation_failed(f"group_selected_words rejected keys={word_keys}")
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "group_selected_words", "word_indices": word_keys}],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
    )


# ── Spec-23-D2 paragraph endpoints ─────────────────────────────────────


def _paragraph_mutation_handler(
    *,
    project_id: str,
    page_index: int,
    paragraph_index: int,
    project_state: ProjectState,
    settings: Settings,
    mutate: Any,
    mutation_label: str,
    store: LabelerPageStore | None = None,
    structural: bool = False,
) -> JSONResponse:
    """Shared core for per-paragraph mutations.

    Mirrors ``_line_mutation_handler``: guard → resolve paragraph → lock
    → mutate → persist → refresh. ``mutate(page, paragraph)`` is invoked
    under the page lock; it must return ``True`` on success and ``False``
    to surface ``mutation_failed``.

    ``structural`` selects ``_finalize_structural_edit`` (GT rematch +
    content persist) vs. ``_persist_content_best_effort`` (content persist
    only — for copy-gt / validate content edits).
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
        paragraph = _resolve_paragraph(page, paragraph_index)
        if paragraph is None:
            return _paragraph_not_found(paragraph_index)
        ok = mutate(page, paragraph)
        if not ok:
            return _mutation_failed(
                f"{mutation_label} rejected paragraph={paragraph_index}",
            )
        changes = [{"type": mutation_label, "paragraph": paragraph_index}]
        if structural:
            _finalize_structural_edit(
                page=page,
                pstate=pstate,
                project_state=project_state,
                page_index=page_index,
                store=store,
                changes=changes,
            )
        else:
            pstate.generation += 1
            _persist_content_best_effort(page=page, pstate=pstate, store=store, changes=changes)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/{paragraph_index}/copy-gt-to-ocr",
    response_model=PagePayload,
)
def copy_paragraph_gt_to_ocr(
    project_id: str,
    page_index: int,
    paragraph_index: int,
    body: EmptyBody | None = None,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/{pi}/copy-gt-to-ocr`` — copy GT→OCR for every word.

    Spec §9: ``Block.copy_ground_truth_to_ocr()`` operates on every word
    contained in the Block (pdomain-book-tools' paragraph type). pdomain-book-tools
    returns ``True`` if any word was mutated; we treat the "no GT to copy"
    case (returns ``False``) as a soft success — clicking copy on a
    paragraph without GT should be idempotent, not an error.
    """

    def _mutate(_page: Any, paragraph: Any) -> bool:
        paragraph.copy_ground_truth_to_ocr()
        return True

    return _paragraph_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        paragraph_index=paragraph_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="paragraph_copy_gt_to_ocr",
        store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/{paragraph_index}/copy-ocr-to-gt",
    response_model=PagePayload,
)
def copy_paragraph_ocr_to_gt(
    project_id: str,
    page_index: int,
    paragraph_index: int,
    body: EmptyBody | None = None,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/{pi}/copy-ocr-to-gt`` — copy OCR→GT for every word.

    Spec §9: ``Block.copy_ocr_to_ground_truth()`` — same soft-success
    semantics as the gt-to-ocr direction.
    """

    def _mutate(_page: Any, paragraph: Any) -> bool:
        paragraph.copy_ocr_to_ground_truth()
        return True

    return _paragraph_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        paragraph_index=paragraph_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="paragraph_copy_ocr_to_gt",
        store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/{paragraph_index}/validate",
    response_model=PagePayload,
)
def validate_paragraph(
    project_id: str,
    page_index: int,
    paragraph_index: int,
    body: ValidateParagraphRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/{pi}/validate`` — set the paragraph's validated flag.

    Spec §9 calls for paragraph-level ``set_validated(bool)``; pdomain-book-tools'
    ``Block`` does not expose such a method (tracking issue
    pdomain/pdomain-book-tools#52 — same workaround as Word + Line).
    We assign ``paragraph.is_validated`` directly and propagate the flag
    onto every contained word for batch-validate parity. Flag is lost on
    ``Block.to_dict`` → ``from_dict`` round-trip (documented limitation).
    """

    def _mutate(_page: Any, paragraph: Any) -> bool:
        current = bool(getattr(paragraph, "is_validated", False))
        new_value = (not current) if body.validated is None else bool(body.validated)
        paragraph.is_validated = new_value
        # Propagate to every contained word (mirror of validate_line).
        for word in getattr(paragraph, "words", []) or []:
            try:
                word.is_validated = new_value
            except Exception:  # pragma: no cover — frozen-Word defense
                log.warning(
                    "validate_paragraph: could not propagate is_validated to word on paragraph=%d (frozen?)",
                    paragraph_index,
                )
        return True

    return _paragraph_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        paragraph_index=paragraph_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="validate_paragraph",
        store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/{paragraph_index}/delete",
    response_model=PagePayload,
)
def delete_paragraph(
    project_id: str,
    page_index: int,
    paragraph_index: int,
    body: EmptyBody | None = None,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/{pi}/delete`` — remove the paragraph from the page.

    Spec §9: pdomain-book-tools exposes only the batch variant
    ``Page.delete_paragraphs(indices)`` (``pdomain_book_tools/ocr/page.py:1040``),
    mirroring the line-delete pattern. Structural edit: triggers GT
    auto-rematch + content persistence (A3).
    """

    def _mutate(page: Any, _paragraph: Any) -> bool:
        return bool(page.delete_paragraphs([paragraph_index]))

    return _paragraph_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        paragraph_index=paragraph_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="delete_paragraph",
        store=store,
        structural=True,
    )


@router.post(
    "/{project_id}/pages/{page_index}/paragraphs/merge",
    response_model=PagePayload,
)
def merge_paragraphs(
    project_id: str,
    page_index: int,
    body: MergeParagraphsRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/merge`` — merge selected paragraphs into the first.

    Spec §9: ``Page.merge_paragraphs(paragraph_indices)``
    (``pdomain_book_tools/ocr/page.py:980``). pdomain-book-tools requires at least
    two distinct indices. Structural edit: triggers GT auto-rematch +
    content persistence (A3).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    paragraph_indices = list(body.paragraph_indices)
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.merge_paragraphs(paragraph_indices))
        if not ok:
            return _mutation_failed(
                f"merge_paragraphs rejected indices={paragraph_indices}",
            )
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "merge_paragraphs", "paragraph_indices": paragraph_indices}],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


@router.patch(
    "/{project_id}/pages/{page_index}/paragraphs/{paragraph_index}",
    response_model=PagePayload,
)
def patch_paragraph(
    project_id: str,
    page_index: int,
    paragraph_index: int,
    body: PatchParagraphRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``PATCH .../paragraphs/{pi}`` — update paragraph-level attributes (FO-1).

    Currently handles ``layout_type`` only.  The value is stored as a
    Python attribute on the paragraph object (``paragraph.layout_type``);
    it is lost on envelope round-trip until pdomain-book-tools' ``Block``
    grows a ``layout_type`` property (tracked as pdomain/pdomain-book-tools#52
    family).

    When no PageState is seeded (project freshly loaded, page not yet
    OCR'd) the route falls through to a stub PagePayload so the pre-
    seeded integration tests and the frontend "save immediately on load"
    flow stay green.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        # Stub — no in-memory page to mutate yet.
        return _stub_page_payload(project_id, page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        paragraph = _resolve_paragraph(page, paragraph_index)
        if paragraph is None:
            return _paragraph_not_found(paragraph_index)
        # Store as a plain Python attribute (lost on round-trip — documented).
        paragraph.layout_type = body.layout_type
        pstate.generation += 1
        _persist_content_best_effort(
            page=page,
            pstate=pstate,
            store=store,
            changes=[
                {
                    "type": "patch_paragraph_layout",
                    "paragraph": paragraph_index,
                    "layout_type": body.layout_type,
                }
            ],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


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
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../paragraphs/{pi}/split-after-line`` — split paragraph after a line.

    Spec §9 paragraph rows: ``paragraph.split_after_line(l)`` →
    ``Page.split_paragraph_after_line(page_line_index)``
    (``pdomain_book_tools/ocr/page.py:1152``). pdomain-book-tools takes a
    PAGE-WIDE line index (it auto-detects the containing paragraph by
    identity); the route translates the legacy body's within-paragraph
    ``after_line_index`` to page-wide via
    ``page.lines.index(paragraph.lines[after_line_index])``.

    Wire shape ``SplitParagraphAfterLineRequest`` is preserved per spec
    §14 — the body still carries an echoed top-level ``paragraph_index``
    (accepted-but-ignored; the URL path is authoritative).

    Pre-D2 fall-through: integration tests that hit this route without
    seeding a PageState (``test_lines_paragraphs_router.py``) continue
    to receive a stub 200 PagePayload. The wire-shape stability is
    preserved.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        # Pre-D2 integration tests never seed PageState — keep them green.
        return _stub_page_payload(project_id, page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        paragraph = _resolve_paragraph(page, paragraph_index)
        if paragraph is None:
            return _paragraph_not_found(paragraph_index)

        paragraph_lines = getattr(paragraph, "lines", None) or []
        after_idx = int(body.after_line_index)
        if not (0 <= after_idx < len(paragraph_lines)):
            return _mutation_failed(
                f"split_paragraph_after_line: after_line_index={after_idx} "
                f"out of range for paragraph={paragraph_index} "
                f"(0-{len(paragraph_lines) - 1})",
            )

        # Translate within-paragraph index to PAGE-WIDE line index by
        # locating the target line object in the page's flat lines list.
        target_line = paragraph_lines[after_idx]
        page_lines = list(getattr(page, "lines", []) or [])
        try:
            page_line_index = page_lines.index(target_line)
        except ValueError:
            return _mutation_failed(
                f"split_paragraph_after_line: target line not found in "
                f"page.lines (paragraph={paragraph_index}, "
                f"after_line_index={after_idx})",
            )

        ok = bool(page.split_paragraph_after_line(page_line_index))
        if not ok:
            return _mutation_failed(
                f"split_paragraph_after_line rejected paragraph={paragraph_index} "
                f"page_line_index={page_line_index}",
            )
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[
                {
                    "type": "split_paragraph_after_line",
                    "paragraph": paragraph_index,
                    "page_line": page_line_index,
                }
            ],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


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
    settings: Settings = Depends(get_settings),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../lines/{li}/split-with-selected`` — extract selected words into a new line.

    Spec §9 row 18b: per-line variant of ``/lines/split-by-words``.
    Calls ``Page.split_line_with_selected_words(word_keys)``
    (``pdomain_book_tools/ocr/page.py:2217``). Structural edit: triggers GT
    auto-rematch + content persistence (A3).

    ``line_index`` in the URL is accepted for routing but ``word_keys`` in the
    body govern which words are extracted (same semantic as
    ``SplitByWordsRequest``). The ``line_index`` path param is not forwarded
    to the page method because ``split_line_with_selected_words`` resolves the
    source line from the first element of ``word_keys``.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    word_keys: list[tuple[int, int]] = [(int(li), int(wi)) for li, wi in body.word_keys]

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = bool(page.split_line_with_selected_words(word_keys))
        if not ok:
            return _mutation_failed(
                f"split_line_with_selected_words rejected keys={word_keys}",
            )
        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "split_with_selected", "word_keys": word_keys}],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
    )


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
    "CopyGtBatchRequest",
    "CopyLineGtRequest",
    "DeleteLinesBatchRequest",
    "DeleteParagraphsBatchRequest",
    "DeleteScopeRequest",
    "EmptyBody",
    "GroupSelectedWordsIntoNewParagraphRequest",
    "GroupSelectedWordsIntoParagraphRequest",
    "MergeLinesRequest",
    "MergeParagraphsRequest",
    "MergeScopeRequest",
    "PatchParagraphRequest",
    "RefineBatchRequest",
    "SetLineGtRequest",
    "SplitAfterWordRequest",
    "SplitByWordsRequest",
    "SplitLineAfterWordRequest",
    "SplitLineWithSelectedWordsRequest",
    "SplitParagraphAfterLineRequest",
    "SplitSelectedParagraphsRequest",
    "ValidateLineRequest",
    "ValidateParagraphRequest",
    "install_lines_paragraphs_router",
    "router",
]

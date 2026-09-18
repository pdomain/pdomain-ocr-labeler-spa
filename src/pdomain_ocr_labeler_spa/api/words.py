"""``/api/projects/{project_id}/pages/{page_index}/words`` router — word mutations (§5.4).

Spec authority:
- ``docs/architecture/01-data-models.md §2`` — wire shapes for word routes.
- ``docs/architecture/02-backend.md §5.4`` — endpoint contracts.
- ``specs/23-page-payload-backend.md §9, §12, §13`` — mutation pattern:
  per-page lock → resolve word → call pdomain-book-tools method → bump
  ``PageState.generation`` → cached-envelope autosave (best-effort) →
  refreshed ``PagePayload`` via the keystone ``_page_payload`` helper
  in ``api/pages.py``.

Spec-23-C1 (#315) wired GT / style / component / validated / validate-batch.
Spec-23-C2 (#316) wired add / rebox / nudge / split / merge / erase-pixels.

Pd-book-tools method mapping (spec §9 names → actual pdomain-book-tools API):

- ``set_ground_truth_text(text)`` → ``word.ground_truth_text = text``
  (property setter at ``pdomain_book_tools.ocr.word.Word.ground_truth_text``).
- ``apply_style(style, scope)`` → ``word.apply_style_scope(style, scope)``.
- ``set_component(component, enabled)`` → ``word.apply_component(component, enabled=enabled)``.
- ``set_validated(bool)`` → **no method exists** on pdomain-book-tools'
  ``Word`` today. Tracking issue: pdomain/pdomain-book-tools#52.
  Until that lands, the SPA's ``_apply_word_validated`` helper writes BOTH
  the in-memory ``word.is_validated`` attribute AND the durable
  ``"validated"`` string in ``word.word_labels`` (serialized by
  ``Word.to_dict``/``from_dict``, so it survives restarts — P1.1).
- ``page.add_word(bbox, text)`` → ``Page.add_word_to_page(x1, y1, x2, y2, text)``
  (closest-line picked automatically; ``line_index`` request field is
  informational, not enforced).
- ``word.rebox(bbox)`` → ``Page.rebox_word(li, wi, x1=x1, y1=y1, x2=x2, y2=y2)``.
- ``word.nudge(left, right, top, bottom)`` →
  ``Page.nudge_word_bbox(li, wi, left_delta=left, right_delta=right,
  top_delta=top, bottom_delta=bottom, refine_after=refine_after)``.
- ``word.split(orientation, marker_position)`` →
  ``Page.split_word(li, wi, split_fraction)`` — horizontal only;
  vertical split returns 400 ``mutation_failed``.
- ``page.merge_words(targets)`` — **no method exists** on pdomain-book-tools
  ``Page`` today (tracking issue pdomain/pdomain-book-tools#53).
  Route delegates to per-line ``Line.merge_word_left(wi)`` /
  ``Line.merge_word_right(wi)`` (``pdomain_book_tools/ocr/block.py:785,789``).
- ``page.erase_pixels(bbox, fill_value)`` — **no method exists** in
  pdomain-book-tools (tracking issue #53). Handler mirrors the legacy
  labeler inline implementation at
  ``pd_ocr_labeler/state/page_state.py:1802``: clamp bbox to image
  extents, assign ``cv2_numpy_page_image[top:bottom, left:right] =
  fill_value``, then call ``page.finalize_page_structure()``. P1-CANVAS-ERASE
  (``docs/issues/2026-07-21-canvas-erase-mode-noop.md``) added a page-scoped
  sibling, ``POST .../pages/{page_index}/erase-pixels`` in ``api/pages.py``,
  for canvas drags that have no word to anchor to. ``ErasePixelsRequest``
  and the actual erase implementation (``_erase_pixels_on_page_image``) both
  live in ``api/pages.py`` — this module already imports from it, so that's
  the layer both routes can share without a circular import — and this
  route delegates to it after resolving its word.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pdomain_book_tools.ocr.page import Page
from pydantic import BaseModel, field_validator

from ..core.models import BBox, GlyphAnnotationsModel, Project
from ..core.persistence.config_yaml import AppConfig
from ..core.persistence.page_store import LabelerPageStore
from ..core.project_state import PageState, ProjectState
from ..core.typography_review import TypographyCorrectionLog, stable_page_id, stable_word_id
from ..settings import Settings
from .dependencies import (
    bind_page_labeling_lease,
    get_app_config,
    get_page_store_optional,
    get_project_state,
    get_settings,
)
from .middleware.error_handler import ApiError
from .pages import (
    ErasePixelsRequest,
    PagePayload,
    _bbox_to_coords,
    _erase_pixels_on_page_image,
    _mutation_failed,
    _page_not_loaded,
    _page_payload,
    _save_to_store_best_effort,
    _store_persist_failed_response,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

log = logging.getLogger(__name__)

# Forbidden codepoint ranges for GT input.
# U+FB00-U+FB06: Latin ligatures (ff, fi, fl, ffi, ffl, long-st variants).
# U+017F: Latin small letter long s.
# Spec: docs/specs/2026-05-12-text-normalization-design.md - GT validation.
_GT_FORBIDDEN_CODEPOINTS: frozenset[int] = frozenset(range(0xFB00, 0xFB07)) | {0x017F}

router = APIRouter(
    prefix="/api/projects",
    tags=["words"],
    dependencies=[Depends(bind_page_labeling_lease)],
)


# ── Request models ─────────────────────────────────────────────────────


class UpdateWordGroundTruthRequest(BaseModel):
    """Spec §2 line 285."""

    text: str

    @field_validator("text")
    @classmethod
    def _reject_forbidden_codepoints(cls, v: str) -> str:
        """Reject GT text containing ligature codepoints or long-s.

        Spec (docs/specs/2026-05-12-text-normalization-design.md):
        'Backend rejects GT input containing U+FB00-U+FB06 or U+017F
        with 400 validation_error.'

        GT strings must be clean ASCII / normalized Unicode. The SPA should
        normalize these before calling the API; if raw glyph codepoints arrive
        here, it is a client-side bug and the 400 surfaces it clearly.
        """
        bad = [hex(ord(ch)) for ch in v if ord(ch) in _GT_FORBIDDEN_CODEPOINTS]
        if bad:
            raise ValueError(
                f"GT text contains forbidden codepoints: {', '.join(bad)}. "
                "Normalize ligatures and long-s to ASCII before saving GT."
            )
        return v


class ApplyComponentRequest(BaseModel):
    """Spec §2 lines 293-295."""

    component: str
    enabled: bool


class ToggleValidatedRequest(BaseModel):
    """Spec §2 lines 297-298."""

    validated: bool | None = None


class ValidateBatchRequest(BaseModel):
    """Spec §2 lines 300-306."""

    scope: Literal["page", "paragraph", "line", "word"]
    line_index: int | None = None
    word_indices: list[tuple[int, int]] = []
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    validated: bool


class DeleteWordsBatchRequest(BaseModel):
    """Body for ``POST .../words/delete-batch`` — Lane A / Task A2.

    Matches the ``word-delete`` entry in ``frontend/src/lib/toolbarMapping.ts``
    (``{ scope: "word" }`` plus the selected ``word_indices``). Deletes every
    ``(line, word)`` pair in ``word_indices`` atomically.
    """

    scope: Literal["word"] = "word"
    word_indices: list[tuple[int, int]] = []


class AddWordRequest(BaseModel):
    """Spec §2 lines 308-311."""

    line_index: int | None = None
    bbox: BBox
    text: str = ""


class ReboxWordRequest(BaseModel):
    """Spec §2 lines 313-314."""

    bbox: BBox


class NudgeBboxRequest(BaseModel):
    """Spec §2 lines 316-321."""

    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0
    refine_after: bool = False


class SplitWordRequest(BaseModel):
    """Spec §2 lines 323-325."""

    x_fraction: float
    direction: Literal["horizontal", "vertical"]


class MergeWordsRequest(BaseModel):
    """Spec §2 lines 327-328."""

    direction: Literal["left", "right"]


class MergeWordsBatchRequest(BaseModel):
    """``POST .../words/merge`` body — word-scope collective merge.

    Mirrors ``MergeLinesRequest``'s collective shape (a list the toolbar's
    current selection fills), not the older per-word ``direction`` shape
    ``MergeWordsRequest`` uses. Word merge is stricter than line merge:
    exactly two entries, same line, adjacent word indices — see
    ``merge_words_batch`` for the validation and
    ``docs/issues/2026-09-18-the-word-edit-dialog-the-driver-contract-documents-does-not-exist.md``
    for why.
    """

    scope: Literal["word"] = "word"
    word_indices: list[tuple[int, int]] = []


# ``ErasePixelsRequest`` lives in ``api/pages.py`` now (imported above) —
# both the page-scoped and word-scoped erase-pixels routes need it, and
# this module already imports from ``api/pages.py``, so defining it there
# avoids a circular import.


# ── Helpers ────────────────────────────────────────────────────────────


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


def _word_not_found(line_index: int, word_index: int) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiError(
            error="word_not_found",
            message=f"word not found: line {line_index}, word {word_index}",
        ).model_dump(),
    )


def _resolve_page_object(pstate: PageState | None) -> Page | None:
    """Pull the ``Page``-like object out of ``PageState.page_record``.

    After the greenfield event-store adoption (M5b), the OCR lane stores a
    live ``pdomain_book_tools.ocr.page.Page`` directly in
    ``PageLoadOutcome.payload``.  This helper returns it directly when
    present — no envelope-lift needed for the OCR lane.

    For the store-reload lane (new process pointing at an existing project),
    the payload slot is empty and the caller should seed the page via
    ``POST .../load`` before mutating.

    Returns ``None`` when no record is cached yet or payload is not a Page.
    Callers map ``None`` to a 400 ``page_not_loaded`` envelope.
    """
    if pstate is None or pstate.page_record is None:
        return None
    payload_obj = pstate.page_record.payload
    if payload_obj is None:
        return None

    # OCR lane: payload IS the live Page object (event-store adoption M5b).
    # isinstance check keeps the static type; duck-typed test stubs still
    # work because they also pass isinstance(stub, Page) checks via the
    # Page Protocol (or we use hasattr("lines") as the secondary gate).
    if isinstance(payload_obj, Page):
        return payload_obj

    # Secondary gate for duck-typed test stubs that expose .lines without
    # being actual Page instances.
    if hasattr(payload_obj, "lines"):
        from typing import cast as _cast

        return _cast("Page", payload_obj)

    log.warning(
        "_resolve_page_object: payload type %s has no .lines — page_not_loaded",
        type(payload_obj).__name__,
    )
    return None


def _resolve_word(page: Any, line_index: int, word_index: int) -> Any | None:
    """Resolve ``page.lines[line_index].words[word_index]`` or ``None``.

    Defensive against missing attributes (allows the SPA-side stubs in
    tests to opt out of the full Page contract) and out-of-range
    indices — both map to a 404 ``word_not_found`` envelope.
    """
    lines = getattr(page, "lines", None)
    if lines is None or not (0 <= line_index < len(lines)):
        return None
    words = getattr(lines[line_index], "words", None)
    if words is None or not (0 <= word_index < len(words)):
        return None
    return words[word_index]


def _apply_word_validated(word: Any, validated: bool) -> None:
    """Set a word's validated state on BOTH carriers (PARITY-GAP P1.1, sweep C55).

    1. ``word.is_validated`` — dynamic Python attribute; the in-memory fast
       path the payload read prioritizes (immediate UI feedback without a
       store round-trip).
    2. ``"validated"`` in ``word.word_labels`` — the durable carrier:
       pdomain-book-tools serializes ``word_labels`` through
       ``Word.to_dict``/``from_dict`` (``pdomain_book_tools/ocr/word.py:677/:737``),
       so the content blob written by ``save_page_content_to_store`` persists
       it across restarts, and the read-path fallback in
       ``core/page_to_line_matches.py`` maps it back to ``is_validated``.

    Both carriers are always written together so they can never disagree.
    Defensive against duck-typed test stubs without a ``word_labels`` list —
    the attribute write still happens; the label write is skipped.
    """
    word.is_validated = validated
    labels = getattr(word, "word_labels", None)
    if not isinstance(labels, list):
        return
    if validated:
        if "validated" not in labels:
            labels.append("validated")
    else:
        while "validated" in labels:
            labels.remove("validated")


# ``_save_to_store_best_effort`` and ``_store_persist_failed_response`` live
# in ``api/pages.py`` now (imported above) — the erase-pixels shared helper
# (also in ``api/pages.py``) needs them, and this module already imports
# from ``api/pages.py``, so keeping them there avoids a circular import.
# The other word-mutation routes below use the same imported names.


def _refresh_payload_response(
    *,
    project_id: str,
    page_index: int,
    project_state: ProjectState,
    settings: Settings,
    page_store: LabelerPageStore | None,
    app_config: AppConfig | None = None,
) -> JSONResponse:
    """Build the spec-23-A populated ``PagePayload`` response.

    ``page_store`` is required, not defaulted: ``_page_payload`` needs it to
    read the page's image-provenance digest, and a route that omitted it
    reported a *different* ``page_image`` facet — and so a different
    ``RegionView.stale`` — than ``GET /pages/{idx}`` reported for the very
    same page state. Pass the route's own ``get_page_store_optional``
    dependency; ``None`` is honest only where no store is wired at all.
    """
    payload = _page_payload(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=page_store,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


def _write_cached_envelope_best_effort(
    *,
    page: Any,
    project_state: ProjectState,
    page_index: int,
    settings: Settings,
) -> None:
    """Backward-compat stub for ``lines_paragraphs.py`` import.

    The cached-lane envelope write was retired (M5b). Callers in
    ``lines_paragraphs.py`` still import this name; it's kept here as a
    no-op so those imports don't break. Word-mutation routes have been
    migrated to ``_save_to_store_best_effort`` (the event-store path).
    """


# ── Routes ─────────────────────────────────────────────────────────────


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/gt",
    response_model=PagePayload,
)
def update_word_ground_truth(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: UpdateWordGroundTruthRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/gt`` — update ground-truth text for a word.

    Spec 23 §9 row 1: ``word.set_ground_truth_text(text)`` → property
    setter ``word.ground_truth_text = text``. Holds the per-page lock
    for the full mutation window: resolve → mutate → generation bump →
    event-store write (spec §13).
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
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        word.ground_truth_text = body.text
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[{"type": "word_gt", "line": line_index, "word": word_index, "text": body.text}],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/component",
    response_model=PagePayload,
)
def apply_component(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ApplyComponentRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/component`` — toggle a word component flag.

    Spec 23 §9 row 3: ``word.set_component(component_id)`` →
    ``word.apply_component(component, enabled=enabled)`` in pdomain-book-tools.
    ``enabled=False`` removes the component (idempotent — pdomain-book-tools'
    ``apply_component`` discards if not present).
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
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        word.apply_component(body.component, enabled=body.enabled)
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {
                    "type": "word_component",
                    "line": line_index,
                    "word": word_index,
                    "component": body.component,
                    "enabled": body.enabled,
                }
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/validated",
    response_model=PagePayload,
)
def toggle_validated(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ToggleValidatedRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/validated`` — toggle the validated flag.

    Spec 23 §9 row 4 calls for ``word.set_validated(bool)``. pdomain-book-tools
    does not yet expose this method (tracking issue
    pdomain/pdomain-book-tools#52). Until that lands,
    ``_apply_word_validated`` writes both the in-memory ``word.is_validated``
    attribute and the durable ``"validated"`` entry in ``word.word_labels``;
    the latter round-trips through ``Word.to_dict``/``from_dict`` so the
    state survives a server restart (PARITY-GAP P1.1, sweep C55).

    Body shape:
    - ``validated=None`` → toggle the current flag.
    - ``validated=bool`` → set to that exact value.
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
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        current = bool(getattr(word, "is_validated", False)) or (
            "validated" in (getattr(word, "word_labels", []) or [])
        )
        new_value = (not current) if body.validated is None else bool(body.validated)
        _apply_word_validated(word, new_value)
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {
                    "type": "word_validated",
                    "line": line_index,
                    "word": word_index,
                    "validated": new_value,
                }
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/validate-batch",
    response_model=PagePayload,
)
def validate_batch(
    *,
    project_id: str,
    page_index: int,
    body: ValidateBatchRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/validate-batch`` — bulk validate/unvalidate a scope.

    Spec 23 §9 row 5: iterate over the requested scope and apply
    ``_apply_word_validated(word, body.validated)`` to each (writes both the
    in-memory attribute and the durable ``word_labels`` carrier). Scopes:

    - ``page``: every word on the page.
    - ``paragraph``: words in ``page.paragraphs[pi]`` for each ``pi`` in
      ``paragraph_indices``.
    - ``line``: words in ``page.lines[li]`` for each ``li`` in
      ``line_indices`` (or the single ``body.line_index`` for backward
      compatibility with the existing wire shape).
    - ``word``: each ``(li, wi)`` tuple in ``word_indices``.

    Single ``pstate.generation`` bump for the whole batch (one
    user-observable mutation event); one event-store write.
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
        targets = _collect_validate_batch_targets(page, body)
        for word in targets:
            _apply_word_validated(word, body.validated)
        # Bump generation even if targets was empty — observable from
        # the SPA as "I sent a validate-batch and got an updated
        # generation back".
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[{"type": "validate_batch", "scope": body.scope, "validated": body.validated}],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


def _collect_validate_batch_targets(page: Any, body: ValidateBatchRequest) -> list[Any]:
    """Walk the requested scope and return the list of target words.

    Defensive against missing ``page.lines`` / ``page.paragraphs`` —
    returns whatever subset is reachable. Out-of-range indices are
    silently skipped (the SPA may send stale indices from a re-OCRed
    page and shouldn't get a 500 for it; the batch is best-effort by
    design).
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
        line_ids: list[int] = list(body.line_indices)
        if body.line_index is not None:
            line_ids.append(body.line_index)
        for li in line_ids:
            if 0 <= li < len(lines):
                targets.extend(getattr(lines[li], "words", []) or [])
        return targets
    # Remaining branch: scope == "word".
    for li, wi in body.word_indices:
        w = _resolve_word(page, li, wi)
        if w is not None:
            targets.append(w)
    return targets


@router.post(
    "/{project_id}/pages/{page_index}/words/delete-batch",
    response_model=PagePayload,
)
def delete_words_batch(
    *,
    project_id: str,
    page_index: int,
    body: DeleteWordsBatchRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/delete-batch`` — delete selected words (Lane A / A2).

    Thin scope-resolver over ``Page.delete_words(word_keys)``. Atomic: one
    structural mutation + one event per request. Matches the
    ``word-delete`` toolbarMapping entry.

    Deleting a word shifts every later word in its line down one index, so
    ``_reindex_word_sidecar_maps_after_batch_removal`` walks the same
    per-line, highest-index-first order ``Page.delete_words`` uses to keep
    ``PageState.char_bboxes_map`` / ``glyph_annotations_map`` /
    ``glyph_predictions_map`` — keyed ``"{line_index}_{word_index}"`` —
    attached to the words they actually belong to (see
    ``_merge_words_core``, which reindexes for the same reason after a
    word merge removes a word).
    """
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
        ok = bool(page.delete_words(word_keys))
        if not ok:
            return _mutation_failed(f"delete_words rejected keys={word_keys}")
        _reindex_word_sidecar_maps_after_batch_removal(pstate, word_keys=word_keys)
        from .lines_paragraphs import _finalize_structural_edit

        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "words_delete_batch", "word_indices": word_keys}],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/add",
    response_model=PagePayload,
)
def add_word(
    *,
    project_id: str,
    page_index: int,
    body: AddWordRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/add`` — insert a new word bbox.

    Spec 23 §9 row 6: ``page.add_word(bbox, text, line_index=None)`` →
    ``Page.add_word_to_page(x1, y1, x2, y2, text)`` in pdomain-book-tools.
    The request body's ``line_index`` is informational only:
    pdomain-book-tools picks the closest line by bbox centroid (see
    ``Page.add_word_to_page`` at
    ``pdomain_book_tools/ocr/page.py:2132``).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    x1, y1, x2, y2 = _bbox_to_coords(body.bbox)
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        ok = page.add_word_to_page(x1, y1, x2, y2, body.text)
        if not ok:
            return _mutation_failed(f"add_word_to_page rejected bbox=({x1}, {y1}, {x2}, {y2})")
        from .lines_paragraphs import _finalize_structural_edit

        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[{"type": "word_add", "bbox": [x1, y1, x2, y2], "text": body.text}],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/rebox",
    response_model=PagePayload,
)
def rebox_word(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ReboxWordRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/rebox`` — replace the word's bounding box.

    Spec 23 §9 row 7: ``word.rebox(bbox)`` →
    ``Page.rebox_word(li, wi, x1=x1, y1=y1, x2=x2, y2=y2)`` in
    pdomain-book-tools (``pdomain_book_tools/ocr/page.py:2043``).
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
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        x1, y1, x2, y2 = _bbox_to_coords(body.bbox)
        ok = page.rebox_word(line_index, word_index, x1=x1, y1=y1, x2=x2, y2=y2)
        if not ok:
            return _mutation_failed(
                f"rebox_word rejected line={line_index} word={word_index} bbox=({x1}, {y1}, {x2}, {y2})"
            )
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {
                    "type": "word_rebox",
                    "line": line_index,
                    "word": word_index,
                    "bbox": [x1, y1, x2, y2],
                }
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/nudge",
    response_model=PagePayload,
)
def nudge_bbox(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: NudgeBboxRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/nudge`` — nudge bbox edges by pixel offsets.

    Spec 23 §9 row 8: ``word.nudge(left, right, top, bottom)`` →
    ``Page.nudge_word_bbox(li, wi, left_delta=left, right_delta=right,
    top_delta=top, bottom_delta=bottom, refine_after=refine_after)`` in
    pdomain-book-tools (``pdomain_book_tools/ocr/page.py:2571``).
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
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        ok = page.nudge_word_bbox(
            line_index,
            word_index,
            left_delta=body.left,
            right_delta=body.right,
            top_delta=body.top,
            bottom_delta=body.bottom,
            refine_after=body.refine_after,
        )
        if not ok:
            return _mutation_failed(
                f"nudge_word_bbox rejected line={line_index} word={word_index} "
                f"deltas=({body.left}, {body.right}, {body.top}, {body.bottom})"
            )
        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {
                    "type": "word_nudge",
                    "line": line_index,
                    "word": word_index,
                    "deltas": [body.left, body.right, body.top, body.bottom],
                }
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/split",
    response_model=PagePayload,
)
def split_word(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: SplitWordRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/split`` — split one word bbox into two.

    Spec 23 §9 row 9: ``word.split(orientation, marker_position)`` →
    ``Page.split_word(li, wi, split_fraction)`` in pdomain-book-tools
    (``pdomain_book_tools/ocr/page.py:1756``). pdomain-book-tools only supports
    horizontal split today; ``direction='vertical'`` returns 400.

    Refuses (400 ``word_split_would_orphan_annotations``) when the target
    word carries a char-bbox sidecar entry, a glyph annotation, or a
    typography correction — ``Page.split_word`` replaces the word with two
    brand-new ``Word`` objects, so there is no sound way to carry that
    per-word state onto either half (see the block comment above
    ``_WordEditRefusalKind``). Every later word in the line still shifts
    down by one index when the split adds a word; their sidecar entries are
    reindexed via an identity snapshot taken before/after the mutation,
    same mechanism ``lines_paragraphs.py`` uses for line/paragraph merges.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    if body.direction != "horizontal":
        direction = body.direction
        return _mutation_failed(
            f"split_word direction={direction!r} not supported; only horizontal split is exposed"
        )

    project = project_state.loaded_project
    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if project is None or pstate is None or page is None:
        return _page_not_loaded(page_index)

    from .lines_paragraphs import (
        _finalize_structural_edit,
        _reindex_sidecar_maps_after_structural_edit,
        _snapshot_word_positions,
    )

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)

        kind = _word_structural_edit_refusal_kind(
            project=project,
            project_state=project_state,
            pstate=pstate,
            page=page,
            page_index=page_index,
            line_index=line_index,
            word_index=word_index,
            word=word,
        )
        if kind is not None:
            return _word_split_refused(kind=kind, line_index=line_index, word_index=word_index)

        before = _snapshot_word_positions(page)
        ok = page.split_word(line_index, word_index, body.x_fraction)
        if not ok:
            return _mutation_failed(
                f"split_word rejected line={line_index} word={word_index} fraction={body.x_fraction}"
            )
        _reindex_sidecar_maps_after_structural_edit(
            pstate, before=before, after=_snapshot_word_positions(page)
        )

        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[
                {
                    "type": "word_split",
                    "line": line_index,
                    "word": word_index,
                    "fraction": body.x_fraction,
                }
            ],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


# ── Word merge / split — shared refusal core ────────────────────────────
#
# Two routes reach the same merge: the older per-word `direction` shape
# (`merge_words`, used by StructureSection's "Merge with prev/next") and
# the collective shape the toolbar's `toolbar-word-merge` cell sends
# (`merge_words_batch`, mirroring `lines/merge`). Both share
# `_merge_words_core` so the refusal check, text/bbox merge, and sidecar
# reindex live in exactly one place — see
# docs/issues/2026-09-18-the-word-edit-dialog-the-driver-contract-documents-does-not-exist.md
# ruling 2. Deliberately does NOT delegate to pdomain-book-tools'
# `Line.merge_word_left`/`merge_word_right`: that helper clears
# `ground_truth_text` for *every* word in the line (a line-wide GT reset
# meant for the "line shape changed" case), which would erase the GT of
# words this merge never touched — the wrong result for "OCR split one
# word in two". `Word.merge()` (the same primitive book-tools' helper
# calls under the hood) concatenates OCR + GT text with no separator and
# unions the two bounding boxes; that is exactly ruling 2's contract, so
# it is called directly instead.
#
# `split_word` (above) shares the same refusal-kind check via
# `_word_structural_edit_refusal_kind`: `Page.split_word` replaces the
# target word with two brand-new `Word` objects, so neither this module's
# index-offset reindex (merge, delete) nor `lines_paragraphs.py`'s
# identity-snapshot reindex (line/paragraph merge) can describe what the
# *split word's own* sidecar entry should become — an identity snapshot
# would just find the original object gone and silently drop it. Splitting
# a word that carries a sidecar entry is refused outright, exactly like
# merge, rather than guessing how to divide it. Every *other* word in the
# line still shifts by one index when the split adds a word, so split
# reuses `lines_paragraphs._snapshot_word_positions` /
# `_reindex_sidecar_maps_after_structural_edit` to carry their sidecar
# entries forward — the identity-snapshot approach the line-merge fix
# already uses, and it works here because those words' objects are
# untouched by the split.

_WordEditRefusalKind = Literal["char_bbox", "glyph_annotation", "typography_correction"]


def _resolve_logical_page_id(project: Project, page_index: int, project_state: ProjectState) -> str:
    """Return the same logical page id ``api/typography.py::_logical_page_id`` would.

    Typography corrections are keyed by a word_id derived from this id
    (``stable_word_id``) — the refusal check below must resolve the exact
    same id typography reads/writes use, including the labeling-bundle
    override, or it would silently miss corrections that exist under a
    bundle-scoped page id.
    """
    bundle = project_state.labeling_bundle
    if bundle is not None:
        return bundle.page_id
    return stable_page_id(project_id=project.project_id, page_index=page_index)


def _reading_order_for_word(page: Any, line_index: int, word_index: int) -> int:
    """Return this word's page-wide reading-order index (0-based).

    Mirrors the counter in ``core/page_to_line_matches.py`` (words counted
    line-by-line, word-by-word) — ``stable_word_id`` needs the identical
    value, or it derives a different id than the one the typography
    journal was written under.
    """
    order = 0
    for li, line in enumerate(getattr(page, "lines", None) or []):
        words = getattr(line, "words", None) or []
        if li == line_index:
            return order + word_index
        order += len(words)
    return order + word_index


def _word_merge_annotation_kind(
    *,
    pstate: PageState,
    line_index: int,
    word_index: int,
    word: Any,
) -> Literal["char_bbox", "glyph_annotation"] | None:
    """Return which sidecar/attribute kind this word carries, else None.

    ``char_bboxes_map``/``glyph_annotations_map`` are keyed positionally
    (``"{line_index}_{word_index}"``), NOT by the typography word_id — a
    key merely being present (even an explicitly-empty
    ``GlyphAnnotationsModel()``) means a human reviewed this word, so its
    presence alone is enough to refuse (see ``set_glyph_annotations``).
    ``word.glyph_annotations`` (the pdomain-book-tools attribute) is
    checked too — ``core/page_to_line_matches.py`` reads it as a fallback
    when the sidecar has no entry, so it is a second live source of the
    same kind of state.
    """
    sidecar_key = f"{line_index}_{word_index}"
    if sidecar_key in pstate.char_bboxes_map:
        return "char_bbox"
    if sidecar_key in pstate.glyph_annotations_map:
        return "glyph_annotation"
    if getattr(word, "glyph_annotations", None) is not None:
        return "glyph_annotation"
    return None


def _word_merge_has_typography_correction(
    *,
    project: Project,
    logical_page_id: str,
    page: Any,
    line_index: int,
    word_index: int,
    word: Any,
) -> bool:
    """Return True when this word's derived word_id has a typography correction."""
    reading_order = _reading_order_for_word(page, line_index, word_index)
    text = str(getattr(word, "text", "") or "")
    word_id = stable_word_id(
        project_id=project.project_id,
        page_id=logical_page_id,
        reading_order=reading_order,
        text=text,
    )
    log = TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent)
    return log.head(logical_page_id, word_id) is not None


def _word_structural_edit_refusal_kind(
    *,
    project: Project,
    project_state: ProjectState,
    pstate: PageState,
    page: Any,
    page_index: int,
    line_index: int,
    word_index: int,
    word: Any,
) -> _WordEditRefusalKind | None:
    """Return which sidecar/annotation kind blocks a structural edit on ``word``, else None.

    Shared by word merge (checked for both the keep and remove word) and
    word split (checked for the word being split) — same three checks in
    the same order: positional sidecar maps, the book-tools
    ``glyph_annotations`` attribute, then a typography correction lookup.
    """
    kind: _WordEditRefusalKind | None = _word_merge_annotation_kind(
        pstate=pstate, line_index=line_index, word_index=word_index, word=word
    )
    if kind is None:
        logical_page_id = _resolve_logical_page_id(project, page_index, project_state)
        if _word_merge_has_typography_correction(
            project=project,
            logical_page_id=logical_page_id,
            page=page,
            line_index=line_index,
            word_index=word_index,
            word=word,
        ):
            kind = "typography_correction"
    return kind


def _word_merge_invalid_selection(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ApiError(error="word_merge_invalid_selection", message=message).model_dump(),
    )


def _word_merge_refused(*, kind: _WordEditRefusalKind, line_index: int, word_index: int) -> JSONResponse:
    readable = kind.replace("_", " ")
    return JSONResponse(
        status_code=400,
        content=ApiError(
            error="word_merge_would_orphan_annotations",
            message=(
                f"Cannot merge: word at line {line_index}, word {word_index} carries {readable} "
                "that would be lost. Merge is refused rather than orphaning it."
            ),
            details={"line_index": line_index, "word_index": word_index, "kind": kind},
        ).model_dump(),
    )


def _word_split_refused(*, kind: _WordEditRefusalKind, line_index: int, word_index: int) -> JSONResponse:
    readable = kind.replace("_", " ")
    return JSONResponse(
        status_code=400,
        content=ApiError(
            error="word_split_would_orphan_annotations",
            message=(
                f"Cannot split: word at line {line_index}, word {word_index} carries {readable} "
                "that would be lost. Split is refused rather than orphaning it."
            ),
            details={"line_index": line_index, "word_index": word_index, "kind": kind},
        ).model_dump(),
    )


def _reindex_word_sidecar_map(
    mapping: dict[str, object], *, line_index: int, removed_word_index: int
) -> None:
    """Drop ``removed_word_index``'s own entry and shift later words down by one.

    Called after a word is removed from a line (merge, delete). ``mapping``
    is keyed ``"{line_index}_{word_index}"`` — every later word in the same
    line now sits one index lower, so its sidecar entry must move with it or
    it silently attaches to the wrong word on the next read. The removed
    word's own entry is dropped outright rather than left at its old index:
    that index now names a different word, so leaving the entry in place
    would misattach it. (Merge's caller never has an entry to drop here —
    it refuses the merge first if either word carries one — so this is a
    no-op for merge and the fix delete needs.)
    """
    prefix = f"{line_index}_"
    updated: dict[str, object] = {}
    for key, value in mapping.items():
        if key.startswith(prefix):
            suffix = key[len(prefix) :]
            if suffix.isdigit():
                word_index = int(suffix)
                if word_index == removed_word_index:
                    continue
                if word_index > removed_word_index:
                    updated[f"{line_index}_{word_index - 1}"] = value
                    continue
        updated[key] = value
    mapping.clear()
    mapping.update(updated)


def _reindex_word_sidecar_maps_after_removal(
    pstate: PageState, *, line_index: int, removed_word_index: int
) -> None:
    _reindex_word_sidecar_map(
        pstate.char_bboxes_map, line_index=line_index, removed_word_index=removed_word_index
    )
    _reindex_word_sidecar_map(
        pstate.glyph_annotations_map, line_index=line_index, removed_word_index=removed_word_index
    )
    _reindex_word_sidecar_map(
        pstate.glyph_predictions_map, line_index=line_index, removed_word_index=removed_word_index
    )


def _reindex_word_sidecar_maps_after_batch_removal(
    pstate: PageState, *, word_keys: Sequence[tuple[int, int]]
) -> None:
    """Reindex sidecar maps after ``Page.delete_words(word_keys)`` removes several words.

    ``Page.delete_words`` dedupes ``word_keys``, groups them by line, and
    within each line removes highest word_index first (so an earlier removal
    in the same call never shifts an index a later removal still needs) —
    see ``pdomain_book_tools.ocr.page.Page.delete_words``. The reindex must
    walk the same order per line, or a multi-word delete in one line computes
    the wrong final indices.
    """
    by_line: dict[int, list[int]] = {}
    for line_index, word_index in set(word_keys):
        by_line.setdefault(line_index, []).append(word_index)
    for line_index, word_indices in by_line.items():
        for word_index in sorted(word_indices, reverse=True):
            _reindex_word_sidecar_maps_after_removal(
                pstate, line_index=line_index, removed_word_index=word_index
            )


def _merge_words_core(
    *,
    project: Project,
    project_state: ProjectState,
    pstate: PageState,
    page: Any,
    page_index: int,
    line_index: int,
    keep_index: int,
    remove_index: int,
) -> JSONResponse | None:
    """Merge ``remove_index`` into ``keep_index`` within one line, or refuse.

    Returns a 400 ``JSONResponse`` when either word carries typography
    corrections, glyph annotations, or char bboxes (see module docstring
    above ``_WordEditRefusalKind``). On success mutates ``page``/``pstate``
    in place (merged text/bbox on the surviving word, sidecar-map
    reindex) and returns None; the caller still owns
    ``_finalize_structural_edit`` (rematch + persist — the single choke
    point for content saves, per ``save_page_content_to_store``).
    """
    line = page.lines[line_index]
    words = line.words
    keep_word = words[keep_index]
    remove_word = words[remove_index]

    for word_index, word in ((keep_index, keep_word), (remove_index, remove_word)):
        kind = _word_structural_edit_refusal_kind(
            project=project,
            project_state=project_state,
            pstate=pstate,
            page=page,
            page_index=page_index,
            line_index=line_index,
            word_index=word_index,
            word=word,
        )
        if kind is not None:
            return _word_merge_refused(kind=kind, line_index=line_index, word_index=word_index)

    # Word.merge() — concatenates OCR + GT text with no separator (in
    # left-to-right bbox order) and unions the two bounding boxes. `keep_word`
    # survives at `keep_index`; `remove_word` is discarded.
    keep_word.merge(remove_word)
    line.remove_item(remove_word)
    _reindex_word_sidecar_maps_after_removal(pstate, line_index=line_index, removed_word_index=remove_index)
    return None


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/merge",
    response_model=PagePayload,
)
def merge_words(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: MergeWordsRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/merge`` — merge with adjacent word.

    Used by the right panel's ``StructureSection`` ("Merge with prev/next").
    Spec 23 §9 row 10 names ``page.merge_words(targets)``, which is not
    implemented in pdomain-book-tools (tracking pdomain/pdomain-book-tools#53);
    this route resolves the adjacent pair itself and calls the shared
    ``_merge_words_core`` (see the block comment above it for why it does
    not delegate to ``Line.merge_word_left``/``merge_word_right``).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    project = project_state.loaded_project
    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if project is None or pstate is None or page is None:
        return _page_not_loaded(page_index)

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)
        # Resolve the line — guaranteed in-range by _resolve_word success.
        line = page.lines[line_index]
        words = line.words
        if body.direction == "left":
            if word_index == 0:
                return _mutation_failed(f"merge_word_left rejected line={line_index} word={word_index}")
            keep_index, remove_index = word_index - 1, word_index
        else:
            if word_index >= len(words) - 1:
                return _mutation_failed(f"merge_word_right rejected line={line_index} word={word_index}")
            keep_index, remove_index = word_index, word_index + 1

        refusal = _merge_words_core(
            project=project,
            project_state=project_state,
            pstate=pstate,
            page=page,
            page_index=page_index,
            line_index=line_index,
            keep_index=keep_index,
            remove_index=remove_index,
        )
        if refusal is not None:
            return refusal

        from .lines_paragraphs import _finalize_structural_edit

        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[
                {
                    "type": "word_merge",
                    "line": line_index,
                    "word": word_index,
                    "direction": body.direction,
                }
            ],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/merge",
    response_model=PagePayload,
)
def merge_words_batch(
    *,
    project_id: str,
    page_index: int,
    body: MergeWordsBatchRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/merge`` — merge exactly two adjacent same-line words.

    Mirrors ``lines/merge``'s collective shape (the toolbar sends the
    current ``selected_words`` set) rather than the older per-word
    ``direction`` shape ``merge_words`` uses. Word merge is stricter than
    line merge: exactly two entries, same line, adjacent word indices —
    anything else is a 400 ``word_merge_invalid_selection`` rather than a
    silent no-op, matching how this route's `toolbar-word-merge` cell
    surfaces a reason instead of just staying disabled (driver-contract
    §2.9). Backs the ``toolbar-word-merge`` toolbar cell — see
    ``docs/issues/2026-09-18-the-word-edit-dialog-the-driver-contract-documents-does-not-exist.md``.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    project = project_state.loaded_project
    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if project is None or pstate is None or page is None:
        return _page_not_loaded(page_index)

    word_indices: list[tuple[int, int]] = [(int(li), int(wi)) for li, wi in body.word_indices]
    if len(word_indices) != 2:
        return _word_merge_invalid_selection(
            f"word merge requires exactly two selected words, got {len(word_indices)}"
        )
    (line_a, word_a), (line_b, word_b) = word_indices
    if line_a != line_b:
        return _word_merge_invalid_selection("selected words must be on the same line to merge")
    if abs(word_a - word_b) != 1:
        return _word_merge_invalid_selection("selected words must be adjacent to merge")

    line_index = line_a
    keep_index, remove_index = sorted((word_a, word_b))

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        if _resolve_word(page, line_index, keep_index) is None or (
            _resolve_word(page, line_index, remove_index) is None
        ):
            return _word_not_found(line_index, remove_index)

        refusal = _merge_words_core(
            project=project,
            project_state=project_state,
            pstate=pstate,
            page=page,
            page_index=page_index,
            line_index=line_index,
            keep_index=keep_index,
            remove_index=remove_index,
        )
        if refusal is not None:
            return refusal

        from .lines_paragraphs import _finalize_structural_edit

        _finalize_structural_edit(
            page=page,
            pstate=pstate,
            project_state=project_state,
            page_index=page_index,
            store=store,
            changes=[
                {
                    "type": "word_merge_batch",
                    "line_index": line_index,
                    "word_indices": [keep_index, remove_index],
                }
            ],
        )

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/erase-pixels",
    response_model=PagePayload,
)
def erase_pixels(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: ErasePixelsRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/erase-pixels`` — erase pixels in a bbox.

    Spec 23 §9 row 11 names ``page.erase_pixels(bbox, fill_value=255)``,
    which does not exist in pdomain-book-tools (tracking ConcaveTrillion/
    pdomain-book-tools#53). The actual erase (clamp bbox to image extents,
    fill, ``page.finalize_page_structure()``, post-erase image-blob
    persistence, event-store write) is delegated to the shared
    ``api.pages._erase_pixels_on_page_image`` helper — mirrors the legacy
    labeler's inline implementation at
    ``pd_ocr_labeler/state/page_state.py:1802`` — which this route shares
    with the page-scoped ``POST .../pages/{page_index}/erase-pixels`` route
    (P1-CANVAS-ERASE) so the two cannot drift.

    ``(line_index, word_index)`` here is only used to resolve a target word
    (returning 404 ``word_not_found`` when it doesn't exist) and to anchor
    the changelog entry for selection feedback; the actual erase rectangle
    is always taken from ``body.bbox`` (image-coordinate, not
    word-relative).
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
        word = _resolve_word(page, line_index, word_index)
        if word is None:
            return _word_not_found(line_index, word_index)

        erase_err = _erase_pixels_on_page_image(
            page=page,
            pstate=pstate,
            store=store,
            body=body,
            line_index=line_index,
            word_index=word_index,
        )
        if erase_err is not None:
            return erase_err

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


# ── Char-bboxes endpoint ──────────────────────────────────────────────


class SetCharBboxesRequest(BaseModel):
    """``POST .../words/{li}/{wi}/char-bboxes`` body — CharFixer Apply.

    Replaces all per-character bounding-box annotations for the given word
    with *char_bboxes* (one ``BBox`` per character, in image-pixel coords).

    Stored in ``PageState.char_bboxes_map`` and embedded under
    ``labeler_sidecars`` in the event-store content blob (Wave 0.1). Surfaced
    onto ``WordMatch.char_bboxes`` at payload-build time.
    """

    char_bboxes: list[BBox]


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/char-bboxes",
    response_model=PagePayload,
)
def set_char_bboxes(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: SetCharBboxesRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
    app_config: AppConfig = Depends(get_app_config),
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/char-bboxes`` — persist CharFixer per-char bboxes.

    Stores the per-character bounding boxes from the CharFixer Apply button
    into ``PageState.char_bboxes_map`` and best-effort content-blob
    ``labeler_sidecars``. Does not mutate book-tools word fields (no
    first-class char-bbox concept there).
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    # Composite sidecar key — stable as long as the page is not re-OCR'd.
    sidecar_key = f"{line_index}_{word_index}"
    bbox_dicts = [{"x": b.x, "y": b.y, "width": b.width, "height": b.height} for b in body.char_bboxes]

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        pstate.char_bboxes_map[sidecar_key] = bbox_dicts

        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {
                    "type": "set_char_bboxes",
                    "line_index": line_index,
                    "word_index": word_index,
                    "count": len(bbox_dicts),
                }
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


class SetGlyphAnnotationsRequest(BaseModel):
    """``POST .../words/{li}/{wi}/glyph-annotations`` body — spec §6.1.

    ``annotations=None`` means "unset back to not-reviewed" (clears confirmed
    annotations without touching predictions).
    ``annotations=GlyphAnnotationsModel()`` means "reviewed, nothing to mark".
    """

    annotations: GlyphAnnotationsModel | None


class AcceptGlyphPredictionRequest(BaseModel):
    """``POST .../words/{li}/{wi}/accept-prediction`` body — spec §6.1.

    No fields — confirms the current predictions wholesale, promoting them
    to ``source="human_confirmed"`` annotations.
    """


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/glyph-annotations",
    response_model=PagePayload,
)
def set_glyph_annotations(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: SetGlyphAnnotationsRequest,
    project_state: ProjectState = Depends(get_project_state),  # pyright: ignore[reportCallInDefaultInitializer]
    settings: Settings = Depends(get_settings),  # pyright: ignore[reportCallInDefaultInitializer]
    app_config: AppConfig = Depends(get_app_config),  # pyright: ignore[reportCallInDefaultInitializer]
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/glyph-annotations`` — set/clear word glyph annotations.

    Writes ``PageState.glyph_annotations_map`` and best-effort content-blob
    ``labeler_sidecars`` (Wave 2 T3). ``annotations=None`` clears back to
    "not reviewed" without touching predictions.

    Spec: ``specs/20-glyph-annotations.md`` §6.1.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    sidecar_key = f"{line_index}_{word_index}"
    ann_dict = body.annotations.model_dump() if body.annotations is not None else None

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        if ann_dict is not None:
            pstate.glyph_annotations_map[sidecar_key] = ann_dict
        else:
            _ = pstate.glyph_annotations_map.pop(sidecar_key, None)

        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {
                    "type": "set_glyph_annotations",
                    "line_index": line_index,
                    "word_index": word_index,
                }
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


@router.post(
    "/{project_id}/pages/{page_index}/words/{line_index}/{word_index}/accept-prediction",
    response_model=PagePayload,
)
def accept_glyph_prediction(
    *,
    project_id: str,
    page_index: int,
    line_index: int,
    word_index: int,
    body: AcceptGlyphPredictionRequest,  # pyright: ignore[reportUnusedParameter]
    project_state: ProjectState = Depends(get_project_state),  # pyright: ignore[reportCallInDefaultInitializer]
    settings: Settings = Depends(get_settings),  # pyright: ignore[reportCallInDefaultInitializer]
    app_config: AppConfig = Depends(get_app_config),  # pyright: ignore[reportCallInDefaultInitializer]
    store: LabelerPageStore | None = Depends(get_page_store_optional),
) -> JSONResponse:
    """``POST .../words/{li}/{wi}/accept-prediction`` — confirm glyph predictions.

    Promotes ``glyph_predictions`` to ``glyph_annotations`` with
    ``source="human_confirmed"``.  Predictions remain on the in-memory word
    model (they are not cleared by this call — re-running the classifier
    would regenerate them).

    Spec: ``specs/20-glyph-annotations.md`` §6.1.
    """
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err

    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    if pstate is None or page is None:
        return _page_not_loaded(page_index)

    sidecar_key = f"{line_index}_{word_index}"

    # Read current predictions from the sidecar map (if any)
    predictions_dict = pstate.glyph_predictions_map.get(sidecar_key)
    if predictions_dict is None:
        return JSONResponse(
            status_code=400,
            content=ApiError(
                error="no_predictions",
                message=f"No predictions found for word {line_index}/{word_index}",
            ).model_dump(),
        )

    # Promote predictions to confirmed annotations
    from typing import cast

    predictions_as_dict = cast("dict[str, object]", predictions_dict)
    confirmed: dict[str, object] = {**predictions_as_dict, "source": "human_confirmed"}

    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        pstate.glyph_annotations_map[sidecar_key] = confirmed

        pstate.generation += 1
        if not _save_to_store_best_effort(
            pstate=pstate,
            store=store,
            changes=[
                {
                    "type": "accept_glyph_prediction",
                    "line_index": line_index,
                    "word_index": word_index,
                }
            ],
        ):
            return _store_persist_failed_response(page_id=pstate.page_id)

    return _refresh_payload_response(
        project_id=project_id,
        page_index=page_index,
        project_state=project_state,
        settings=settings,
        app_config=app_config,
        page_store=store,
    )


def install_words_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the words router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "AddWordRequest",
    "ApplyComponentRequest",
    "DeleteWordsBatchRequest",
    "ErasePixelsRequest",
    "MergeWordsBatchRequest",
    "MergeWordsRequest",
    "NudgeBboxRequest",
    "ReboxWordRequest",
    "SetCharBboxesRequest",
    "SplitWordRequest",
    "ToggleValidatedRequest",
    "UpdateWordGroundTruthRequest",
    "ValidateBatchRequest",
    "install_words_router",
    "router",
]

"""Domain models — the typed in-memory shapes shared by adapters + wire.

Spec authority:
- ``docs/architecture/01-data-models.md §1`` — all domain model shapes.
- ``docs/architecture/01-data-models.md`` lines 7-12 — convention: domain models
  live here and are reused by both the ``IStorage`` / ``IOCREngine``
  Protocols AND the wire (no separate DTO layer).

Adding new models: append; never reorder. Generated TS via
``make openapi-export`` keys on field name + position.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, TypedDict

from pdomain_book_contracts.annotation import RegionRole
from pydantic import BaseModel, ConfigDict, Field

_MAX_DISPLAY_DIMENSION = 1200


class Project(BaseModel):
    """One labeler project — ``docs/architecture/01-data-models.md §1`` lines 28-44.

    Mirrors legacy ``pd_ocr_labeler/models/project_model.py:9``.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str
    project_root: Path
    image_paths: list[Path]
    ground_truth_map: dict[str, str]
    version: str = "1.0"
    source_lib: str = "doctr-pdomain-labeled"
    total_pages: int
    saved_pages: int = 0
    current_page_index: int = 0
    include_images: bool = True
    copied_images: bool = False

    @property
    def page_count(self) -> int:
        return len(self.image_paths)


class PageSource(StrEnum):
    """How a page's OCR data was sourced — spec §1 ``PageSource``."""

    OCR = "ocr"
    CACHED_OCR = "cached_ocr"
    FILESYSTEM = "filesystem"
    FALLBACK = "fallback"


class MatchStatus(StrEnum):
    """Per-word match result — spec §1 ``MatchStatus``.

    Exactly five values, matching legacy ``WordMatch.match_status``.
    """

    EXACT = "exact"
    FUZZY = "fuzzy"
    MISMATCH = "mismatch"
    UNMATCHED_OCR = "unmatched_ocr"
    UNMATCHED_GT = "unmatched_gt"


class BBox(BaseModel):
    """Image-coordinate bounding box — ``docs/architecture/01-data-models.md §1`` lines 137-143."""

    x: int
    y: int
    width: int
    height: int


class RegionView(BaseModel):
    """One resolved region as the labeler renders it — spec §"Reading order..." / resolver.

    ``confirmed=True`` means a person put it there; ``confirmed=False`` means it is a
    proposal above the labeler's display threshold (zero — the labeler shows everything
    and renders the two differently). ``region_id`` is set only when confirmed.
    ``proposal_id`` is set for an unconfirmed proposal (the proposal itself), and also for
    a confirmed region promoted from one (its origin) — an explicit hand-drawn sentinel
    when a person drew the region unprompted, or ``None`` when the origin was never
    stamped. ``member_word_signatures`` is populated for a confirmed region (bounding-box
    signatures, never a line/word ordinal); empty for a region resolved from a proposal,
    which carries no membership of its own. ``stale`` is only ever True for an unconfirmed
    proposal whose run read facets that have since changed on the page.
    """

    region_id: str | None = None
    proposal_id: str | None = None
    role: RegionRole
    box: BBox
    confirmed: bool
    confidence: float | None = None
    member_word_signatures: list[tuple[float, float, float, float, bool | None]] = Field(default_factory=list)
    stale: bool = False


class RegionProposalView(BaseModel):
    """One proposal as the labeler's proposal list shows it — role, confidence, evidence.

    ``disposition`` and ``decided_region_id`` are ``None`` until a person accepts or
    rejects the proposal; that is what distinguishes "nobody has looked yet" from
    "looked at and refused" once a decision is recorded.

    ``carried_from_run_id``/``carried_from_proposal_id`` are set only when this
    proposal's decision was not a person's own: a re-run matched it against an
    earlier proposal's confirmed region or recorded rejection and reused that
    decision rather than asking again. Both are ``None`` for a decision a person
    made directly on this exact proposal, carried or not — the one signal a
    caller has for telling a carried decision from a fresh one, including
    after a ``reopened`` decision reverses it (a ``POST .../unreject`` reverses
    only the proposal named in the URL; it never rewrites the ``carried_from_*``
    fields of the decision it reverses, so this stays true before and after).

    ``disposition`` also reads ``"reopened"``: a person asked to see a
    rejected — possibly carried-rejected — proposal again. A reopened
    proposal has no ``decided_region_id`` and behaves as undecided in
    ``PagePayload.regions``, the same as one nobody has looked at yet.
    """

    proposal_id: str
    run_id: str
    page_index: int
    role: RegionRole
    box: BBox
    confidence: float
    # Open-ended: shape varies per detector (mirrors RegionProposal.evidence
    # upstream, which is equally open-ended), so no single TypedDict fits.
    evidence: dict[str, Any]
    disposition: str | None = None
    decided_region_id: str | None = None
    carried_from_run_id: str | None = None
    carried_from_proposal_id: str | None = None


class EncodedDims(BaseModel):
    """Source + display dimensions with scale factor.

    Algorithm matches legacy ``image_tabs._compute_encoded_dimensions:962``:
    display_width = min(src_width, 1200), display_height proportional (integer
    math), scale = display_width / src_width.
    """

    src_width: int
    src_height: int
    display_width: int
    display_height: int
    scale: float

    @classmethod
    def from_source_dims(cls, src_width: int, src_height: int) -> EncodedDims:
        display_width = min(src_width, _MAX_DISPLAY_DIMENSION)
        display_height = int(src_height * display_width / src_width)
        scale = display_width / src_width
        return cls(
            src_width=src_width,
            src_height=src_height,
            display_width=display_width,
            display_height=display_height,
            scale=scale,
        )


class LigatureMarkModel(BaseModel):
    """One ligature occurrence within a word — spec ``specs/20-glyph-annotations.md`` §3.

    Mirrors ``pdomain_book_tools.ocr.glyph_annotations.LigatureMark`` as a Pydantic model
    so it serialises correctly in the wire contract.

    ``kind`` is the ligature kind string (e.g. ``"ct"``, ``"fi"``).  Values
    correspond to ``pdomain_book_tools.ocr.glyph_annotations.LigatureKind`` but are
    kept as plain strings here to avoid importing from pdomain_book_tools at schema
    definition time (lazy import strategy for the OCR dependency).

    ``char_span`` is a ``[start, end)`` tuple of char indices into the GT string,
    or ``None`` when the span is unknown (coarse-grained label).
    """

    kind: str
    char_span: tuple[int, int] | None = None


class GlyphAnnotationsModel(BaseModel):
    """Glyph-level side-channel annotations for one word — spec §3 + D-044.

    Mirrors ``pdomain_book_tools.ocr.glyph_annotations.GlyphAnnotations`` and adds
    ``source`` (D-044: object-level provenance, not per-mark).

    Tri-state semantics (spec §1):
    - ``WordMatch.glyph_annotations is None`` — not yet reviewed.
    - ``WordMatch.glyph_annotations == GlyphAnnotationsModel()`` — reviewed, nothing to annotate.
    - ``WordMatch.glyph_annotations`` with marks — reviewed, marks present.

    ``glyph_predictions`` on ``WordMatch`` uses the same shape but with
    ``source="predicted"``; predictions are NEVER persisted in the envelope.
    """

    ligatures: list[LigatureMarkModel] = Field(default_factory=list)
    long_s_positions: list[int] = Field(default_factory=list)
    swash: bool = False
    source: Literal["human", "predicted", "human_confirmed"] = "human"


class WordMatch(BaseModel):
    """Per-word match result — spec §1 ``WordMatch``."""

    model_config = ConfigDict(extra="forbid")

    line_index: int
    word_index: int | None
    ocr_text: str
    ground_truth_text: str
    match_status: MatchStatus
    fuzz_score: float | None = None
    normalized_match: bool = False
    """True when ``match_status=exact`` was only achieved after normalization
    (long-s / ligature → ASCII). The UI renders a ``≈`` badge on this word's
    status icon. Default False (non-normalized exact or any other status).
    Added in issue #259 / spec
    ``docs/specs/2026-05-12-text-normalization-design.md``."""
    is_validated: bool = False
    text_style_labels: list[str] = Field(default_factory=list)
    word_components: list[str] = Field(default_factory=list)
    bbox: BBox
    word_id: str | None = None
    # Per-character bounding boxes (image-pixel coords) set via the CharFixer
    # Apply button (POST .../char-bboxes).  ``None`` until the user has
    # applied char bboxes for this word; empty list means bboxes were cleared.
    # Persisted in ``word_attributes["{li}_{wi}"]["char_bboxes"]`` in the
    # saved envelope so they survive page reloads.
    char_bboxes: list[BBox] | None = None
    # Glyph-level annotations — spec ``specs/20-glyph-annotations.md`` §3.
    # None = "not yet reviewed"; GlyphAnnotationsModel() = "reviewed, nothing".
    # Persisted in the v2.2 envelope word dict (``glyph_annotations`` key).
    glyph_annotations: GlyphAnnotationsModel | None = None
    # Classifier predictions — NOT persisted; regenerated on each page fetch.
    # Rendered as greyed-out chips in the UI (spec §5.1).
    glyph_predictions: GlyphAnnotationsModel | None = None


class LineMatch(BaseModel):
    """Per-line rollup with pre-computed counters — spec §1 ``LineMatch``."""

    line_index: int
    paragraph_index: int | None
    # FO-7: block_index groups lines into top-level layout blocks.
    # Populated when the OCR engine exposes a block layer (e.g. via
    # ``Page.items[block_idx]``).  ``None`` until M3-proper wires a real
    # ``LocalDoctrPageLoader`` that maps lines → parent block indices.
    # The frontend ``selection-walk.ts`` uses this to enable block-level
    # sibling navigation; when ``None`` on all lines, block walk is a no-op.
    block_index: int | None = None
    ocr_line_text: str
    ground_truth_line_text: str
    word_matches: list[WordMatch]
    overall_match_status: MatchStatus
    exact_count: int
    fuzzy_count: int
    mismatch_count: int
    unmatched_gt_count: int
    unmatched_ocr_count: int
    validated_word_count: int
    total_word_count: int
    is_fully_validated: bool


class Selection(BaseModel):
    """Backend-canonical per-page UI selection state."""

    selection_mode: Literal["paragraph", "line", "word"] = "word"
    selected_paragraphs: set[int] = Field(default_factory=set)
    selected_lines: set[int] = Field(default_factory=set)
    selected_words: set[tuple[int, int]] = Field(default_factory=set)


class LineFilter(StrEnum):
    """Line display filter — spec §1 ``LineFilter``."""

    UNVALIDATED = "unvalidated"
    MISMATCHED = "mismatched"
    ALL = "all"


class JobStatus(StrEnum):
    """Job lifecycle state — spec §1 ``JobStatus``.

    Mirrors ``core.jobs.runner.JobStatus`` exactly (including ``CANCELLED``,
    reached via cooperative cancel — spec §5.10). The two enums are kept
    separate (runtime layer vs. wire layer) but
    ``tests/unit/core/jobs/test_job_type_contract.py`` proves they agree so
    they cannot silently drift — see
    ``docs/issues/2026-07-21-jobs-api-openapi-mismatch.md`` (P1-JOBS-API).
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    """Discriminant for background job kind — spec §1 ``JobType``.

    Values are exactly the ``job_type`` strings the runner's registered
    handlers accept (``core.jobs.runner._HANDLERS`` /
    ``core.jobs.runner.registered_job_types()``); previously this enum
    listed job types the runner never produced and omitted four it does —
    see ``docs/issues/2026-07-21-jobs-api-openapi-mismatch.md`` (P1-JOBS-API).
    ``tests/unit/core/jobs/test_job_type_contract.py`` fails if a registered
    handler has no matching member (or vice versa).
    """

    RELOAD_OCR = "reload_ocr"
    SAVE_PROJECT = "save_project"
    EXPORT = "export"
    ROTATE_PAGE = "rotate_page"
    AUTO_ROTATE_ALL = "auto_rotate_all"
    REFINE_BBOXES = "refine_bboxes"
    PROPOSE_PAGE_KINDS = "propose_page_kinds"
    PROPOSE_REGIONS = "propose_regions"
    # A store-miss page load moved onto the job system —
    # docs/specs/2026-08-08-page-load-progress-design.md "Move page loading
    # onto the job system". GET /api/projects/{id}/pages/{idx} submits this
    # only when the page is absent from both in-memory state and the labeled
    # store; a hit stays fully synchronous and submits no job.
    LOAD_PAGE = "load_page"


class JobProgress(BaseModel):
    """Progress counters for a running job — spec §1 ``JobProgress``."""

    current: int = 0
    total: int = 0
    current_page: int | None = None
    message: str = ""


class JobResultFailure(TypedDict):
    """One page save failure — mirrors ``api.pages.SaveFailure``'s shape."""

    page_index: int
    error: str


class JobResult(TypedDict, total=False):
    """Job-type-specific extra data a handler produced — spec §1 ``Job.result``.

    Flat and optional (``total=False``) across every job type rather than a
    ``JobType``-discriminated union: the union would be brittle as handlers
    change, and this flat shape still gives the generated TypeScript real
    field names — see
    ``docs/issues/2026-07-21-jobs-api-openapi-mismatch.md`` (P1-JOBS-API).
    ``core.jobs.runner.to_public_job`` populates these from the runner's
    ``Job.payload`` (allowlisted via ``core.jobs.runner._PAYLOAD_RESULT_KEYS``)
    and ``Job.result``. Keys that exist today:

    - ``save_project``: ``failures``, ``skipped_pages`` (int — pages not yet
      registered in the store), ``skipped_indices``.
    - ``refine_bboxes``: ``refined`` (int — words touched).
    - ``propose_page_kinds``: ``run_id``, ``proposal_count``.
    - ``export``: ``words_exported_detection``, ``words_exported_recognition``,
      ``pages_skipped_not_validated`` — also merged flat at the SSE frame's
      top level for backward compatibility (``JobRunner._emit``); both
      places carry the same data.

    ``reload_ocr``, ``rotate_page``, ``auto_rotate_all``, ``propose_regions``
    and ``load_page`` do not populate this field today.
    """

    failures: list[JobResultFailure]
    skipped_pages: int
    skipped_indices: list[int]
    refined: int
    run_id: str
    proposal_count: int
    words_exported_detection: int
    words_exported_recognition: int
    pages_skipped_not_validated: int


class Job(BaseModel):
    """Background job record — spec §1 ``Job``. Mirrors pgdp-prep ``core/models.py``."""

    id: str
    type: JobType
    project_id: str | None
    status: JobStatus
    progress: JobProgress
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    result: JobResult | None = None
    """Job-type-specific extra data the handler produced; ``None`` when the
    handler wrote nothing. See ``JobResult`` for the documented shape."""


__all__ = [
    "BBox",
    "EncodedDims",
    "GlyphAnnotationsModel",
    "Job",
    "JobProgress",
    "JobResult",
    "JobResultFailure",
    "JobStatus",
    "JobType",
    "LigatureMarkModel",
    "LineFilter",
    "LineMatch",
    "MatchStatus",
    "PageSource",
    "Project",
    "RegionProposalView",
    "RegionView",
    "Selection",
    "WordMatch",
]

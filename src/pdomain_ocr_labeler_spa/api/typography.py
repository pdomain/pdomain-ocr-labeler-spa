"""Server-authoritative typography review and portable correction export."""

from __future__ import annotations

import hashlib
import json
from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pdomain_book_tools.typography import (
    GRAPHEME_SEGMENTATION_VERSION,
    REVIEW_CONTRACT_VERSION,
    CoordinateTransform,
    CorrectionBundle,
    CorrectionDecision,
    LabelingBundle,
    LabelState,
    ModelRun,
    PageGeometry,
    ReplacementArtifact,
    ReviewState,
    StyleLabel,
    TypographyCorrection,
    TypographyReviewMetadata,
    TypographySpan,
    TypographyTaxonomy,
    TypographyTaxonomyLabel,
    WordGeometry,
    WordTypography,
    split_graphemes,
)
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError

from ..core.models import Project
from ..core.project_state import ProjectState
from ..core.typography_review import (
    ImportedTextBinding,
    ImportedTextValidationHead,
    ImportedTextValidationLog,
    StaleImportedTextValidationError,
    StaleTypographyBindingError,
    TypographyBinding,
    TypographyCorrectionLog,
    TypographyJournalEnvelope,
    stable_page_id,
    stable_word_id,
    typography_reviewed,
)
from ..core.typography_review_counts import append_typography_review_counts_best_effort
from .dependencies import bind_page_labeling_lease, get_project_state

if TYPE_CHECKING:
    from collections.abc import Mapping

router = APIRouter(tags=["typography"])

_TYPOGRAPHY_POLICY: dict[StyleLabel, tuple[bool, bool]] = {
    StyleLabel.ITALIC: (True, True),
    StyleLabel.BOLD: (True, True),
    StyleLabel.SMALL_CAPS: (True, True),
    StyleLabel.LETTER_SPACED: (True, False),
    StyleLabel.SUPERSCRIPT: (True, False),
    StyleLabel.SUBSCRIPT: (True, False),
    StyleLabel.UNDERLINE: (False, False),
    StyleLabel.FONT_BLACKLETTER: (True, False),
    StyleLabel.FONT_ANTIQUA: (True, False),
    StyleLabel.FONT_UPRIGHT_IN_ITALIC: (True, False),
    StyleLabel.FONT_OTHER_REVIEWED: (False, False),
}

TYPOGRAPHY_TAXONOMY = TypographyTaxonomy(
    version="labeler-v1",
    labels=tuple(
        TypographyTaxonomyLabel(
            value=label.value,
            display_name=label.value.replace("_", " ").title(),
            required_for_completion=_TYPOGRAPHY_POLICY[label][0],
            trainable=_TYPOGRAPHY_POLICY[label][1],
        )
        for label in StyleLabel
    ),
)

_TYPOGRAPHY_REQUIRED_LABELS = {
    label.value for label in TYPOGRAPHY_TAXONOMY.labels if label.required_for_completion
}
"""Every ``core.typography_review.typography_reviewed`` call in this module
shares this fixed set, derived from the router's default taxonomy — not a
bundle's own taxonomy, even when one is loaded. Preserves the behavior this
module has always had (``_current_head``, ``typography_page_review``, and
now ``append_typography_correction``'s rollup write all evaluated
completeness against this same fixed set before P2-TYPOGRAPHY-ROLLUP, and
still do)."""


class LabelStates(RootModel[dict[str, Literal["unknown", "positive", "negative"]]]):
    """Exact tri-state map retained by FastAPI's OpenAPI compatibility pass."""


class TypographyContractDescriptor(BaseModel):
    """Runtime descriptor plus nullable fields that publish canonical schemas."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
    review_contract_version: str
    grapheme_map_version: str
    taxonomy: TypographyTaxonomy
    label_states_schema: LabelStates | None = None
    word_typography: WordTypography | None = None
    correction: TypographyCorrection | None = None


class ReplacementArtifactPayload(BaseModel):
    """Untrusted bytes paired with a declared replacement artifact."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    artifact_id: str
    data_base64: str


class TypographyCorrectionSubmission(BaseModel):
    """Correction intent; trusted lineage is deliberately absent."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    expected_head: str = Field(min_length=64, max_length=64)
    correction_id: str
    taxonomy_version: str
    taxonomy_hash: str
    grapheme_map_version: str
    labeler_id: str = "local"
    decision: CorrectionDecision
    replacement: WordTypography | None = None
    replacement_text_sha256: str | None = None
    replacement_page_sha256: str | None = None
    replacement_image_sha256: str | None = None
    replacement_page_head_sha256: str | None = None
    replacement_word_revision: int | None = Field(default=None, ge=1)
    metadata: TypographyReviewMetadata | None = None
    replacement_artifacts: tuple[ReplacementArtifact, ...] = ()
    replacement_artifact_payloads: tuple[ReplacementArtifactPayload, ...] = ()
    page_geometry: PageGeometry | None = None
    geometry: tuple[WordGeometry, ...] | None = None
    model_runs: tuple[ModelRun, ...] = ()
    coordinate_transforms: tuple[CoordinateTransform, ...] = ()


class TypographyHeadResponse(BaseModel):
    """Canonical current binding and latest correction for one word."""

    project_id: str
    page_index: int
    logical_page_id: str
    word_id: str
    page_sha256: str
    image_sha256: str
    text_sha256: str
    page_head_sha256: str
    word_revision: int
    text: str
    graphemes: tuple[str, ...]
    grapheme_map_version: str
    taxonomy: TypographyTaxonomy
    imported_text_validation_available: bool
    revision: int
    correction: TypographyCorrection | None
    # P1-VALIDATE-GATE: whether *this word's own* graphemes have a complete,
    # accepted typography review — the per-word analogue of
    # ``TypographyPageReviewResponse.typography_reviewed_words``. Computed by
    # ``_typography_reviewed`` from this word's own current correction, which
    # ``_current_head`` has already epoch-filtered to this word's binding, so
    # no separate staleness check is needed here (contrast
    # ``typography_page_review``, which shares one page-wide epoch across
    # words and so re-checks each word's own hashes against it).
    typography_reviewed: bool
    head_token: str


class ImportedTextValidationSubmission(BaseModel):
    """Explicit CAS intent for the exact imported text currently displayed."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    expected_head: str = Field(min_length=64, max_length=64)
    validated: bool


class ImportedTextValidationResponse(BaseModel):
    """Persistent text-validation head for one imported bundle word."""

    project_id: str
    page_index: int
    word_id: str
    text: str
    text_sha256: str
    occurrence_id: str
    revision: int
    validated: bool
    head_token: str


class TypographyPageReviewResponse(BaseModel):
    """Current per-page correction heads and completion counts."""

    project_id: str
    page_index: int
    logical_page_id: str
    reviewed_words: int
    text_reviewed_words: int
    typography_reviewed_words: int
    blocked_words: int
    total_words: int
    complete: bool
    heads: tuple[TypographyCorrection, ...]


class TypographyWorklistWord(BaseModel):
    """One bundle-native word plus its current local review state."""

    word_id: str
    text: str
    graphemes: tuple[str, ...]
    source_review_state: ReviewState
    source_label_states: dict[str, LabelState]
    source_spans: tuple[TypographySpan, ...]
    warnings: tuple[str, ...]
    current_correction: TypographyCorrection | None
    decision: CorrectionDecision | None
    reviewed: bool
    typography_reviewed: bool
    text_reviewed: bool


class TypographyWorklistResponse(BaseModel):
    """Ordered geometry-free review input for the active portable bundle."""

    project_id: str
    page_index: int
    logical_page_id: str
    bundle_id: str
    taxonomy: TypographyTaxonomy
    words: tuple[TypographyWorklistWord, ...]
    total_words: int
    text_reviewed_words: int
    typography_reviewed_words: int
    blocked_words: int
    complete: bool


class CorrectionBundleExportRequest(BaseModel):
    """Portable source bundle and optional frozen word-head selection."""

    labeling_bundle: LabelingBundle | None = None
    selected_word_ids: tuple[str, ...] | None = None


class CorrectionBundleExportResponse(BaseModel):
    """Immutable exported bundle and its project-local relative path."""

    bundle: CorrectionBundle
    relative_path: str
    artifact_relative_paths: dict[str, str]


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _bundle_payload_by_hash(state: ProjectState, sha256: str) -> bytes:
    loaded = state.loaded_labeling_bundle
    if loaded is None:
        raise ValueError("labeling bundle is not loaded")
    matches = [
        loaded.artifact_payloads[artifact.artifact_id]
        for artifact in loaded.bundle.artifacts
        if artifact.sha256 == sha256
    ]
    if len(matches) != 1:
        raise ValueError("labeling bundle does not expose one exact artifact payload")
    return matches[0]


def _server_replacement_artifacts(
    *,
    correction_id: str,
    state: ProjectState,
    current: TypographyBinding,
) -> tuple[tuple[ReplacementArtifact, ...], tuple[tuple[ReplacementArtifact, bytes], ...]]:
    bundle = state.labeling_bundle
    if bundle is None:
        return (), ()
    page_payload = _bundle_payload_by_hash(state, current.page_sha256)
    image_payload = _bundle_payload_by_hash(state, current.image_sha256)
    page_head_payload = _canonical_bytes(
        {
            "configuration_hash": bundle.configuration_hash,
            "image_sha256": bundle.image_sha256,
            "page_id": bundle.page_id,
            "page_sha256": bundle.page_sha256,
        }
    )
    payloads = (
        ("page", current.page_sha256, page_payload, "application/json"),
        ("image", current.image_sha256, image_payload, "image/png"),
        ("page-head", current.page_head_sha256, page_head_payload, "application/json"),
    )
    artifacts: list[ReplacementArtifact] = []
    verified: list[tuple[ReplacementArtifact, bytes]] = []
    for role, expected_sha256, payload, media_type in payloads:
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise ValueError(f"current {role} artifact does not match its binding")
        artifact = ReplacementArtifact(
            artifact_id=f"{correction_id}:{role}",
            relative_path=f"{correction_id}.{role}",
            sha256=expected_sha256,
            byte_size=len(payload),
            media_type=media_type,
        )
        artifacts.append(artifact)
        verified.append((artifact, payload))
    return tuple(artifacts), tuple(verified)


def _project_page(project_id: str, page_index: int, state: ProjectState) -> Project:
    project = state.loaded_project
    if project is None or project.project_id != project_id:
        raise HTTPException(status_code=404, detail="project not found")
    if page_index < 0 or page_index >= project.total_pages:
        raise HTTPException(status_code=404, detail="page not found")
    return project


def _logical_page_id(project: Project, page_index: int, state: ProjectState) -> str:
    bundle = state.labeling_bundle
    if bundle is not None:
        return bundle.page_id
    return stable_page_id(project_id=project.project_id, page_index=page_index)


def _bundle_word(state: ProjectState, word_id: str) -> WordTypography | None:
    bundle = state.labeling_bundle
    if bundle is None:
        return None
    return next((word for word in bundle.words if word.word_id == word_id), None)


def _source_text(project: Project, page_index: int, state: ProjectState) -> str:
    image = state.labeling_image_path(page_index)
    return project.ground_truth_map.get(image.name, project.ground_truth_map.get(image.stem, ""))


def _current_page(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> object | None:
    if page_override is not None:
        return page_override
    page_state = state.get_page_state(page_index)
    if page_state is None or page_state.page_record is None:
        return None
    return page_state.page_record.payload


def _page_words(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> tuple[object, ...] | None:
    page = _current_page(project, page_index, state, page_override)
    if page is None:
        return None
    words = getattr(page, "words", None)
    if isinstance(words, (list, tuple)):
        return tuple(words)
    lines = getattr(page, "lines", None)
    if isinstance(lines, (list, tuple)):
        return tuple(word for line in lines for word in (getattr(line, "words", None) or ()))
    return ()


def _review_words(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> tuple[str, ...]:
    bundle = state.labeling_bundle
    if bundle is not None:
        return tuple(word.text for word in bundle.words)
    page_words = _page_words(project, page_index, state, page_override)
    if page_words is not None:
        return tuple(
            ground_truth
            if isinstance((ground_truth := getattr(word, "ground_truth_text", None)), str)
            else text
            if isinstance((text := getattr(word, "text", None)), str)
            else ""
            for word in page_words
        )
    return tuple(_source_text(project, page_index, state).split())


def _corrected_word_text(word: object) -> str:
    ground_truth = getattr(word, "ground_truth_text", None)
    if isinstance(ground_truth, str):
        return ground_truth
    text = getattr(word, "text", None)
    return text if isinstance(text, str) else ""


def _word_identity_text(word: object) -> str:
    """Return the OCR text this word's stable identity is derived from.

    A word's ``word_id`` must survive ground-truth correction — editing
    ground truth is the core activity of this product. This reads the same
    field ``core/page_to_line_matches.py`` feeds into ``stable_word_id``
    when it mints the id embedded in the page payload: raw OCR ``text``,
    never ``ground_truth_text``. Use ``_corrected_word_text``/
    ``_review_words`` for the word's current (ground-truth) content — a
    deliberately different, live value.
    """
    text = getattr(word, "text", None)
    return text if isinstance(text, str) else ""


def _review_identity_texts(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> tuple[str, ...]:
    """Return each on-page word's OCR text, in reading order.

    This is the stable half of a word's identity (see
    ``_word_identity_text``) and mirrors ``core/page_to_line_matches.py``'s
    ``ocr_text`` exactly, so a ``word_id`` computed here always agrees with
    the id embedded in the page payload the frontend already holds,
    regardless of any ground-truth edit. Only used for the derived-id path
    — bundle-backed projects carry a genuinely stored ``word_id`` and never
    reach this function.
    """
    page_words = _page_words(project, page_index, state, page_override)
    if page_words is not None:
        return tuple(_word_identity_text(word) for word in page_words)
    return tuple(_source_text(project, page_index, state).split())


def _canonical_word_id_map(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> dict[str, str]:
    """Map every id a correction might be recorded under to its current id.

    Word identity moved from ground-truth text (live, the pre-fix scheme)
    to OCR text (stable). A correction appended before this fix keeps the
    ground-truth-derived id it was written under — the append-only journal
    is never rewritten — so resolving "this word's history" by the new id
    alone would silently orphan it. This maps both the current id and the
    legacy (ground-truth-derived) id for each on-page position to the
    current id, so a lookup that canonicalizes a stored ``word_id`` through
    this map finds the same word's history under either scheme.

    Empty for bundle-backed projects: their ``word_id`` is stored on the
    imported ``WordTypography``, never derived, so no legacy scheme exists.
    """
    if state.labeling_bundle is not None:
        return {}
    page_id = _logical_page_id(project, page_index, state)
    identity_texts = _review_identity_texts(project, page_index, state, page_override)
    legacy_texts = _review_words(project, page_index, state, page_override)
    mapping: dict[str, str] = {}
    for index, identity_text in enumerate(identity_texts):
        current_id = stable_word_id(
            project_id=project.project_id, page_id=page_id, reading_order=index, text=identity_text
        )
        legacy_id = stable_word_id(
            project_id=project.project_id, page_id=page_id, reading_order=index, text=legacy_texts[index]
        )
        mapping[current_id] = current_id
        mapping[legacy_id] = current_id
    return mapping


def _text_validated_word_ids(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> set[str]:
    bundle = state.labeling_bundle
    if bundle is not None:
        return {
            word.word_id
            for word in bundle.words
            if _imported_text_head(project, page_index, state, word.word_id).validated
        }
    page_words = _page_words(project, page_index, state, page_override)
    if page_words is None:
        return set()
    page_id = _logical_page_id(project, page_index, state)
    identity_texts = _review_identity_texts(project, page_index, state, page_override)
    return {
        stable_word_id(
            project_id=project.project_id,
            page_id=page_id,
            reading_order=index,
            text=identity_texts[index],
        )
        for index, word in enumerate(page_words)
        if "validated" in (getattr(word, "word_labels", None) or ())
    }


def _imported_text_binding(
    project: Project, page_index: int, state: ProjectState, word_id: str
) -> ImportedTextBinding:
    bundle = state.labeling_bundle
    if bundle is None or bundle.bundle_id is None:
        raise HTTPException(status_code=404, detail="labeling bundle not loaded")
    word = next((candidate for candidate in bundle.words if candidate.word_id == word_id), None)
    if word is None:
        raise HTTPException(status_code=404, detail="word not found in labeling bundle")
    return ImportedTextBinding(
        bundle_id=bundle.bundle_id,
        page_id=bundle.page_id,
        page_sha256=bundle.page_sha256,
        page_head_sha256=bundle.page_head_sha256,
        word_id=word.word_id,
        text=word.text,
        text_sha256=word.text_sha256,
    )


def _imported_text_head(
    project: Project, page_index: int, state: ProjectState, word_id: str
) -> ImportedTextValidationHead:
    binding = _imported_text_binding(project, page_index, state, word_id)
    return ImportedTextValidationLog(project.project_root, corpus_root=project.project_root.parent).head(
        binding
    )


def _imported_text_response(
    project: Project,
    page_index: int,
    head: ImportedTextValidationHead,
) -> ImportedTextValidationResponse:
    return ImportedTextValidationResponse(
        project_id=project.project_id,
        page_index=page_index,
        word_id=head.binding.word_id,
        text=head.binding.text,
        text_sha256=head.binding.text_sha256,
        occurrence_id=head.occurrence_id,
        revision=head.revision,
        validated=head.validated,
        head_token=head.head_token,
    )


def _page_line_words(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> list[list[object]]:
    page = _current_page(project, page_index, state, page_override)
    if page is None:
        return [list(_source_text(project, page_index, state).split())]
    lines = getattr(page, "lines", None)
    if lines is not None:
        return [list(getattr(line, "words", None) or ()) for line in lines]
    return [list(_page_words(project, page_index, state, page_override) or ())]


def _current_page_content(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> object:
    """Build the hash input for this page's ``page_sha256`` staleness fingerprint.

    Structural only: ordered line/word boundaries, word count, and each
    word's OCR — never ground-truth — text. A typography correction is a
    statement about one word's own graphemes: it must go stale when that
    word's own content changes (already covered, word-scoped, by
    ``text_sha256`` — see ``_initial_binding``) or when a structural edit
    (add/delete/merge/split) shifts reading order — never merely because
    some *other* word's ground truth was corrected. See
    ``docs/context/decisions.md``, 2026-09-18, "Typography epoch
    granularity".

    Deliberately excludes bounding boxes too, for the same reason: a word's
    position is edited routinely (``nudge_bbox``), just like ground truth,
    and a shared page-wide fingerprint that included it would reproduce the
    same over-invalidation bug through a different door. Word position is
    consequently *not* separately protected at word scope either — the
    upstream ``pdomain_book_contracts`` review contract hard-validates
    ``WordTypography.text_sha256`` against a literal ``sha256(text)``, so
    there is no available per-word hash slot left to carry a bbox
    fingerprint without a wire-format change to that contract. A word's own
    bbox nudge therefore no longer invalidates any review, including its
    own — a known, narrower gap than the one this fixes, surfaced here
    rather than fixed silently.

    See ``_legacy_page_content`` for the pre-fix (whole-page,
    ground-truth- and bbox-inclusive) formula this supersedes, and
    ``_legacy_binding``/``_current_epoch_migration_aware`` for how a
    correction recorded under that formula keeps resolving.
    """
    page_id = _logical_page_id(project, page_index, state)
    reading_order = 0
    projected_lines: list[list[dict[str, object]]] = []
    for line in _page_line_words(project, page_index, state, page_override):
        projected_line: list[dict[str, object]] = []
        for word in line:
            text = word if isinstance(word, str) else _word_identity_text(word)
            projected_line.append(
                {
                    "word_id": stable_word_id(
                        project_id=project.project_id,
                        page_id=page_id,
                        reading_order=reading_order,
                        text=text,
                    ),
                    "text": text,
                }
            )
            reading_order += 1
        projected_lines.append(projected_line)
    return {"lines": projected_lines}


def _legacy_page_content(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> object:
    """Build the pre-fix (2026-08-22 through 2026-09-18) whole-page hash input.

    Preserved verbatim from before this fix, unreachable from any new
    correction: every word's ground-truth text and bounding box, keyed by a
    ground-truth-derived ``word_id``. Used only by ``_legacy_binding``, to
    recognize a correction recorded under this formula as still current —
    see ``_current_epoch_migration_aware``.
    """
    page_id = _logical_page_id(project, page_index, state)
    reading_order = 0
    projected_lines: list[list[dict[str, object]]] = []
    for line in _page_line_words(project, page_index, state, page_override):
        projected_line: list[dict[str, object]] = []
        for word in line:
            text = word if isinstance(word, str) else _corrected_word_text(word)
            bbox = None
            if not isinstance(word, str):
                for field in ("ground_truth_bounding_box", "bounding_box", "bbox"):
                    if (candidate_bbox := getattr(word, field, None)) is not None:
                        bbox = candidate_bbox
                        break
            if bbox is None:
                bbox_value = None
            elif callable(model_dump := getattr(bbox, "model_dump", None)):
                bbox_value = model_dump(mode="json")
            elif isinstance(bbox, (list, tuple)):
                bbox_value = list(bbox)
            elif isinstance(bbox, dict):
                bbox_value = bbox
            else:
                bbox_value = {
                    field: getattr(bbox, field)
                    for field in ("x", "y", "width", "height")
                    if hasattr(bbox, field)
                }
            projected_line.append(
                {
                    "word_id": stable_word_id(
                        project_id=project.project_id,
                        page_id=page_id,
                        reading_order=reading_order,
                        text=text,
                    ),
                    "corrected_text": text,
                    "bbox": bbox_value,
                }
            )
            reading_order += 1
        projected_lines.append(projected_line)
    return {"lines": projected_lines}


def _word_text(
    project: Project,
    page_index: int,
    word_id: str,
    state: ProjectState,
    page_override: object | None = None,
) -> str:
    bundle_word = _bundle_word(state, word_id)
    if bundle_word is not None:
        return bundle_word.text
    page_id = _logical_page_id(project, page_index, state)
    # Canonicalize first: a caller may still hold a legacy (ground-truth-
    # derived) id minted before this fix shipped — see
    # ``_canonical_word_id_map``.
    id_map = _canonical_word_id_map(project, page_index, state, page_override)
    canonical_word_id = id_map.get(word_id, word_id)
    identity_texts = _review_identity_texts(project, page_index, state, page_override)
    content_texts = _review_words(project, page_index, state, page_override)
    for index, identity_text in enumerate(identity_texts):
        candidate = stable_word_id(
            project_id=project.project_id, page_id=page_id, reading_order=index, text=identity_text
        )
        if candidate == canonical_word_id:
            return content_texts[index]
    raise HTTPException(status_code=404, detail="word not found on page")


def _active_word_ids(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> set[str]:
    bundle = state.labeling_bundle
    if bundle is not None:
        return {word.word_id for word in bundle.words}
    page_id = _logical_page_id(project, page_index, state)
    identity_texts = _review_identity_texts(project, page_index, state, page_override)
    return {
        stable_word_id(
            project_id=project.project_id,
            page_id=page_id,
            reading_order=index,
            text=identity_text,
        )
        for index, identity_text in enumerate(identity_texts)
    }


def _initial_binding(
    project: Project,
    page_index: int,
    word_id: str,
    state: ProjectState,
    page_override: object | None = None,
) -> TypographyBinding:
    bundle = state.labeling_bundle
    bundle_word = _bundle_word(state, word_id)
    if bundle is not None and bundle_word is not None:
        return TypographyBinding(
            page_sha256=bundle.page_sha256,
            image_sha256=bundle.image_sha256,
            text_sha256=bundle_word.text_sha256,
            page_head_sha256=bundle.page_head_sha256,
            word_revision=bundle_word.word_revision,
        )
    image_sha = hashlib.sha256(state.labeling_image_path(page_index).read_bytes()).hexdigest()
    text_sha = hashlib.sha256(
        _word_text(project, page_index, word_id, state, page_override).encode()
    ).hexdigest()
    page_sha = _canonical_hash(
        {
            "content": _current_page_content(project, page_index, state, page_override),
            "image_sha256": image_sha,
            "page_index": page_index,
            "project_id": project.project_id,
        }
    )
    page_head = _canonical_hash(
        {
            "logical_page": _logical_page_id(project, page_index, state),
            "page_sha256": page_sha,
        }
    )
    return TypographyBinding(
        page_sha256=page_sha,
        image_sha256=image_sha,
        text_sha256=text_sha,
        page_head_sha256=page_head,
        word_revision=0,
    )


def _legacy_binding(
    project: Project,
    page_index: int,
    word_id: str,
    state: ProjectState,
    page_override: object | None = None,
) -> TypographyBinding | None:
    """Return the page's pre-fix whole-page binding, or ``None`` for a bundle.

    A bundle-backed project never used the whole-page scheme this bridges
    (``_initial_binding`` already returns early for one, from the bundle's
    own ``page_sha256`` — see ``_canonical_word_id_map``'s equivalent early
    return), so there is nothing to migrate.

    Otherwise mirrors ``_initial_binding`` exactly, except hashed over
    ``_legacy_page_content`` instead of ``_current_page_content``. Exists
    only so a correction recorded before this fix shipped — whose
    ``base_page_sha256``/``page_head_sha256`` were computed under that old
    formula — is not treated as orphaned the instant this fix ships,
    provided nothing on the page has changed since it was recorded. See
    ``_current_epoch_migration_aware``.
    """
    if state.labeling_bundle is not None:
        return None
    image_sha = hashlib.sha256(state.labeling_image_path(page_index).read_bytes()).hexdigest()
    text_sha = hashlib.sha256(
        _word_text(project, page_index, word_id, state, page_override).encode()
    ).hexdigest()
    page_sha = _canonical_hash(
        {
            "content": _legacy_page_content(project, page_index, state, page_override),
            "image_sha256": image_sha,
            "page_index": page_index,
            "project_id": project.project_id,
        }
    )
    page_head = _canonical_hash(
        {
            "logical_page": _logical_page_id(project, page_index, state),
            "page_sha256": page_sha,
        }
    )
    return TypographyBinding(
        page_sha256=page_sha,
        image_sha256=image_sha,
        text_sha256=text_sha,
        page_head_sha256=page_head,
        word_revision=0,
    )


def _current_epoch_migration_aware(
    records: tuple[TypographyJournalEnvelope, ...] | list[TypographyJournalEnvelope],
    *,
    logical_page_id: str,
    current: TypographyBinding,
    legacy: TypographyBinding | None,
) -> tuple[TypographyJournalEnvelope, ...]:
    """Resolve the current page epoch, accepting either page-hash scheme.

    Tries *current* (this fix's structural-only scheme) first — every
    correction recorded after this fix uses it exclusively, so this is the
    only branch a page ever needs once it has been touched again. Falls
    back to *legacy* (``_legacy_binding``, ``None`` for a bundle-backed
    project) only when that finds nothing, bridging a correction recorded
    before this fix shipped.

    A pre-fix correction followed, on the same page, by a post-fix one sits
    in the *older* (legacy) epoch under this fallback and is not reachable
    through the new one — the two page-hash formulas hash different content,
    so a pre-fix root can never chain onto a post-fix record. That pre-fix
    correction is not silently orphaned by this: ``current_epoch`` still
    finds it, just as a still-current (if superseded-going-forward) epoch —
    the same outcome a genuine structural edit would have produced.
    """
    epoch = TypographyCorrectionLog.current_epoch(records, logical_page_id=logical_page_id, current=current)
    if epoch or legacy is None:
        return epoch
    return TypographyCorrectionLog.current_epoch(records, logical_page_id=logical_page_id, current=legacy)


def _page_root_matches(
    root: TypographyCorrection,
    current: TypographyBinding,
    legacy: TypographyBinding | None,
) -> bool:
    """Whether *root* still matches the page's live state, under either
    page-hash scheme — the non-epoch-walking counterpart of
    ``_current_epoch_migration_aware``, used by callers that already hold a
    lineage root and only need to recheck it.
    """

    def _matches(binding: TypographyBinding) -> bool:
        return (
            root.base_page_sha256 == binding.page_sha256
            and root.base_image_sha256 == binding.image_sha256
            and root.page_head_sha256 == binding.page_head_sha256
        )

    return _matches(current) or (legacy is not None and _matches(legacy))


def _current_head(
    project: Project,
    page_index: int,
    word_id: str,
    log: TypographyCorrectionLog,
    state: ProjectState,
) -> TypographyHeadResponse:
    # A caller may still hold a legacy (ground-truth-derived) id minted
    # before word identity moved to OCR text — canonicalize up front so a
    # stale-but-still-valid id keeps resolving, and the response hands back
    # the current id going forward. See ``_canonical_word_id_map``.
    id_map = _canonical_word_id_map(project, page_index, state)
    word_id = id_map.get(word_id, word_id)
    logical_page_id = _logical_page_id(project, page_index, state)
    initial = _initial_binding(project, page_index, word_id, state)
    legacy = _legacy_binding(project, page_index, word_id, state)
    records = _current_epoch_migration_aware(
        log.records(logical_page_id),
        logical_page_id=logical_page_id,
        current=initial,
        legacy=legacy,
    )
    word_head = next(
        (
            row.correction
            for row in reversed(records)
            if id_map.get(row.correction.word_id, row.correction.word_id) == word_id
        ),
        None,
    )
    # ``word_head`` itself stays whatever the epoch found — a later
    # correction still needs it to continue this word's own revision chain
    # (``revision``/``supersedes_id``/``word_revision``), even when the text
    # below has drifted. Only "is this word's own graphemes review still
    # about its own current text" is affected: a structural page epoch no
    # longer breaks on a ground-truth edit (see ``_current_page_content``),
    # so that currency is no longer a side effect of the page epoch check
    # above and must be checked here explicitly. ``text_sha256`` is
    # word-scoped, so this only affects *this* word's own
    # ``typography_reviewed``, never another word's.
    own_text_is_current = word_head is None or word_head.effective_text_sha256 == initial.text_sha256
    text = _word_text(project, page_index, word_id, state)
    response = TypographyHeadResponse(
        project_id=project.project_id,
        page_index=page_index,
        logical_page_id=logical_page_id,
        word_id=word_id,
        page_sha256=initial.page_sha256,
        image_sha256=initial.image_sha256,
        text_sha256=initial.text_sha256,
        page_head_sha256=initial.page_head_sha256,
        word_revision=word_head.effective_word_revision if word_head else 0,
        text=text,
        graphemes=split_graphemes(text),
        grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
        taxonomy=(state.labeling_bundle.taxonomy if state.labeling_bundle else TYPOGRAPHY_TAXONOMY),
        imported_text_validation_available=state.labeling_bundle is not None,
        revision=word_head.revision if word_head else 0,
        correction=word_head,
        typography_reviewed=(
            own_text_is_current
            and typography_reviewed(word_head, required_labels=_TYPOGRAPHY_REQUIRED_LABELS)
        ),
        head_token="0" * 64,
    )
    return response.model_copy(
        update={"head_token": _canonical_hash(response.model_dump(mode="json", exclude={"head_token"}))}
    )


def _correction_lineage_binding(
    initial: TypographyBinding,
    records: tuple[TypographyJournalEnvelope, ...],
    word_id: str,
    id_map: Mapping[str, str],
) -> TypographyBinding:
    """Resolve portable correction ancestry without replacing persisted UI state.

    *word_id* and every ``record.correction.word_id`` are canonicalized
    through *id_map* before comparison, so a lineage that started under a
    legacy (ground-truth-derived) id — see ``_canonical_word_id_map`` — is
    still recognized as the same word's history.
    """
    page_head = records[-1].correction if records else None
    word_head = next(
        (
            record.correction
            for record in reversed(records)
            if id_map.get(record.correction.word_id, record.correction.word_id) == word_id
        ),
        None,
    )
    return TypographyBinding(
        page_sha256=page_head.effective_page_sha256 if page_head else initial.page_sha256,
        image_sha256=page_head.effective_image_sha256 if page_head else initial.image_sha256,
        text_sha256=word_head.effective_text_sha256 if word_head else initial.text_sha256,
        page_head_sha256=(page_head.effective_page_head_sha256 if page_head else initial.page_head_sha256),
        word_revision=(
            word_head.effective_word_revision
            if word_head
            else (initial.word_revision if page_head is None else 0)
        ),
    )


@router.get("/api/typography/contract", response_model=TypographyContractDescriptor)
def get_typography_contract() -> TypographyContractDescriptor:
    """Return released contract versions and expose its types in OpenAPI."""
    return TypographyContractDescriptor(
        review_contract_version=REVIEW_CONTRACT_VERSION,
        grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
        taxonomy=TYPOGRAPHY_TAXONOMY,
    )


@router.get(
    "/api/projects/{project_id}/pages/{page_index}/typography/words/{word_id}/head",
    response_model=TypographyHeadResponse,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def get_typography_head(
    project_id: str,
    page_index: int,
    word_id: str,
    state: ProjectState = Depends(get_project_state),
) -> TypographyHeadResponse:
    """Resolve current page and word lineage from server-owned state."""
    project = _project_page(project_id, page_index, state)
    return _current_head(
        project,
        page_index,
        word_id,
        TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent),
        state,
    )


@router.post(
    "/api/projects/{project_id}/pages/{page_index}/typography/words/{word_id}/corrections",
    response_model=TypographyHeadResponse,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def append_typography_correction(
    project_id: str,
    page_index: int,
    word_id: str,
    submission: TypographyCorrectionSubmission,
    state: ProjectState = Depends(get_project_state),
) -> TypographyHeadResponse:
    """Append canonical intent against the current server-derived head."""
    project = _project_page(project_id, page_index, state)
    logical_page_id = _logical_page_id(project, page_index, state)
    taxonomy = state.labeling_bundle.taxonomy if state.labeling_bundle else TYPOGRAPHY_TAXONOMY
    log = TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent)
    with state.get_page_lock(page_index):
        id_map = _canonical_word_id_map(project, page_index, state)
        head = _current_head(project, page_index, word_id, log, state)
        initial = _initial_binding(project, page_index, word_id, state)
        records = log.current_epoch(
            log.records(logical_page_id),
            logical_page_id=logical_page_id,
            current=initial,
        )
        lineage = _correction_lineage_binding(initial, records, head.word_id, id_map)
        if submission.expected_head != head.head_token:
            raise HTTPException(status_code=409, detail="typography head is stale")
        if (
            submission.taxonomy_version != taxonomy.version
            or submission.taxonomy_hash != taxonomy.taxonomy_hash
            or submission.grapheme_map_version != GRAPHEME_SEGMENTATION_VERSION
        ):
            raise HTTPException(status_code=422, detail="typography contract is stale or tampered")
        if submission.replacement is not None:
            try:
                submission.replacement.validate_taxonomy(taxonomy)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="invalid typography taxonomy states") from exc
            allowed_labels = set(taxonomy.label_values())
            used_labels = set(submission.replacement.label_states) | {
                span.label for span in submission.replacement.spans
            }
            if not used_labels <= allowed_labels:
                raise HTTPException(status_code=422, detail="unknown typography label")
        try:
            correction = TypographyCorrection(
                correction_id=submission.correction_id,
                # Continue the existing lineage's own stored id — which may
                # be a legacy, ground-truth-derived id minted before this
                # fix shipped — so ``TypographyCorrectionLog``'s exact-match
                # revision-chain validation (``core/typography_review.py``)
                # keeps matching it. A word with no prior review starts a
                # fresh lineage under its current (OCR-derived) id.
                word_id=(head.correction.word_id if head.correction is not None else head.word_id),
                revision=head.revision + 1,
                supersedes_id=head.correction.correction_id if head.correction else None,
                base_page_sha256=lineage.page_sha256,
                base_image_sha256=lineage.image_sha256,
                base_text_sha256=lineage.text_sha256,
                base_word_revision=lineage.word_revision,
                replacement_text_sha256=submission.replacement_text_sha256,
                replacement_page_sha256=submission.replacement_page_sha256,
                replacement_image_sha256=submission.replacement_image_sha256,
                replacement_page_head_sha256=submission.replacement_page_head_sha256,
                replacement_word_revision=submission.replacement_word_revision,
                taxonomy_version=submission.taxonomy_version,
                taxonomy_hash=submission.taxonomy_hash,
                grapheme_map_version=submission.grapheme_map_version,
                page_head_sha256=lineage.page_head_sha256,
                labeler_id=submission.labeler_id,
                decision=submission.decision,
                replacement=submission.replacement,
                metadata=submission.metadata,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid typography correction") from exc
        replacement_artifacts = submission.replacement_artifacts
        server_verified_payloads: tuple[tuple[ReplacementArtifact, bytes], ...] = ()
        if (
            not replacement_artifacts
            and correction.decision
            in {
                CorrectionDecision.ACCEPT,
                CorrectionDecision.APPROVED_EDIT,
                CorrectionDecision.REVIEWED_REGULAR,
            }
            and correction.replacement is not None
            and correction.replacement_text_sha256 == initial.text_sha256
            and correction.replacement_page_sha256 == initial.page_sha256
            and correction.replacement_image_sha256 == initial.image_sha256
            and correction.replacement_page_head_sha256 == initial.page_head_sha256
        ):
            try:
                replacement_artifacts, server_verified_payloads = _server_replacement_artifacts(
                    correction_id=correction.correction_id,
                    state=state,
                    current=initial,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="current replacement artifacts are unavailable",
                ) from exc
        try:
            correction_history = (
                *(record.correction for record in records),
                correction,
            )
            _ = CorrectionBundle(
                schema_version=REVIEW_CONTRACT_VERSION,
                configuration_hash="0" * 64,
                labeling_bundle_id="0" * 64,
                corrections=correction_history,
                replacement_artifacts=replacement_artifacts,
                page_geometry=submission.page_geometry,
                geometry=submission.geometry,
                model_runs=submission.model_runs,
                coordinate_transforms=submission.coordinate_transforms,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid portable correction components") from exc
        artifacts_by_id = {artifact.artifact_id: artifact for artifact in replacement_artifacts}
        if len(artifacts_by_id) != len(replacement_artifacts):
            raise HTTPException(status_code=422, detail="replacement artifact ids must be unique")
        payloads_by_id = {
            artifact_payload.artifact_id: artifact_payload
            for artifact_payload in submission.replacement_artifact_payloads
        }
        if server_verified_payloads:
            verified_payloads = list(server_verified_payloads)
        elif (
            len(payloads_by_id) != len(submission.replacement_artifact_payloads)
            or payloads_by_id.keys() != artifacts_by_id.keys()
        ):
            raise HTTPException(
                status_code=422,
                detail="replacement artifact payloads must match declarations",
            )
        else:
            verified_payloads = []
            for artifact_id, artifact in artifacts_by_id.items():
                try:
                    payload = b64decode(payloads_by_id[artifact_id].data_base64, validate=True)
                except (Base64Error, ValueError) as exc:
                    raise HTTPException(
                        status_code=422, detail="invalid replacement artifact payload"
                    ) from exc
                if (
                    len(payload) != artifact.byte_size
                    or hashlib.sha256(payload).hexdigest() != artifact.sha256
                ):
                    raise HTTPException(status_code=422, detail="replacement artifact hash mismatch")
                verified_payloads.append((artifact, payload))
        try:
            log.append(
                correction,
                logical_page_id=logical_page_id,
                current=initial,
                replacement_artifacts=replacement_artifacts,
                page_geometry=submission.page_geometry,
                geometry=submission.geometry,
                model_runs=submission.model_runs,
                coordinate_transforms=submission.coordinate_transforms,
                artifact_payloads=tuple(verified_payloads),
            )
        except StaleTypographyBindingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="replacement artifact publication failed") from exc
        # P2-TYPOGRAPHY-ROLLUP: append only after the correction above has
        # durably succeeded — mirrors save_page_content_to_store's "append
        # only after the head write has succeeded" ordering — and the
        # rollup append is itself best-effort, so an unwritable rollup never
        # turns this already-accepted correction into a failed request.
        append_typography_review_counts_best_effort(
            correction_log=log,
            logical_page_id=logical_page_id,
            total_words=len(_active_word_ids(project, page_index, state)),
            required_labels=_TYPOGRAPHY_REQUIRED_LABELS,
        )
        return _current_head(project, page_index, word_id, log, state)


def _page_records(
    project: Project,
    page_index: int,
    state: ProjectState,
) -> tuple[TypographyJournalEnvelope, ...]:
    page_id = _logical_page_id(project, page_index, state)
    return TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent).records(
        page_id
    )


@router.get(
    "/api/projects/{project_id}/pages/{page_index}/typography/words/{word_id}/text-validation",
    response_model=ImportedTextValidationResponse,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def get_imported_text_validation(
    project_id: str,
    page_index: int,
    word_id: str,
    state: ProjectState = Depends(get_project_state),
) -> ImportedTextValidationResponse:
    """Return the explicit text-review head for one imported word."""
    project = _project_page(project_id, page_index, state)
    with state.get_page_lock(page_index):
        return _imported_text_response(
            project, page_index, _imported_text_head(project, page_index, state, word_id)
        )


@router.post(
    "/api/projects/{project_id}/pages/{page_index}/typography/words/{word_id}/text-validation",
    response_model=ImportedTextValidationResponse,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def set_imported_text_validation(
    project_id: str,
    page_index: int,
    word_id: str,
    submission: ImportedTextValidationSubmission,
    state: ProjectState = Depends(get_project_state),
) -> ImportedTextValidationResponse:
    """CAS-append an explicit validation or retraction for exact imported text."""
    project = _project_page(project_id, page_index, state)
    with state.get_page_lock(page_index):
        binding = _imported_text_binding(project, page_index, state, word_id)
        log = ImportedTextValidationLog(project.project_root, corpus_root=project.project_root.parent)
        try:
            head = log.append(
                binding,
                validated=submission.validated,
                expected_head=submission.expected_head,
            )
        except StaleImportedTextValidationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _imported_text_response(project, page_index, head)


@router.get(
    "/api/projects/{project_id}/pages/{page_index}/typography/review",
    response_model=TypographyPageReviewResponse,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def get_typography_review(
    project_id: str,
    page_index: int,
    state: ProjectState = Depends(get_project_state),
) -> TypographyPageReviewResponse:
    """Return latest per-word heads and review progress for a page."""
    with state.get_page_lock(page_index):
        return typography_page_review(project_id, page_index, state)


def typography_page_review(
    project_id: str,
    page_index: int,
    state: ProjectState,
    *,
    page: object | None = None,
) -> TypographyPageReviewResponse:
    """Evaluate the review gate for the page's current word identities."""
    if state.has_book_labeling_session and not state.has_bound_labeling_page(page_index):
        lease = state.open_labeling_page(page_index)
        if lease is None:
            raise RuntimeError("book typography review could not open a page lease")
        try:
            with state.bind_labeling_page(page_index, lease):
                return typography_page_review(project_id, page_index, state, page=page)
        finally:
            lease.close()
    project = _project_page(project_id, page_index, state)
    records = _page_records(project, page_index, state)
    active_word_ids = _active_word_ids(project, page_index, state, page)
    if active_word_ids:
        epoch_word_id = next(iter(active_word_ids))
        records = _current_epoch_migration_aware(
            records,
            logical_page_id=_logical_page_id(project, page_index, state),
            current=_initial_binding(project, page_index, epoch_word_id, state, page),
            legacy=_legacy_binding(project, page_index, epoch_word_id, state, page),
        )
    else:
        records = ()
    # Canonicalize every stored correction's id before grouping: a lineage
    # that started under a legacy (ground-truth-derived) id — see
    # ``_canonical_word_id_map`` — must still roll up under the same word.
    id_map = _canonical_word_id_map(project, page_index, state, page)
    heads_by_word: dict[str, TypographyCorrection] = {}
    for record in records:
        canonical_id = id_map.get(record.correction.word_id, record.correction.word_id)
        heads_by_word[canonical_id] = record.correction
    text_validated_word_ids = _text_validated_word_ids(project, page_index, state, page)
    heads_by_word = {
        word_id: correction for word_id, correction in heads_by_word.items() if word_id in active_word_ids
    }
    total = len(active_word_ids)
    lineage_root = records[0].correction if records else None
    canonical_heads = tuple(sorted(heads_by_word.items(), key=lambda item: item[0]))
    text_reviewed = 0
    typography_reviewed_count = 0
    blocked = total - len(canonical_heads)
    for canonical_id, correction in canonical_heads:
        try:
            current = _initial_binding(project, page_index, canonical_id, state, page)
            legacy = _legacy_binding(project, page_index, canonical_id, state, page)
        except HTTPException:
            stale = True
        else:
            # Text currency is checked against this word's own *latest* head
            # (``correction``, already the last row seen for this word), not
            # its first correction in the epoch — a word re-reviewed after
            # its own ground-truth edit must read as current, not
            # permanently stale. See ``_current_head``'s identical check.
            stale = (
                lineage_root is None
                or not _page_root_matches(lineage_root, current, legacy)
                or correction.effective_text_sha256 != current.text_sha256
            )
        valid_text = not stale and canonical_id in text_validated_word_ids
        valid_typography = not stale and typography_reviewed(
            correction, required_labels=_TYPOGRAPHY_REQUIRED_LABELS
        )
        if valid_text:
            text_reviewed += 1
        if valid_typography:
            typography_reviewed_count += 1
        if not valid_text or not valid_typography:
            blocked += 1
    return TypographyPageReviewResponse(
        project_id=project_id,
        page_index=page_index,
        logical_page_id=_logical_page_id(project, page_index, state),
        reviewed_words=len(canonical_heads),
        text_reviewed_words=text_reviewed,
        typography_reviewed_words=typography_reviewed_count,
        blocked_words=blocked,
        total_words=total,
        complete=(text_reviewed == total and typography_reviewed_count == total and blocked == 0),
        heads=tuple(correction for _canonical_id, correction in canonical_heads),
    )


@router.get(
    "/api/projects/{project_id}/pages/{page_index}/typography/worklist",
    response_model=TypographyWorklistResponse,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def get_typography_worklist(
    project_id: str,
    page_index: int,
    state: ProjectState = Depends(get_project_state),
) -> TypographyWorklistResponse:
    """Return the ordered, bundle-native typography review worklist."""
    project = _project_page(project_id, page_index, state)
    bundle = state.labeling_bundle
    if bundle is None:
        raise HTTPException(status_code=404, detail="labeling bundle not loaded")
    bundle_id = bundle.bundle_id
    if bundle_id is None:
        raise HTTPException(status_code=422, detail="labeling bundle content id is unavailable")
    with state.get_page_lock(page_index):
        records = _page_records(project, page_index, state)
        if bundle.words:
            records = TypographyCorrectionLog.current_epoch(
                records,
                logical_page_id=bundle.page_id,
                current=_initial_binding(project, page_index, bundle.words[0].word_id, state),
            )
        heads = {
            record.correction.word_id: record.correction
            for record in records
            if any(word.word_id == record.correction.word_id for word in bundle.words)
        }
        text_validated = _text_validated_word_ids(project, page_index, state)
        required_labels = {label.value for label in bundle.taxonomy.labels if label.required_for_completion}
        words: list[TypographyWorklistWord] = []
        typography_reviewed_words = 0
        blocked_words = 0
        for source_word in bundle.words:
            correction = heads.get(source_word.word_id)
            replacement = correction.replacement if correction is not None else None
            word_typography_reviewed = bool(
                correction is not None
                and correction.decision
                in {
                    CorrectionDecision.ACCEPT,
                    CorrectionDecision.APPROVED_EDIT,
                    CorrectionDecision.REVIEWED_REGULAR,
                }
                and replacement is not None
                and replacement.review_state in {ReviewState.REVIEWED, ReviewState.REVIEWED_REGULAR}
                and all(
                    replacement.label_states.get(label) in {LabelState.POSITIVE, LabelState.NEGATIVE}
                    for label in required_labels
                )
            )
            text_reviewed = source_word.word_id in text_validated
            reviewed = correction is not None
            if word_typography_reviewed:
                typography_reviewed_words += 1
            if not text_reviewed or not word_typography_reviewed:
                blocked_words += 1
            words.append(
                TypographyWorklistWord(
                    word_id=source_word.word_id,
                    text=source_word.text,
                    graphemes=split_graphemes(source_word.text),
                    source_review_state=source_word.review_state,
                    source_label_states=dict(source_word.label_states),
                    source_spans=source_word.spans,
                    warnings=source_word.warnings,
                    current_correction=correction,
                    decision=correction.decision if correction is not None else None,
                    reviewed=reviewed,
                    typography_reviewed=word_typography_reviewed,
                    text_reviewed=text_reviewed,
                )
            )
        text_reviewed_words = len(text_validated & {word.word_id for word in bundle.words})
    total_words = len(words)
    return TypographyWorklistResponse(
        project_id=project_id,
        page_index=page_index,
        logical_page_id=bundle.page_id,
        bundle_id=bundle_id,
        taxonomy=bundle.taxonomy,
        words=tuple(words),
        total_words=total_words,
        text_reviewed_words=text_reviewed_words,
        typography_reviewed_words=typography_reviewed_words,
        blocked_words=blocked_words,
        complete=(
            text_reviewed_words == total_words
            and typography_reviewed_words == total_words
            and blocked_words == 0
        ),
    )


@router.post(
    "/api/projects/{project_id}/pages/{page_index}/typography/correction-bundles/export",
    response_model=CorrectionBundleExportResponse,
    dependencies=[Depends(bind_page_labeling_lease)],
)
def export_typography_correction_bundle(
    project_id: str,
    page_index: int,
    request: CorrectionBundleExportRequest,
    state: ProjectState = Depends(get_project_state),
) -> CorrectionBundleExportResponse:
    """Create one deterministic immutable project-local correction bundle."""
    project = _project_page(project_id, page_index, state)
    stored_labeling_bundle = state.labeling_bundle
    if stored_labeling_bundle is not None:
        if (
            request.labeling_bundle is not None
            and request.labeling_bundle.bundle_id != stored_labeling_bundle.bundle_id
        ):
            raise HTTPException(status_code=409, detail="labeling bundle does not match loaded project")
        labeling_bundle = stored_labeling_bundle
    elif request.labeling_bundle is not None:
        labeling_bundle = request.labeling_bundle
    else:
        raise HTTPException(status_code=422, detail="labeling bundle is required")
    log = TypographyCorrectionLog(project.project_root, corpus_root=project.project_root.parent)
    with state.get_page_lock(page_index):
        records = _page_records(project, page_index, state)
        active_word_ids = _active_word_ids(project, page_index, state)
        if active_word_ids:
            epoch_word_id = next(iter(active_word_ids))
            records = _current_epoch_migration_aware(
                records,
                logical_page_id=_logical_page_id(project, page_index, state),
                current=_initial_binding(project, page_index, epoch_word_id, state),
                legacy=_legacy_binding(project, page_index, epoch_word_id, state),
            )
        else:
            records = ()
        # Canonicalize every stored correction's id before matching against
        # it: a lineage that started under a legacy (ground-truth-derived)
        # id — see ``_canonical_word_id_map`` — must still be selectable and
        # exportable under its current word.
        id_map = _canonical_word_id_map(project, page_index, state)
        text_validated_word_ids = _text_validated_word_ids(project, page_index, state)
        latest_ids = {id_map.get(record.correction.word_id, record.correction.word_id) for record in records}
        selected_ids = latest_ids if request.selected_word_ids is None else set(request.selected_word_ids)
        if (
            not records
            or not selected_ids
            or (request.selected_word_ids is not None and len(selected_ids) != len(request.selected_word_ids))
            or not selected_ids <= latest_ids
            or not selected_ids <= active_word_ids
            or not selected_ids <= text_validated_word_ids
        ):
            raise HTTPException(
                status_code=422,
                detail="selected heads must be active and text-validated",
            )
        lineage_root = records[0].correction
        latest_by_word = {
            word_id: next(
                record.correction
                for record in reversed(records)
                if id_map.get(record.correction.word_id, record.correction.word_id) == word_id
            )
            for word_id in selected_ids
        }
        for word_id in selected_ids:
            initial = _initial_binding(project, page_index, word_id, state)
            legacy = _legacy_binding(project, page_index, word_id, state)
            # Text currency is checked against this word's *latest* head —
            # not its first correction in the epoch — so a word re-reviewed
            # after its own ground-truth edit exports cleanly instead of
            # reading as permanently stale. See
            # ``typography_page_review``'s identical fix.
            if not _page_root_matches(lineage_root, initial, legacy) or (
                latest_by_word[word_id].effective_text_sha256 != initial.text_sha256
            ):
                raise HTTPException(status_code=409, detail="selected correction head is stale")
        accepted = {
            CorrectionDecision.ACCEPT,
            CorrectionDecision.APPROVED_EDIT,
            CorrectionDecision.REVIEWED_REGULAR,
        }
        for correction in latest_by_word.values():
            replacement = correction.replacement
            if (
                correction.decision not in accepted
                or replacement is None
                or replacement.review_state not in {ReviewState.REVIEWED, ReviewState.REVIEWED_REGULAR}
                or any(
                    replacement.label_states.get(label.value)
                    not in {LabelState.POSITIVE, LabelState.NEGATIVE}
                    for label in TYPOGRAPHY_TAXONOMY.labels
                    if label.required_for_completion
                )
            ):
                raise HTTPException(
                    status_code=409,
                    detail="selected text and typography reviews must be complete before export",
                )
        selected_head_positions = tuple(
            index
            for index, record in enumerate(records)
            if id_map.get(record.correction.word_id, record.correction.word_id) in selected_ids
            and not any(
                later.correction.word_id == record.correction.word_id for later in records[index + 1 :]
            )
        )
        selected = records[: max(selected_head_positions, default=-1) + 1]
        artifacts: dict[str, ReplacementArtifact] = {}
        geometry: dict[str, WordGeometry] = {}
        model_runs: dict[str, ModelRun] = {}
        transforms: dict[str, CoordinateTransform] = {}
        page_geometry: PageGeometry | None = None
        for record in selected:
            if record.page_geometry is not None:
                page_geometry = record.page_geometry
            for artifact in record.replacement_artifacts:
                previous_artifact = artifacts.setdefault(artifact.artifact_id, artifact)
                if previous_artifact != artifact:
                    raise HTTPException(status_code=422, detail="conflicting replacement artifact provenance")
            if record.geometry is not None:
                geometry = {word_geometry.word_id: word_geometry for word_geometry in record.geometry}
            for model_run in record.model_runs:
                model_runs[model_run.run_id] = model_run
            for transform in record.coordinate_transforms:
                transforms[transform.transform_id] = transform
        for artifact in artifacts.values():
            try:
                payload = log.read_artifact(artifact.sha256)
            except (OSError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="replacement artifact is unavailable") from exc
            if len(payload) != artifact.byte_size:
                raise HTTPException(status_code=422, detail="replacement artifact size mismatch")
        try:
            labeling_bundle_id = labeling_bundle.bundle_id
            if labeling_bundle_id is None:
                raise ValueError("labeling bundle content id was not derived")
            exported_artifacts = tuple(
                artifact.model_copy(update={"relative_path": f"{artifact.sha256}.artifact"})
                for artifact in artifacts.values()
            )
            bundle = CorrectionBundle(
                schema_version=REVIEW_CONTRACT_VERSION,
                configuration_hash=labeling_bundle.configuration_hash,
                labeling_bundle_id=labeling_bundle_id,
                corrections=tuple(record.correction for record in selected),
                replacement_artifacts=exported_artifacts,
                page_geometry=page_geometry,
                geometry=tuple(geometry.values()) if geometry else None,
                model_runs=tuple(model_runs.values()),
                coordinate_transforms=tuple(transforms.values()),
            )
            bundle.validate_against(labeling_bundle)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="correction bundle does not match labeling bundle",
            ) from exc
    relative = Path(".pd-pages") / "typography-exports" / f"{bundle.bundle_id}.json"
    payload = bundle.model_dump_json(indent=2).encode()
    try:
        artifact_relative_paths: dict[str, str] = {}
        for artifact in exported_artifacts:
            artifact_name = artifact.relative_path
            log.publish_export(artifact_name, log.read_artifact(artifact.sha256))
            artifact_relative_paths[artifact.artifact_id] = (
                Path(".pd-pages") / "typography-exports" / artifact_name
            ).as_posix()
        log.publish_export(f"{bundle.bundle_id}.json", payload)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail="unsafe typography export path") from exc
    return CorrectionBundleExportResponse(
        bundle=bundle,
        relative_path=relative.as_posix(),
        artifact_relative_paths=artifact_relative_paths,
    )


def install_typography_router(app: FastAPI) -> None:
    """Register typography routes and preserve the label-state enum in OpenAPI."""
    app.include_router(router)
    original_openapi = app.openapi

    def enum_preserving_openapi() -> dict[str, object]:
        schema = original_openapi()
        components = schema.get("components")
        if isinstance(components, dict):
            schemas = components.get("schemas")
            if isinstance(schemas, dict):
                word_schema = schemas.get("WordTypography") or schemas.get("WordTypography-Output")
                if isinstance(word_schema, dict):
                    schemas["WordTypography"] = word_schema
                    properties = word_schema.get("properties")
                    if isinstance(properties, dict):
                        properties["label_states"] = {"$ref": "#/components/schemas/LabelStates"}
        return schema

    app.openapi = enum_preserving_openapi  # type: ignore[method-assign]


__all__ = ["TypographyContractDescriptor", "install_typography_router"]

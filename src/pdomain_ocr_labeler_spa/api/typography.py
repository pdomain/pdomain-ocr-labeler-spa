"""Server-authoritative typography review and portable correction export."""

from __future__ import annotations

import hashlib
import json
from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from typing import ClassVar, Literal

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
)
from .dependencies import get_project_state

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


def _source_text(project: Project, page_index: int) -> str:
    image = project.image_paths[page_index]
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
    return tuple(_source_text(project, page_index).split())


def _corrected_word_text(word: object) -> str:
    ground_truth = getattr(word, "ground_truth_text", None)
    if isinstance(ground_truth, str):
        return ground_truth
    text = getattr(word, "text", None)
    return text if isinstance(text, str) else ""


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
    texts = _review_words(project, page_index, state, page_override)
    return {
        stable_word_id(
            project_id=project.project_id,
            page_id=page_id,
            reading_order=index,
            text=texts[index],
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


def _current_page_content(
    project: Project,
    page_index: int,
    state: ProjectState,
    page_override: object | None = None,
) -> object:
    page = _current_page(project, page_index, state, page_override)
    if page is None:
        line_words: list[list[object]] = [list(_source_text(project, page_index).split())]
    else:
        lines = getattr(page, "lines", None)
        line_words = (
            [list(getattr(line, "words", None) or ()) for line in lines]
            if lines is not None
            else [list(_page_words(project, page_index, state, page_override) or ())]
        )
    page_id = _logical_page_id(project, page_index, state)
    reading_order = 0
    projected_lines: list[list[dict[str, object]]] = []
    for line in line_words:
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
    for index, text in enumerate(_review_words(project, page_index, state, page_override)):
        candidate = stable_word_id(
            project_id=project.project_id, page_id=page_id, reading_order=index, text=text
        )
        if candidate == word_id:
            return text
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
    return {
        stable_word_id(
            project_id=project.project_id,
            page_id=page_id,
            reading_order=index,
            text=text,
        )
        for index, text in enumerate(_review_words(project, page_index, state, page_override))
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
    image_sha = hashlib.sha256(project.image_paths[page_index].read_bytes()).hexdigest()
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


def _current_head(
    project: Project,
    page_index: int,
    word_id: str,
    log: TypographyCorrectionLog,
    state: ProjectState,
) -> TypographyHeadResponse:
    logical_page_id = _logical_page_id(project, page_index, state)
    initial = _initial_binding(project, page_index, word_id, state)
    records = log.current_epoch(
        log.records(logical_page_id),
        logical_page_id=logical_page_id,
        current=initial,
    )
    word_head = next((row.correction for row in reversed(records) if row.correction.word_id == word_id), None)
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
        head_token="0" * 64,
    )
    return response.model_copy(
        update={"head_token": _canonical_hash(response.model_dump(mode="json", exclude={"head_token"}))}
    )


def _correction_lineage_binding(
    initial: TypographyBinding,
    records: tuple[TypographyJournalEnvelope, ...],
    word_id: str,
) -> TypographyBinding:
    """Resolve portable correction ancestry without replacing persisted UI state."""
    page_head = records[-1].correction if records else None
    word_head = next(
        (record.correction for record in reversed(records) if record.correction.word_id == word_id),
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
        head = _current_head(project, page_index, word_id, log, state)
        initial = _initial_binding(project, page_index, word_id, state)
        records = log.current_epoch(
            log.records(logical_page_id),
            logical_page_id=logical_page_id,
            current=initial,
        )
        lineage = _correction_lineage_binding(initial, records, word_id)
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
                word_id=word_id,
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
    project = _project_page(project_id, page_index, state)
    records = _page_records(project, page_index, state)
    active_word_ids = _active_word_ids(project, page_index, state, page)
    if active_word_ids:
        epoch_word_id = next(iter(active_word_ids))
        records = TypographyCorrectionLog.current_epoch(
            records,
            logical_page_id=_logical_page_id(project, page_index, state),
            current=_initial_binding(project, page_index, epoch_word_id, state, page),
        )
    else:
        records = ()
    heads_by_word: dict[str, TypographyCorrection] = {}
    first_by_word: dict[str, TypographyCorrection] = {}
    for record in records:
        first_by_word.setdefault(record.correction.word_id, record.correction)
        heads_by_word[record.correction.word_id] = record.correction
    text_validated_word_ids = _text_validated_word_ids(project, page_index, state, page)
    heads_by_word = {
        word_id: correction for word_id, correction in heads_by_word.items() if word_id in active_word_ids
    }
    first_by_word = {
        word_id: correction for word_id, correction in first_by_word.items() if word_id in active_word_ids
    }
    total = len(active_word_ids)
    lineage_root = records[0].correction if records else None
    heads = tuple(sorted(heads_by_word.values(), key=lambda item: item.word_id))
    accepted = {
        CorrectionDecision.ACCEPT,
        CorrectionDecision.APPROVED_EDIT,
        CorrectionDecision.REVIEWED_REGULAR,
    }
    text_reviewed = 0
    typography_reviewed = 0
    blocked = total - len(heads)
    for correction in heads:
        replacement = correction.replacement
        try:
            current = _initial_binding(project, page_index, correction.word_id, state, page)
        except HTTPException:
            stale = True
        else:
            first = first_by_word[correction.word_id]
            stale = (
                lineage_root is None
                or lineage_root.base_page_sha256 != current.page_sha256
                or lineage_root.base_image_sha256 != current.image_sha256
                or first.base_text_sha256 != current.text_sha256
                or lineage_root.page_head_sha256 != current.page_head_sha256
            )
        valid_text = not stale and correction.word_id in text_validated_word_ids
        valid_typography = False
        if not stale and correction.decision in accepted and replacement is not None:
            required_labels = {
                label.value for label in TYPOGRAPHY_TAXONOMY.labels if label.required_for_completion
            }
            valid_typography = replacement.review_state in {
                ReviewState.REVIEWED,
                ReviewState.REVIEWED_REGULAR,
            } and all(
                replacement.label_states.get(label) in {LabelState.POSITIVE, LabelState.NEGATIVE}
                for label in required_labels
            )
        if valid_text:
            text_reviewed += 1
        if valid_typography:
            typography_reviewed += 1
        if not valid_text or not valid_typography:
            blocked += 1
    return TypographyPageReviewResponse(
        project_id=project_id,
        page_index=page_index,
        logical_page_id=_logical_page_id(project, page_index, state),
        reviewed_words=len(heads),
        text_reviewed_words=text_reviewed,
        typography_reviewed_words=typography_reviewed,
        blocked_words=blocked,
        total_words=total,
        complete=(text_reviewed == total and typography_reviewed == total and blocked == 0),
        heads=heads,
    )


@router.get(
    "/api/projects/{project_id}/pages/{page_index}/typography/worklist",
    response_model=TypographyWorklistResponse,
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
            typography_reviewed = bool(
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
            if typography_reviewed:
                typography_reviewed_words += 1
            if not text_reviewed or not typography_reviewed:
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
                    typography_reviewed=typography_reviewed,
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
            records = log.current_epoch(
                records,
                logical_page_id=_logical_page_id(project, page_index, state),
                current=_initial_binding(project, page_index, epoch_word_id, state),
            )
        else:
            records = ()
        text_validated_word_ids = _text_validated_word_ids(project, page_index, state)
        latest_ids = {record.correction.word_id for record in records}
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
        for word_id in selected_ids:
            initial = _initial_binding(project, page_index, word_id, state)
            word_root = next(record.correction for record in records if record.correction.word_id == word_id)
            if (
                lineage_root.base_page_sha256 != initial.page_sha256
                or lineage_root.base_image_sha256 != initial.image_sha256
                or lineage_root.page_head_sha256 != initial.page_head_sha256
                or word_root.base_text_sha256 != initial.text_sha256
            ):
                raise HTTPException(status_code=409, detail="selected correction head is stale")
        latest_by_word = {
            word_id: next(
                record.correction for record in reversed(records) if record.correction.word_id == word_id
            )
            for word_id in selected_ids
        }
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
            if record.correction.word_id in selected_ids
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

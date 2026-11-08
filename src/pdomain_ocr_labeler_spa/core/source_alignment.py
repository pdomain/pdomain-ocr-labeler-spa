"""Composed source evidence with explicit source-to-OCR groups and review annotations."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, ClassVar, Literal
from uuid import uuid4

from pdomain_book_contracts.layout.text_hints import LayoutTextHint
from pdomain_book_contracts.matching import MatchPolicy
from pdomain_book_contracts.matching.pgdp_bounded import (
    PgdpBoundedMatch,
    match_pgdp_documents_bounded,
)
from pdomain_book_contracts.matching.pgdp_layout_projection import (
    PgdpAlignmentDisposition,
    PgdpFormattingProjection,
    PgdpPageAlignment,
    compose_pgdp_alignments,
    project_f2_formatting,
)
from pdomain_book_contracts.matching.pgdp_visible import (
    PgdpOcrWord,
    PgdpVisibleDocument,
    match_document_from_ocr_words,
)
from pdomain_book_contracts.typography.spans import StyleSpan
from pydantic import BaseModel, ConfigDict, Field

from .regions.coordinates import bounding_box_to_pixels

if TYPE_CHECKING:
    from pdomain_book_tools.ocr.page import Page
    from pdomain_book_tools.ocr.word import Word

    from .persistence.page_store import LabelerPageStore
    from .project_state import PageState, ProjectState

ReviewDecision = Literal["pending", "accepted", "rejected", "edited"]


class SourceAlignmentEvidence(BaseModel):
    """Exact persisted selected-page wire from source-data; never recreate P3 IDs."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", populate_by_name=True)
    wire_schema: Literal["pdomain.pgdp-source-alignment"] = Field(alias="schema")
    version: Literal[1]
    project_id: str
    page_key: str
    page_id: str
    f2: PgdpVisibleDocument
    p3: PgdpVisibleDocument
    f2_to_p3: PgdpBoundedMatch
    hints: tuple[LayoutTextHint, ...] = ()
    style_spans: tuple[StyleSpan, ...] = ()


class OcrWordReference(BaseModel):
    token_id: str
    line_index: int
    word_index: int
    reading_order: int


class SourceAlignmentGroup(BaseModel):
    group_id: str
    source_word_ids: tuple[str, ...]
    f2_token_ids: tuple[str, ...]
    p3_token_ids: tuple[str, ...]
    ocr_token_ids: tuple[str, ...]
    f2_text: str
    p3_text: str
    ocr_text: str
    ocr_refs: tuple[OcrWordReference, ...]
    box: tuple[int, int, int, int] | None
    disposition: PgdpAlignmentDisposition
    warnings: tuple[str, ...] = ()
    decision: ReviewDecision = "pending"
    note: str = ""
    reviewed_text: str | None = None


class SourceAlignmentResult(BaseModel):
    result_id: str
    page_id: str
    page_key: str
    input_generation: int
    ocr_signature: str
    alignment: PgdpPageAlignment
    projection: PgdpFormattingProjection
    groups: tuple[SourceAlignmentGroup, ...]
    f2: PgdpVisibleDocument
    p3: PgdpVisibleDocument
    ocr: PgdpVisibleDocument
    warnings: tuple[str, ...] = ()


class SourceAlignmentResponse(BaseModel):
    generation: int
    result: SourceAlignmentResult | None
    stale: bool = False


def alignment_policy() -> MatchPolicy:
    return MatchPolicy(
        policy_id="pgdp-source-review",
        version="1",
        low_margin_threshold=0.05,
        max_merge_size=3,
        max_state_count=100_000,
        max_transition_count=1_000_000,
        max_grapheme_work_count=10_000_000,
    )


def ocr_references(page: Page) -> tuple[OcrWordReference, ...]:
    positions = {
        id(word): (li, wi) for li, line in enumerate(page.lines) for wi, word in enumerate(line.words)
    }
    return tuple(
        OcrWordReference(
            token_id=f"ocr-{index}",
            line_index=positions.get(id(word), (-1, index))[0],
            word_index=positions.get(id(word), (-1, index))[1],
            reading_order=index,
        )
        for index, word in enumerate(page.words)
    )


def ocr_document(page: Page, *, page_id: str) -> PgdpVisibleDocument:
    words: list[PgdpOcrWord] = []
    for ref, word in zip(ocr_references(page), page.words, strict=True):
        box = word.bounding_box
        pixels = (
            bounding_box_to_pixels(box, page_width=page.width, page_height=page.height)
            if box.has_usable_coordinates
            else None
        )
        words.append(
            PgdpOcrWord(
                token_id=ref.token_id,
                text=word.text,
                line_id=f"line-{ref.line_index}" if ref.line_index >= 0 else f"unplaced-{ref.reading_order}",
                box=pixels,
            )
        )
    return match_document_from_ocr_words(tuple(words), document_id=f"{page_id}:ocr", page_id=page_id)


def ocr_signature(page: Page) -> str:
    """Detect raw OCR/topology/box changes while preserving separate human GT."""
    snapshot = [
        [
            ref.line_index,
            ref.word_index,
            word.text,
            word.bounding_box.to_ltrb(),
            word.bounding_box.is_normalized,
        ]
        for ref, word in zip(ocr_references(page), page.words, strict=True)
    ]
    return hashlib.sha256(
        json.dumps([page.width, page.height, snapshot], ensure_ascii=False).encode()
    ).hexdigest()


def load_source_evidence(state: ProjectState, page_index: int) -> SourceAlignmentEvidence | None:
    """Read only verified artifact bytes while the caller holds its page lease."""
    loaded = state.loaded_labeling_bundle
    if loaded is None:
        return None
    candidates: list[SourceAlignmentEvidence] = []
    shared = loaded.artifact_payloads.get("source_alignment")
    if shared is not None:
        candidates.append(SourceAlignmentEvidence.model_validate_json(shared))
    for artifact in loaded.bundle.artifacts:
        if artifact.relative_path.startswith("evidence/f2-p3/") and artifact.relative_path.endswith(".json"):
            payload = loaded.artifact_payloads.get(artifact.artifact_id)
            if payload is None:
                raise ValueError("Prepared source alignment evidence is unavailable")
            candidates.append(SourceAlignmentEvidence.model_validate_json(payload))
    matching = [item for item in candidates if item.page_id == loaded.bundle.page_id]
    if not matching:
        project = state.loaded_project
        key = project.image_paths[page_index].name if project is not None else ""
        matching = [item for item in candidates if item.page_key == key]
    if len(matching) > 1:
        raise ValueError("Prepared page has conflicting source alignment evidence")
    if not matching:
        if candidates:
            raise ValueError("Source alignment evidence belongs to another prepared page")
        return None
    selected = matching[0]
    allowed = {word.word_id for word in loaded.bundle.words}
    if any(word_id not in allowed for item in selected.f2.token_lookup for word_id in item.source_word_ids):
        raise ValueError("Source alignment references unknown prepared word identities")
    return selected


def _token_text(document: PgdpVisibleDocument) -> dict[str, str]:
    return {
        token.token_id: token.text
        for page in document.document.pages
        for line in page.lines
        for token in line.tokens
    }


def align_source_page(
    evidence: SourceAlignmentEvidence, *, page: Page, generation: int
) -> SourceAlignmentResult:
    if (
        evidence.f2_to_p3.graph.source_document != evidence.f2.document
        or evidence.f2_to_p3.graph.target_document != evidence.p3.document
    ):
        raise ValueError("Source alignment does not reference the persisted F2 and P3 documents")
    ocr = ocr_document(page, page_id=evidence.page_id)
    matched = match_pgdp_documents_bounded(
        source=evidence.p3.document, target=ocr.document, policy=alignment_policy()
    )
    alignment = compose_pgdp_alignments(
        f2_to_p3=evidence.f2_to_p3.graph,
        p3_to_ocr=matched.graph,
        f2_to_p3_windows=evidence.f2_to_p3.windows,
        p3_to_ocr_windows=matched.windows,
        f2_to_p3_strategy=evidence.f2_to_p3.strategy,
        p3_to_ocr_strategy=matched.strategy,
    )
    projection = project_f2_formatting(
        alignment=alignment, hints=evidence.hints, style_spans=evidence.style_spans
    )
    source_ids = {entry.token_id: entry.source_word_ids for entry in evidence.f2.token_lookup}
    refs = {ref.token_id: ref for ref in ocr_references(page)}
    snapshots = {word.token_id: word for word in ocr.ocr_words}
    f2_text, p3_text, ocr_text = _token_text(evidence.f2), _token_text(evidence.p3), _token_text(ocr)
    groups: list[SourceAlignmentGroup] = []
    for group in alignment.groups:
        boxes = [snapshots[token_id].box for token_id in group.ocr_token_ids]
        usable = [box for box in boxes if box is not None and box[0] < box[2] and box[1] < box[3]]
        box = None
        if usable and len(usable) == len(boxes):
            box = (
                int(min(b[0] for b in usable)),
                int(min(b[1] for b in usable)),
                int(max(b[2] for b in usable)),
                int(max(b[3] for b in usable)),
            )
        groups.append(
            SourceAlignmentGroup(
                group_id=group.group_id,
                source_word_ids=tuple(
                    dict.fromkeys(
                        word_id for token in group.f2_token_ids for word_id in source_ids.get(token, ())
                    )
                ),
                f2_token_ids=group.f2_token_ids,
                p3_token_ids=group.p3_token_ids,
                ocr_token_ids=group.ocr_token_ids,
                f2_text=" ".join(f2_text[token] for token in group.f2_token_ids),
                p3_text=" ".join(p3_text[token] for token in group.p3_token_ids),
                ocr_text=" ".join(ocr_text[token] for token in group.ocr_token_ids),
                ocr_refs=tuple(refs[token] for token in group.ocr_token_ids),
                box=box,
                disposition=group.disposition,
                warnings=group.warnings,
            )
        )
    return SourceAlignmentResult(
        result_id=str(uuid4()),
        page_id=evidence.page_id,
        page_key=evidence.page_key,
        input_generation=generation,
        ocr_signature=ocr_signature(page),
        alignment=alignment,
        projection=projection,
        groups=tuple(groups),
        f2=evidence.f2,
        p3=evidence.p3,
        ocr=ocr,
        warnings=alignment.warnings + projection.warnings,
    )


def grouped_word_bindings(page: Page, result: SourceAlignmentResult) -> dict[str, tuple[Word, ...]]:
    """Bind source IDs through explicit groups; unresolved groups never gain geometry."""
    if result.ocr_signature != ocr_signature(page):
        raise ValueError("Source alignment is stale for the current OCR topology")
    words = page.words
    bindings: dict[str, tuple[Word, ...]] = {}
    for group in result.groups:
        if (
            group.decision == "rejected"
            or group.disposition not in {PgdpAlignmentDisposition.ACCEPTED, PgdpAlignmentDisposition.CHANGED}
            or not group.ocr_refs
        ):
            continue
        bound = tuple(words[ref.reading_order] for ref in group.ocr_refs)
        for source_id in group.source_word_ids:
            if source_id in bindings and bindings[source_id] != bound:
                raise ValueError("Source identity belongs to conflicting alignment groups")
            bindings[source_id] = bound
    return bindings


def scalar_word_binding(page: Page, result: SourceAlignmentResult, source_id: str) -> Word:
    groups = [group for group in result.groups if source_id in group.source_word_ids]
    if len(groups) != 1 or len(groups[0].source_word_ids) != 1 or len(groups[0].ocr_refs) != 1:
        raise ValueError("This scalar operation requires a one-to-one source/OCR group")
    bound = grouped_word_bindings(page, result).get(source_id)
    if bound is None:
        raise ValueError("Source word is unresolved or rejected in the current alignment")
    return bound[0]


def carry_group_reviews(
    previous: SourceAlignmentResult | None, result: SourceAlignmentResult
) -> SourceAlignmentResult:
    """Carry human annotations only across the same OCR snapshot and links."""
    if previous is None or previous.ocr_signature != result.ocr_signature:
        return result
    old = {group.group_id: group for group in previous.groups}
    groups: list[SourceAlignmentGroup] = []
    for group in result.groups:
        updated = group
        prior = old.get(group.group_id)
        if prior is not None and (
            prior.source_word_ids,
            prior.f2_token_ids,
            prior.p3_token_ids,
            prior.ocr_token_ids,
        ) == (group.source_word_ids, group.f2_token_ids, group.p3_token_ids, group.ocr_token_ids):
            updated = group.model_copy(
                update={"decision": prior.decision, "note": prior.note, "reviewed_text": prior.reviewed_text}
            )
        groups.append(updated)
    return result.model_copy(update={"groups": tuple(groups)})


def alignment_from_page(page: Page) -> SourceAlignmentResult | None:
    result: object = getattr(page, "_labeler_source_alignment", None)
    return result if isinstance(result, SourceAlignmentResult) else None


def stamp_alignment(page: Page, result: SourceAlignmentResult | None) -> None:
    object.__setattr__(page, "_labeler_source_alignment", result)


def persist_alignment(
    *, state: PageState, page: Page, result: SourceAlignmentResult, store: LabelerPageStore | None
) -> None:
    """Commit the typed sidecar before publishing its new generation."""
    from .page_state import save_page_content_to_store

    old = state.source_alignment
    state.source_alignment = result
    try:
        if store is not None and state.page_id is not None:
            _ = save_page_content_to_store(
                page_id=state.page_id,
                page=page,
                store=store,
                labeler_sidecars=state,
                changes=[{"type": "source_alignment", "result_id": result.result_id}],
            )
    except Exception:
        state.source_alignment = old
        raise
    state.generation += 1
    stamp_alignment(page, result)

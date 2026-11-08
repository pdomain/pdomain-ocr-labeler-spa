from __future__ import annotations

import json
from pathlib import Path

import pytest
from pdomain_book_contracts.annotation.provenance import (
    ConfidenceTier,
    KnowledgeState,
    LabelSource,
)
from pdomain_book_contracts.layout.text_hints import LayoutTextHint, LayoutTextLine
from pdomain_book_contracts.matching.models import MatchQuarantineReason
from pdomain_book_contracts.matching.pgdp_bounded import match_pgdp_documents_bounded
from pdomain_book_contracts.matching.pgdp_visible import match_document_from_pgdp_text
from pdomain_book_contracts.typography.labels import StyleLabel
from pdomain_book_contracts.typography.spans import SourceSlice, StyleSpan, split_graphemes

from pdomain_ocr_labeler_spa.core.source_alignment import SourceAlignmentEvidence, alignment_policy
from pdomain_ocr_labeler_spa.core.source_text import build_source_text_preview


def _evidence() -> SourceAlignmentEvidence:
    f2_raw = b"<i>r\xc3\xa9gime</i> voyageur"
    p3_raw = b"r\xc3\xa9gime voyageur"
    f2 = match_document_from_pgdp_text(f2_raw, document_id="f2", page_id="020.png", artifact_id="f2")
    p3 = match_document_from_pgdp_text(p3_raw, document_id="p3", page_id="020.png", artifact_id="p3")
    return SourceAlignmentEvidence(
        schema="pdomain.pgdp-source-alignment",
        version=1,
        project_id="project",
        page_key="020.png",
        page_id="020.png",
        f2=f2,
        p3=p3,
        f2_to_p3=match_pgdp_documents_bounded(
            source=f2.document, target=p3.document, policy=alignment_policy()
        ),
        style_spans=(
            StyleSpan(
                label=StyleLabel.ITALIC,
                start=0,
                end=6,
                state=KnowledgeState.POSITIVE,
                label_source=LabelSource.F2,
                confidence_tier=ConfidenceTier.GOLD,
                source_slices=(SourceSlice(artifact_sha256="a" * 64, byte_start=3, byte_end=10),),
                rule_ref="F2 italic",
                semantic_reason=None,
                warnings=(),
            ),
        ),
    )


def test_consolidated_preview_keeps_p3_words_and_maps_exact_f2_styles() -> None:
    preview = build_source_text_preview(
        page_key="020.png",
        f2_payload=b'{"020.png":"<i>r\\u00e9gime</i> voyageur"}',
        p3_payload=b'{"020.png":"r\\u00e9gime voyageur"}',
        evidence=_evidence(),
    )

    assert preview.available
    assert preview.f2 is not None and preview.f2.raw_text == "<i>régime</i> voyageur"
    assert preview.p3 is not None and preview.p3.raw_text == "régime voyageur"
    assert preview.consolidated is not None
    assert preview.consolidated.text == "régime voyageur"
    assert "".join(run.text for run in preview.consolidated.runs) == "régime voyageur"
    assert preview.consolidated.runs[0].text == "régime"
    assert preview.consolidated.runs[0].styles == ("italic",)
    assert preview.consolidated.unresolved == ()


def test_sources_remain_available_without_persisted_source_alignment() -> None:
    preview = build_source_text_preview(
        page_key="020.png",
        f2_payload=b'{"020.png":"<i>r\\u00e9gime</i> voyageur"}',
        p3_payload=b'{"020.png":"r\\u00e9gime voyageur"}',
        evidence=None,
    )

    assert preview.available
    assert preview.f2 is not None and preview.f2.visible_text == "régime voyageur"
    assert preview.p3 is not None and preview.p3.visible_text == "régime voyageur"
    assert preview.consolidated is None
    assert preview.warnings == ("Consolidated source needs persisted F2-to-P3 alignment evidence.",)


def test_preview_reports_unavailable_when_prepared_sources_are_absent() -> None:
    preview = build_source_text_preview(
        page_key="020.png",
        f2_payload=None,
        p3_payload=None,
        evidence=None,
        project_id="ordinary-project",
        page_index=4,
    )

    assert not preview.available
    assert preview.project_id == "ordinary-project"
    assert preview.page_index == 4
    assert preview.f2 is None
    assert preview.p3 is None
    assert preview.consolidated is None


def test_preview_rejects_source_snapshots_that_disagree_with_persisted_evidence() -> None:
    with pytest.raises(ValueError, match="prepared F2 visible text"):
        build_source_text_preview(
            page_key="020.png",
            f2_payload=b'{"020.png":"different source words"}',
            p3_payload=b'{"020.png":"r\\u00e9gime voyageur"}',
            evidence=_evidence(),
        )


def test_quarantined_window_does_not_project_identical_graph_operations() -> None:
    evidence = _evidence()
    quarantined_graph = evidence.f2_to_p3.graph.model_copy(
        update={"accepted": False, "quarantine_reasons": (MatchQuarantineReason.LOW_MARGIN,)}
    )
    quarantined = evidence.model_copy(
        update={
            "f2_to_p3": evidence.f2_to_p3.model_copy(
                update={
                    "graph": quarantined_graph,
                    "windows": tuple(
                        window.model_copy(update={"graph": quarantined_graph})
                        for window in evidence.f2_to_p3.windows
                    ),
                }
            )
        }
    )

    preview = build_source_text_preview(
        page_key="020.png",
        f2_payload=b'{"020.png":"<i>r\\u00e9gime</i> voyageur"}',
        p3_payload=b'{"020.png":"r\\u00e9gime voyageur"}',
        evidence=quarantined,
    )

    assert preview.consolidated is not None
    assert preview.consolidated.text == "régime voyageur"
    assert all(not run.styles for run in preview.consolidated.runs)
    assert preview.consolidated.unresolved[0].source_text == "régime"


def test_accepted_local_window_projects_when_assembled_graph_is_quarantined() -> None:
    evidence = _evidence()
    quarantined_graph = evidence.f2_to_p3.graph.model_copy(
        update={"accepted": False, "quarantine_reasons": (MatchQuarantineReason.LOW_MARGIN,)}
    )
    locally_accepted = evidence.model_copy(
        update={"f2_to_p3": evidence.f2_to_p3.model_copy(update={"graph": quarantined_graph})}
    )

    preview = build_source_text_preview(
        page_key="020.png",
        f2_payload=b'{"020.png":"<i>r\\u00e9gime</i> voyageur"}',
        p3_payload=b'{"020.png":"r\\u00e9gime voyageur"}',
        evidence=locally_accepted,
    )

    assert preview.consolidated is not None
    assert preview.consolidated.runs[0].text == "régime"
    assert preview.consolidated.runs[0].styles == ("italic",)


def test_layout_lines_keep_p3_ranges_and_f2_indents_without_text_search() -> None:
    f2_raw = "First line\r\n        Repeated line\r\nThird line\r\n        Repeated line"
    p3_raw = "First line\r\nRepeated line\r\nThird line\r\nRepeated line"
    f2 = match_document_from_pgdp_text(f2_raw.encode(), document_id="f2", page_id="poem", artifact_id="f2")
    p3 = match_document_from_pgdp_text(p3_raw.encode(), document_id="p3", page_id="poem", artifact_id="p3")
    evidence = SourceAlignmentEvidence(
        schema="pdomain.pgdp-source-alignment",
        version=1,
        project_id="project",
        page_key="poem",
        page_id="poem",
        f2=f2,
        p3=p3,
        f2_to_p3=match_pgdp_documents_bounded(
            source=f2.document, target=p3.document, policy=alignment_policy()
        ),
        hints=(
            LayoutTextHint(
                kind="formatted_block",
                source="f2",
                source_ref="F2",
                text=f2_raw,
                grapheme_range=(0, len(split_graphemes(f2_raw))),
                lines=(
                    LayoutTextLine(text="First line", stanza_index=0),
                    LayoutTextLine(text="Repeated line", stanza_index=0, indent_hint="8 spaces"),
                    LayoutTextLine(text="Third line", stanza_index=1),
                    LayoutTextLine(text="Repeated line", stanza_index=1, indent_hint="8 spaces"),
                ),
            ),
        ),
    )

    preview = build_source_text_preview(
        page_key="poem",
        f2_payload=json.dumps({"poem": f2_raw}).encode(),
        p3_payload=json.dumps({"poem": p3_raw}).encode(),
        evidence=evidence,
    )

    assert preview.consolidated is not None
    assert preview.consolidated.text == p3_raw
    hint = preview.consolidated.layout_hints[0]
    first_repeated, second_repeated = hint.lines[1], hint.lines[3]
    assert first_repeated.indent_columns == 8
    assert second_repeated.indent_columns == 8
    assert first_repeated.grapheme_range != second_repeated.grapheme_range
    graphemes = split_graphemes(preview.consolidated.text)
    for line in hint.lines:
        assert line.grapheme_range is not None
        start, end = line.grapheme_range
        assert "".join(graphemes[start:end]) == line.text


def test_api_returns_structured_error_for_inconsistent_source_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.responses import JSONResponse

    from pdomain_ocr_labeler_spa.api import source_alignment
    from pdomain_ocr_labeler_spa.core.models import Project
    from pdomain_ocr_labeler_spa.core.project_state import ProjectState

    state = ProjectState()
    state.set_loaded_project(
        Project(
            project_id="project",
            project_root=tmp_path,
            image_paths=[tmp_path / "020.png"],
            ground_truth_map={},
            total_pages=1,
        )
    )

    def inconsistent_preview(_state: ProjectState, _page_index: int) -> object:
        return build_source_text_preview(
            page_key="020.png",
            f2_payload=b'{"020.png":"different source words"}',
            p3_payload=b'{"020.png":"r\\u00e9gime voyageur"}',
            evidence=_evidence(),
        )

    monkeypatch.setattr(source_alignment, "source_text_preview_for_page", inconsistent_preview)
    response = source_alignment.get_source_text("project", 0, state)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    payload = json.loads(response.body)
    assert payload["error"] == "source_text_invalid"
    assert "prepared F2 visible text" in payload["message"]

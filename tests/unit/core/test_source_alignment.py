from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pdomain_book_contracts.matching.pgdp_bounded import match_pgdp_documents_bounded
from pdomain_book_contracts.matching.pgdp_visible import (
    PgdpTokenLookup,
    match_document_from_pgdp_text,
)
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.core.source_alignment import (
    SourceAlignmentEvidence,
    align_source_page,
    alignment_policy,
    grouped_word_bindings,
    ocr_signature,
    scalar_word_binding,
)

if TYPE_CHECKING:
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectedRegion
    from pdomain_ocr_labeler_spa.core.source_alignment import SourceAlignmentResult


def _page(texts: tuple[str, ...]) -> Page:
    return Page.from_dict(
        {
            "width": 1000,
            "height": 1600,
            "page_index": 0,
            "items": [
                {
                    "type": "Block",
                    "child_type": "WORDS",
                    "block_category": "LINE",
                    "items": [
                        {
                            "type": "Word",
                            "text": text,
                            "bounding_box": {
                                "top_left": {"x": 10 + i * 50, "y": 20},
                                "bottom_right": {"x": 45 + i * 50, "y": 40},
                                "is_normalized": False,
                            },
                        }
                        for i, text in enumerate(texts)
                    ],
                }
            ],
        }
    )


def _evidence(*, f2_text: bytes = b"11 717", p3_text: bytes = b"11717") -> SourceAlignmentEvidence:
    f2 = match_document_from_pgdp_text(f2_text, document_id="f2", page_id="15.png", artifact_id="F2")
    f2 = f2.model_copy(
        update={
            "token_lookup": tuple(
                PgdpTokenLookup(
                    token_id=item.token_id,
                    visible_grapheme_range=item.visible_grapheme_range,
                    source_word_ids=(f"stored-{index}",),
                )
                for index, item in enumerate(f2.token_lookup)
            )
        }
    )
    p3 = match_document_from_pgdp_text(p3_text, document_id="p3", page_id="15.png", artifact_id="P3")
    return SourceAlignmentEvidence(
        schema="pdomain.pgdp-source-alignment",
        version=1,
        project_id="project",
        page_key="15.png",
        page_id="15.png",
        f2=f2,
        p3=p3,
        f2_to_p3=match_pgdp_documents_bounded(
            source=f2.document, target=p3.document, policy=alignment_policy()
        ),
    )


def test_composed_group_preserves_source_ids_and_ocr_topology() -> None:
    page = _page(("11717",))
    page.words[0].ground_truth_text = "human correction"
    before = page.to_dict()
    result = align_source_page(_evidence(), page=page, generation=3)
    assert page.to_dict() == before
    assert result.p3 == _evidence().p3
    group = next(group for group in result.groups if group.source_word_ids)
    assert group.source_word_ids == ("stored-0", "stored-1")
    assert group.ocr_token_ids == ("ocr-0",)
    assert group.box == (10, 20, 45, 40)
    assert group.decision == "pending"
    assert grouped_word_bindings(page, result)["stored-0"] == (page.words[0],)
    with pytest.raises(ValueError, match="one-to-one"):
        _ = scalar_word_binding(page, result, "stored-0")


def test_ocr_signature_detects_topology_or_geometry_changes() -> None:
    page = _page(("11717",))
    signature = ocr_signature(page)
    page.words[0].ground_truth_text = "human correction"
    assert ocr_signature(page) == signature
    page.words[0].text = "changed OCR"
    assert ocr_signature(page) != signature


def test_typed_sidecar_review_survives_round_trip() -> None:
    from pdomain_ocr_labeler_spa.core.labeler_sidecars import LabelerSidecars

    result = align_source_page(_evidence(), page=_page(("11717",)), generation=3)
    group = result.groups[0].model_copy(update={"decision": "edited", "reviewed_text": "human suggestion"})
    result = result.model_copy(update={"groups": (group,)})
    section = LabelerSidecars(source_alignment=result).to_blob_section()
    restored = LabelerSidecars.from_content_dict({"labeler_sidecars": section})
    assert restored.source_alignment == result
    assert restored.source_alignment is not None
    assert restored.source_alignment.groups[0].reviewed_text == "human suggestion"


def test_grouped_structure_review_refreshes_union_signatures() -> None:
    from pdomain_book_contracts.layout.text_hints import LayoutStructure, LayoutStructureLine

    from pdomain_ocr_labeler_spa.core.regions.layout_structure import reviewed_structure
    from pdomain_ocr_labeler_spa.core.source_alignment import stamp_alignment

    page = _page(("11717",))
    result = align_source_page(_evidence(), page=page, generation=0)
    stamp_alignment(page, result)
    structure = LayoutStructure(
        kind="blockquote", lines=(LayoutStructureLine(text="11 717", word_ids=("stored-0", "stored-1")),)
    )
    reviewed = reviewed_structure(structure, page=page, bundle=None)
    assert len(reviewed.lines[0].word_signatures) == 2
    assert reviewed.lines[0].word_signatures[0] == reviewed.lines[0].word_signatures[1]


def test_api_review_checks_result_generation_and_preserves_human_text(tmp_path: Path) -> None:
    from fastapi.responses import JSONResponse

    from pdomain_ocr_labeler_spa.api.source_alignment import ReviewAlignmentRequest, review_alignment
    from pdomain_ocr_labeler_spa.core.models import PageSource, Project
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome
    from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState

    state = ProjectState()
    state.set_loaded_project(
        Project(
            project_id="project",
            project_root=tmp_path,
            image_paths=[tmp_path / "15.png"],
            ground_truth_map={},
            total_pages=1,
        )
    )
    page = _page(("11717",))
    page.words[0].ground_truth_text = "human GT"
    result = align_source_page(_evidence(), page=page, generation=3)
    pstate = PageState(
        page_index=0,
        generation=3,
        source_alignment=result,
        page_record=PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page),
    )
    state.set_page_state(0, pstate)
    stale = review_alignment(
        "project",
        0,
        result.groups[0].group_id,
        ReviewAlignmentRequest(expected_generation=2, result_id=result.result_id, decision="accepted"),
        state=state,
        store=None,
    )
    assert isinstance(stale, JSONResponse) and stale.status_code == 409
    accepted = review_alignment(
        "project",
        0,
        result.groups[0].group_id,
        ReviewAlignmentRequest(expected_generation=3, result_id=result.result_id, decision="accepted"),
        state=state,
        store=None,
    )
    assert not isinstance(accepted, JSONResponse)
    assert accepted.generation == 4
    assert accepted.result is not None and accepted.result.groups[0].decision == "accepted"
    assert page.words[0].ground_truth_text == "human GT"


def test_changed_composed_verse_retains_stanzas_and_indent_without_exact_ocr_search() -> None:
    from pdomain_book_contracts.annotation import RegionRole
    from pdomain_book_contracts.layout.text_hints import LayoutStructure
    from pdomain_book_contracts.matching.pgdp_visible import match_document_from_pgdp_tokens
    from pdomain_book_contracts.sources.pgdp.f2.structure import layout_hints_from_tokens
    from pdomain_book_contracts.sources.pgdp.f2.tokens import tokenize_f2
    from pydantic import JsonValue, TypeAdapter

    from pdomain_ocr_labeler_spa.core.regions.text_layout import composed_layout_regions

    raw = b"/*\nRoses are red\n  Violets are blue\n\nDreams are bright\n*/"
    parsed = tokenize_f2(raw)
    f2 = match_document_from_pgdp_tokens(parsed, document_id="f2", page_id="15.png", artifact_id="F2")
    f2 = f2.model_copy(
        update={
            "token_lookup": tuple(
                item.model_copy(update={"source_word_ids": (f"stored-{index}",)})
                for index, item in enumerate(f2.token_lookup)
            )
        }
    )
    p3 = match_document_from_pgdp_text(
        b"Roses are red\nViolets are blue\nDreams are bright",
        document_id="p3",
        page_id="15.png",
        artifact_id="P3",
    )
    evidence = SourceAlignmentEvidence(
        schema="pdomain.pgdp-source-alignment",
        version=1,
        project_id="project",
        page_key="15.png",
        page_id="15.png",
        f2=f2,
        p3=p3,
        f2_to_p3=match_pgdp_documents_bounded(
            source=f2.document, target=p3.document, policy=alignment_policy()
        ),
        hints=layout_hints_from_tokens(parsed, source_ref="F2"),
    )
    rows: list[JsonValue] = []
    for texts in (("ROSES", "are", "red"), ("Violets", "are", "blue"), ("Dreams", "are", "bright")):
        base = TypeAdapter(dict[str, JsonValue]).validate_python(_page(texts).to_dict())["items"]
        assert isinstance(base, list)
        row = base[0]
        assert isinstance(row, dict)
        rows.append(row)
    page = Page.from_dict({"width": 1000, "height": 1600, "page_index": 0, "items": rows})
    result = align_source_page(evidence, page=page, generation=0)
    proposals = composed_layout_regions(page=page, result=result)
    verse = next(region for region in proposals if region.role == RegionRole.POETRY)
    payload = TypeAdapter(dict[str, JsonValue]).validate_python(verse.evidence)
    lines = LayoutStructure.model_validate(payload["layout_structure"]).lines
    assert len(lines) == 3
    assert lines[1].indent_hint == "2 spaces"
    assert lines[2].stanza_index is not None and lines[1].stanza_index is not None
    assert lines[2].stanza_index > lines[1].stanza_index


@pytest.mark.parametrize("cancel", [True, False])
def test_alignment_discards_cancelled_or_changed_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, cancel: bool
) -> None:
    import asyncio
    import threading

    from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
    from pdomain_ocr_labeler_spa.core.jobs.handlers import source_alignment as handler
    from pdomain_ocr_labeler_spa.core.jobs.runner import JobRunner
    from pdomain_ocr_labeler_spa.core.models import PageSource, Project
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome
    from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState

    state = ProjectState()
    state.set_loaded_project(
        Project(
            project_id="project",
            project_root=tmp_path,
            image_paths=[tmp_path / "15.png"],
            ground_truth_map={},
            total_pages=1,
        )
    )
    page = _page(("11717",))
    pstate = PageState(
        page_index=0, page_record=PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    )
    state.set_page_state(0, pstate)
    runner = JobRunner(JobEventBroker(), context={"project_state": state})
    job_id = runner.submit_idempotent(
        "source_alignment",
        request_id="alignment-request",
        project_id="project",
        payload={"page_index": 0, "expected_generation": 0},
    )
    job = runner.get_job(job_id)
    assert job is not None
    started, release = threading.Event(), threading.Event()

    def evidence_for_page(_state: ProjectState, _page_index: int) -> SourceAlignmentEvidence:
        return _evidence()

    def blocking_align(
        evidence: SourceAlignmentEvidence, *, page: Page, generation: int
    ) -> SourceAlignmentResult:
        started.set()
        if not release.wait(5):
            raise TimeoutError("test did not release matching")
        return align_source_page(evidence, page=page, generation=generation)

    monkeypatch.setattr(handler, "load_source_evidence", evidence_for_page)
    monkeypatch.setattr(handler, "align_source_page", blocking_align)

    async def scenario() -> None:
        assert job is not None
        task = asyncio.create_task(handler.handle_source_alignment(runner, job))
        assert await asyncio.to_thread(started.wait, 5)
        if cancel:
            _ = await runner.request_cancel(job_id)
        else:
            pstate.generation += 1
        release.set()
        if cancel:
            await task
        else:
            with pytest.raises(ValueError, match="changed while"):
                await task

    asyncio.run(scenario())
    assert pstate.source_alignment is None


def test_composed_source_keeps_optional_edition_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from pdomain_ocr_labeler_spa.core.models import Project
    from pdomain_ocr_labeler_spa.core.project_state import ProjectState
    from pdomain_ocr_labeler_spa.core.regions import text_layout

    state = ProjectState()
    state.set_loaded_project(
        Project(
            project_id="project",
            project_root=tmp_path,
            image_paths=[tmp_path / "15.png"],
            ground_truth_map={},
            total_pages=1,
        )
    )
    edition = tmp_path / "edition"
    edition.mkdir()
    _ = (edition / "layout-hints.json").write_text(
        json.dumps(
            {
                "schema": "pdomain.edition-layout-hints",
                "version": 1,
                "groups": [
                    {
                        "page_ids": ["15.png"],
                        "hints": [
                            {
                                "kind": "poetry",
                                "source": "gutenberg_html",
                                "text": "11 717",
                                "lines": [{"text": "11 717"}],
                                "source_ref": "edition.html",
                            }
                        ],
                    }
                ],
            }
        )
    )

    def source_for_page(_state: ProjectState, _index: int) -> SourceAlignmentEvidence:
        return _evidence()

    monkeypatch.setattr(text_layout, "load_source_evidence", source_for_page)
    evidence = text_layout.load_layout_evidence(state, 0)
    assert evidence.composed_source
    assert evidence.hints[0].source == "gutenberg_html"
    assert "retained" in " ".join(evidence.warnings)


def test_rejected_group_cannot_refresh_structure_geometry() -> None:
    from pdomain_book_contracts.layout.text_hints import LayoutStructure, LayoutStructureLine

    from pdomain_ocr_labeler_spa.core.regions.layout_structure import (
        refresh_structure_signatures,
        reviewed_structure,
    )
    from pdomain_ocr_labeler_spa.core.source_alignment import stamp_alignment

    page = _page(("11717", "safe"))
    result = align_source_page(
        _evidence(f2_text=b"11 717 safe", p3_text=b"11717 safe"), page=page, generation=0
    )
    rejected = result.model_copy(
        update={
            "groups": tuple(
                group.model_copy(update={"decision": "rejected"})
                if "stored-0" in group.source_word_ids
                else group
                for group in result.groups
            )
        }
    )
    assert grouped_word_bindings(page, rejected) == {"stored-2": (page.words[1],)}
    assert grouped_word_bindings(page, result)["stored-0"] == (page.words[0],)
    stamp_alignment(page, rejected)
    structure = LayoutStructure(
        kind="blockquote", lines=(LayoutStructureLine(text="11 717", word_ids=("stored-0", "stored-1")),)
    )
    with pytest.raises(ValueError, match="rejected"):
        _ = refresh_structure_signatures(structure, page=page)
    with pytest.raises(ValueError, match="rejected"):
        _ = reviewed_structure(structure, page=page, bundle=None)


@pytest.mark.parametrize(
    "source_lines",
    [
        ("THE HISTORY OF ROME", "BY JOHN SMITH", "LONDON AND NEW YORK"),
        ("The History of Rome", "By John Smith", "London and New York"),
        ("CHAPTER ONE", "The unexpected visitor", "The morning after"),
        ("The dawn of empire", "The people of Rome", "The rise of Rome"),
    ],
)
def test_formatted_titles_and_chapter_headings_abstain_from_poetry(source_lines: tuple[str, ...]) -> None:
    from pdomain_book_contracts.annotation import RegionRole
    from pdomain_book_contracts.layout.text_hints import LayoutTextHint, LayoutTextLine
    from pdomain_book_contracts.typography.spans import split_graphemes

    from pdomain_ocr_labeler_spa.core.regions.text_layout import composed_layout_regions

    text = "\n".join(source_lines)
    hint = LayoutTextHint(
        kind="formatted_block",
        source="f2",
        source_ref="F2",
        text=text,
        lines=tuple(LayoutTextLine(text=line) for line in source_lines),
        grapheme_range=(0, len(split_graphemes(text))),
    )
    evidence = _evidence(f2_text=text.encode(), p3_text=text.encode()).model_copy(update={"hints": (hint,)})
    page = _page(tuple(text.split()))
    result = align_source_page(evidence, page=page, generation=0)
    regions = composed_layout_regions(page=page, result=result)
    assert regions
    assert all(region.role != RegionRole.POETRY for region in regions)


def test_composed_columns_keep_isolated_shared_header_outside_column_boxes() -> None:
    from pdomain_book_contracts.annotation import RegionRole
    from pdomain_book_contracts.layout.text_hints import LayoutStructure
    from pydantic import JsonValue, TypeAdapter

    from pdomain_ocr_labeler_spa.core.regions.text_layout import composed_layout_regions

    rows: list[tuple[tuple[str, tuple[int, int, int, int]], ...]] = [
        (
            ("THE", (318, 14, 375, 32)),
            ("CANADIAN", (394, 14, 546, 32)),
            ("MECCA", (559, 14, 661, 32)),
            ("3", (956, 21, 968, 39)),
        ),
        (("caption", (110, 541, 378, 550)),),
    ]
    rows.extend(((f"left{index}", (8, top, 481, top + 20)),) for index, top in enumerate(range(570, 821, 50)))
    rows.extend(
        ((f"right{index}", (502, top, 975, top + 20)),) for index, top in enumerate(range(722, 1023, 50))
    )
    items: list[dict[str, object]] = []
    tokens: list[str] = []
    for row in rows:
        tokens.extend(text for text, _ in row)
        items.append(
            {
                "type": "Block",
                "child_type": "WORDS",
                "block_category": "LINE",
                "items": [
                    {
                        "type": "Word",
                        "text": text,
                        "bounding_box": {
                            "top_left": {"x": box[0], "y": box[1]},
                            "bottom_right": {"x": box[2], "y": box[3]},
                            "is_normalized": False,
                        },
                    }
                    for text, box in row
                ],
            }
        )
    page = Page.from_dict({"width": 1000, "height": 1600, "page_index": 0, "items": items})
    text = " ".join(token for token in tokens if token != "caption").encode()
    result = align_source_page(_evidence(f2_text=text, p3_text=text), page=page, generation=0)
    regions = composed_layout_regions(page=page, result=result)
    columns: list[DetectedRegion] = []
    headers: list[DetectedRegion] = []
    for region in regions:
        data = TypeAdapter(dict[str, JsonValue]).validate_python(region.evidence)
        if data.get("layout_structure") is not None:
            structure = LayoutStructure.model_validate(data["layout_structure"])
            if structure.kind == "column_flow":
                columns.append(region)
        elif region.box[1] == 14:
            headers.append(region)
    assert len(columns) == 2
    assert [column.box[1] for column in columns] == [570, 722]
    assert len(headers) == 1
    assert headers[0].box == (318, 14, 968, 39)
    assert any(region.box == (110, 541, 378, 550) for region in regions)
    assert all(region.role != RegionRole.TABLE for region in regions)


def _saved_grouped_verse(tmp_path: Path) -> tuple[Page, SourceAlignmentResult]:
    import json
    from uuid import uuid4

    from pdomain_book_contracts.layout.text_hints import LayoutStructure, LayoutStructureLine
    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import PageRecord, ProvenanceNode

    from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
    from pdomain_ocr_labeler_spa.core.labeler_sidecars import LabelerSidecars
    from pdomain_ocr_labeler_spa.core.page_state import save_page_content_to_store
    from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
    from pdomain_ocr_labeler_spa.core.source_alignment import alignment_from_page, stamp_alignment

    page = _page(("11717", "safe"))
    page.words[0].ground_truth_text = "human correction"
    result = align_source_page(
        _evidence(f2_text=b"11 717 safe", p3_text=b"11717 safe"), page=page, generation=0
    )
    result = result.model_copy(
        update={
            "groups": tuple(
                group.model_copy(
                    update={"decision": "edited", "note": "reviewed verse", "reviewed_text": "11 717"}
                )
                if "stored-0" in group.source_word_ids
                else group.model_copy(update={"decision": "rejected"})
                for group in result.groups
            )
        }
    )
    stamp_alignment(page, result)
    structure = LayoutStructure(
        kind="poetry",
        lines=(
            LayoutStructureLine(
                text="11 717", word_ids=("stored-0", "stored-1"), stanza_index=2, indent_hint="2 spaces"
            ),
        ),
    )
    page.lines[0].additional_block_attributes.update(
        {"region_id": "reviewed-verse", "layout_structure": structure.to_dict()}
    )
    page.lines[0].block_role_labels = ["poetry"]
    page_id = uuid4()
    project_root = tmp_path / "project"
    store = LabelerPageStore(project_root)
    try:
        aggregate = PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr"))
        content_hash = store.blobs.write(json.dumps(page.to_dict()).encode())
        aggregate.ocr_completed(
            provenance_node=ProvenanceNode(id="ocr", source="ocr", tool="test", blob_refs=[content_hash]),
            blob_refs=[content_hash],
        )
        store.save_page(aggregate)
        _ = save_page_content_to_store(
            page_id=page_id, page=page, store=store, labeler_sidecars=LabelerSidecars(source_alignment=result)
        )
    finally:
        store.close()
    store = LabelerPageStore(project_root)
    try:
        saved = load_page_from_store(store, page_id)
        assert saved is not None
        assert alignment_from_page(saved) == result
        assert saved.words[0].ground_truth_text == "human correction"
        return saved, result
    finally:
        store.close()


@pytest.mark.parametrize("copy_lane", ["frozen", "region_snapshot", "legacy_envelope"])
def test_saved_grouped_verse_exports_through_page_copy_boundaries(tmp_path: Path, copy_lane: str) -> None:
    import asyncio
    import json

    from pdomain_book_contracts.layout.text_hints import LayoutStructure
    from pydantic import JsonValue, TypeAdapter

    from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import (
        ExportPageRef,
        append_confirmed_regions,
        export_output_dir,
        freeze_export_page,
        load_export_page,
        load_frozen_export_page,
    )
    from pdomain_ocr_labeler_spa.core.jobs.handlers.region_export import (
        RegionExportPage,
        handle_region_export,
    )
    from pdomain_ocr_labeler_spa.core.jobs.runner import JobRunner
    from pdomain_ocr_labeler_spa.core.labeler_sidecars import LabelerSidecars, content_dict_with_sidecars
    from pdomain_ocr_labeler_spa.core.source_alignment import alignment_from_page
    from pdomain_ocr_labeler_spa.settings import Settings

    saved, result = _saved_grouped_verse(tmp_path)
    project_root = tmp_path / "project"
    assert append_confirmed_regions(saved, tmp_path / "live", prefix="verse") == 1
    output = tmp_path / "out"
    if copy_lane == "frozen":
        image_path = tmp_path / "scan.png"
        _ = image_path.write_bytes(b"scan")
        snapshot = freeze_export_page(
            page=saved,
            image_path=image_path,
            page_index=0,
            prefix="verse",
            blob_project_dir=project_root / ".pd-pages",
        )
        copied, _image = load_frozen_export_page(snapshot)
        assert isinstance(copied, Page)
        assert alignment_from_page(copied) == result
        assert append_confirmed_regions(copied, output, prefix="verse") == 1
    elif copy_lane == "legacy_envelope":
        envelope = tmp_path / "legacy.json"
        _ = envelope.write_text(
            json.dumps(
                {
                    "schema": {"name": "pd_ocr_labeler.user_page"},
                    "payload": {
                        "page": content_dict_with_sidecars(saved, LabelerSidecars(source_alignment=result)),
                    },
                }
            )
        )
        copied = load_export_page(ExportPageRef(page_index=0, prefix="verse", json_path=envelope), None)
        assert isinstance(copied, Page)
        assert alignment_from_page(copied) == result
        assert append_confirmed_regions(copied, output, prefix="verse") == 1
    else:
        snapshot_region = RegionExportPage.from_page(saved, prefix="verse")
        settings = Settings(data_root=tmp_path / "data")
        runner = JobRunner(JobEventBroker(), context={"settings": settings})
        job_id = runner.submit(
            "export", project_id="project", payload={"region_pages": [snapshot_region.model_dump()]}
        )
        job = runner.get_job(job_id)
        assert job is not None
        asyncio.run(handle_region_export(runner, job))
        output = export_output_dir(settings.data_root, "project", "all")
    document = TypeAdapter(dict[str, JsonValue]).validate_json(
        (output / "regions" / "structure.json").read_bytes()
    )
    entries = document["regions"]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)
    exported = LayoutStructure.model_validate(entry["structure"])
    assert exported.kind == "poetry"
    assert exported.lines[0].word_ids == ("stored-0", "stored-1")
    assert exported.lines[0].stanza_index == 2
    assert len(exported.lines[0].word_signatures) == 2


@pytest.mark.parametrize("copy_lane", ["frozen", "region_snapshot"])
def test_export_copy_prefers_latest_rejection_over_stale_sidecar(tmp_path: Path, copy_lane: str) -> None:
    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import (
        append_confirmed_regions,
        freeze_export_page,
        load_frozen_export_page,
    )
    from pdomain_ocr_labeler_spa.core.jobs.handlers.region_export import RegionExportPage
    from pdomain_ocr_labeler_spa.core.labeler_sidecars import sidecars_from_page
    from pdomain_ocr_labeler_spa.core.page_content_snapshot import restore_page_content
    from pdomain_ocr_labeler_spa.core.source_alignment import alignment_from_page, stamp_alignment

    page, previous = _saved_grouped_verse(tmp_path)
    stored = sidecars_from_page(page)
    assert stored is not None
    stored.char_bboxes_map["kept"] = [1, 2, 3, 4]
    current = previous.model_copy(
        update={
            "groups": tuple(
                group.model_copy(update={"decision": "rejected", "note": "latest rejection"})
                for group in previous.groups
            )
        }
    )
    stamp_alignment(page, current)
    assert stored.source_alignment == previous
    if copy_lane == "frozen":
        image_path = tmp_path / "scan.png"
        _ = image_path.write_bytes(b"scan")
        snapshot = freeze_export_page(
            page=page,
            image_path=image_path,
            page_index=0,
            prefix="verse",
            blob_project_dir=tmp_path / "project" / ".pd-pages",
        )
        copied, _image = load_frozen_export_page(snapshot)
    else:
        copied = restore_page_content(RegionExportPage.from_page(page, prefix="verse").page_json)
    assert alignment_from_page(copied) == current
    copied_sidecars = sidecars_from_page(copied)
    assert copied_sidecars is not None and copied_sidecars.char_bboxes_map["kept"] == [1, 2, 3, 4]
    with pytest.raises(ValueError, match="rejected"):
        _ = append_confirmed_regions(copied, tmp_path / "out", prefix="verse")


def test_page_copy_rejects_alignment_from_another_ocr_snapshot(tmp_path: Path) -> None:
    from pydantic import JsonValue, TypeAdapter

    from pdomain_ocr_labeler_spa.core.page_content_snapshot import restore_page_content, snapshot_page_content

    page, _result = _saved_grouped_verse(tmp_path)
    snapshot = snapshot_page_content(page)
    page.words[0].text = "different OCR"
    with pytest.raises(ValueError, match="stale"):
        _ = snapshot_page_content(page)
    changed = TypeAdapter(dict[str, JsonValue]).validate_python(page.to_dict())
    changed["labeler_sidecars"] = snapshot["labeler_sidecars"]
    with pytest.raises(ValueError, match="stale"):
        _ = restore_page_content(changed)


@pytest.mark.parametrize("wide_bridge", [False, True])
def test_composed_columns_abstain_from_splitting_continuous_paragraph(*, wide_bridge: bool) -> None:
    from pdomain_book_contracts.layout.text_hints import LayoutStructure
    from pydantic import JsonValue, TypeAdapter

    from pdomain_ocr_labeler_spa.core.regions.text_layout import composed_layout_regions

    items: list[dict[str, object]] = []
    tokens: list[str] = []
    for line in range(6):
        if wide_bridge:
            edges = ((34, 300), (400, 970)) if line % 2 == 0 else ((34, 200), (210, 650), (700, 970))
        else:
            edges = ((34, 484), (504, 570))
        words: list[dict[str, object]] = []
        for index, (left, right) in enumerate(edges):
            text = f"paragraph{line}word{index}"
            tokens.append(text)
            words.append(
                {
                    "type": "Word",
                    "text": text,
                    "bounding_box": {
                        "top_left": {"x": left, "y": 1050 + line * 30},
                        "bottom_right": {"x": right, "y": 1070 + line * 30},
                        "is_normalized": False,
                    },
                }
            )
        items.append({"type": "Block", "child_type": "WORDS", "block_category": "LINE", "items": words})
    page = Page.from_dict({"width": 1000, "height": 1800, "page_index": 0, "items": items})
    source = " ".join(tokens).encode()
    result = align_source_page(_evidence(f2_text=source, p3_text=source), page=page, generation=0)
    for region in composed_layout_regions(page=page, result=result):
        evidence = TypeAdapter(dict[str, JsonValue]).validate_python(region.evidence)
        structure = evidence.get("layout_structure")
        assert structure is None or LayoutStructure.model_validate(structure).kind != "column_flow"


def test_consumed_quote_fragments_cannot_create_independent_column_support() -> None:
    from pdomain_book_contracts.layout.text_hints import LayoutStructure, LayoutTextHint, LayoutTextLine
    from pdomain_book_contracts.typography.spans import split_graphemes
    from pydantic import JsonValue, TypeAdapter

    from pdomain_ocr_labeler_spa.core.regions.text_layout import composed_layout_regions

    items: list[dict[str, object]] = []
    tokens: list[str] = []
    hints: list[LayoutTextHint] = []
    cursor = 0
    for line in range(6):
        words: list[dict[str, object]] = []
        for side, (left, right) in enumerate(((24, 367), (405, 951))):
            text = f"row{line}side{side}"
            tokens.append(text)
            end = cursor + len(split_graphemes(text))
            if side == line % 2:
                hints.append(
                    LayoutTextHint(
                        kind="blockquote",
                        source="f2",
                        source_ref="F2",
                        text=text,
                        lines=(LayoutTextLine(text=text),),
                        grapheme_range=(cursor, end),
                    )
                )
            cursor = end + 1
            words.append(
                {
                    "type": "Word",
                    "text": text,
                    "bounding_box": {
                        "top_left": {"x": left, "y": 1111 + line * 30},
                        "bottom_right": {"x": right, "y": 1131 + line * 30},
                        "is_normalized": False,
                    },
                }
            )
        items.append({"type": "Block", "child_type": "WORDS", "block_category": "LINE", "items": words})
    page = Page.from_dict({"width": 1000, "height": 1800, "page_index": 0, "items": items})
    source = " ".join(tokens).encode()
    evidence = _evidence(f2_text=source, p3_text=source).model_copy(update={"hints": tuple(hints)})
    result = align_source_page(evidence, page=page, generation=0)
    regions = composed_layout_regions(page=page, result=result)
    assert len(regions) == 6
    for region in regions:
        data = TypeAdapter(dict[str, JsonValue]).validate_python(region.evidence)
        assert LayoutStructure.model_validate(data["layout_structure"]).kind == "blockquote"

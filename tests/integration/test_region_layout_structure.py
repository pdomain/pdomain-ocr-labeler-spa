"""Reviewed layout stays beside regions without moving OCR words."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from pdomain_book_tools.ocr.page import Page
from pdomain_book_tools.typography import LabelingBundle

from pdomain_ocr_labeler_spa.api.pages import PagePayload
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import ProjectState

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

_BASE = "/api/projects/book1/pages/0"


def test_loose_mirror_rejects_word_bound_structure(
    toolbar_loaded: tuple[TestClient, ProjectState, object],
) -> None:
    client, _state, _page = toolbar_loaded
    response = client.post(
        f"{_BASE}/regions",
        json={
            "role": "poetry",
            "box": {"x": 0, "y": 0, "width": 40, "height": 40},
            "layout_structure": {
                "kind": "poetry",
                "lines": [{"text": "one", "word_ids": ["unsupported"], "stanza_index": 0}],
            },
        },
    )
    assert response.status_code == 400
    assert "prepared" in response.text.lower()


def test_column_structure_can_be_reviewed_edited_and_cleared(
    toolbar_loaded: tuple[TestClient, ProjectState, object],
) -> None:
    client, _state, _page = toolbar_loaded
    structure = {"kind": "column_flow", "column_group_id": "columns", "column_index": 0, "reading_order": 1}
    response = client.post(
        f"{_BASE}/regions",
        json={
            "role": "paragraph",
            "box": {"x": 0, "y": 0, "width": 40, "height": 40},
            "layout_structure": structure,
        },
    )
    assert response.status_code == 200, response.text
    payload = PagePayload.model_validate_json(response.content)
    region = next(region for region in payload.regions if region.confirmed)
    assert region.layout_structure is not None
    assert region.layout_structure.column_index == 0
    edited = client.patch(
        f"{_BASE}/regions/{region.region_id}",
        json={
            "layout_structure": {**structure, "reading_order": 2},
        },
    )
    assert edited.status_code == 200, edited.text
    payload = PagePayload.model_validate_json(edited.content)
    region = next(region for region in payload.regions if region.confirmed)
    assert region.layout_structure is not None
    assert region.layout_structure.reading_order == 2
    cleared = client.patch(f"{_BASE}/regions/{region.region_id}", json={"layout_structure": None})
    assert cleared.status_code == 200
    payload = PagePayload.model_validate_json(cleared.content)
    assert all(region.layout_structure is None for region in payload.regions)


@contextmanager
def _prepared_client(
    tmp_path: Path,
) -> Generator[tuple[TestClient, ProjectState, LabelerPageStore, Page, UUID, LabelingBundle, str]]:
    from uuid import uuid4

    from fastapi.testclient import TestClient
    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import PageRecord

    from pdomain_ocr_labeler_spa.bootstrap import build_app
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
    from pdomain_ocr_labeler_spa.core.project_state import PageState
    from pdomain_ocr_labeler_spa.settings import Settings
    from tests.fixtures.layout_book import write_layout_bundle

    projects = tmp_path / "projects"
    projects.mkdir()
    root = projects / "layout-book"
    bundle, page = write_layout_bundle(root)
    settings = Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        no_prefetch=True,
        source_projects_root=projects,
    )
    app = build_app(settings)
    with TestClient(app) as client:
        loaded = client.post("/api/projects/load", json={"project_root": str(root)})
        assert loaded.status_code == 200, loaded.text
        from starlette.requests import Request

        from pdomain_ocr_labeler_spa.api.dependencies import get_page_store_optional, get_project_state

        request = Request({"type": "http", "app": app})
        state = get_project_state(request)
        store = get_page_store_optional(request)
        assert store is not None
        page_id = uuid4()
        store.save_page(PageAggregate(PageRecord(page_id=page_id, page_index=0, source="ocr")))
        pstate = PageState(
            page_index=0, page_record=PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
        )
        pstate.page_id = page_id
        state.set_page_state(0, pstate)
        project = state.loaded_project
        assert project is not None
        base = f"/api/projects/{project.project_id}/pages/0"
        _seed_proposal(project.project_root)
        yield client, state, store, page, page_id, bundle, base


@pytest.mark.parametrize("geometry_edit", ["nudge", "rebox"])
@pytest.mark.parametrize("nested", [False, True])
def test_prepared_structure_reload_edit_export_preserves_ids(
    tmp_path: Path, geometry_edit: str, nested: bool
) -> None:
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import (
        LayoutStructureFile,
        append_confirmed_regions,
    )
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import (
        confirmed_regions_from_page,
        find_region_block,
    )
    from pdomain_ocr_labeler_spa.core.regions.layout_structure import prepared_word_bindings

    with _prepared_client(tmp_path) as (client, _state, store, page, page_id, bundle, base):
        original_words = tuple(page.words)
        bindings = prepared_word_bindings(page, bundle)
        word_ids = tuple(bindings)
        structure = {
            "kind": "poetry",
            "lines": [
                {
                    "text": "First gentle verse",
                    "word_ids": word_ids[:3],
                    "stanza_index": 0,
                    "indent_hint": "2em",
                }
            ],
        }
        accepted = client.post(
            f"{base}/regions/proposals/verse-proposal/accept",
            json={
                "role": "poetry",
                "box": {"x": 10, "y": 30, "width": 300, "height": 160},
                "layout_structure": structure,
            },
        )
        assert accepted.status_code == 200, accepted.text
        payload = PagePayload.model_validate_json(accepted.content)
        region = next(region for region in payload.regions if region.confirmed)
        assert tuple(page.words) == original_words
        assert region.layout_structure is not None
        assert region.layout_structure.lines[0].word_ids == word_ids[:3]
        corrected = client.patch(
            f"{base}/regions/{region.region_id}",
            json={
                "layout_structure": {
                    **structure,
                    "lines": [
                        {
                            "text": "First gentle verse",
                            "word_ids": word_ids[:3],
                            "stanza_index": 1,
                            "indent_hint": "3em",
                        }
                    ],
                }
            },
        )
        assert corrected.status_code == 200, corrected.text
        inner_id = _nest_extra_region(client, base, page, region.region_id or "") if nested else None
        original_boxes = {region.region_id: region.box for region in confirmed_regions_from_page(page)}
        _correct_bound_word(client, base, page, original_words[0], geometry_edit)
        reloaded = load_page_from_store(store, page_id)
        assert isinstance(reloaded, Page)
        rebound = prepared_word_bindings(reloaded, bundle)
        assert rebound[word_ids[0]].ground_truth_text == "Corrected"
        roundtripped = Page.from_dict(reloaded.to_dict())
        final = prepared_word_bindings(roundtripped, bundle)
        assert tuple(final) == word_ids
        assert {
            region.region_id: region.box for region in confirmed_regions_from_page(roundtripped)
        } == original_boxes
        if inner_id is not None:
            outer = find_region_block(roundtripped, region.region_id or "")
            inner = find_region_block(roundtripped, inner_id)
            assert outer is not None and inner is not None
            assert roundtripped.find_parent_block(inner) is outer
            assert roundtripped.find_parent_block(outer) is not None
        output = tmp_path / "export"
        assert append_confirmed_regions(roundtripped, output, prefix="layout/page") == (2 if nested else 1)
        exported = LayoutStructureFile.model_validate_json((output / "regions/structure.json").read_bytes())
        saved = exported.regions[0].structure.lines[0]
        assert saved.word_ids == word_ids[:3]
        assert saved.stanza_index == 1 and saved.indent_hint == "3em"
        assert json.loads(saved.word_signatures[0]) == [22, 44, 95, 66, False]
        region_block = find_region_block(roundtripped, region.region_id or "")
        assert region_block is not None
        owner = roundtripped.find_parent_block(region_block) or roundtripped
        owner.remove_item(region_block)
        assert append_confirmed_regions(roundtripped, output, prefix="layout/page") == 0
        cleared = LayoutStructureFile.model_validate_json((output / "regions/structure.json").read_bytes())
        assert cleared.regions == []


def _correct_bound_word(
    client: TestClient, base: str, page: Page, target: object, geometry_edit: str
) -> None:
    line_index, word_index = next(
        (line_index, word_index)
        for line_index, line in enumerate(page.lines)
        for word_index, word in enumerate(line.words)
        if word is target
    )
    word_route = f"{base}/words/{line_index}/{word_index}"
    text_edit = client.post(f"{word_route}/gt", json={"text": "Corrected"})
    assert text_edit.status_code == 200, text_edit.text
    geometry_body = (
        {"left": -2, "right": 5, "top": -4, "bottom": 6}
        if geometry_edit == "nudge"
        else {"bbox": {"x": 22, "y": 44, "width": 73, "height": 22}}
    )
    box_edit = client.post(f"{word_route}/{geometry_edit}", json=geometry_body)
    assert box_edit.status_code == 200, box_edit.text


def _nest_extra_region(client: TestClient, base: str, page: Page, outer_id: str) -> str:
    from pdomain_book_tools.ocr.block import BlockChildType

    from pdomain_ocr_labeler_spa.core.regions.block_adapter import find_region_block

    response = client.post(
        f"{base}/regions",
        json={
            "role": "paragraph",
            "box": {"x": 30, "y": 40, "width": 200, "height": 100},
        },
    )
    assert response.status_code == 200, response.text
    inner_id = next(
        region.region_id
        for region in PagePayload.model_validate_json(response.content).regions
        if region.confirmed and region.region_id != outer_id
    )
    assert inner_id is not None
    outer = find_region_block(page, outer_id)
    inner = find_region_block(page, inner_id)
    assert outer is not None and inner is not None
    parent = next(block for block in page.items if block.words)
    page.remove_item(inner)
    page.remove_item(outer)
    outer.child_type = BlockChildType.BLOCKS
    outer.items = [inner]
    parent.items = [*parent.items, outer]
    assert page.find_parent_block(inner) is outer
    assert page.find_parent_block(outer) is parent
    return inner_id


def _seed_proposal(root: Path) -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import RegionProposal
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    RegionProposalLog(root).append_proposals(
        [
            RegionProposal(
                proposal_id="verse-proposal",
                run_id="layout-run",
                page_index=0,
                role=RegionRole.POETRY,
                box=(10, 30, 310, 190),
                confidence=0.7,
                evidence={"source": "gutenberg_html"},
            )
        ]
    )


def test_ordinary_acceptance_does_not_save_unreviewed_structure(
    toolbar_loaded: tuple[TestClient, ProjectState, object],
) -> None:
    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.regions.models import RegionProposal
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    client, state, _page = toolbar_loaded
    project = state.loaded_project
    assert project is not None
    RegionProposalLog(project.project_root).append_proposals(
        [
            RegionProposal(
                proposal_id="unreviewed",
                run_id="layout-run",
                page_index=0,
                role=RegionRole.POETRY,
                box=(0, 0, 40, 40),
                confidence=0.7,
                evidence={
                    "layout_structure": {
                        "kind": "poetry",
                        "lines": [{"text": "one", "word_ids": ["unsupported"], "stanza_index": 0}],
                    }
                },
            ),
        ]
    )
    response = client.post(f"{_BASE}/regions/proposals/unreviewed/accept", json={})
    assert response.status_code == 200, response.text
    payload = PagePayload.model_validate_json(response.content)
    assert all(region.layout_structure is None for region in payload.regions)


@pytest.mark.parametrize("failure", ["missing_word", "malformed_sidecar"])
def test_failed_structure_export_preserves_previous_labels_and_structure(
    tmp_path: Path, failure: str
) -> None:
    from pdomain_book_contracts.layout.text_hints import LayoutStructure, LayoutStructureLine
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import append_confirmed_regions
    from pdomain_ocr_labeler_spa.core.regions.block_adapter import find_region_block
    from pdomain_ocr_labeler_spa.core.regions.layout_structure import prepared_word_bindings

    with _prepared_client(tmp_path) as (client, _state, _store, page, _page_id, bundle, base):
        word_ids = tuple(prepared_word_bindings(page, bundle))
        structure = LayoutStructure(
            kind="poetry",
            lines=(
                LayoutStructureLine(
                    text="First gentle verse",
                    word_ids=word_ids[:3],
                    stanza_index=0,
                ),
            ),
        )
        accepted = client.post(
            f"{base}/regions/proposals/verse-proposal/accept",
            json={
                "layout_structure": structure.to_dict(),
            },
        )
        assert accepted.status_code == 200, accepted.text
        region_id = next(
            region.region_id
            for region in PagePayload.model_validate_json(accepted.content).regions
            if region.confirmed
        )
        output = tmp_path / "export"
        assert append_confirmed_regions(page, output, prefix="layout/page") == 1
        labels = output / "regions/labels.json"
        sidecar = output / "regions/structure.json"
        if failure == "malformed_sidecar":
            sidecar.write_bytes(b"malformed previous evidence")
        before = labels.read_bytes(), sidecar.read_bytes()
        edited = Page.from_dict(page.to_dict())
        block = find_region_block(edited, region_id or "")
        assert block is not None
        block.block_role_labels = ["paragraph"]
        block.additional_block_attributes["layout_structure"] = (
            structure.model_copy(
                update={
                    "lines": (structure.lines[0].model_copy(update={"word_ids": ("missing",)}),),
                }
            ).to_dict()
            if failure == "missing_word"
            else structure.model_copy(
                update={
                    "lines": (structure.lines[0].model_copy(update={"indent_hint": "changed"}),),
                }
            ).to_dict()
        )
        with pytest.raises(ValueError):
            append_confirmed_regions(edited, output, prefix="layout/page")
        assert (labels.read_bytes(), sidecar.read_bytes()) == before

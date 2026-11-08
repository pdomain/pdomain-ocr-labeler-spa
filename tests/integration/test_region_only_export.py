"""Reviewed regions export without changing general text-review gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _register_page_in_project
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from pdomain_ocr_labeler_spa.core.project_state import ProjectState


def test_region_only_export_uses_reviewed_regions_without_text_validation(
    toolbar_loaded: tuple[TestClient, ProjectState, object],
) -> None:
    client, state, _page = toolbar_loaded
    assert isinstance(client.app, FastAPI)
    store = client.app.state.page_store
    assert isinstance(store, LabelerPageStore)
    page_id = state.page_states[0].page_id
    assert page_id is not None
    _register_page_in_project(store=store, project_id="book1", page_id=page_id, page_index=0)
    created = client.post(
        "/api/projects/book1/pages/0/regions",
        json={
            "role": "paragraph",
            "box": {"x": 0, "y": 0, "width": 40, "height": 40},
            "layout_structure": {
                "kind": "column_flow",
                "column_group_id": "pair",
                "column_index": 0,
                "reading_order": 0,
            },
        },
    )
    assert created.status_code == 200, created.text
    general = client.post("/api/projects/book1/export", json={"scope": "current", "page_index": 0})
    assert general.status_code == 409
    response = client.post(
        "/api/projects/book1/export",
        json={
            "scope": "current",
            "page_index": 0,
            "regions_only": True,
        },
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    events = client.get(f"/api/jobs/{job_id}/events")
    assert "event: complete" in events.text, events.text
    settings = client.app.state.settings
    assert isinstance(settings, Settings)
    root = Path(settings.data_root) / "doctr-export" / "book1" / "all"
    labels = json.loads((root / "regions" / "labels.json").read_text())
    assert labels["pages"][0]["regions"][0]["role"] == "paragraph"
    structure = json.loads((root / "regions" / "structure.json").read_text())
    assert structure["regions"][0]["structure"]["column_index"] == 0
    assert not (root / "recognition").exists()
    assert not (root / "detection").exists()

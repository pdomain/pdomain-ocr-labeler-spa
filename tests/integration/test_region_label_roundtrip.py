"""A drawn region, its resized box, and its words survive a fresh store load."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
from pdomain_ocr_labeler_spa.core.regions.block_adapter import (
    confirmed_regions_from_page,
    find_region_block,
)

_BASE = "/api/projects/book1/pages/0"


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("JSON value must be an object")
    raw: dict[object, object] = value  # pyright: ignore[reportUnknownVariableType]
    mapping: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise TypeError("JSON object key must be a string")
        mapping[key] = item
    return mapping


def _object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("JSON value must be a list")
    raw: list[object] = value  # pyright: ignore[reportUnknownVariableType]
    return list(raw)


def _confirmed_region_id(payload: dict[str, object]) -> str:
    for item in _object_list(payload["regions"]):
        region = _object_dict(item)
        if region.get("confirmed") is not True:
            continue
        region_id = region.get("region_id")
        if isinstance(region_id, str):
            return region_id
    raise AssertionError("created page has no confirmed region")


def test_drawn_resized_region_and_its_words_reload_from_a_fresh_store(
    toolbar_loaded: tuple[TestClient, ProjectState, object],
) -> None:
    client, project_state, _page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "paragraph", "box": {"x": 5, "y": 6, "width": 50, "height": 40}},
    )
    assert created.status_code == 200, created.text
    # TestClient.json() is typed as Any. _object_dict checks the shape.
    created_body = _object_dict(created.json())  # pyright: ignore[reportAny]
    region_id = _confirmed_region_id(created_body)

    resized = client.patch(
        f"{_BASE}/regions/{region_id}",
        json={"box": {"x": 12, "y": 18, "width": 40, "height": 22}},
    )
    assert resized.status_code == 200, resized.text

    membership = client.put(
        f"{_BASE}/regions/{region_id}/words",
        json={"word_refs": [{"line_index": 0, "word_index": 0}]},
    )
    assert membership.status_code == 200, membership.text

    page_state = project_state.page_states[0]
    page_id = page_state.page_id
    assert page_id is not None
    project = project_state.loaded_project
    assert project is not None

    fresh = LabelerPageStore(project_dir=project.project_root)
    try:
        reloaded = load_page_from_store(fresh, page_id)
    finally:
        fresh.close()

    assert reloaded is not None
    region = find_region_block(reloaded, region_id)
    assert region is not None
    assert {word.text for word in region.words} == {"one"}
    resolved = next(item for item in confirmed_regions_from_page(reloaded) if item.region_id == region_id)
    assert resolved.role.value == "paragraph"
    assert resolved.box == (12, 18, 52, 40)

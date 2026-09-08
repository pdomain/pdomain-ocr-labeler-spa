"""Integration tests for ``api/regions.py`` — create, edit, delete, membership, proposals."""

from __future__ import annotations

from typing import Any

_BASE = "/api/projects/book1/pages/0"


def test_create_region_adds_a_confirmed_region_to_the_payload(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 5, "y": 5, "width": 50, "height": 50}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    regions = [reg for reg in body["regions"] if reg["confirmed"]]
    assert len(regions) == 1
    assert regions[0]["role"] == "poetry"
    assert regions[0]["box"] == {"x": 5, "y": 5, "width": 50, "height": 50}
    assert regions[0]["region_id"]


def test_create_region_with_an_unsupported_role_returns_400(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(
        f"{_BASE}/regions",
        json={"role": "catchword", "box": {"x": 5, "y": 5, "width": 50, "height": 50}},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_region_role"


def test_edit_region_changes_role_and_box(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 5, "y": 5, "width": 50, "height": 50}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])

    r = client.patch(
        f"{_BASE}/regions/{region_id}",
        json={"role": "blockquote", "box": {"x": 10, "y": 10, "width": 20, "height": 20}},
    )
    assert r.status_code == 200, r.text
    region = next(reg for reg in r.json()["regions"] if reg["region_id"] == region_id)
    assert region["role"] == "blockquote"
    assert region["box"] == {"x": 10, "y": 10, "width": 20, "height": 20}


def test_edit_unknown_region_returns_404(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.patch(f"{_BASE}/regions/does-not-exist", json={"role": "poetry"})
    assert r.status_code == 404, r.text
    assert r.json()["error"] == "region_not_found"


def test_delete_region_removes_it_from_the_payload(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 5, "y": 5, "width": 50, "height": 50}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])

    r = client.delete(f"{_BASE}/regions/{region_id}")
    assert r.status_code == 200, r.text
    assert all(reg["region_id"] != region_id for reg in r.json()["regions"])


def test_create_region_stamps_the_hand_drawn_sentinel_as_its_origin(toolbar_loaded: Any) -> None:
    """A person drawing a region unprompted, not accepting a proposal, is a distinct fact."""
    client, _ps, _page = toolbar_loaded
    r = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 5, "y": 5, "width": 50, "height": 50}},
    )
    assert r.status_code == 200, r.text
    region = next(reg for reg in r.json()["regions"] if reg["confirmed"])
    assert region["proposal_id"] == "hand-drawn"


def test_create_a_container_region_then_nest_a_child_under_it(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    container = client.post(
        f"{_BASE}/regions",
        json={
            "role": "figure",
            "box": {"x": 0, "y": 0, "width": 200, "height": 300},
            "child_type": "blocks",
        },
    ).json()
    parent_id = next(reg["region_id"] for reg in container["regions"] if reg["confirmed"])

    r = client.post(
        f"{_BASE}/regions",
        json={
            "role": "caption",
            "box": {"x": 10, "y": 10, "width": 20, "height": 20},
            "parent_region_id": parent_id,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    child_id = next(
        reg["region_id"] for reg in body["regions"] if reg["confirmed"] and reg["role"] == "caption"
    )

    from pdomain_ocr_labeler_spa.api.regions import find_region_block

    parent_block = find_region_block(page, parent_id)
    child_block = find_region_block(page, child_id)
    assert parent_block is not None and child_block is not None
    assert child_block in parent_block.items
    assert child_block not in page.items


def test_nesting_under_a_non_container_parent_returns_400(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    leaf = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 0, "y": 0, "width": 50, "height": 50}},
    ).json()
    leaf_id = next(reg["region_id"] for reg in leaf["regions"] if reg["confirmed"])

    r = client.post(
        f"{_BASE}/regions",
        json={
            "role": "caption",
            "box": {"x": 5, "y": 5, "width": 10, "height": 10},
            "parent_region_id": leaf_id,
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "parent_not_nesting_capable"


def test_nesting_under_an_unknown_parent_returns_404(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.post(
        f"{_BASE}/regions",
        json={
            "role": "caption",
            "box": {"x": 5, "y": 5, "width": 10, "height": 10},
            "parent_region_id": "does-not-exist",
        },
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"] == "region_not_found"

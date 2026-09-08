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


def test_edit_region_with_an_unsupported_role_returns_400(toolbar_loaded: Any) -> None:
    """A rejected role must never reach the blob — a later ``from_dict`` would fail to load it."""
    client, _ps, _page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 5, "y": 5, "width": 50, "height": 50}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])

    r = client.patch(f"{_BASE}/regions/{region_id}", json={"role": "catchword"})
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_region_role"

    # The rejection must never have reached the blob — the region still carries its
    # original role, proving nothing was mutated before the 400 was returned.
    payload = client.get(_BASE).json()
    region = next(reg for reg in payload["regions"] if reg["region_id"] == region_id)
    assert region["role"] == "poetry"


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
    # ``Block.add_item`` recomputes the owner's bounding box from its items; without the
    # create route's save/restore, nesting a small child would shrink the container's
    # box to fit it instead of leaving what a person drew alone.
    assert parent_block.bounding_box is not None
    assert parent_block.bounding_box.to_ltrb() == (0.0, 0.0, 200.0, 300.0)


def test_delete_nested_region_removes_it_from_its_parent_and_preserves_parent_box(
    toolbar_loaded: Any,
) -> None:
    """Exercises ``_region_owner``'s tree-walking branch, not just its ``return page``
    fallback — a region created with ``parent_region_id`` lives in the parent's
    ``items``, and deleting it must not let ``Block.remove_item``'s bounding-box
    recompute shrink the container to whatever it has left.
    """
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

    nested = client.post(
        f"{_BASE}/regions",
        json={
            "role": "caption",
            "box": {"x": 10, "y": 10, "width": 20, "height": 20},
            "parent_region_id": parent_id,
        },
    ).json()
    child_id = next(
        reg["region_id"] for reg in nested["regions"] if reg["confirmed"] and reg["role"] == "caption"
    )

    from pdomain_ocr_labeler_spa.api.regions import find_region_block

    parent_block = find_region_block(page, parent_id)
    child_block = find_region_block(page, child_id)
    assert parent_block is not None and child_block is not None
    assert parent_block.bounding_box is not None
    original_parent_box = parent_block.bounding_box.to_ltrb()

    r = client.delete(f"{_BASE}/regions/{child_id}")
    assert r.status_code == 200, r.text
    assert all(reg["region_id"] != child_id for reg in r.json()["regions"])

    assert child_block not in parent_block.items
    assert find_region_block(page, child_id) is None
    assert parent_block.bounding_box is not None
    assert parent_block.bounding_box.to_ltrb() == original_parent_box


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


def test_set_membership_moves_words_into_the_region(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 0, "y": 0, "width": 200, "height": 300}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])

    r = client.put(
        f"{_BASE}/regions/{region_id}/words",
        json={"word_refs": [{"line_index": 0, "word_index": 0}, {"line_index": 0, "word_index": 1}]},
    )
    assert r.status_code == 200, r.text
    from pdomain_ocr_labeler_spa.api.regions import find_region_block

    region = find_region_block(page, region_id)
    assert region is not None
    assert {w.text for w in region.words} == {"one", "two"}
    assert len(page.lines[0].words) == 0


def test_set_membership_preserves_the_explicit_box(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 1, "y": 1, "width": 199, "height": 299}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])

    r = client.put(
        f"{_BASE}/regions/{region_id}/words", json={"word_refs": [{"line_index": 0, "word_index": 0}]}
    )
    assert r.status_code == 200, r.text
    region = next(reg for reg in r.json()["regions"] if reg["region_id"] == region_id)
    # Box stays what was explicitly set — never re-derived from the union of member words.
    assert region["box"] == {"x": 1, "y": 1, "width": 199, "height": 299}


def test_set_membership_replaces_the_prior_set(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 0, "y": 0, "width": 200, "height": 300}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])
    client.put(f"{_BASE}/regions/{region_id}/words", json={"word_refs": [{"line_index": 0, "word_index": 0}]})

    # "one" (word_index 0) was moved into the region above, so "two" — originally at
    # word_index 1 on this line — has shifted down to word_index 0: positions are
    # resolved against the *current* live tree, never a stored ordinal.
    r = client.put(
        f"{_BASE}/regions/{region_id}/words", json={"word_refs": [{"line_index": 0, "word_index": 0}]}
    )
    assert r.status_code == 200, r.text
    from pdomain_ocr_labeler_spa.api.regions import find_region_block

    region = find_region_block(page, region_id)
    assert region is not None
    assert {w.text for w in region.words} == {"two"}
    # The released word ("one") comes back as a recovered block, not dropped.
    assert any("recovered" in b.block_role_labels for b in page.items)


def test_set_membership_on_unknown_region_returns_404(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    r = client.put(f"{_BASE}/regions/does-not-exist/words", json={"word_refs": []})
    assert r.status_code == 404, r.text


def test_set_membership_on_unknown_word_returns_404(toolbar_loaded: Any) -> None:
    client, _ps, _page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 0, "y": 0, "width": 200, "height": 300}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])
    r = client.put(
        f"{_BASE}/regions/{region_id}/words", json={"word_refs": [{"line_index": 99, "word_index": 0}]}
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"] == "word_not_found"


def test_set_membership_on_a_container_region_returns_400(toolbar_loaded: Any) -> None:
    """A container region (``child_type=blocks``) holds regions, not words — the
    mirror image of ``parent_not_nesting_capable``. The rejection must land before
    any word is moved out of its line.
    """
    client, _ps, page = toolbar_loaded
    container = client.post(
        f"{_BASE}/regions",
        json={
            "role": "figure",
            "box": {"x": 0, "y": 0, "width": 200, "height": 300},
            "child_type": "blocks",
        },
    ).json()
    container_id = next(reg["region_id"] for reg in container["regions"] if reg["confirmed"])

    r = client.put(
        f"{_BASE}/regions/{container_id}/words", json={"word_refs": [{"line_index": 0, "word_index": 0}]}
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "region_not_word_capable"
    # Nothing moved before the rejection — the word is still on its original line.
    assert {w.text for w in page.lines[0].words} == {"one", "two"}


# Moved here from Task 2: it needs the membership route above to put words in the
# region before deleting it. Under Task 2 alone the PUT 404s, the region has no
# members, and the recovered-block assertion cannot pass.
def test_delete_region_recovers_its_member_words(toolbar_loaded: Any) -> None:
    client, _ps, page = toolbar_loaded
    created = client.post(
        f"{_BASE}/regions",
        json={"role": "poetry", "box": {"x": 0, "y": 0, "width": 200, "height": 300}},
    ).json()
    region_id = next(reg["region_id"] for reg in created["regions"] if reg["confirmed"])
    client.put(f"{_BASE}/regions/{region_id}/words", json={"word_refs": [{"line_index": 0, "word_index": 0}]})

    before_word_count = len(page.words)
    r = client.delete(f"{_BASE}/regions/{region_id}")
    assert r.status_code == 200, r.text
    assert len(page.words) == before_word_count
    assert any("recovered" in b.block_role_labels for b in page.items)


def _live_ref(page: Any, text: str) -> dict[str, int]:
    """Resolve ``text``'s current ``(line_index, word_index)`` in the live tree.

    The membership route resolves refs against ``page.lines`` as it stands right
    now, and a region joins ``page.lines``, so a ref computed from the original
    OCR layout goes stale the moment anything moves. Reading it back off the page
    the fixture yields keeps these tests honest about that.
    """
    for line_index, line in enumerate(page.lines):
        for word_index, word in enumerate(line.words):
            if word.text == text:
                return {"line_index": line_index, "word_index": word_index}
    raise AssertionError(f"word {text!r} is not on the page")


def _make_region(client: Any, *, role: str, box: dict[str, int]) -> str:
    created = client.post(f"{_BASE}/regions", json={"role": role, "box": box}).json()
    return next(
        reg["region_id"]
        for reg in created["regions"]
        if reg["confirmed"] and reg["box"] == box and reg["role"] == role
    )


def test_moving_a_word_between_regions_leaves_the_source_box_alone(toolbar_loaded: Any) -> None:
    """``Block.lines`` returns ``[self]`` for a WORDS-typed block, so a leaf region
    is itself an entry in ``page.lines``: the block a claimed word is taken from can
    be another *region*, and ``Block.remove_item`` ends in
    ``recompute_bounding_box``. Without saving and restoring the source region's box,
    a person's drawn region silently shrinks to whatever words it has left.
    """
    client, _ps, page = toolbar_loaded
    source_id = _make_region(client, role="poetry", box={"x": 0, "y": 0, "width": 200, "height": 300})
    target_id = _make_region(client, role="blockquote", box={"x": 5, "y": 5, "width": 20, "height": 20})

    moved = client.put(
        f"{_BASE}/regions/{source_id}/words",
        json={"word_refs": [_live_ref(page, "one"), _live_ref(page, "two")]},
    )
    assert moved.status_code == 200, moved.text
    source_box_before = next(reg["box"] for reg in moved.json()["regions"] if reg["region_id"] == source_id)

    stolen = client.put(f"{_BASE}/regions/{target_id}/words", json={"word_refs": [_live_ref(page, "one")]})
    assert stolen.status_code == 200, stolen.text

    regions = {reg["region_id"]: reg for reg in stolen.json()["regions"] if reg["confirmed"]}
    assert regions[source_id]["box"] == source_box_before == {"x": 0, "y": 0, "width": 200, "height": 300}
    assert {w.text for w in _region_block_of(page, target_id).words} == {"one"}
    assert {w.text for w in _region_block_of(page, source_id).words} == {"two"}


def test_claiming_a_regions_last_word_does_not_erase_the_region(toolbar_loaded: Any) -> None:
    """The worst case of the same bug: with no words left, ``recompute_bounding_box``
    sets the source region's box to ``None``, and ``confirmed_regions_from_page``
    skips any block whose box is ``None``. The region then vanishes from
    ``PagePayload.regions`` while still living in the page blob — invisible on the
    canvas, undeletable through the UI, and still serialized on every save.
    """
    client, _ps, page = toolbar_loaded
    source_id = _make_region(client, role="poetry", box={"x": 0, "y": 0, "width": 200, "height": 300})
    target_id = _make_region(client, role="blockquote", box={"x": 5, "y": 5, "width": 20, "height": 20})

    client.put(f"{_BASE}/regions/{source_id}/words", json={"word_refs": [_live_ref(page, "one")]})
    stolen = client.put(f"{_BASE}/regions/{target_id}/words", json={"word_refs": [_live_ref(page, "one")]})
    assert stolen.status_code == 200, stolen.text

    source_view = next((reg for reg in stolen.json()["regions"] if reg["region_id"] == source_id), None)
    assert source_view is not None, "the emptied source region vanished from the payload"
    assert source_view["box"] == {"x": 0, "y": 0, "width": 200, "height": 300}
    assert _region_block_of(page, source_id).bounding_box is not None
    assert _region_block_of(page, source_id).words == []


def _region_block_of(page: Any, region_id: str) -> Any:
    from pdomain_ocr_labeler_spa.api.regions import find_region_block

    block = find_region_block(page, region_id)
    assert block is not None, f"region {region_id} is not on the page"
    return block


def test_membership_moves_the_named_word_not_an_equal_looking_twin(toolbar_loaded: Any) -> None:
    """``Block.remove_item`` tests ``item in self._items``, and ``Word`` is a plain
    dataclass, so that is value equality: ``list.remove`` drops the *first* equal
    word, not the one that was named. On a line holding two words with the same
    text and the same box — a real shape in OCR output — claiming the second one
    removed the first and handed the region the second, leaving one object in two
    places on the page and losing the other outright.
    """
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.word import Word

    client, _ps, page = toolbar_loaded
    twin_box = BoundingBox.from_ltrb(0, 0, 10, 10, is_normalized=False)
    line = page.lines[0]
    line.items = [Word(text="twin", bounding_box=twin_box), Word(text="twin", bounding_box=twin_box)]
    first, second = line.words[0], line.words[1]
    assert first == second and first is not second, "the two twins must be equal but distinct"

    region_id = _make_region(client, role="poetry", box={"x": 0, "y": 0, "width": 200, "height": 300})
    ref = {"line_index": page.lines.index(line), "word_index": 1}
    r = client.put(f"{_BASE}/regions/{region_id}/words", json={"word_refs": [ref]})
    assert r.status_code == 200, r.text

    region = _region_block_of(page, region_id)
    assert any(w is second for w in region.words), "the region did not get the word that was named"
    assert [w is first for w in line.words] == [True], "the line kept the wrong twin"
    assert sum(1 for w in page.words if w is first) == 1
    assert sum(1 for w in page.words if w is second) == 1


def test_creating_a_region_on_a_mixed_coordinate_page_names_the_real_problem(
    toolbar_loaded: Any,
) -> None:
    """``Page.is_content_normalized`` raises ``ValueError`` on a page that mixes
    normalized and pixel-space word boxes. Reading it inside the role-validation
    catch reported that as ``invalid_region_role``, which names the wrong cause;
    reading it outside any catch (what ``edit_region`` did) turned it into a 500.
    """
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.word import Word

    client, _ps, page = toolbar_loaded
    page.lines[1].items = [
        Word(text="norm", bounding_box=BoundingBox.from_ltrb(0, 0, 0.5, 0.5, is_normalized=True))
    ]

    created = client.post(
        f"{_BASE}/regions", json={"role": "poetry", "box": {"x": 5, "y": 5, "width": 50, "height": 50}}
    )
    assert created.status_code == 400, created.text
    assert created.json()["error"] == "mixed_page_coordinates"


def test_editing_a_regions_box_on_a_mixed_coordinate_page_reports_400_not_500(
    toolbar_loaded: Any,
) -> None:
    """``edit_region`` read ``page.is_content_normalized`` outside the catch its
    sibling read it inside, so the same page 500'd from one route and 400'd from
    the other. Both now report the real problem.
    """
    from pdomain_book_contracts.geometry.bounding_box import BoundingBox
    from pdomain_book_tools.ocr.word import Word

    client, _ps, page = toolbar_loaded
    region_id = _make_region(client, role="poetry", box={"x": 0, "y": 0, "width": 50, "height": 50})
    page.lines[1].items = [
        Word(text="norm", bounding_box=BoundingBox.from_ltrb(0, 0, 0.5, 0.5, is_normalized=True))
    ]

    edited = client.patch(
        f"{_BASE}/regions/{region_id}", json={"box": {"x": 1, "y": 1, "width": 10, "height": 10}}
    )
    assert edited.status_code == 400, edited.text
    assert edited.json()["error"] == "mixed_page_coordinates"

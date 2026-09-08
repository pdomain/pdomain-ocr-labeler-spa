"""Conformance: block_role_labels and override_page_sort_order round-trip on Block.

Pins the property the region-provenance design leans on to justify storing
confirmed regions as ``Block`` objects rather than a new sidecar: a role label
and an explicit sort order both survive ``to_dict`` / ``from_dict``. A future
``Block`` refactor that drops either field breaks this fixture, not a
downstream region test three layers away.
"""

from __future__ import annotations

import json
from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "region_block_round_trip.json"


def test_block_role_labels_and_sort_order_round_trip() -> None:
    from pdomain_book_tools.ocr.block import Block

    raw = json.loads(_FIXTURE.read_text())
    block = Block.from_dict(raw)

    assert block.block_role_labels == ["poetry"]
    assert block.override_page_sort_order == 3
    assert block.additional_block_attributes.get("region_id") == "fixture-region-1"

    round_tripped = Block.from_dict(block.to_dict())
    assert round_tripped.block_role_labels == ["poetry"]
    assert round_tripped.override_page_sort_order == 3
    assert round_tripped.additional_block_attributes.get("region_id") == "fixture-region-1"


def test_the_fixture_round_trips_to_an_identical_document() -> None:
    """Guards the fixture against silent hand-editing, and ``Block`` against
    quietly dropping or renaming *any* field — not just the three this suite
    reads. The whole ``to_dict()`` is compared, key for key; the previous
    version checked three keys while its name promised the golden document.
    """
    from pdomain_book_tools.ocr.block import Block

    raw = json.loads(_FIXTURE.read_text())

    assert Block.from_dict(raw).to_dict() == raw

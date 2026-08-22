"""Unit tests for content-blob labeler sidecar helpers (Wave 0.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pdomain_ocr_labeler_spa.core.labeler_sidecars import (
    LABELER_SIDECARS_KEY,
    LabelerSidecars,
    apply_sidecars_to_page_state,
    content_dict_with_sidecars,
    parse_content_blob,
    sidecars_from_page,
    stamp_sidecars_on_page,
)


@dataclass
class _FakePage:
    text: str = "x"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Page", "label": self.text}


@dataclass
class _FakePageState:
    char_ranges_map: dict[str, object] = field(default_factory=dict)
    char_bboxes_map: dict[str, object] = field(default_factory=dict)


def test_content_dict_embeds_nonempty_sidecars() -> None:
    sidecars = LabelerSidecars(
        char_ranges_map={"0_0": [{"start": 0, "end": 1, "styles": ["bold"]}]},
        char_bboxes_map={"0_0": [{"x": 1, "y": 2, "width": 3, "height": 4}]},
    )
    content = content_dict_with_sidecars(_FakePage(), sidecars)
    assert content["type"] == "Page"
    assert content[LABELER_SIDECARS_KEY]["char_ranges_map"]["0_0"][0]["styles"] == ["bold"]
    assert content[LABELER_SIDECARS_KEY]["char_bboxes_map"]["0_0"][0]["width"] == 3


def test_content_dict_omits_key_when_sidecars_empty() -> None:
    content = content_dict_with_sidecars(_FakePage(), LabelerSidecars())
    assert LABELER_SIDECARS_KEY not in content


def test_parse_content_blob_round_trip() -> None:
    sidecars = LabelerSidecars(
        char_ranges_map={"1_2": [{"start": 0, "end": 2, "styles": []}]},
        logical_page_id="bd9e9b33-2c33-53f2-ac8f-a532c5c1686d",
    )
    raw = content_dict_with_sidecars(_FakePage("p"), sidecars)
    import json

    page_dict, extracted = parse_content_blob(json.dumps(raw).encode("utf-8"))
    assert page_dict["label"] == "p"
    assert extracted.char_ranges_map == sidecars.char_ranges_map
    assert extracted.char_bboxes_map == {}
    assert extracted.logical_page_id == sidecars.logical_page_id


def test_from_page_state_and_apply() -> None:
    pstate = _FakePageState()
    pstate.char_ranges_map = {"0_0": [{"start": 0, "end": 1, "styles": ["italic"]}]}
    snap = LabelerSidecars.from_page_state(pstate)
    other = _FakePageState()
    other.char_bboxes_map = {"stale": []}
    apply_sidecars_to_page_state(other, snap)
    assert other.char_ranges_map == {"0_0": [{"start": 0, "end": 1, "styles": ["italic"]}]}
    assert other.char_bboxes_map == {}
    # Mutating the applied map must not mutate the snapshot source.
    other.char_ranges_map["0_0"] = []
    assert pstate.char_ranges_map["0_0"][0]["styles"] == ["italic"]


def test_stamp_and_read_on_page() -> None:
    page = _FakePage()
    sidecars = LabelerSidecars(char_bboxes_map={"0_1": []})
    stamp_sidecars_on_page(page, sidecars)
    assert sidecars_from_page(page) is sidecars

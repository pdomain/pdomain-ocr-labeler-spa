from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.labeler_sidecars import (
    LabelerSidecars,
    LegacyTypographyPayloadError,
)
from pdomain_ocr_labeler_spa.core.models import WordMatch


def test_openapi_contains_no_legacy_char_range_route_or_schema() -> None:
    schema = build_app().openapi()

    assert not any("char-ranges" in path for path in schema["paths"])
    assert "CharRange" not in schema["components"]["schemas"]
    assert "SetCharRangesRequest" not in schema["components"]["schemas"]


def test_word_match_rejects_legacy_char_ranges_payload() -> None:
    with pytest.raises(ValidationError):
        WordMatch.model_validate(
            {
                "line_index": 0,
                "word_index": 0,
                "ocr_text": "Word",
                "ground_truth_text": "Word",
                "match_status": "exact",
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
                "char_ranges": [{"start": 0, "end": 1, "styles": ["italic"]}],
            }
        )


def test_labeler_sidecars_reject_legacy_char_ranges_map() -> None:
    with pytest.raises(ValueError, match="char_ranges_map"):
        LabelerSidecars.from_content_dict(
            {"labeler_sidecars": {"char_ranges_map": {"0_0": [{"start": 0, "end": 1, "styles": ["italic"]}]}}}
        )


def test_store_reload_propagates_legacy_char_ranges_rejection() -> None:
    payload = json.dumps({"labeler_sidecars": {"char_ranges_map": {"0_0": []}}}).encode()
    provenance = SimpleNamespace(
        head_id="head",
        nodes={"head": SimpleNamespace(blob_refs=("blob",))},
    )
    store = SimpleNamespace(
        get_page=lambda _page_id: SimpleNamespace(record=SimpleNamespace(provenance=provenance)),
        blobs=SimpleNamespace(read=lambda _blob_ref: payload),
    )

    with pytest.raises(LegacyTypographyPayloadError, match="char_ranges_map"):
        load_page_from_store(store, "page-id")

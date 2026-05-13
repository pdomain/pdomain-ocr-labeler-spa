"""Tests for core/models.py domain models — issue #181."""

from __future__ import annotations

import pytest

from pd_ocr_labeler_spa.core.models import EncodedDims, MatchStatus


class TestMatchStatus:
    def test_has_exactly_five_values(self) -> None:
        assert len(MatchStatus) == 5

    def test_values_match_legacy_enum(self) -> None:
        values = {m.value for m in MatchStatus}
        assert values == {"exact", "fuzzy", "mismatch", "unmatched_ocr", "unmatched_gt"}

    def test_is_str_enum(self) -> None:
        assert isinstance(MatchStatus.EXACT, str)
        assert MatchStatus.EXACT == "exact"


@pytest.mark.parametrize(
    "src_width, src_height, exp_display_width, exp_display_height, exp_scale",
    [
        (1200, 1600, 1200, 1600, 1.0),
        (2400, 3200, 1200, 1600, 0.5),
        (800, 1000, 800, 1000, 1.0),
        (1800, 2700, 1200, 1800, 1200 / 1800),
        (600, 900, 600, 900, 1.0),
        (3000, 4000, 1200, 1600, 0.4),
    ],
)
def test_encoded_dims_from_source_dims(
    src_width: int,
    src_height: int,
    exp_display_width: int,
    exp_display_height: int,
    exp_scale: float,
) -> None:
    dims = EncodedDims.from_source_dims(src_width, src_height)
    assert dims.src_width == src_width
    assert dims.src_height == src_height
    assert dims.display_width == exp_display_width
    assert dims.display_height == exp_display_height
    assert dims.scale == pytest.approx(exp_scale)

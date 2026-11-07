"""GT input must reject presentation-form ligatures and long-s.

Focused unit coverage for the UpdateWordGroundTruthRequest validator.
HTTP coverage also lives in tests/integration/test_text_norm_config.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pdomain_ocr_labeler_spa.api.words import UpdateWordGroundTruthRequest


@pytest.mark.parametrize(
    "text",
    [
        "\ufb01ne",  # U+FB01 fi ligature
        "a\u017fb",  # U+017F long-s
        "\ufb00oo",  # U+FB00 ff
        "\ufb02y",  # U+FB02 fl
    ],
)
def test_gt_request_rejects_forbidden_codepoints(text: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        UpdateWordGroundTruthRequest(text=text)
    assert "forbidden" in str(exc_info.value).lower()


def test_gt_request_accepts_ascii_clean_text() -> None:
    req = UpdateWordGroundTruthRequest(text="fine action")
    assert req.text == "fine action"

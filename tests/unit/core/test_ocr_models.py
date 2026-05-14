"""Pin OCR config DTO shapes against ``docs/architecture/01-data-models.md`` §OCR.

These models are M3 prerequisites — ``GET /api/ocr-config`` /
``POST /api/ocr-config/models`` / ``POST /api/ocr-config/rescan`` all
key on them. Shipping the typed shells now (no router yet) lets the
M3 router land as a thin wiring slice without re-deriving the schema.

Spec authority: ``docs/architecture/01-data-models.md`` lines 377-400 (commit
``c49f14f``-era; see line numbers in each test for the exact
field/option being pinned).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pd_ocr_labeler_spa.core.ocr_models import (
    GetOCRConfigResponse,
    OCRModelOption,
    SetOCRModelsRequest,
)


class TestOCRModelOption:
    """Spec §01-data-models.md lines 377-383."""

    def test_minimal_stock_option(self) -> None:
        opt = OCRModelOption(key="stock", label="Stock", source="stock")
        assert opt.key == "stock"
        assert opt.revision is None
        assert opt.is_default is False
        assert opt.weights_id is None

    def test_huggingface_option_with_revision(self) -> None:
        opt = OCRModelOption(
            key="hf:my/model",
            label="my/model",
            source="huggingface",
            revision="abc123",
            is_default=True,
            weights_id="sha256:deadbeef",
        )
        assert opt.source == "huggingface"
        assert opt.revision == "abc123"
        assert opt.is_default is True

    def test_local_option(self) -> None:
        opt = OCRModelOption(
            key="local:/tmp/foo.pt",
            label="foo.pt",
            source="local",
        )
        assert opt.source == "local"

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OCRModelOption(key="x", label="x", source="bogus")  # type: ignore[arg-type]

    def test_extras_forbidden(self) -> None:
        # Top-level envelope per spec §01-data-models.md line 15 ⇒
        # ``extra="forbid"``. (D-003 extras-tolerance carve-out is
        # session_state.json-only, not OCR config.)
        with pytest.raises(ValidationError):
            OCRModelOption(  # type: ignore[call-arg]
                key="x", label="x", source="stock", extra_field="nope"
            )


class TestGetOCRConfigResponse:
    """Spec §01-data-models.md lines 385-396."""

    def _opt(self, key: str = "stock") -> OCRModelOption:
        return OCRModelOption(key=key, label=key, source="stock")

    def test_minimal_response(self) -> None:
        resp = GetOCRConfigResponse(
            detection_options=[self._opt("d-stock")],
            recognition_options=[self._opt("r-stock")],
            selected_detection="d-stock",
            selected_recognition="r-stock",
            hf_pinned_revision=None,
            selection_reason="stock-fallback",
        )
        assert resp.selected_detection == "d-stock"
        assert resp.hf_pinned_revision is None

    @pytest.mark.parametrize(
        "reason",
        [
            "hf-latest",
            "hf-only",
            "local-newer-than-hf",
            "local-only-hf-unreachable",
            "hf-unreachable-no-local",
            "stock-fallback",
        ],
    )
    def test_all_selection_reasons_accepted(self, reason: str) -> None:
        resp = GetOCRConfigResponse(
            detection_options=[self._opt()],
            recognition_options=[self._opt()],
            selected_detection="stock",
            selected_recognition="stock",
            hf_pinned_revision=None,
            selection_reason=reason,  # type: ignore[arg-type]
        )
        assert resp.selection_reason == reason

    def test_invalid_selection_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GetOCRConfigResponse(
                detection_options=[self._opt()],
                recognition_options=[self._opt()],
                selected_detection="stock",
                selected_recognition="stock",
                hf_pinned_revision=None,
                selection_reason="bogus",  # type: ignore[arg-type]
            )


class TestSetOCRModelsRequest:
    """Spec §01-data-models.md lines 397-400."""

    def test_minimal(self) -> None:
        req = SetOCRModelsRequest(
            detection_key="hf:det",
            recognition_key="hf:reco",
        )
        assert req.detection_key == "hf:det"
        assert req.hf_pinned_revision is None

    def test_pinned_revision(self) -> None:
        req = SetOCRModelsRequest(
            detection_key="hf:det",
            recognition_key="hf:reco",
            hf_pinned_revision="v2",
        )
        assert req.hf_pinned_revision == "v2"

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            SetOCRModelsRequest(detection_key="x")  # type: ignore[call-arg]

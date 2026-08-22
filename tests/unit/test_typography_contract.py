from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pdomain_book_tools.typography import (
    GRAPHEME_SEGMENTATION_VERSION,
    REVIEW_CONTRACT_VERSION,
)

from pdomain_ocr_labeler_spa.api.typography import install_typography_router


def test_typography_contract_versions_and_openapi_types() -> None:
    app = FastAPI()
    install_typography_router(app)

    response = TestClient(app).get("/api/typography/contract")
    assert response.status_code == 200
    assert response.json()["review_contract_version"] == REVIEW_CONTRACT_VERSION
    assert response.json()["grapheme_map_version"] == GRAPHEME_SEGMENTATION_VERSION

    schemas = app.openapi()["components"]["schemas"]
    assert "WordTypography" in schemas
    assert "TypographyCorrection" in schemas
    assert schemas["WordTypography"]["properties"]["label_states"] == {
        "$ref": "#/components/schemas/LabelStates"
    }
    assert schemas["LabelStates"]["additionalProperties"]["enum"] == [
        "unknown",
        "positive",
        "negative",
    ]

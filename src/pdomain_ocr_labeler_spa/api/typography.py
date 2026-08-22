"""Portable typography review contract exposed through FastAPI/OpenAPI."""

from __future__ import annotations

from typing import ClassVar, Literal

from fastapi import APIRouter, FastAPI
from pdomain_book_tools.typography import (
    GRAPHEME_SEGMENTATION_VERSION,
    REVIEW_CONTRACT_VERSION,
    TypographyCorrection,
    WordTypography,
)
from pydantic import BaseModel, ConfigDict, RootModel

router = APIRouter(prefix="/api/typography", tags=["typography"])


class LabelStates(RootModel[dict[str, Literal["unknown", "positive", "negative"]]]):
    """Exact tri-state map retained by FastAPI's OpenAPI compatibility pass."""


class TypographyContractDescriptor(BaseModel):
    """Runtime descriptor plus nullable fields that publish canonical schemas."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    review_contract_version: str
    grapheme_map_version: str
    label_states_schema: LabelStates | None = None
    word_typography: WordTypography | None = None
    correction: TypographyCorrection | None = None


@router.get("/contract", response_model=TypographyContractDescriptor)
def get_typography_contract() -> TypographyContractDescriptor:
    """Return released contract versions and expose its types in OpenAPI."""
    return TypographyContractDescriptor(
        review_contract_version=REVIEW_CONTRACT_VERSION,
        grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
    )


def install_typography_router(app: FastAPI) -> None:
    """Register the portable typography contract router."""
    app.include_router(router)
    original_openapi = app.openapi

    def enum_preserving_openapi() -> dict[str, object]:
        schema = original_openapi()
        components = schema.get("components")
        if isinstance(components, dict):
            schemas = components.get("schemas")
            if isinstance(schemas, dict):
                word_schema = schemas.get("WordTypography")
                if isinstance(word_schema, dict):
                    properties = word_schema.get("properties")
                    if isinstance(properties, dict):
                        properties["label_states"] = {"$ref": "#/components/schemas/LabelStates"}
        return schema

    app.openapi = enum_preserving_openapi  # type: ignore[method-assign]


__all__ = ["TypographyContractDescriptor", "install_typography_router"]

"""Shared page lifecycle types must not be exported from core.models."""

import pytest


@pytest.mark.parametrize("name", ["PageRecord", "RotationSource"])
def test_models_does_not_export_shared_page_lifecycle_type(name: str) -> None:
    import pdomain_ocr_labeler_spa.core.models as m

    assert not hasattr(m, name)

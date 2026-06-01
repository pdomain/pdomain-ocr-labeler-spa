"""Verify LabelerPageStore is wired into app.state via page_store_factory."""

import pytest

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings


@pytest.mark.integration
def test_app_state_has_page_store_factory(tmp_path) -> None:
    settings = Settings(
        host="127.0.0.1",
        port=8000,
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
    )
    app = build_app(settings)
    # The app must expose a page_store_factory on app.state after build
    assert hasattr(app.state, "page_store_factory")

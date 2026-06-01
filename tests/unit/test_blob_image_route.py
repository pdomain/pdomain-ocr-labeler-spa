"""Test that /api/blobs/{hash} serves blob bytes from the BlobStore."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings


@pytest.mark.integration
def test_blob_image_route_returns_image_bytes(tmp_path: Path) -> None:
    settings = Settings(
        host="127.0.0.1",
        port=8000,
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
    )
    app = build_app(settings)
    # Pre-load a blob
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    store = LabelerPageStore(project_dir=project_dir)
    fake_image = b"\x89PNG\r\n\x1a\n fake content"
    blob_hash = store.blobs.write(fake_image)
    app.state.page_store = store

    with TestClient(app) as client:
        resp = client.get(f"/api/blobs/{blob_hash}")
        assert resp.status_code == 200
        assert resp.content == fake_image

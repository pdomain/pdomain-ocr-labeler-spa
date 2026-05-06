"""Shared pytest fixtures for ``pd-ocr-labeler-spa``.

Per ``specs/02-backend.md §14``:

- ``settings`` builds a hermetic ``Settings`` rooted at ``tmp_path`` so
  filesystem storage / cache / config never escape the test sandbox.
- ``client`` is ``TestClient(build_app(settings))`` as a context manager
  so lifespan startup/shutdown run.

M0 only exercises ``/healthz`` and the in-process ``Settings``. As later
milestones add adapters and an ``AppState`` startup hook, this fixture
graph grows in step.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = build_app(settings)
    with TestClient(app) as c:
        yield c

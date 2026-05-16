"""Shared pytest fixtures for ``pd-ocr-labeler-spa``.

Per ``docs/architecture/02-backend.md §14``:

- ``settings`` builds a hermetic ``Settings`` rooted at ``tmp_path`` so
  filesystem storage / cache / config never escape the test sandbox.
- ``client`` is ``TestClient(build_app(settings))`` as a context manager
  so lifespan startup/shutdown run.

M0 only exercises ``/healthz`` and the in-process ``Settings``. As later
milestones add adapters and an ``AppState`` startup hook, this fixture
graph grows in step.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _has_gpu_available() -> bool:
    """Check if GPU is available on the system."""
    try:
        import torch

        return torch.cuda.is_available()
    except (ImportError, RuntimeError):
        return False


@pytest.fixture
def gpu_available() -> bool:
    """True if a CUDA GPU is available on the system."""
    return _has_gpu_available()


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


@pytest.fixture
def v22_envelope_str() -> str:
    """A minimal v2.2 envelope JSON string with three words carrying
    all three tri-state ``glyph_annotations`` values:

    - word 0: ``null`` (no annotation)
    - word 1: ``{"long_s_positions": []}`` (annotated, no positions)
    - word 2: ``{"long_s_positions": [3], "source": "human"}`` (annotated, human-confirmed)

    The ``payload.page`` uses the flattened SPA ``lines``/``words`` dict
    shape so the round-trip test can walk the structure without importing
    pd_book_tools.
    """
    envelope: dict = {
        "schema": {
            "name": "pd_ocr_labeler.user_page",
            "version": "2.2",
        },
        "provenance": {
            "saved_at": "2026-05-16T00:00:00.000Z",
            "saved_by": "Save Page",
            "source_lane": "labeled",
            "app": {"name": "pd_ocr_labeler_spa", "version": "0.1.0"},
            "toolchain": {"python": "3.13.1", "pd_book_tools": "0.5.1"},
            "ocr": {"engine": "doctr", "models": []},
        },
        "source": {
            "project_id": "v22-round-trip",
            "page_index": 0,
            "page_number": 1,
            "image_path": "001.png",
            "rotation_degrees": 90,
            "rotation_source": "user",
        },
        "payload": {
            "page": {
                "type": "Page",
                "page_index": 0,
                "width": 1240,
                "height": 1754,
                "lines": [
                    {
                        "words": [
                            {
                                "ocr_text": "the",
                                "confidence": 0.95,
                                "glyph_annotations": None,
                            },
                            {
                                "ocr_text": "long",
                                "confidence": 0.90,
                                "glyph_annotations": {"long_s_positions": []},
                            },
                            {
                                "ocr_text": "sword",
                                "confidence": 0.88,
                                "glyph_annotations": {
                                    "long_s_positions": [3],
                                    "source": "human",
                                },
                            },
                        ]
                    }
                ],
            }
        },
    }
    return json.dumps(envelope)

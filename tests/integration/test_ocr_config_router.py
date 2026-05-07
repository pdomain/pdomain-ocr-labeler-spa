"""M3 slice 8a acceptance: ``api/ocr_config.py`` router skeleton wires
the iter-7 OCR config DTOs into the public HTTP surface.

Spec authority:

- ``specs/02-backend.md §5.8`` lines 317-322 — endpoint contracts
  (``GET /api/ocr-config``, ``POST /api/ocr-config/models``,
  ``POST /api/ocr-config/rescan``).
- ``specs/01-data-models.md §`` lines 374-400 — wire shapes
  (``OCRModelOption``, ``GetOCRConfigResponse``,
  ``SetOCRModelsRequest``).

What slice 8a ships under TDD:

1. ``GET /api/ocr-config`` returns a ``GetOCRConfigResponse``-shaped
   payload composed from the iter-7 DTOs. No actual model loading,
   HuggingFace probe, or local weights scan happens yet — that's
   slice 8b+ work that goes through ``core/page_state.ensure_page_model``
   and the ``IOCREngine`` adapter. Slice 8a hardcodes a single
   ``stock`` option for both detection and recognition lists, with
   ``selection_reason="stock-fallback"`` per the spec literal set.
   This composes the iter-7 DTO foundation so future slices can swap
   the body without changing the route shape or its tests.

2. The route is ``include_in_schema=True`` because OpenAPI export
   (``make openapi-export``) drives the frontend ``types.ts``; it must
   surface so the SPA's ``src/api/types.ts`` regenerates.

Slice 8a deliberately does NOT:

- Implement ``POST /api/ocr-config/models`` or
  ``POST /api/ocr-config/rescan`` — those mutate selection state
  which doesn't exist yet (no ``OCRConfigCarrier`` / no persistent
  ``ocr_config.json`` writeback). Slice 8b+ work.
- Touch the ``IOCREngine`` adapter. The provenance string
  ``"stock-fallback"`` is honest in slice 8a — no HF probe, no local
  scan, so the only legitimate reason is "we fell back to bundled
  stock weights." When slice 8b+ wire real probing, the response body
  will start emitting other ``selection_reason`` values; the route
  shape and tests below stay valid.
- Persist a selection. The route is read-only in slice 8a.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


# ──────────────────────────────────────────────────────────────────────
# GET /api/ocr-config
# ──────────────────────────────────────────────────────────────────────


def test_get_ocr_config_returns_200(client: TestClient) -> None:
    """The route exists at the spec-canonical URL."""
    resp = client.get("/api/ocr-config")
    assert resp.status_code == 200, resp.text


def test_get_ocr_config_payload_validates_against_dto(client: TestClient) -> None:
    """Response body parses cleanly into ``GetOCRConfigResponse``.

    This is the first-line spec contract: anything that doesn't validate
    against the iter-7 DTO is a wire-shape break.
    """
    from pd_ocr_labeler_spa.core.ocr_models import GetOCRConfigResponse

    resp = client.get("/api/ocr-config")
    parsed = GetOCRConfigResponse.model_validate(resp.json())
    # Spec-mandated invariants:
    assert isinstance(parsed.detection_options, list)
    assert isinstance(parsed.recognition_options, list)
    assert parsed.selected_detection
    assert parsed.selected_recognition


def test_get_ocr_config_slice8a_stock_fallback(client: TestClient) -> None:
    """Slice 8a body is honest: only stock options, ``stock-fallback`` reason.

    Per the slice-8a docstring, no real probing happens yet, so the
    only legitimate ``selection_reason`` is ``"stock-fallback"``. When
    slice 8b+ wire real HF / local discovery, this test gets retired
    or relaxed — but until then, drift toward fake-discovery output
    would be a regression.
    """
    resp = client.get("/api/ocr-config")
    body = resp.json()
    assert body["selection_reason"] == "stock-fallback"
    # The selected key for both lists points into the options list of
    # the same kind — the modal can't render a selection that doesn't
    # exist as an option.
    det_keys = {opt["key"] for opt in body["detection_options"]}
    rec_keys = {opt["key"] for opt in body["recognition_options"]}
    assert body["selected_detection"] in det_keys
    assert body["selected_recognition"] in rec_keys


def test_get_ocr_config_options_are_stock_sourced(client: TestClient) -> None:
    """Every option in slice 8a has ``source="stock"``.

    Same scope reason as ``test_get_ocr_config_slice8a_stock_fallback``:
    no HF probe / no local scan → no ``"huggingface"`` or ``"local"``
    options can legitimately appear.
    """
    resp = client.get("/api/ocr-config")
    body = resp.json()
    for opt in body["detection_options"] + body["recognition_options"]:
        assert opt["source"] == "stock", opt


def test_get_ocr_config_hf_pinned_revision_unset(client: TestClient) -> None:
    """``hf_pinned_revision`` is ``None`` when no HF model is selected.

    Spec line 390 declares the field ``str | None``; with stock-only
    options there's no HF revision to surface. Future slices that
    surface a default HF model would emit a real revision string
    here — until then, ``None`` is the only honest value.
    """
    resp = client.get("/api/ocr-config")
    body = resp.json()
    assert body["hf_pinned_revision"] is None


def test_get_ocr_config_appears_in_openapi_schema(client: TestClient) -> None:
    """``GET /api/ocr-config`` surfaces in OpenAPI for ``types.ts`` gen.

    ``make openapi-export`` walks the OpenAPI doc to emit
    ``frontend/src/api/types.ts``; an accidentally
    ``include_in_schema=False`` route would silently break the SPA's
    types contract.
    """
    spec = client.get("/openapi.json").json()
    assert "/api/ocr-config" in spec["paths"]
    assert "get" in spec["paths"]["/api/ocr-config"]

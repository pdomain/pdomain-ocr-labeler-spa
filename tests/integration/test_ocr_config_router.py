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


# ──────────────────────────────────────────────────────────────────────
# POST /api/ocr-config/models — slice 8c-i (stateless echo)
# ──────────────────────────────────────────────────────────────────────
#
# Slice 8c-i ships the route shape — same DTO contract as GET — but
# without a persistent OCRConfigCarrier yet. The handler validates
# requested keys against the slice-8a stock-fallback option lists and
# echoes a GetOCRConfigResponse with ``selected_*`` set from the
# request body. Unknown keys → 400. ``selection_reason`` stays
# ``"stock-fallback"`` because no real probing exists yet (slice 8c-ii+
# work). When carrier-backed selection state lands, this test file gets
# extended to verify persistence; the route shape stays the same.


def test_post_ocr_config_models_returns_200_for_known_keys(client: TestClient) -> None:
    """The route exists at the spec-canonical URL and accepts the
    iter-7 ``SetOCRModelsRequest`` body."""
    resp = client.post(
        "/api/ocr-config/models",
        json={
            "detection_key": "stock",
            "recognition_key": "stock",
            "hf_pinned_revision": None,
        },
    )
    assert resp.status_code == 200, resp.text


def test_post_ocr_config_models_response_validates_against_dto(
    client: TestClient,
) -> None:
    """Response body parses cleanly into ``GetOCRConfigResponse``.

    Spec §5.8 line 320 declares the POST returns the same DTO as GET so
    the frontend can refresh from a single shape.
    """
    from pd_ocr_labeler_spa.core.ocr_models import GetOCRConfigResponse

    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "stock", "recognition_key": "stock"},
    )
    parsed = GetOCRConfigResponse.model_validate(resp.json())
    assert parsed.selected_detection == "stock"
    assert parsed.selected_recognition == "stock"


def test_post_ocr_config_models_echoes_selected_keys(client: TestClient) -> None:
    """``selected_detection`` and ``selected_recognition`` reflect the
    request body, not a hardcoded default. Future slices that add
    non-stock options must keep this round-trip property."""
    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "stock", "recognition_key": "stock"},
    )
    body = resp.json()
    assert body["selected_detection"] == "stock"
    assert body["selected_recognition"] == "stock"


def test_post_ocr_config_models_unknown_detection_key_returns_400(
    client: TestClient,
) -> None:
    """Unknown detection key → 400 — slice 8a's stock-only option list
    means anything else is a contract violation. Future slices that
    discover real models will widen the accept-set; this test gets
    relaxed when that lands."""
    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "hf:unknown", "recognition_key": "stock"},
    )
    assert resp.status_code == 400, resp.text


def test_post_ocr_config_models_unknown_recognition_key_returns_400(
    client: TestClient,
) -> None:
    """Unknown recognition key → 400 — same reasoning as detection."""
    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "stock", "recognition_key": "local:/no/such"},
    )
    assert resp.status_code == 400, resp.text


def test_post_ocr_config_models_extra_field_rejected_with_validation_error(
    client: TestClient,
) -> None:
    """``SetOCRModelsRequest`` is ``extra="forbid"`` — a stray key
    surfaces through the project's validation_error envelope (HTTP 400
    with ``error="validation_error"``, ``details[*].type=="extra_forbidden"``).
    The status code is 400 rather than the FastAPI default 422 because
    the app installs a unified validation-error handler — see
    ``api/middleware/validation_error.py`` (or equivalent). Pins the
    iter-7 DTO contract end-to-end through the route."""
    resp = client.post(
        "/api/ocr-config/models",
        json={
            "detection_key": "stock",
            "recognition_key": "stock",
            "rogue_field": "nope",
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "validation_error"
    types = {d["type"] for d in body["details"]}
    assert "extra_forbidden" in types


def test_post_ocr_config_models_slice8c_i_keeps_stock_fallback_reason(
    client: TestClient,
) -> None:
    """Until real probing exists (slice 8c-ii+), ``selection_reason``
    must stay ``"stock-fallback"``. A drift to e.g. ``"hf-latest"``
    here would be dishonest — there's no HF probe behind it."""
    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "stock", "recognition_key": "stock"},
    )
    body = resp.json()
    assert body["selection_reason"] == "stock-fallback"


def test_post_ocr_config_models_appears_in_openapi_schema(
    client: TestClient,
) -> None:
    """``POST /api/ocr-config/models`` surfaces in OpenAPI so
    ``make openapi-export`` regenerates ``types.ts``. Without this,
    the frontend mutation hook can't be typed against the same DTO.
    """
    spec = client.get("/openapi.json").json()
    assert "/api/ocr-config/models" in spec["paths"]
    assert "post" in spec["paths"]["/api/ocr-config/models"]

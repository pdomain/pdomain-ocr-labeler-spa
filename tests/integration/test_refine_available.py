"""Integration tests for ``GET /api/refine/available`` capability probe.

CU-6.1 acceptance test: the probe endpoint exists, returns 200, and includes
capability flags that the frontend ErasePixelsSection reads to gate its Apply
button.

Spec authority:
- ``src/pdomain_ocr_labeler_spa/api/refine.py`` — ``RefineAvailableResponse`` shape.
- ``docs/hifi-followons.md #FO-9`` — ErasePixelsSection capability probe.

The endpoint returns ``{ available: bool, reason: str }`` — *not* the
per-feature ``{ erase_pixels, refine_bboxes }`` split described in the CU-6.1
task template.  The existing ``RefineAvailableResponse`` model predates that
template and is already wired end-to-end; changing the schema would break the
existing frontend hook.  This file tests the actual contract.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Bare client — no project loaded, probe must work without one."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


# ── CU-6.1 acceptance tests ───────────────────────────────────────────────────


def test_refine_available_returns_200(client: TestClient) -> None:
    """Probe always returns 200 regardless of whether a project is loaded."""
    resp = client.get("/api/refine/available")
    assert resp.status_code == 200


def test_refine_available_returns_capability_flags(client: TestClient) -> None:
    """Response must include ``available`` bool and ``reason`` string.

    The frontend ``useRefineAvailable`` hook reads ``available`` to decide
    whether to enable the ErasePixelsSection Apply button (FO-9).
    """
    resp = client.get("/api/refine/available")
    assert resp.status_code == 200
    body = resp.json()
    # Both fields must be present.
    assert "available" in body, f"missing 'available' in {body}"
    assert "reason" in body, f"missing 'reason' in {body}"
    # Type checks.
    assert isinstance(body["available"], bool)
    assert isinstance(body["reason"], str)


def test_refine_available_returns_true(client: TestClient) -> None:
    """Lane A / Task A1: the refine_bboxes handler is now registered, so the
    capability probe reports ``available=True`` with an empty reason.

    Before A1 this returned ``False`` (handler unregistered). Flipping the
    probe lets ``ErasePixelsSection`` enable its Apply button (FO-9).
    """
    resp = client.get("/api/refine/available")
    body = resp.json()
    assert body["available"] is True
    assert body["reason"] == "", f"reason should be empty when available; got {body['reason']!r}"


def test_refine_available_no_project_required(client: TestClient) -> None:
    """The probe must respond without a project loaded (bare client fixture)."""
    # No /api/projects/load call made — probe should still return 200.
    resp = client.get("/api/refine/available")
    assert resp.status_code == 200
    body = resp.json()
    assert "available" in body

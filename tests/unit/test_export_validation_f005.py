"""F-005 — Export request contradictory-mode + page-index validation tests.

Spec authority: GH issue #410.

Problem:
- ``detection_only=True`` AND ``recognition_only=True`` disables both outputs
  while the API reports success.
- Negative ``page_index`` for ``scope="current"`` silently produces no output.
- ``scope="all_validated"`` with a ``page_index`` supplied is contradictory and
  should be rejected.

Fix: Pydantic ``@model_validator(mode='after')`` checks added to
``ExportRequest``.

Issue: ConcaveTrillion/pd-ocr-labeler-spa#410.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Slice 1 — failing tests (red before fix)
# ---------------------------------------------------------------------------


class TestMutuallyExclusiveModes:
    """detection_only and recognition_only cannot both be True."""

    def test_both_detection_and_recognition_only_rejected(self, client: TestClient) -> None:
        """detection_only=True AND recognition_only=True must return 400.

        When both are True, ``detection = not recognition_only`` and
        ``recognition = not detection_only`` both evaluate to False, producing
        no output while the API claims success. This is a nonsensical request.
        """
        resp = client.post(
            "/api/projects/test-project/export",
            json={
                "scope": "all_validated",
                "detection_only": True,
                "recognition_only": True,
            },
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body.get("error") == "validation_error"

    def test_detection_only_alone_accepted(self, client: TestClient) -> None:
        """detection_only=True alone (recognition_only=False) is valid."""
        resp = client.post(
            "/api/projects/test-project/export",
            json={
                "scope": "all_validated",
                "detection_only": True,
                "recognition_only": False,
            },
        )
        assert resp.status_code == 202, resp.text

    def test_recognition_only_alone_accepted(self, client: TestClient) -> None:
        """recognition_only=True alone (detection_only=False) is valid."""
        resp = client.post(
            "/api/projects/test-project/export",
            json={
                "scope": "all_validated",
                "detection_only": False,
                "recognition_only": True,
            },
        )
        assert resp.status_code == 202, resp.text

    def test_neither_mode_flag_accepted(self, client: TestClient) -> None:
        """Both flags False (default) — valid, exports both detection and recognition."""
        resp = client.post(
            "/api/projects/test-project/export",
            json={"scope": "all_validated"},
        )
        assert resp.status_code == 202, resp.text


class TestPageIndexBounds:
    """page_index must be non-negative when scope=='current'."""

    def test_negative_page_index_rejected(self, client: TestClient) -> None:
        """scope='current' with page_index=-1 must return 400.

        The handler silently produces no output for negative indexes because the
        candidate filename pattern ``_NNN.json`` doesn't match. We reject at the
        API boundary instead.
        """
        resp = client.post(
            "/api/projects/test-project/export",
            json={"scope": "current", "page_index": -1},
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body.get("error") == "validation_error"

    def test_zero_page_index_accepted(self, client: TestClient) -> None:
        """scope='current' with page_index=0 is the first page — valid."""
        resp = client.post(
            "/api/projects/test-project/export",
            json={"scope": "current", "page_index": 0},
        )
        assert resp.status_code == 202, resp.text

    def test_positive_page_index_accepted(self, client: TestClient) -> None:
        """scope='current' with page_index=5 is valid."""
        resp = client.post(
            "/api/projects/test-project/export",
            json={"scope": "current", "page_index": 5},
        )
        assert resp.status_code == 202, resp.text


class TestContradictoryScope:
    """scope='all_validated' with page_index supplied is contradictory."""

    def test_all_validated_with_page_index_rejected(self, client: TestClient) -> None:
        """scope='all_validated' with a page_index must return 400.

        page_index is only meaningful for scope='current'. Supplying it for
        all_validated is a contradictory request that the spec says should be
        rejected (strict behaviour).
        """
        resp = client.post(
            "/api/projects/test-project/export",
            json={"scope": "all_validated", "page_index": 0},
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body.get("error") == "validation_error"

    def test_all_validated_without_page_index_still_accepted(self, client: TestClient) -> None:
        """scope='all_validated' without page_index remains valid (regression guard)."""
        resp = client.post(
            "/api/projects/test-project/export",
            json={"scope": "all_validated"},
        )
        assert resp.status_code == 202, resp.text


# ---------------------------------------------------------------------------
# Parametric table — all invalid combos must return 400
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,description",
    [
        (
            {"scope": "all_validated", "detection_only": True, "recognition_only": True},
            "both mode flags True",
        ),
        (
            {"scope": "current", "page_index": -1},
            "negative page_index",
        ),
        (
            {"scope": "current", "page_index": -100},
            "very negative page_index",
        ),
        (
            {"scope": "all_validated", "page_index": 0},
            "all_validated with page_index=0",
        ),
        (
            {"scope": "all_validated", "page_index": 3},
            "all_validated with page_index=3",
        ),
    ],
)
def test_invalid_export_combos_rejected(client: TestClient, payload: dict, description: str) -> None:
    """Every contradictory / invalid export request combo must return 400."""
    resp = client.post(
        "/api/projects/test-project/export",
        json=payload,
    )
    assert resp.status_code == 400, f"Expected 400 for {description!r}, got {resp.status_code}: {resp.text}"

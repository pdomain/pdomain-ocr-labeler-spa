"""F-001 — Export path-traversal containment tests.

Spec authority: ``docs/specs/2026-05-24-F-001-export-path-traversal.md``.

Slice 1: failing tests (red before fix).
Slice 3: regression coverage — valid labels and attack-vector table.

Issue: ConcaveTrillion/pd-ocr-labeler-spa#406.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Slice 1 — traversal must be rejected (tests written before fix)
# ---------------------------------------------------------------------------


def test_traversal_via_style_filter(client: TestClient) -> None:
    """A crafted style_filter with ../ must be rejected 422 before the fix."""
    resp = client.post(
        "/api/projects/my-project/export",
        json={"scope": "all_validated", "style_filters": ["../../evil"]},
    )
    assert resp.status_code == 422


def test_export_output_dir_containment_guard(tmp_path: object) -> None:
    """export_output_dir must raise ValueError for a traversal subfolder."""
    from pathlib import Path

    from pd_ocr_labeler_spa.core.jobs.handlers.export import export_output_dir

    with pytest.raises(ValueError, match="resolves outside"):
        export_output_dir(Path(str(tmp_path)), "proj", "../../evil")


# ---------------------------------------------------------------------------
# Slice 3 — attack-vector parametrize table (all must return 422)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"style_filters": ["../../etc"]},  # upward traversal
        {"style_filters": ["/etc/passwd"]},  # absolute path
        {"style_filters": ["a/b"]},  # embedded separator
        {"style_filters": [""]},  # empty string
        {"style_filters": ["a" * 65]},  # over-length label
        {"component_filter": "../evil"},  # component_filter traversal
    ],
)
def test_attack_vectors_rejected_422(client: TestClient, payload: dict) -> None:
    """Every attack-vector entry must be rejected with 422."""
    resp = client.post(
        "/api/projects/my-project/export",
        json={"scope": "all_validated", **payload},
    )
    assert resp.status_code == 422, (
        f"Expected 422 for payload {payload!r}, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Slice 3 — valid labels must pass (202, not 422)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    ["italics", "small caps", "drop cap", "all", "a-1", "footnote marker"],
)
def test_valid_style_filters_accepted(client: TestClient, label: str) -> None:
    """Valid style-label strings must be accepted (202 Accepted, not 422)."""
    resp = client.post(
        "/api/projects/my-project/export",
        json={"scope": "all_validated", "style_filters": [label]},
    )
    assert resp.status_code == 202, f"Expected 202 for label {label!r}, got {resp.status_code}: {resp.text}"


@pytest.mark.parametrize(
    "label",
    ["italics", "small caps", "all"],
)
def test_export_output_dir_valid_subfolders(tmp_path: object, label: str) -> None:
    """Valid subfolders must not raise and must be inside tmp_path."""
    from pathlib import Path

    from pd_ocr_labeler_spa.core.jobs.handlers.export import export_output_dir

    result = export_output_dir(Path(str(tmp_path)), "proj", label)
    assert str(result).startswith(str(tmp_path))

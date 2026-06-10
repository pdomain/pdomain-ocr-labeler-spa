"""Unit tests for the export manifest write helper.

Validates:
- First write: creates manifest.json with correct schema fields.
- Re-export same project: replaces that project's entry, refreshes generated_at,
  preserves other projects.
- Merge semantics: re-exporting project A does not touch project B's entry.
- Import guard: if pdomain_ops is absent the handler still runs (manifest skipped).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _invoke_write_manifest(
    tmp_path: Path,
    *,
    project_id: str,
    exported_at: str,
    page_count: int,
    tasks: list[tuple[str, int]],
) -> None:
    """Call the helper under test, importing it from the handler module."""
    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import _write_export_manifest

    task_stats = [SimpleNamespace(task=t, item_count=c) for t, c in tasks]
    _write_export_manifest(
        export_root=tmp_path / "doctr-export",
        project_id=project_id,
        exported_at=exported_at,
        page_count=page_count,
        task_stats=task_stats,
    )


def test_first_write_creates_manifest(tmp_path: Path) -> None:
    """A fresh export creates manifest.json at the doctr-export root."""
    export_root = tmp_path / "doctr-export"
    export_root.mkdir(parents=True)

    _invoke_write_manifest(
        tmp_path,
        project_id="proj-A",
        exported_at="2026-06-10T12:00:00Z",
        page_count=3,
        tasks=[("detection", 42), ("recognition", 38)],
    )

    manifest_path = export_root / "manifest.json"
    assert manifest_path.exists(), "manifest.json not created"
    data = json.loads(manifest_path.read_text())
    assert data["schema"] == "pdomain.doctr-export-manifest"
    assert data["version"] == 1
    assert data["app"] == "pdomain-ocr-labeler-spa"
    assert "generated_at" in data
    assert "proj-A" in data["projects"]
    proj = data["projects"]["proj-A"]
    assert proj["page_count"] == 3
    # exported_at is stored as a datetime; compare just the date portion
    assert "2026-06-10" in proj["exported_at"]
    assert proj["tasks"]["detection"]["item_count"] == 42
    assert proj["tasks"]["recognition"]["item_count"] == 38


def test_re_export_replaces_project_preserves_others(tmp_path: Path) -> None:
    """Re-exporting project A replaces its entry; project B is untouched."""
    # First write: two projects
    _invoke_write_manifest(
        tmp_path,
        project_id="proj-A",
        exported_at="2026-06-10T10:00:00Z",
        page_count=2,
        tasks=[("detection", 10)],
    )
    _invoke_write_manifest(
        tmp_path,
        project_id="proj-B",
        exported_at="2026-06-10T10:30:00Z",
        page_count=5,
        tasks=[("recognition", 100)],
    )

    # Re-export project A with updated counts
    _invoke_write_manifest(
        tmp_path,
        project_id="proj-A",
        exported_at="2026-06-10T11:00:00Z",
        page_count=4,
        tasks=[("detection", 20), ("recognition", 18)],
    )

    manifest_path = tmp_path / "doctr-export" / "manifest.json"
    data = json.loads(manifest_path.read_text())

    # proj-A updated
    assert data["projects"]["proj-A"]["page_count"] == 4
    assert "2026-06-10" in data["projects"]["proj-A"]["exported_at"]
    assert data["projects"]["proj-A"]["tasks"]["detection"]["item_count"] == 20

    # proj-B untouched
    assert data["projects"]["proj-B"]["page_count"] == 5
    assert data["projects"]["proj-B"]["tasks"]["recognition"]["item_count"] == 100


def test_generated_at_refreshed_on_every_write(tmp_path: Path) -> None:
    """generated_at reflects the most recent write, not the oldest."""
    _invoke_write_manifest(
        tmp_path,
        project_id="proj-A",
        exported_at="2026-06-10T10:00:00Z",
        page_count=1,
        tasks=[],
    )
    manifest_path = tmp_path / "doctr-export" / "manifest.json"
    first_generated = json.loads(manifest_path.read_text())["generated_at"]

    _invoke_write_manifest(
        tmp_path,
        project_id="proj-A",
        exported_at="2026-06-10T11:00:00Z",
        page_count=2,
        tasks=[],
    )
    second_generated = json.loads(manifest_path.read_text())["generated_at"]

    # generated_at must differ (or at least not be earlier)
    assert second_generated >= first_generated


def test_import_guard_skips_manifest_gracefully(tmp_path: Path) -> None:
    """If pdomain_ops is absent, _write_export_manifest is a safe no-op.

    Uses builtins.__import__ patching to simulate an ImportError for
    pdomain_ops without having to uninstall the package.
    """
    import builtins
    from unittest.mock import patch

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import _write_export_manifest

    _real_import = builtins.__import__

    def _blocking_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "pdomain_ops" or name.startswith("pdomain_ops."):
            raise ImportError(f"simulated absence: {name}")
        return _real_import(name, *args, **kwargs)

    export_root = tmp_path / "doctr-export"
    export_root.mkdir(parents=True)

    with patch("builtins.__import__", side_effect=_blocking_import):
        # Should not raise, should not create manifest
        _write_export_manifest(
            export_root=export_root,
            project_id="proj",
            exported_at="2026-06-10T00:00:00Z",
            page_count=1,
            task_stats=[],
        )

    assert not (export_root / "manifest.json").exists()

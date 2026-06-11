"""Integration test: export job handler writes manifest.json.

Uses monkeypatching of ``_load_page_from_envelope_file`` and
``_page_is_validated`` to avoid the pdomain-book-tools + cv2 stack
while still exercising the full FastAPI + job runner + manifest write path.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


def _seed_project_files(data_root: Path, project_id: str, page_count: int = 1) -> None:
    """Create minimal JSON + PNG stubs so the export handler finds files."""
    project_dir = data_root / "labeled-projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    for i in range(page_count):
        # Minimal valid envelope (content doesn't matter — we'll stub the loader)
        envelope = {
            "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
            "payload": {"page": {"words": [], "lines": [], "blocks": []}},
        }
        json_path = project_dir / f"{project_id}_{i:03d}.json"
        json_path.write_text(json.dumps(envelope), encoding="utf-8")

        # Stub PNG alongside the JSON
        png_path = project_dir / f"{project_id}_{i:03d}.png"
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # just the PNG magic bytes


def _make_fake_page(n_words: int = 2) -> SimpleNamespace:
    """Build a minimal page-like object with validated words."""
    word = SimpleNamespace(
        text="hello",
        ground_truth_text="hello",
        word_labels=["validated"],
        bounding_box=SimpleNamespace(x=0.1, y=0.1, width=0.2, height=0.05),
        ground_truth_bounding_box=SimpleNamespace(x=0.1, y=0.1, width=0.2, height=0.05),
        text_style_labels=[],
        word_components=[],
    )
    return SimpleNamespace(words=[word] * n_words)


def _parse_sse_events(raw: bytes) -> list[dict]:  # pyright: ignore[reportExplicitAny]
    """Parse ``event: <type>\\ndata: {...}\\n\\n`` SSE frames."""
    events = []
    for block in raw.decode().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        event_type = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_type = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_type and data is not None:
            events.append({"event": event_type, "data": data})
    return events


def test_export_writes_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A completed export job creates manifest.json in the doctr-export root."""
    import pdomain_ocr_labeler_spa.core.jobs.handlers.export as _export_mod

    settings = _make_settings(tmp_path)
    project_id = "manifest-test-proj"
    _seed_project_files(settings.data_root, project_id, page_count=2)

    fake_page = _make_fake_page(n_words=3)

    # Stub the heavy loaders so the test doesn't need pdomain_book_tools or cv2.
    monkeypatch.setattr(_export_mod, "_load_page_from_envelope_file", lambda p: fake_page)
    monkeypatch.setattr(_export_mod, "_page_is_validated", lambda p: True)
    # Stub _export_page so we don't need cv2 at all.
    monkeypatch.setattr(_export_mod, "_export_page", lambda *a, **kw: None)

    app = build_app(settings)
    with TestClient(app) as client:
        resp = client.post(
            f"/api/projects/{project_id}/export",
            json={
                "scope": "all_validated",
                "style_filters": [],
                "component_filter": None,
                "include_classification": False,
                "detection_only": False,
                "recognition_only": False,
            },
        )
        assert resp.status_code == 202, f"unexpected status: {resp.status_code} {resp.text}"
        job_id = resp.json()["job_id"]

        # Drain the SSE stream until a terminal event
        events_resp = client.get(f"/api/jobs/{job_id}/events")
        events = _parse_sse_events(events_resp.content)

    event_types = [e["event"] for e in events]
    assert "complete" in event_types, f"'complete' event not seen; got {event_types}"

    data_root = Path(str(settings.data_root))
    manifest_path = data_root / "doctr-export" / "manifest.json"
    assert manifest_path.exists(), f"manifest.json not created at {manifest_path}; SSE events: {event_types}"

    data = json.loads(manifest_path.read_text())
    assert data["schema"] == "pdomain.doctr-export-manifest"
    assert data["version"] == 1
    assert data["app"] == "pdomain-ocr-labeler-spa"
    assert "generated_at" in data
    assert project_id in data["projects"], (
        f"project '{project_id}' not in manifest projects: {list(data['projects'].keys())}"
    )
    proj = data["projects"][project_id]
    assert proj["page_count"] == 2
    # Both detection and recognition task entries should be present
    assert "detection" in proj["tasks"]
    assert "recognition" in proj["tasks"]


def test_manifest_merge_on_re_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-exporting a project updates its manifest entry; other projects remain."""
    import pdomain_ocr_labeler_spa.core.jobs.handlers.export as _export_mod

    settings = _make_settings(tmp_path)
    proj_a = "proj-a"
    proj_b = "proj-b"
    _seed_project_files(settings.data_root, proj_a, page_count=1)
    _seed_project_files(settings.data_root, proj_b, page_count=3)

    fake_page = _make_fake_page(n_words=1)
    monkeypatch.setattr(_export_mod, "_load_page_from_envelope_file", lambda p: fake_page)
    monkeypatch.setattr(_export_mod, "_page_is_validated", lambda p: True)
    monkeypatch.setattr(_export_mod, "_export_page", lambda *a, **kw: None)

    app = build_app(settings)
    with TestClient(app) as client:
        # Export proj-a
        resp = client.post(
            f"/api/projects/{proj_a}/export",
            json={
                "scope": "all_validated",
                "style_filters": [],
                "component_filter": None,
                "include_classification": False,
                "detection_only": False,
                "recognition_only": False,
            },
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        client.get(f"/api/jobs/{job_id}/events")  # drain to completion

        # Export proj-b
        resp = client.post(
            f"/api/projects/{proj_b}/export",
            json={
                "scope": "all_validated",
                "style_filters": [],
                "component_filter": None,
                "include_classification": False,
                "detection_only": False,
                "recognition_only": False,
            },
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        client.get(f"/api/jobs/{job_id}/events")  # drain to completion

        # Re-export proj-a — should update its entry without touching proj-b
        resp = client.post(
            f"/api/projects/{proj_a}/export",
            json={
                "scope": "all_validated",
                "style_filters": [],
                "component_filter": None,
                "include_classification": False,
                "detection_only": False,
                "recognition_only": False,
            },
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        client.get(f"/api/jobs/{job_id}/events")  # drain to completion

    data_root = Path(str(settings.data_root))
    manifest_path = data_root / "doctr-export" / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())

    # Both projects must be present
    assert proj_a in data["projects"]
    assert proj_b in data["projects"]
    # proj-b page count must still be 3
    assert data["projects"][proj_b]["page_count"] == 3

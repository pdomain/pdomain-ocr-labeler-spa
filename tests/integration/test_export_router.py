"""Integration tests for ``api/export.py`` — 202 + job SSE cycle.

Spec authority:
- ``docs/architecture/02-backend.md §5.9`` — ``POST /api/projects/{pid}/export``
  returns 202 ``ExportResponse{job_id}``.
- ``docs/architecture/02-backend.md §5.10`` — ``GET /api/jobs/{job_id}/events``
  SSE stream ends on terminal event.

Acceptance (issue #187):
- export 202+job SSE cycle integration test.
"""

from __future__ import annotations

import json
from pathlib import Path

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


@pytest.fixture
def client(tmp_path: Path) -> TestClient:  # pyright: ignore[reportInvalidTypeForm, reportReturnType]
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    # Use TestClient as context manager so the lifespan (job runner) starts.
    with TestClient(app) as c:
        yield c  # pyright: ignore[reportReturnType]


def _parse_sse_events(raw: bytes) -> list[dict]:
    """Parse ``event: <type>\ndata: {...}\n\n`` SSE frames."""
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


# ── Route existence ───────────────────────────────────────────────────────────


def test_export_route_in_openapi(client: TestClient) -> None:
    """``POST /api/projects/{pid}/export`` is registered in the app."""
    spec = client.get("/openapi.json").json()
    path = "/api/projects/{project_id}/export"
    assert path in spec["paths"]
    assert "post" in spec["paths"][path]


def test_exports_list_route_in_openapi(client: TestClient) -> None:
    """``GET /api/projects/{pid}/exports`` is registered in the app."""
    spec = client.get("/openapi.json").json()
    path = "/api/projects/{project_id}/exports"
    assert path in spec["paths"]
    assert "get" in spec["paths"][path]


# ── POST /export — 202 + job_id ───────────────────────────────────────────────


def test_export_returns_202(client: TestClient) -> None:
    """``POST /api/projects/test-project/export`` returns 202 Accepted."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "all_validated"},
    )
    assert resp.status_code == 202, resp.text


def test_export_response_has_job_id(client: TestClient) -> None:
    """Response body contains a non-empty ``job_id`` string."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "all_validated"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str)
    assert body["job_id"]  # non-empty


def test_export_job_is_visible_in_job_list(client: TestClient) -> None:
    """A submitted export job appears in ``GET /api/jobs``."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "all_validated"},
    )
    job_id = resp.json()["job_id"]
    jobs = client.get("/api/jobs").json()
    assert any(j["job_id"] == job_id for j in jobs)


def test_export_job_has_correct_type(client: TestClient) -> None:
    """The submitted job has ``job_type == "export"``."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "all_validated"},
    )
    job_id = resp.json()["job_id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["job_type"] == "export"


def test_export_job_carries_project_id(client: TestClient) -> None:
    """The submitted job has ``project_id`` matching the URL parameter."""
    resp = client.post(
        "/api/projects/my-project/export",
        json={"scope": "all_validated"},
    )
    job_id = resp.json()["job_id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["project_id"] == "my-project"


def test_export_with_scope_all_validated(client: TestClient) -> None:
    """Scope ``all_validated`` is accepted and submitted as export job."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "all_validated"},
    )
    assert resp.status_code == 202


def test_export_with_style_filters(client: TestClient) -> None:
    """Style filters are accepted in the request body."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={
            "scope": "all_validated",
            "style_filters": ["italics", "small_caps"],
        },
    )
    assert resp.status_code == 202


def test_export_invalid_scope_returns_422(client: TestClient) -> None:
    """An invalid scope value returns 400 (validation error)."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "bad_scope"},
    )
    assert resp.status_code == 400  # Pydantic validation → our 400 handler


# ── SSE cycle: POST /export → EventSource /api/jobs/{id}/events ───────────────


def test_export_sse_cycle_completes(client: TestClient) -> None:
    """Full export 202+job SSE cycle: submit → SSE stream → terminal event.

    Issue #187 acceptance criteria: "export 202+job SSE cycle integration test".

    The stub export handler completes instantly (asyncio.sleep(0)) so the
    terminal event arrives quickly. The TestClient's run_async context
    ensures the runner background task has a chance to process the job.
    """
    # Submit the export job.
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "all_validated"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Open the SSE stream and collect until the terminal event.
    terminal_events = {"complete", "error", "cancelled"}
    events: list[dict] = []

    with client.stream("GET", f"/api/jobs/{job_id}/events") as sse_resp:
        assert sse_resp.status_code == 200
        raw = b""
        for chunk in sse_resp.iter_raw():
            raw += chunk
            # Parse incrementally so we stop as soon as terminal arrives.
            parsed = _parse_sse_events(raw)
            if any(e["event"] in terminal_events for e in parsed):
                events = parsed
                break

    terminal = [e for e in events if e["event"] in terminal_events]
    assert terminal, f"No terminal event received; events={events}"
    assert terminal[0]["event"] == "complete", f"Expected complete, got {terminal[0]}"


def test_export_sse_snapshot_event_has_correct_job_id(client: TestClient) -> None:
    """The first SSE frame (snapshot) contains the correct job state."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "all_validated"},
    )
    job_id = resp.json()["job_id"]

    with client.stream("GET", f"/api/jobs/{job_id}/events") as sse_resp:
        raw = b""
        for chunk in sse_resp.iter_raw():
            raw += chunk
            if b"\n\n" in raw:
                break

    events = _parse_sse_events(raw)
    assert events, "Expected at least one SSE frame"
    # The first event must be a status snapshot (queued/running/complete/etc.)
    first = events[0]
    assert "status" in first["data"]
    assert first["data"]["status"] in ("queued", "running", "complete", "error", "cancelled")


# ── GET /exports (list) ───────────────────────────────────────────────────────


def test_exports_list_returns_empty_list(client: TestClient) -> None:
    """``GET /api/projects/{pid}/exports`` returns empty list (no manifest yet)."""
    resp = client.get("/api/projects/test-project/exports")
    assert resp.status_code == 200
    assert resp.json() == []


# ── page_index validation (#225) ──────────────────────────────────────────────


def test_export_current_without_page_index_returns_400(client: TestClient) -> None:
    """``scope="current"`` without ``page_index`` returns 400 validation error.

    Issue #225 acceptance: "page_index required when scope=='current'".
    Our error_handler maps RequestValidationError → 400 validation_error.
    """
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "current"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("error") == "validation_error"


def test_export_current_requires_loaded_persisted_reviewed_page(client: TestClient) -> None:
    """``scope="current"`` cannot bypass text and typography review."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "current", "page_index": 0},
    )
    assert resp.status_code == 409


def test_export_all_validated_without_page_index_accepted(client: TestClient) -> None:
    """``scope="all_validated"`` without ``page_index`` returns 202 (page_index not required)."""
    resp = client.post(
        "/api/projects/test-project/export",
        json={"scope": "all_validated"},
    )
    assert resp.status_code == 202


# ── GET /export/styles (#225) ─────────────────────────────────────────────────


def test_export_styles_route_in_openapi(client: TestClient) -> None:
    """``GET /api/projects/{pid}/export/styles`` is registered in the app."""
    spec = client.get("/openapi.json").json()
    path = "/api/projects/{project_id}/export/styles"
    assert path in spec["paths"]
    assert "get" in spec["paths"][path]


def test_export_styles_returns_200(client: TestClient) -> None:
    """``GET /api/projects/{pid}/export/styles`` returns 200."""
    resp = client.get("/api/projects/test-project/export/styles")
    assert resp.status_code == 200


def test_export_styles_returns_list(client: TestClient) -> None:
    """``GET /api/projects/{pid}/export/styles`` returns a JSON array."""
    resp = client.get("/api/projects/test-project/export/styles")
    assert isinstance(resp.json(), list)


# ── Skipped-page count in terminal message (#task-7) ─────────────────────────


def test_export_excludes_pages_that_fail_to_load_before_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A page that cannot be reviewed is absent from the frozen export set."""
    import pdomain_ocr_labeler_spa.core.jobs.handlers.export as _export_mod

    # Inject two fake pages into the scan list so the handler enters the load loop.
    fake_json = tmp_path / "book_001.json"
    fake_img = tmp_path / "book_001.png"
    fake_json.write_text("{}", encoding="utf-8")
    fake_img.write_bytes(b"")

    monkeypatch.setattr(
        _export_mod, "_scan_labeled_pages", lambda data_root, project_id: [fake_json, fake_json]
    )
    monkeypatch.setattr(_export_mod, "_resolve_image_path", lambda p: fake_img)
    # Make every page fail to load — triggers the skipped_count path.
    monkeypatch.setattr(_export_mod, "_load_page_from_envelope_file", lambda p: None)

    settings = _make_settings(tmp_path)
    app = build_app(settings)

    terminal_message: str | None = None

    with TestClient(app) as c:
        resp = c.post("/api/projects/test-project/export", json={"scope": "all_validated"})
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["job_id"]

        terminal_events = {"complete", "error", "cancelled"}
        with c.stream("GET", f"/api/jobs/{job_id}/events") as sse_resp:
            assert sse_resp.status_code == 200
            raw = b""
            for chunk in sse_resp.iter_raw():
                raw += chunk
                parsed = _parse_sse_events(raw)
                terminal = [e for e in parsed if e["event"] in terminal_events]
                if terminal:
                    terminal_message = terminal[0]["data"].get("message", "")
                    break

    assert terminal_message is not None, "SSE stream never delivered a terminal event"
    assert terminal_message == "Exported 0 pages"


# ── Export stats breakdown in terminal SSE event (Lane E3) ───────────────────


def test_export_terminal_event_carries_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The terminal SSE event carries detection/recognition/skipped stats.

    Lane E3 (plan docs/plans/2026-06-03-labeler-spa-legacy-parity.md): legacy
    returns detection/recognition word counts + skipped-not-validated; SPA
    logged counts only. Assert the structured fields appear on the terminal
    event so the dialog can render them.
    """
    from unittest.mock import MagicMock

    import pdomain_ocr_labeler_spa.core.jobs.handlers.export as _export_mod

    data_root = tmp_path / "data"
    proj_dir = data_root / "labeled-projects" / "stats-project"
    proj_dir.mkdir(parents=True)
    # Two pages: one fully validated, one not validated (skipped).
    good_json = proj_dir / "stats-project_000.json"
    bad_json = proj_dir / "stats-project_001.json"
    good_json.write_text("{}", encoding="utf-8")
    bad_json.write_text("{}", encoding="utf-8")
    img = proj_dir / "img.png"
    img.write_bytes(b"")

    validated_page = _stats_page([_stats_word(True, "alpha", True), _stats_word(True, "beta", True)])
    not_validated_page = _stats_page([_stats_word(False, "gamma", True)])

    def fake_load(path):
        return validated_page if path == good_json else not_validated_page

    monkeypatch.setattr(_export_mod, "_scan_labeled_pages", lambda dr, pid: [good_json, bad_json])
    monkeypatch.setattr(_export_mod, "_resolve_image_path", lambda p: img)
    monkeypatch.setattr(_export_mod, "_load_page_from_envelope_file", fake_load)
    # Avoid cv2 / book-tools export I/O — we only assert stats accounting.
    monkeypatch.setattr(_export_mod, "_export_page", lambda *a, **k: None)

    settings = _make_settings(tmp_path)
    settings.__dict__["data_root"] = data_root  # type: ignore[index]
    app = build_app(settings)

    terminal_data: dict | None = None
    terminal_events = {"complete", "error", "cancelled"}

    with TestClient(app) as c:
        from types import SimpleNamespace

        from pdomain_ocr_labeler_spa.core.models import Project

        c.app.state.project_state.set_loaded_project(  # type: ignore[attr-defined]
            Project(
                project_id="stats-project",
                project_root=proj_dir,
                image_paths=[img, img],
                ground_truth_map={},
                total_pages=2,
            )
        )
        monkeypatch.setattr(
            "pdomain_ocr_labeler_spa.api.typography.typography_page_review",
            lambda *_args, **_kwargs: SimpleNamespace(complete=True),
        )
        # Point the runner's settings at our data_root.
        c.app.state.settings.__dict__["data_root"] = data_root  # type: ignore[attr-defined]
        c.app.state.job_runner.context["settings"] = MagicMock(data_root=data_root)  # type: ignore[attr-defined]

        resp = c.post("/api/projects/stats-project/export", json={"scope": "all_validated"})
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["job_id"]

        with c.stream("GET", f"/api/jobs/{job_id}/events") as sse_resp:
            assert sse_resp.status_code == 200
            raw = b""
            for chunk in sse_resp.iter_raw():
                raw += chunk
                parsed = _parse_sse_events(raw)
                terminal = [e for e in parsed if e["event"] in terminal_events]
                if terminal:
                    terminal_data = terminal[0]["data"]
                    break

    assert terminal_data is not None, "no terminal event received"
    assert terminal_data["status"] == "complete", terminal_data
    # Only the reviewed, validated page is queued. The unvalidated page is not part
    # of the frozen export set, so the worker cannot count it as a runtime skip.
    assert terminal_data.get("words_exported_detection") == 2, terminal_data
    assert terminal_data.get("words_exported_recognition") == 2, terminal_data
    assert terminal_data.get("pages_skipped_not_validated") == 0, terminal_data


def test_export_rejects_unindexed_validated_legacy_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every validated legacy page must map to an index that can be reviewed."""
    import pdomain_ocr_labeler_spa.core.jobs.handlers.export as _export_mod
    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import ExportPageRef
    from pdomain_ocr_labeler_spa.core.models import Project

    project_root = tmp_path / "project"
    project_root.mkdir()
    image_path = project_root / "page.png"
    image_path.write_bytes(b"")
    legacy_path = project_root / "legacy.json"
    legacy_path.write_text("{}", encoding="utf-8")
    validated_page = _stats_page([_stats_word(True, "alpha", True)])

    monkeypatch.setattr(
        _export_mod,
        "resolve_export_page_refs",
        lambda *_args: [ExportPageRef(page_index=-1, prefix="legacy", json_path=legacy_path)],
    )
    monkeypatch.setattr(_export_mod, "load_export_page", lambda *_args: validated_page)

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as test_client:
        test_client.app.state.project_state.set_loaded_project(  # type: ignore[attr-defined]
            Project(
                project_id="test-project",
                project_root=project_root,
                image_paths=[image_path],
                ground_truth_map={},
                total_pages=1,
            )
        )
        response = test_client.post(
            "/api/projects/test-project/export",
            json={"scope": "all_validated"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == ("Unindexed validated pages cannot be typography-reviewed for export")


def test_frozen_export_page_reloads_reviewed_content_after_sources_mutate(tmp_path: Path) -> None:
    """The worker input is content-addressed page and image bytes, not mutable heads."""
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import (
        freeze_export_page,
        load_frozen_export_page,
    )

    bbox = {
        "top_left": {"x": 0, "y": 0},
        "bottom_right": {"x": 20, "y": 20},
        "is_normalized": False,
    }
    page = Page.from_dict(
        {
            "width": 20,
            "height": 20,
            "page_index": 0,
            "bounding_box": bbox,
            "items": [
                {
                    "type": "Block",
                    "child_type": "BLOCKS",
                    "items": [
                        {
                            "type": "Block",
                            "child_type": "WORDS",
                            "items": [
                                {
                                    "type": "Word",
                                    "text": "OCR",
                                    "ground_truth_text": "Reviewed",
                                    "word_labels": ["validated"],
                                    "bounding_box": bbox,
                                }
                            ],
                            "bounding_box": bbox,
                        }
                    ],
                    "bounding_box": bbox,
                }
            ],
        }
    )
    image_path = tmp_path / "source.png"
    image_path.write_bytes(b"reviewed-image")
    snapshot = freeze_export_page(
        page=page,
        image_path=image_path,
        page_index=0,
        prefix="page-0",
        blob_project_dir=tmp_path / ".pd-pages",
    )

    page.words[0].ground_truth_text = "Later mutation"
    image_path.write_bytes(b"later-image")
    frozen_page, frozen_image = load_frozen_export_page(snapshot)

    assert frozen_page.words[0].ground_truth_text == "Reviewed"
    assert frozen_image.read_bytes() == b"reviewed-image"


def _stats_word(validated: bool, text: str, has_bbox: bool):
    """Build a MagicMock word for the Lane E3 stats accounting test."""
    from unittest.mock import MagicMock

    w = MagicMock()
    w.word_labels = ["validated"] if validated else []
    w.ground_truth_text = text
    w.text = text
    w.text_style_labels = []
    w.word_components = []
    w.bounding_box = object() if has_bbox else None
    return w


def _stats_page(words):
    """Build a serializable book-tools page with the given word attributes."""
    from pdomain_book_tools.ocr.page import Page

    bbox = {
        "top_left": {"x": 0, "y": 0},
        "bottom_right": {"x": 20, "y": 20},
        "is_normalized": False,
    }
    word_dicts = [
        {
            "type": "Word",
            "text": word.text,
            "ground_truth_text": word.ground_truth_text,
            "word_labels": list(word.word_labels),
            "bounding_box": bbox,
        }
        for word in words
    ]
    return Page.from_dict(
        {
            "width": 20,
            "height": 20,
            "page_index": 0,
            "bounding_box": bbox,
            "items": [
                {
                    "type": "Block",
                    "child_type": "BLOCKS",
                    "items": [
                        {
                            "type": "Block",
                            "child_type": "WORDS",
                            "items": word_dicts,
                            "bounding_box": bbox,
                        }
                    ],
                    "bounding_box": bbox,
                }
            ],
        }
    )

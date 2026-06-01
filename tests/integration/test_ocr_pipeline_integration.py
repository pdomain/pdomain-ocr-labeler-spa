"""Integration test: reload-ocr pipeline -> page_to_line_matches -> GET pages.

After M5b (greenfield event-store adoption), the envelope->Page lift is a stub.
The pipeline tests verify that reload-ocr completes without crashing and that
GET /pages/{idx} returns a valid 200 response (may have empty line_matches
until the blob-store-based lift replaces the stub).

Marks: integration, slow — requires DocTR or skips the line_matches count assertion.
"""

from __future__ import annotations

import json
import shutil
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
def ocr_project_root(tmp_path: Path, tiny_png: Path) -> Path:
    """Project root with one valid PNG — real OCR will be attempted."""
    root = tmp_path / "projects" / "ocr_test"
    root.mkdir(parents=True)
    shutil.copy(tiny_png, root / "001.png")
    return root


@pytest.fixture
def ocr_client(tmp_path: Path, ocr_project_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=ocr_project_root.parent)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(ocr_project_root)},
        )
        assert resp.status_code == 200, resp.text
        yield c


def _drain_sse_to_terminal(client: TestClient, job_id: str) -> str | None:
    """Drain the SSE stream until a terminal event; return its type."""
    terminal_type = None
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        for line in stream.iter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("data:"):
                try:
                    ev = json.loads(line[5:].strip())
                    if ev.get("type") in ("complete", "error"):
                        terminal_type = ev.get("type")
                        break
                except json.JSONDecodeError:
                    pass
            elif line.startswith("event:"):
                event_name = line[6:].strip()
                if event_name in ("complete", "error"):
                    terminal_type = event_name
                    break
    return terminal_type


@pytest.mark.integration
@pytest.mark.slow
def test_reload_ocr_pipeline_completes_and_returns_200(
    ocr_client: TestClient,
) -> None:
    """After reload-ocr completes, GET /pages/0 returns 200 with a valid shape.

    Rewritten from the original no_envelope_lift_warning test (M5b): the
    envelope→Page lift is now a stub in _page_payload (pages.py), so the
    "envelope→Page lift failed" warning IS expected and is not an error.

    Asserts:
    - reload-ocr job completes (terminal == "complete")
    - GET /pages/0 returns 200 with required fields
    - OCR pipeline does not crash (no uncaught exception)
    """
    resp = ocr_client.post("/api/projects/ocr_test/pages/0/reload-ocr", json={})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    terminal_type = _drain_sse_to_terminal(ocr_client, job_id)
    assert terminal_type == "complete", f"OCR job ended with: {terminal_type}"

    get_resp = ocr_client.get("/api/projects/ocr_test/pages/0")
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert "project_id" in body
    assert "page_index" in body
    assert isinstance(body.get("line_matches"), list)


@pytest.mark.integration
@pytest.mark.slow
def test_reload_ocr_pipeline_line_matches_structure(
    ocr_client: TestClient,
) -> None:
    """After reload-ocr, GET /pages/0 returns line_matches as a list and no payload_error.

    Does not assert len > 0 because DocTR may find 0 words on a 10x10 white image.
    Asserts structural correctness: field exists, is a list, payload_error is None.
    """
    resp = ocr_client.post("/api/projects/ocr_test/pages/0/reload-ocr", json={})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    terminal_type = _drain_sse_to_terminal(ocr_client, job_id)
    assert terminal_type == "complete"

    get_resp = ocr_client.get("/api/projects/ocr_test/pages/0")
    assert get_resp.status_code == 200
    body = get_resp.json()

    assert isinstance(body.get("line_matches"), list), (
        f"line_matches must be a list, got: {type(body.get('line_matches'))}"
    )
    pr = body.get("page_record")
    if pr is not None:
        assert pr.get("payload_error") is None, (
            f"payload_error should be None after successful OCR, got: {pr['payload_error']}"
        )

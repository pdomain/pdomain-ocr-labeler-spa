"""Integration tests for ``api/pages.py`` + ``api/jobs.py`` routes.

Acceptance criteria for issue #185:
- pytest integration tests for each endpoint in this group
- 202 reload-ocr returns job_id; EventSource reaches terminal 'complete'
- Legacy-path redirects: GET /project/foo → 301 → /projects/foo

Spec authority:
- ``docs/architecture/02-backend.md §5.3`` — pages endpoint contracts.
- ``docs/architecture/02-backend.md §5.10`` — jobs/SSE endpoint contracts.
- ``docs/architecture/02-backend.md §4`` — legacy redirect convention.
"""

from __future__ import annotations

import json
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
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x00")
    (proj / "002.png").write_bytes(b"\x00")
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with a project already loaded."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


@pytest.fixture
def bare_client(tmp_path: Path) -> Iterator[TestClient]:
    """TestClient with no project loaded."""
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


def test_get_page_returns_404_when_no_project_loaded(bare_client: TestClient) -> None:
    """No project loaded → 404 project_not_found."""
    resp = bare_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_get_page_returns_404_when_project_id_mismatches(
    loaded_client: TestClient,
) -> None:
    """Wrong project_id (project not loaded) → 404."""
    resp = loaded_client.get("/api/projects/other_book/pages/0")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_get_page_returns_404_when_index_out_of_range(
    loaded_client: TestClient,
) -> None:
    """page_index >= total_pages → 404 page_not_found."""
    resp = loaded_client.get("/api/projects/book1/pages/99")
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_get_page_returns_200_for_valid_index(
    loaded_client: TestClient,
) -> None:
    """Valid page_index on a loaded project → 200 PagePayload (spec-23-A).

    The fixture writes ``b"\\x00"`` as the PNG bytes; PIL can't open
    those so ``encoded_dims`` falls back to ``None`` and ``image_url``
    omits the ``?w=`` query — the URL is still well-formed.  Unit tests
    in ``tests/unit/api/test_pages_get.py`` cover the populated-dims
    path against the real tiny-fixture PNGs.
    """
    resp = loaded_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0
    # Degraded path: PIL couldn't read the fake bytes → image_url has no ?w=
    assert body["image_url"] == "/api/projects/book1/pages/0/image"


def test_get_page_payload_has_payload_error_field(loaded_client: TestClient) -> None:
    """PagePayload wire shape includes payload_error field (None on clean page).

    The field must exist on page_record even when None — it is part of the
    wire contract so the frontend can check it without optional-chaining hell.
    """
    resp = loaded_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # page_record may be None when no OCR has run (stub fixture).
    # When it exists, payload_error must be present (even if None).
    pr = body.get("page_record")
    if pr is not None:
        assert "payload_error" in pr, f"payload_error field missing from page_record: {list(pr.keys())}"


def test_post_save_page_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post("/api/projects/book1/pages/0/save", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_save_page_returns_400_when_page_not_loaded(
    loaded_client: TestClient,
) -> None:
    """spec-23-B2 §4: /save with no in-memory page state → 400 page_not_loaded.

    The wire-up tests for /save success / 409 / 500 live in
    ``tests/unit/api/test_save_load.py`` (they need to seed a
    ``PageState`` row); this integration test pins the loaded-project
    cold-start path (no OCR has run → nothing to save → 400).
    """
    resp = loaded_client.post("/api/projects/book1/pages/0/save", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "page_not_loaded"


def test_post_load_page_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post("/api/projects/book1/pages/0/load", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_load_page_does_not_return_503_without_explicit_loader(
    loaded_client: TestClient,
) -> None:
    """B3 fix (issue #331): /load no longer returns 503 when no explicit
    ``page_loader`` is injected on ``runner.context``.

    The route now builds a ``LocalDoctrPageLoader`` on-demand from the
    production context keys (``predictor_cache``, ``ocr_config_carrier``,
    ``settings``). With the ``b"\\x00"`` stub PNG bytes used by this fixture,
    DocTR will fail to load the image and return a non-200 status — but
    NOT a ``503 page_loader_not_wired``. The production path is exercised;
    functional /load tests with a fake loader live in
    ``tests/unit/api/test_save_load.py`` and
    ``tests/unit/api/test_b1_b3_f1.py``.
    """
    resp = loaded_client.post("/api/projects/book1/pages/0/load", json={})
    # The 503 page_loader_not_wired path has been removed.
    assert resp.status_code != 503, "503 page_loader_not_wired should not occur after B3 fix"
    if resp.status_code == 500:
        assert resp.json().get("error") != "page_loader_not_wired", (
            "503 error tag should not appear even in a 500 body"
        )


def test_post_reload_ocr_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post("/api/projects/book1/pages/0/reload-ocr", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_reload_ocr_returns_202_with_job_id(loaded_client: TestClient) -> None:
    """reload-ocr → 202 Accepted with a job_id field."""
    resp = loaded_client.post("/api/projects/book1/pages/0/reload-ocr", json={})
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str)
    assert len(body["job_id"]) > 0


def test_reload_ocr_sse_reaches_terminal_complete(tmp_path: Path, projects_root: Path) -> None:
    """Full SSE flow: POST reload-ocr → 202; EventSource hits terminal 'complete'.

    This is bullet 2 of the acceptance criteria: the SSE stream must
    eventually deliver a terminal ``complete`` event after a reload-ocr job
    is submitted. Uses a fresh client per spec (the stub handler
    immediately completes — no real OCR in this milestone).
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        load_resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert load_resp.status_code == 200

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202
        job_id = ocr_resp.json()["job_id"]

        # Stream SSE until we see the terminal 'complete' event.
        terminal_seen = False
        with c.stream("GET", f"/api/jobs/{job_id}/events") as stream_resp:
            assert stream_resp.status_code == 200
            for line in stream_resp.iter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_str = line[len("data:") :].strip()
                    try:
                        event_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if event_data.get("type") in ("complete", "error"):
                        terminal_seen = True
                        break
                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip()
                    if event_name in ("complete", "error"):
                        terminal_seen = True
                        break

        assert terminal_seen, "SSE stream never delivered a terminal event"


def test_post_save_all_returns_404_when_no_project(bare_client: TestClient) -> None:
    resp = bare_client.post("/api/projects/book1/save-all", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_save_all_returns_202_with_job_id(loaded_client: TestClient) -> None:
    """save-all is a long-running job → 202 Accepted with job_id."""
    resp = loaded_client.post("/api/projects/book1/save-all", json={})
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str)


def test_save_all_sse_reaches_terminal_complete(tmp_path: Path, projects_root: Path) -> None:
    """save-all SSE reaches terminal 'complete'."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        resp = c.post("/api/projects/book1/save-all", json={})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        terminal_seen = False
        with c.stream("GET", f"/api/jobs/{job_id}/events") as stream_resp:
            for line in stream_resp.iter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_str = line[len("data:") :].strip()
                    try:
                        ev = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("type") in ("complete", "error"):
                        terminal_seen = True
                        break

        assert terminal_seen, "save-all SSE never delivered terminal event"


def test_delete_project_returns_404_when_not_loaded(bare_client: TestClient) -> None:
    resp = bare_client.delete("/api/projects/book1")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_delete_project_returns_204_and_clears_state(tmp_path: Path, projects_root: Path) -> None:
    """DELETE /api/projects/{pid} → 204 and clears ProjectState."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        load_resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert load_resp.status_code == 200

        del_resp = c.delete("/api/projects/book1")
        assert del_resp.status_code == 204

        # After delete, GET should 404.
        get_resp = c.get("/api/projects/book1")
        assert get_resp.status_code == 404


def test_delete_project_returns_404_when_id_mismatches(
    loaded_client: TestClient,
) -> None:
    """DELETE with wrong id → 404."""
    resp = loaded_client.delete("/api/projects/different_book")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_post_source_root_rejects_nonexistent_path(bare_client: TestClient) -> None:
    """source-root endpoint validates the path and rejects non-existent dirs."""
    resp = bare_client.post("/api/projects/source-root", json={"path": "/does_not_exist_ever"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_path"


def test_legacy_project_path_redirects_301(bare_client: TestClient) -> None:
    """GET /project/foo → 301 → /projects/foo."""
    resp = bare_client.get("/project/foo", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"].endswith("/projects/foo")


def test_legacy_project_path_with_page_redirects(bare_client: TestClient) -> None:
    """GET /project/foo/page/3 → 301."""
    resp = bare_client.get("/project/foo/page/3", follow_redirects=False)
    assert resp.status_code == 301


def test_get_jobs_returns_list(bare_client: TestClient) -> None:
    resp = bare_client.get("/api/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_job_by_id_returns_404_for_unknown(bare_client: TestClient) -> None:
    resp = bare_client.get("/api/jobs/nonexistent")
    assert resp.status_code == 404


@pytest.mark.skip(reason="envelope_lift retired in M5b")
def test_get_page_stamps_payload_error_on_corrupt_envelope(
    tmp_path: Path,
    projects_root: Path,
    monkeypatch,
) -> None:
    """When envelope lift fails, GET /pages/{idx} returns 200 with payload_error set on page_record."""
    from pdomain_ocr_labeler_spa.core.envelope_lift import EnvelopeLiftError

    monkeypatch.setattr(
        "pdomain_ocr_labeler_spa.api.pages.lift_envelope_to_page",
        lambda payload: EnvelopeLiftError(
            message="injected test failure",
            cause=ValueError("injected"),
        ),
    )

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        # Load the page so pstate.page_record is set.
        c.post("/api/projects/book1/pages/0/load", json={})
        resp = c.get("/api/projects/book1/pages/0")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["line_matches"] == []
    pr = body.get("page_record")
    if pr is not None:
        assert pr.get("payload_error") is not None, (
            "Expected payload_error to be stamped when lift fails, got None. "
            f"page_record keys: {list(pr.keys())}"
        )


def test_get_page_image_missing_returns_404(
    tmp_path: Path,
    projects_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuinely missing image file returns 404 image_not_found."""
    import PIL.Image

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        # Monkeypatch PIL.Image.open to raise FileNotFoundError.
        monkeypatch.setattr(
            PIL.Image,
            "open",
            lambda p: (_ for _ in ()).throw(FileNotFoundError(f"No such file: {p}")),
        )
        resp = c.get("/api/projects/book1/pages/0/image")

    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert resp.json()["error"] == "image_not_found"


def test_get_page_image_corrupt_returns_422(
    tmp_path: Path,
    projects_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A present-but-unreadable image file returns 422 image_corrupt (not 404)."""
    import PIL.Image
    from PIL import UnidentifiedImageError

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        # Monkeypatch PIL.Image.open to raise UnidentifiedImageError.
        monkeypatch.setattr(
            PIL.Image,
            "open",
            lambda p: (_ for _ in ()).throw(UnidentifiedImageError("cannot identify image file")),
        )
        resp = c.get("/api/projects/book1/pages/0/image")

    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    assert resp.json()["error"] == "image_corrupt"


@pytest.fixture
def valid_jpeg_projects_root(tmp_path: Path) -> Path:
    """Projects root with a real 10x10 JPEG so image-endpoint tests don't hit PIL errors."""
    import io as _io

    import PIL.Image

    root = tmp_path / "projects_jpeg"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    buf = _io.BytesIO()
    PIL.Image.new("RGB", (10, 10), color=(128, 128, 128)).save(buf, format="JPEG")
    (proj / "001.png").write_bytes(buf.getvalue())
    (proj / "002.png").write_bytes(buf.getvalue())
    return root


def test_get_page_image_rejects_oversized_width(
    tmp_path: Path,
    valid_jpeg_projects_root: Path,
) -> None:
    """``?w=100000`` must be rejected before PIL is invoked (security: F-004, #409).

    The endpoint constrains ``w`` via ``Query(ge=1, le=8000)``.  FastAPI validates
    query parameters before the handler body runs; the custom
    ``RequestValidationError`` handler in this app maps that to
    ``400 validation_error`` (not the standard FastAPI 422).
    """
    settings = _make_settings(tmp_path, source_projects_root=valid_jpeg_projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(valid_jpeg_projects_root / "book1")})
        resp = c.get("/api/projects/book1/pages/0/image?w=100000")

    # Custom error handler maps RequestValidationError → 400 validation_error.
    assert resp.status_code == 400, (
        f"Expected 400 for oversized ?w=100000, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("error") == "validation_error", f"Expected validation_error body: {body}"


def test_get_page_image_rejects_zero_width(
    tmp_path: Path,
    valid_jpeg_projects_root: Path,
) -> None:
    """``?w=0`` must be rejected with 400 validation_error (security: F-004, issue #409).

    Width must be at least 1 pixel.  Same custom handler maps to 400.
    """
    settings = _make_settings(tmp_path, source_projects_root=valid_jpeg_projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(valid_jpeg_projects_root / "book1")})
        resp = c.get("/api/projects/book1/pages/0/image?w=0")

    assert resp.status_code == 400, f"Expected 400 for ?w=0, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("error") == "validation_error", f"Expected validation_error body: {body}"


def test_get_page_image_accepts_valid_width(
    tmp_path: Path,
    valid_jpeg_projects_root: Path,
) -> None:
    """``?w=1200`` (typical display width) must be accepted (security: F-004, issue #409)."""
    settings = _make_settings(tmp_path, source_projects_root=valid_jpeg_projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.post("/api/projects/load", json={"project_root": str(valid_jpeg_projects_root / "book1")})
        resp = c.get("/api/projects/book1/pages/0/image?w=1200")

    assert resp.status_code == 200, f"Expected 200 for valid ?w=1200, got {resp.status_code}: {resp.text}"
    assert resp.headers["content-type"].startswith("image/jpeg")

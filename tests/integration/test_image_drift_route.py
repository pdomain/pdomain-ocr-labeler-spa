"""Integration coverage for ``PagePayload.image_drift`` on ``GET /pages/{idx}``
— issue 2026-07-21-image-drift-banner-hard-off.

Confirms the full plumbing: an OCR'd page's recorded image digest (written
to the real ``LabelerPageStore`` the load route wires onto ``app.state``)
round-trips through ``_page_payload`` and the route's JSON response.
``tests/unit/api/test_image_drift.py`` covers ``_image_drift_for_page``'s
detection logic directly; this file only proves the route wires it through.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.settings import Settings


@dataclass
class _EmptyStubPage:
    """A duck-typed ``Page`` stand-in with zero lines — real OCR never runs.

    Mirrors ``test_get_page_load_error.py``'s stub: only ``.lines`` /
    ``.paragraphs`` need to exist for ``page_to_line_matches``'s duck-typed
    ``is_page`` check to accept it and build an (empty) ``PageState``.
    """

    lines_: list[object] = field(default_factory=list)
    paragraphs_: list[object] = field(default_factory=list)

    @property
    def lines(self) -> list[object]:
        return self.lines_

    @property
    def paragraphs(self) -> list[object]:
        return self.paragraphs_


class _EmptyTextPageLoader:
    """A ``PageLoader`` whose ``run_ocr`` succeeds without invoking real OCR."""

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def run_ocr(
        self,
        page_index: int,
        *,
        edited_image_bytes: bytes | None = None,
        page_kind: object | None = None,
    ) -> PageLoadOutcome:
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=_EmptyStubPage())


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
        "no_prefetch": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x89PNG\r\n original bytes")
    return root


@pytest.fixture
def app_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text
        yield c


def _stamp_ocrd_page(app_client: TestClient, image_path: Path, image_bytes: bytes) -> None:
    """Register page 0 as OCR'd against ``image_bytes`` in the real page_store.

    Mirrors what ``LocalDoctrPageLoader.run_ocr`` does after a real doctr
    pass, without requiring doctr: write the same bytes the route will later
    re-read to the store via ``_ingest_ocr_result``, then stamp the
    resulting ``page_id`` onto ``PageState`` the same way the real loader
    does (``local_doctr.py`` sets ``pstate.page_id`` from the aggregate).
    """
    store: LabelerPageStore = app_client.app.state.page_store  # type: ignore[attr-defined]
    fake_page = MagicMock()
    fake_page.page_id = uuid4()
    fake_page.to_dict.return_value = {"page_id": str(fake_page.page_id), "lines": []}
    agg = _ingest_ocr_result(page=fake_page, image_bytes=image_bytes, page_index=0, store=store)

    project_state = app_client.app.state.project_state  # type: ignore[attr-defined]
    pstate = project_state.get_page_state(0)
    assert pstate is not None, "GET /pages/0 must have created a PageState"
    pstate.page_id = agg.record.page_id


def test_get_page_reports_no_drift_for_unchanged_image(app_client: TestClient, projects_root: Path) -> None:
    image_path = projects_root / "book1" / "001.png"
    image_bytes = image_path.read_bytes()

    app_client.app.state.job_runner.context["page_loader"] = _EmptyTextPageLoader()  # type: ignore[attr-defined]
    resp = app_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    _stamp_ocrd_page(app_client, image_path, image_bytes)

    # First check after stamping the digest only records the baseline.
    resp = app_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    assert resp.json()["image_drift"] is None

    # A second, unchanged fetch stays clean.
    resp = app_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    assert resp.json()["image_drift"] is None


def test_get_page_reports_drift_for_changed_image(app_client: TestClient, projects_root: Path) -> None:
    image_path = projects_root / "book1" / "001.png"
    image_bytes = image_path.read_bytes()

    app_client.app.state.job_runner.context["page_loader"] = _EmptyTextPageLoader()  # type: ignore[attr-defined]
    app_client.get("/api/projects/book1/pages/0")
    _stamp_ocrd_page(app_client, image_path, image_bytes)
    # Baseline-recording fetch.
    app_client.get("/api/projects/book1/pages/0")

    image_path.write_bytes(b"\x89PNG\r\n replaced bytes, definitely different content")
    project_state = app_client.app.state.project_state  # type: ignore[attr-defined]
    pstate = project_state.get_page_state(0)
    assert pstate is not None
    new_mtime_ns = (pstate.image_drift_mtime_ns or 0) + 10_000_000_000
    os.utime(image_path, ns=(new_mtime_ns, new_mtime_ns))

    resp = app_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["image_drift"] is not None
    assert body["image_drift"]["error"] == "image_changed"


def test_get_page_reports_no_drift_when_digest_unavailable(app_client: TestClient) -> None:
    """No OCR-time digest recorded yet (page_id never stamped) — no drift."""
    app_client.app.state.job_runner.context["page_loader"] = _EmptyTextPageLoader()  # type: ignore[attr-defined]
    resp = app_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    assert resp.json()["image_drift"] is None

"""Tests for the loader-failure marker on ``GET /pages/{idx}``.

Issue: ``docs/issues/2026-08-08-get-page-hides-ocr-failures.md``.

``get_page`` auto-triggers ``ensure_page_model`` (B1, issue #330) when no
page_record is cached for the page yet. A genuine loader failure there used
to degrade silently to an empty ``page_record``, logged only at DEBUG — an
operator never saw it, and the response looked identical to a page whose OCR
ran and legitimately found no text.

This module covers the fix:

- A loader that raises logs a WARNING (with project id + page index, and
  ``exc_info``) and stamps ``PagePayload.page_load_error``.
- A loader that succeeds but finds no words leaves ``page_load_error``
  ``None`` and logs no WARNING — a page with genuinely no text still
  renders without an error marker.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
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
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    return root


@dataclass
class _EmptyStubPage:
    """A ``Page`` stand-in with zero lines — OCR ran and found no text."""

    lines_: list[Any] = field(default_factory=list)
    paragraphs_: list[Any] = field(default_factory=list)

    @property
    def lines(self) -> list[Any]:
        return self.lines_

    @property
    def paragraphs(self) -> list[Any]:
        return self.paragraphs_


class _RaisingPageLoader:
    """A ``PageLoader`` whose ``run_ocr`` always raises."""

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
        raise RuntimeError("doctr predictor unavailable")


class _EmptyTextPageLoader:
    """A ``PageLoader`` whose ``run_ocr`` succeeds but finds no words."""

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


@pytest.fixture
def app_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with ``book1`` loaded and no ``page_loader`` pre-injected.

    Each test injects its own loader onto ``runner.context`` before the
    first GET so the on-demand build in ``get_page`` picks it up.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text
        yield c


def test_loader_failure_stamps_page_load_error_and_logs_warning(
    app_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app_client.app.state.job_runner.context["page_loader"] = _RaisingPageLoader()  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING, logger="pdomain_ocr_labeler_spa.api.pages"):
        resp = app_client.get("/api/projects/book1/pages/0")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_load_error"] is not None
    assert body["page_load_error"]["error"] == "ocr_load_failed"
    assert "doctr predictor unavailable" in body["page_load_error"]["message"]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING-level log record for the loader failure"
    record = warnings[0]
    assert "book1" in record.getMessage()
    assert "page=0" in record.getMessage()
    assert record.exc_info is not None, "the WARNING must keep exc_info for the traceback"


def test_no_text_page_leaves_page_load_error_none_and_logs_no_warning(
    app_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app_client.app.state.job_runner.context["page_loader"] = _EmptyTextPageLoader()  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING, logger="pdomain_ocr_labeler_spa.api.pages"):
        resp = app_client.get("/api/projects/book1/pages/0")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_load_error"] is None
    assert body["line_matches"] == []

    assert not any("ensure_page_model failed" in r.getMessage() for r in caplog.records)

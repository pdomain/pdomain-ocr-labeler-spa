"""Tests for the loader-failure marker on ``GET /pages/{idx}``.

Issues: ``docs/issues/2026-08-08-get-page-hides-ocr-failures.md`` and
``docs/issues/2026-08-08-page-load-progress-unbuilt.md``.

``get_page`` auto-triggers a page load (B1, issue #330) when no page_record
is cached for the page yet. Per
``docs/specs/2026-08-08-page-load-progress-design.md`` "Move page loading
onto the job system", that trigger now has two parts:

1. A synchronous, cheap check of the labeled/cached lanes only
   (``ensure_page_model(..., allow_ocr=False)``) — never runs OCR. A
   failure there (this repo's fake loaders can raise from ``load_labeled``)
   is a deployment/lane-read problem, not an OCR failure, and still stamps
   ``PagePayload.page_load_error`` synchronously, exactly as before.
2. A genuine miss on both lanes submits a ``load_page`` job instead of
   running OCR inline; the GET returns immediately with
   ``page_load_job_id`` set and ``page_load_error`` left ``None``. A GET's
   OCR failure — the old subject of this module — is now an async job
   outcome, covered by ``tests/integration/test_load_page_job.py`` instead
   of here.

This module covers what's left synchronous:

- A labeled/cached-lane read that raises logs a WARNING (with project id +
  page index, and ``exc_info``) and stamps ``PagePayload.page_load_error``
  with a curated (exception-type-only) message.
- A loader that can't be built at all (``ocr_unavailable``) is unchanged —
  it happens before any lane check.
- A labeled/cached-lane *hit* (this repo's fake loaders return it from
  ``load_labeled``) returns the page immediately, including a legitimately
  empty page — leaves both ``page_load_error`` and ``page_load_job_id``
  ``None``, and logs no warning. This also covers the design's "a page
  served from a warm store still returns immediately... and creates no
  job" acceptance criterion for the labeled-lane-hit case.
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
from pdomain_ocr_labeler_spa.core.page_state import PageLoader, PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
        # Prefetch (GAP-2) would otherwise schedule a background fetch of
        # adjacent pages as soon as one page GET returns, racing the
        # explicit multi-fetch assertions below (warn-once-per-project,
        # warn-every-time) against a nondeterministic background task.
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
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    (proj / "002.png").write_bytes(b"\x89PNG\r\n")
    return root


@dataclass
class _EmptyStubPage:
    """A ``Page`` stand-in with zero lines — OCR ran and found no text.

    ``lines``/``paragraphs`` are typed ``list[object]``, not ``list[Any]``:
    this stub only ever holds an empty list (nothing appends a real line or
    paragraph to it — its whole purpose is to duck-type ``.lines`` as empty
    for ``page_to_line_matches``'s ``is_page`` check), so there is no real
    element type to narrow to and ``object`` costs nothing here.
    """

    lines_: list[object] = field(default_factory=list)
    paragraphs_: list[object] = field(default_factory=list)

    @property
    def lines(self) -> list[object]:
        return self.lines_

    @property
    def paragraphs(self) -> list[object]:
        return self.paragraphs_


class _RaisingOnLabeledLanePageLoader:
    """A ``PageLoader`` whose ``load_labeled`` always raises.

    The synchronous lane check (``ensure_page_model(..., allow_ocr=False)``)
    calls ``load_labeled``/``load_cached`` directly with no self-catch of
    arbitrary exceptions (unlike the real ``LocalDoctrPageLoader``, whose
    ``load_labeled`` only ever re-raises ``LegacyTypographyPayloadError``) —
    this test double raises a plain exception to exercise ``get_page``'s own
    try/except around that call.
    """

    _PATH = "/var/lib/pdomain/models/db_resnet50/weights.pt"

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        raise RuntimeError(f"failed to read weights at {self._PATH}")

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def run_ocr(
        self,
        page_index: int,
        *,
        edited_image_bytes: bytes | None = None,
        page_kind: object | None = None,
    ) -> PageLoadOutcome:
        raise AssertionError("run_ocr must not be called — the lane check must fail first")


class _EmptyTextLabeledLoader:
    """A ``PageLoader`` whose ``load_labeled`` hits with a page that has no words.

    Distinct from ``run_ocr`` finding no text (that path is now async — see
    ``tests/integration/test_load_page_job.py``): a labeled-lane hit is the
    synchronous, no-job path, and this is its "legitimately empty" case.
    """

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=_EmptyStubPage())

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def run_ocr(
        self,
        page_index: int,
        *,
        edited_image_bytes: bytes | None = None,
        page_kind: object | None = None,
    ) -> PageLoadOutcome:
        raise AssertionError("run_ocr must not be called — the labeled lane already hit")


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


def test_labeled_lane_failure_stamps_page_load_error_and_logs_warning(
    app_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app_client.app.state.job_runner.context["page_loader"] = _RaisingOnLabeledLanePageLoader()  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING, logger="pdomain_ocr_labeler_spa.api.pages"):
        resp = app_client.get("/api/projects/book1/pages/0")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_load_error"] is not None
    assert body["page_load_error"]["error"] == "ocr_load_failed"
    assert body["page_load_job_id"] is None
    # Client-facing message is curated to the exception type, not str(exc) —
    # see test_lane_failure_message_does_not_leak_exception_details for the
    # dedicated no-path-leak coverage.
    assert "RuntimeError" in body["page_load_error"]["message"]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING-level log record for the lane-check failure"
    record = warnings[0]
    assert "book1" in record.getMessage()
    assert "page=0" in record.getMessage()
    assert record.exc_info is not None, "the WARNING must keep exc_info for the traceback"


def test_labeled_lane_hit_leaves_page_load_error_none_and_creates_no_job(
    app_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app_client.app.state.job_runner.context["page_loader"] = _EmptyTextLabeledLoader()  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING, logger="pdomain_ocr_labeler_spa.api.pages"):
        resp = app_client.get("/api/projects/book1/pages/0")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_load_error"] is None
    assert body["page_load_job_id"] is None
    assert body["line_matches"] == []

    assert not any("ensure_page_model failed" in r.getMessage() for r in caplog.records)
    runner = app_client.app.state.job_runner  # type: ignore[attr-defined]
    assert runner.list_jobs() == [], "a labeled-lane hit must not submit a job"


def _raise_loader_unavailable(runner: Any, project_state: Any, settings: Any) -> PageLoader:
    """Stand-in for ``_build_page_loader_from_context`` that always raises.

    Signature mirrors ``test_b1_b3_f1.py``'s ``_patched_build_loader`` (loose
    ``Any`` params — ``monkeypatch.setattr`` doesn't enforce the original
    signature). The declared ``PageLoader`` return type is never actually
    produced; the body only raises.
    """
    raise RuntimeError("no predictor_cache in runner.context")


def test_loader_build_failure_stamps_ocr_unavailable_and_warns_once_per_project(
    app_client: TestClient,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loader that can't be built at all is a deployment fact, not a
    per-page one: it gets its own error code (not ``ocr_load_failed``), and
    only the FIRST page fetched for a project logs a WARNING — later fetches
    (any page) log at DEBUG instead, so navigating a whole book in this state
    doesn't produce one WARNING per page. Happens before any lane check, so
    this path is unaffected by the job move.
    """
    from pdomain_ocr_labeler_spa.api import pages as pages_mod

    # Deterministic regardless of what ran earlier in this worker process.
    pages_mod._ocr_unavailable_warned_projects.discard("book1")
    monkeypatch.setattr(pages_mod, "_build_page_loader_from_context", _raise_loader_unavailable)

    with caplog.at_level(logging.DEBUG, logger="pdomain_ocr_labeler_spa.api.pages"):
        resp1 = app_client.get("/api/projects/book1/pages/0")
        resp2 = app_client.get("/api/projects/book1/pages/1")

    for resp in (resp1, resp2):
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["page_load_error"] is not None
        assert body["page_load_error"]["error"] == "ocr_unavailable"
        assert "not available in this deployment" in body["page_load_error"]["message"]
        assert body["page_load_job_id"] is None

    relevant = [r for r in caplog.records if "OCR loader unavailable for project=book1" in r.getMessage()]
    warnings = [r for r in relevant if r.levelno == logging.WARNING]
    debugs = [r for r in relevant if r.levelno == logging.DEBUG]
    assert len(warnings) == 1, f"expected exactly one WARNING across two fetches, got {len(warnings)}"
    assert len(debugs) == 1, f"expected the second fetch to log at DEBUG, got {len(debugs)}"


def test_lane_failure_warns_on_every_fetch(
    app_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unlike the deployment-wide loader-unavailable case, a per-page
    lane-check failure on a loader that builds fine warns every time — the
    failure is specific to this page's read, not a standing deployment
    condition, so there's nothing to de-duplicate.
    """
    app_client.app.state.job_runner.context["page_loader"] = _RaisingOnLabeledLanePageLoader()  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING, logger="pdomain_ocr_labeler_spa.api.pages"):
        resp1 = app_client.get("/api/projects/book1/pages/0")
        resp2 = app_client.get("/api/projects/book1/pages/0")

    for resp in (resp1, resp2):
        assert resp.status_code == 200, resp.text
        assert resp.json()["page_load_error"]["error"] == "ocr_load_failed"

    warnings = [r for r in caplog.records if "ensure_page_model failed" in r.getMessage()]
    assert len(warnings) == 2, f"expected a WARNING for each per-page failure, got {len(warnings)}"


def test_lane_failure_message_does_not_leak_exception_details(
    app_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``page_load_error.message`` is client-facing and goes over the wire —
    ``str(exc)`` can carry server filesystem paths, so the response must be
    curated to the exception type at most. Full detail (the path) still
    belongs in the WARNING's exc_info for whoever reads the server log.
    """
    loader = _RaisingOnLabeledLanePageLoader()
    app_client.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING, logger="pdomain_ocr_labeler_spa.api.pages"):
        resp = app_client.get("/api/projects/book1/pages/0")

    assert resp.status_code == 200, resp.text
    message = resp.json()["page_load_error"]["message"]
    assert loader._PATH not in message, f"filesystem path leaked into client response: {message!r}"
    assert "RuntimeError" in message, "curated message should still name the exception type"

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING-level log record for the lane-check failure"
    record = warnings[0]
    assert record.exc_info is not None
    exc = record.exc_info[1]
    assert exc is not None and loader._PATH in str(exc), (
        "full detail (the path) must still be recoverable from the WARNING's exc_info"
    )

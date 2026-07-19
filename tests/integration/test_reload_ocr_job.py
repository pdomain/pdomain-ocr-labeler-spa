"""Integration tests for the ``reload_ocr`` job handler.

Spec: ``specs/23-page-payload-backend.md §6`` — the handler runs OCR via
``LocalDoctrPageLoader.run_ocr`` on a worker thread, reports progress at
four fractions (0.0 / 0.1 / 0.9 / 1.0) with stable messages, and stores
the resulting ``PageLoadOutcome`` on
``ProjectState.page_states[idx].page_record``. Failure path emits an
``ocr_failed`` notification and transitions the job to ``error``.

Issue: #307 (spec-23-B1).

These tests inject a fake ``page_loader`` onto ``runner.context`` so the
handler can be exercised end-to-end without pulling DocTR / pdomain_book_tools
into the test process.

The SSE HTTP stream is race-prone in tests — the job often finishes
before an EventSource subscribes (the broker only replays events that
arrive *after* subscription). We instead wrap ``broker.publish`` to
collect every event at the publish site, which matches what a
race-free SSE subscriber would have seen.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.jobs import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.handlers.reload_ocr import _get_page_loader
from pdomain_ocr_labeler_spa.core.notifications import NotificationKind
from pdomain_ocr_labeler_spa.core.ocr.predictor import PredictorCache
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
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
    (proj / "002.png").write_bytes(b"\x89PNG\r\n")
    return root


class _FakePageLoader:
    """Stand-in for ``LocalDoctrPageLoader`` that the handler calls into."""

    def __init__(self, *, raise_on_run: Exception | None = None) -> None:
        self.calls: list[int] = []
        self._raise = raise_on_run

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        self.calls.append(page_index)
        if self._raise is not None:
            raise self._raise
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload={"fake": "page", "idx": page_index},
        )

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None


def _wrap_broker_publish(broker: JobEventBroker, sink: list[dict[str, Any]]) -> None:
    """Patch ``broker.publish`` to append every event to ``sink``."""
    original = broker.publish

    async def recording_publish(job_id: str, event: dict[str, Any]) -> None:
        sink.append({"job_id": job_id, **event})
        await original(job_id, event)

    broker.publish = recording_publish  # type: ignore[method-assign]


def _wait_for_terminal(events: list[dict[str, Any]], *, timeout: float = 5.0) -> None:
    """Spin until a terminal event lands in ``events``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(e.get("type") in ("complete", "error", "cancelled") for e in events):
            return
        time.sleep(0.01)
    raise AssertionError(f"no terminal event after {timeout}s; events={events}")


@pytest.fixture
def loaded_client_with_loader(
    tmp_path: Path, projects_root: Path
) -> Iterator[tuple[TestClient, _FakePageLoader, list[dict[str, Any]]]]:
    """Loaded project + fake page_loader + broker event recorder."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()
    recorded: list[dict[str, Any]] = []
    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c, loader, recorded


def test_reload_ocr_success_emits_four_progress_events_in_order(
    loaded_client_with_loader: tuple[TestClient, _FakePageLoader, list[dict[str, Any]]],
) -> None:
    """Spec §6: progress at fractions 0.0 / 0.1 / 0.9 / 1.0 in that order.

    The four ``update_progress`` calls must each appear at the broker
    in monotonic order; the terminal event is ``complete``.
    """
    c, loader, events = loaded_client_with_loader

    ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
    assert ocr_resp.status_code == 202

    _wait_for_terminal(events)

    progress_events = [e for e in events if e.get("type") == "progress"]
    fractions = [e["current"] / e["total"] for e in progress_events if e.get("total")]
    spec_fractions = [0.0, 0.1, 0.9, 1.0]
    for expected in spec_fractions:
        assert any(abs(f - expected) < 1e-6 for f in fractions), (
            f"missing progress fraction {expected} in {fractions}"
        )
    # Order: each spec fraction's first occurrence must come in spec order.
    first_indices = [
        next(i for i, f in enumerate(fractions) if abs(f - expected) < 1e-6) for expected in spec_fractions
    ]
    assert first_indices == sorted(first_indices), f"progress fractions out of order: {fractions}"

    assert events[-1].get("type") == "complete", events[-1]
    assert loader.calls == [0]


def test_reload_ocr_stores_outcome_on_project_state(
    loaded_client_with_loader: tuple[TestClient, _FakePageLoader, list[dict[str, Any]]],
) -> None:
    """After a successful reload-ocr, ``page_states[idx].page_record`` is
    the ``PageLoadOutcome`` returned by the loader (spec §6).
    """
    c, _loader, events = loaded_client_with_loader

    ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
    assert ocr_resp.status_code == 202

    _wait_for_terminal(events)
    assert events[-1].get("type") == "complete", events[-1]

    project_state = c.app.state.project_state  # type: ignore[attr-defined]
    pstate = project_state.page_states.get(0)
    assert pstate is not None
    outcome = pstate.page_record
    assert isinstance(outcome, PageLoadOutcome)
    assert outcome.page_index == 0
    assert outcome.source == PageSource.OCR
    assert outcome.payload == {"fake": "page", "idx": 0}


def test_reload_ocr_failure_emits_error_and_ocr_failed_notification(
    tmp_path: Path, projects_root: Path
) -> None:
    """OCR exception → terminal ``error`` event + negative notification."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader(raise_on_run=RuntimeError("doctr exploded"))
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202

        _wait_for_terminal(recorded)

        terminal = recorded[-1]
        assert terminal.get("type") == "error", terminal
        assert "doctr exploded" in terminal.get("error", ""), terminal

        notif_queue = c.app.state.notification_queue  # type: ignore[attr-defined]
        notifications = notif_queue.snapshot()
        ocr_failed = [n for n in notifications if n.kind == NotificationKind.NEGATIVE and "OCR" in n.message]
        assert ocr_failed, (
            f"expected an OCR-failed notification; got {[(n.kind, n.message) for n in notifications]}"
        )


# ── Task A: production wiring path ────────────────────────────────────


def test_reload_ocr_with_production_context_wiring(tmp_path: Path, projects_root: Path) -> None:
    """When predictor_cache / ocr_config_carrier / settings are wired on
    runner.context (production bootstrap path), the handler still completes
    successfully when a page_loader is also injected directly.

    This verifies that the production wiring of the three new context keys
    does not break the existing path — both can coexist. The fake
    page_loader is still used for isolation (no real DocTR in tests).
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _FakePageLoader()
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        runner = c.app.state.job_runner  # type: ignore[attr-defined]
        # Verify production keys are already wired by build_app.
        assert "predictor_cache" in runner.context, (
            "predictor_cache must be wired in runner.context by build_app"
        )
        assert "ocr_config_carrier" in runner.context, (
            "ocr_config_carrier must be wired in runner.context by build_app"
        )
        assert "settings" in runner.context, "settings must be wired in runner.context by build_app"

        # Direct page_loader injection still wins for isolation.
        runner.context["page_loader"] = loader
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]

        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202

        _wait_for_terminal(recorded)
        assert recorded[-1].get("type") == "complete", recorded[-1]
        assert loader.calls == [0]


# OCR timeout contract: docs/architecture/02-backend.md


class _SlowPageLoader:
    """Stand-in ``PageLoader`` whose ``run_ocr`` sleeps past a tiny timeout."""

    def __init__(self, *, sleep_s: float) -> None:
        self._sleep_s = sleep_s
        self.calls: list[int] = []

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        self.calls.append(page_index)
        time.sleep(self._sleep_s)
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload={"fake": "page", "idx": page_index},
        )

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        return None


def test_reload_ocr_times_out_and_marks_job_error(tmp_path: Path, projects_root: Path) -> None:
    """A ``run_ocr`` call exceeding ``Settings.ocr_timeout_s`` errors the job.

    The job must end in ``ERROR`` with "timed out" in the error message,
    and a NEGATIVE notification must be queued — reusing the existing
    failure path (spec §6 ``ocr_failed`` semantics).
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root, ocr_timeout_s=0.05)
    app = build_app(settings)
    loader = _SlowPageLoader(sleep_s=5.0)
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202

        _wait_for_terminal(recorded, timeout=5.0)

        terminal = recorded[-1]
        assert terminal.get("type") == "error", terminal
        assert "timed out" in terminal.get("error", "").lower(), terminal

        notif_queue = c.app.state.notification_queue  # type: ignore[attr-defined]
        notifications = notif_queue.snapshot()
        timeout_notifications = [
            n
            for n in notifications
            if n.kind == NotificationKind.NEGATIVE and "timed out" in n.message.lower()
        ]
        assert timeout_notifications, (
            f"expected an OCR-timeout notification; got {[(n.kind, n.message) for n in notifications]}"
        )


def test_get_page_loader_raises_when_project_not_loaded() -> None:
    """_get_page_loader raises RuntimeError when project_state.loaded_project is None.

    This validates the guard added by the Task A wiring — when the
    production context provides predictor_cache / ocr_config_carrier /
    settings but the project hasn't been loaded yet, the handler should
    fail fast with a clear message rather than a confusing AttributeError.
    """
    from unittest.mock import MagicMock

    from pdomain_ocr_labeler_spa.core.ocr_config_state import OCRConfigCarrier

    runner = MagicMock()
    project_state = ProjectState()  # loaded_project is None
    settings = MagicMock()
    predictor_cache = PredictorCache()
    ocr_carrier = OCRConfigCarrier()

    runner.context = {
        "predictor_cache": predictor_cache,
        "ocr_config_carrier": ocr_carrier,
        "settings": settings,
        # no "page_loader" key
    }

    with pytest.raises(RuntimeError, match="reload_ocr: no project loaded"):
        _get_page_loader(runner, project_state, settings)

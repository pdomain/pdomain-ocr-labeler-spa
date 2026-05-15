"""Integration tests for the ``reload_ocr`` job handler.

Spec: ``specs/23-page-payload-backend.md §6`` — the handler runs OCR via
``LocalDoctrPageLoader.run_ocr`` on a worker thread, reports progress at
four fractions (0.0 / 0.1 / 0.9 / 1.0) with stable messages, and stores
the resulting ``PageLoadOutcome`` on
``ProjectState.page_states[idx].page_record``. Failure path emits an
``ocr_failed`` notification and transitions the job to ``error``.

Issue: #307 (spec-23-B1).

These tests inject a fake ``page_loader`` onto ``runner.context`` so the
handler can be exercised end-to-end without pulling DocTR / pd_book_tools
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

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.jobs import JobEventBroker
from pd_ocr_labeler_spa.core.notifications import NotificationKind
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pd_ocr_labeler_spa.settings import Settings


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

"""Integration tests for the ``load_page`` job — page-load progress.

Spec: ``docs/specs/2026-08-08-page-load-progress-design.md`` "Move page
loading onto the job system". Issue:
``docs/issues/2026-08-08-page-load-progress-unbuilt.md``.

Covers the backend-side acceptance criteria from the design's list:

- A named stage appears within the job's first event (not a bare spinner).
- The stage text changes as the work moves (store miss -> engine/OCR).
- A store miss is visible as its own stage.
- An OCR failure reaches the client (the job's terminal ``error`` event with
  ``error_message``) and is distinguishable from a page with no text (which
  terminates ``complete`` instead).
- A page served from a warm store (in-memory hit) returns immediately, with
  no job.
- Project open creates no job.

These tests inject a fake ``page_loader`` onto ``runner.context`` so the
handler can be exercised end-to-end without pulling DocTR / pdomain_book_tools
into the test process — same pattern as
``tests/integration/test_reload_ocr_job.py``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.jobs import JobEventBroker
from pdomain_ocr_labeler_spa.core.notifications import NotificationKind
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.settings import Settings


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
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    (proj / "002.png").write_bytes(b"\x89PNG\r\n")
    return root


class _StoreMissPageLoader:
    """A ``PageLoader`` whose lanes always miss — every load reaches OCR."""

    def __init__(self, *, raise_on_run: Exception | None = None) -> None:
        self.calls: list[int] = []
        self._raise = raise_on_run

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
        self.calls.append(page_index)
        if self._raise is not None:
            raise self._raise
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload={"fake": "page", "idx": page_index},
        )


class _SlowStoreMissPageLoader:
    """Like ``_StoreMissPageLoader``, but ``run_ocr`` sleeps first.

    Gives a concurrent second fetch a wide, deterministic window in which
    the first fetch's job is still queued or running — used to exercise the
    duplicate-job race without needing real multi-threaded orchestration.
    """

    def __init__(self, *, sleep_s: float) -> None:
        self._sleep_s = sleep_s
        self.calls: list[int] = []

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
        self.calls.append(page_index)
        time.sleep(self._sleep_s)
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload={"fake": "page", "idx": page_index},
        )


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
        if any(e.get("event") in ("complete", "error", "cancelled") for e in events):
            return
        time.sleep(0.01)
    raise AssertionError(f"no terminal event after {timeout}s; events={events}")


@pytest.fixture
def loaded_client_with_miss_loader(
    tmp_path: Path, projects_root: Path
) -> Iterator[tuple[TestClient, _StoreMissPageLoader, list[dict[str, Any]]]]:
    """Loaded project + a page_loader whose lanes always miss + broker recorder."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _StoreMissPageLoader()
    recorded: list[dict[str, Any]] = []
    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text
        yield c, loader, recorded


def test_project_open_creates_no_job(tmp_path: Path, projects_root: Path) -> None:
    """Design acceptance criterion: "Project open creates no job."."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text
        assert c.app.state.job_runner.list_jobs() == []  # type: ignore[attr-defined]


def test_store_miss_creates_job_and_returns_pending_payload(
    loaded_client_with_miss_loader: tuple[TestClient, _StoreMissPageLoader, list[dict[str, Any]]],
) -> None:
    """A store miss submits a ``load_page`` job and the GET returns
    immediately with a pending payload rather than blocking for OCR."""
    c, _loader, _events = loaded_client_with_miss_loader

    resp = c.get("/api/projects/book1/pages/0")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_load_job_id"], "expected a job id on a genuine store miss"
    assert body["page_load_error"] is None
    assert body["page_record"] is None
    # The response returned before OCR ran — a race is possible but the
    # common case is the GET beating the background job to run_ocr.
    runner = c.app.state.job_runner  # type: ignore[attr-defined]
    job = runner.get_job(body["page_load_job_id"])
    assert job is not None
    assert job.job_type == "load_page"


def test_first_event_names_the_store_miss_stage(
    loaded_client_with_miss_loader: tuple[TestClient, _StoreMissPageLoader, list[dict[str, Any]]],
) -> None:
    """The job's first published event already names a real stage and
    reports the store miss — design: "shows a named stage within one
    second" and "A store miss is visible as its own stage."."""
    c, _loader, events = loaded_client_with_miss_loader

    resp = c.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text

    _wait_for_terminal(events)

    # Skip the job-runner's own QUEUED -> RUNNING transition event: it has
    # no message and total=0, and is not one of this handler's named
    # stages.
    progress_events = [e for e in events if e.get("event") == "progress" and e["progress"]["message"]]
    assert progress_events, f"expected at least one progress event; got {events}"
    first_message = progress_events[0]["progress"]["message"]
    assert "not found" in first_message.lower()
    assert "running ocr" in first_message.lower()


def test_stage_changes_from_store_miss_to_running_ocr_with_device(
    loaded_client_with_miss_loader: tuple[TestClient, _StoreMissPageLoader, list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stage text changes as work moves — design: "The stage text
    changes as the work moves between model load, store lookup, and OCR."
    Also verifies the device string (``describe_device()``, already used
    for the ``__main__.py`` boot banner) is surfaced in that second stage.
    """
    from pdomain_ocr_labeler_spa.core.jobs.handlers import load_page as load_page_mod

    monkeypatch.setattr(load_page_mod, "resolve_ocr_device_override", lambda: "cuda:0 (TEST GPU)")

    c, _loader, events = loaded_client_with_miss_loader

    resp = c.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text

    _wait_for_terminal(events)

    # Skip the job-runner's own QUEUED -> RUNNING transition event: it has
    # no message and total=0, and is not one of this handler's named
    # stages.
    progress_events = [e for e in events if e.get("event") == "progress" and e["progress"]["message"]]
    messages = [e["progress"]["message"] for e in progress_events]
    assert len(messages) >= 2, f"expected at least two distinct progress stages; got {messages}"
    assert messages[0] != messages[1]
    assert "cuda:0 (test gpu)" in messages[1].lower()
    assert "running ocr" in messages[1].lower()


def test_success_populates_page_record_and_subsequent_get_is_a_hit_with_no_new_job(
    loaded_client_with_miss_loader: tuple[TestClient, _StoreMissPageLoader, list[dict[str, Any]]],
) -> None:
    c, loader, events = loaded_client_with_miss_loader

    resp = c.get("/api/projects/book1/pages/0")
    assert resp.status_code == 200, resp.text
    first_job_id = resp.json()["page_load_job_id"]
    assert first_job_id

    _wait_for_terminal(events)
    assert events[-1].get("event") == "complete", events[-1]

    resp2 = c.get("/api/projects/book1/pages/0")
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["page_load_job_id"] is None, "a hit after the job completed must not submit another job"
    assert body2["page_load_error"] is None

    runner = c.app.state.job_runner  # type: ignore[attr-defined]
    jobs = runner.list_jobs()
    assert len(jobs) == 1, f"expected exactly one load_page job across both fetches, got {len(jobs)}"
    assert loader.calls == [0]


def test_failure_emits_error_event_distinguishable_from_a_no_text_page(
    tmp_path: Path, projects_root: Path
) -> None:
    """Design acceptance criterion: "An OCR failure reaches the screen with
    its error, and is distinguishable from a page with no text." — an OCR
    exception terminates the job ``error`` (with ``error_message``) rather
    than ``complete`` with an empty ``page_record``."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _StoreMissPageLoader(raise_on_run=RuntimeError("doctr exploded"))
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200

        page_resp = c.get("/api/projects/book1/pages/0")
        assert page_resp.status_code == 200, page_resp.text
        job_id = page_resp.json()["page_load_job_id"]
        assert job_id

        _wait_for_terminal(recorded)

        terminal = recorded[-1]
        assert terminal.get("event") == "error", terminal
        # Curated (exception type name only, not str(exc)) — see
        # test_ocr_failure_message_does_not_leak_filesystem_path for the
        # dedicated no-path-leak coverage of this same curation.
        assert "RuntimeError" in (terminal.get("error_message") or ""), terminal
        assert "doctr exploded" not in (terminal.get("error_message") or ""), terminal

        notif_queue = c.app.state.notification_queue  # type: ignore[attr-defined]
        notifications = notif_queue.snapshot()
        ocr_failed = [n for n in notifications if n.kind == NotificationKind.NEGATIVE and "OCR" in n.message]
        assert ocr_failed, (
            f"expected an OCR-failed notification; got {[(n.kind, n.message) for n in notifications]}"
        )

        # page_record stays unset on failure — never confused with a
        # legitimately empty (no-text) page, which would COMPLETE instead.
        project_state = c.app.state.project_state  # type: ignore[attr-defined]
        pstate = project_state.page_states.get(0)
        assert pstate is None or pstate.page_record is None


def test_warm_store_returns_with_no_job_and_no_latency(tmp_path: Path, projects_root: Path) -> None:
    """Design acceptance criterion: "A page served from a warm store still
    returns immediately, with no added latency from the progress machinery,
    and creates no job." — an in-memory hit (the fastest of the two
    synchronous checks) never even builds a loader."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text

        project_state = c.app.state.project_state  # type: ignore[attr-defined]
        project_state._page_states[0] = PageState(
            page_index=0,
            page_record=PageLoadOutcome(
                page_index=0,
                source=PageSource.OCR,
                payload={"fake": "warm page"},
            ),
        )

        page_resp = c.get("/api/projects/book1/pages/0")

        assert page_resp.status_code == 200, page_resp.text
        body = page_resp.json()
        assert body["page_load_job_id"] is None
        assert body["page_load_error"] is None

        runner = c.app.state.job_runner  # type: ignore[attr-defined]
        assert runner.list_jobs() == [], "an in-memory hit must not submit a job"


# ── Duplicate-job regression: concurrent fetches of one cold page ─────────


def test_concurrent_fetches_of_the_same_cold_page_submit_one_job(tmp_path: Path, projects_root: Path) -> None:
    """Two fetches racing a store miss for the same page must share one
    ``load_page`` job, not each submit their own — that would run OCR
    twice with no ordering on which result got written, the exact race
    ``ensure_page_model``'s own docstring says holding the project lock
    across OCR used to prevent (OCR now runs inside the job, off that
    lock). The loader sleeps so the first job is still queued/running when
    the second fetch arrives moments later.
    """
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _SlowStoreMissPageLoader(sleep_s=0.3)

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text

        first = c.get("/api/projects/book1/pages/0")
        second = c.get("/api/projects/book1/pages/0")

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        first_job_id = first.json()["page_load_job_id"]
        second_job_id = second.json()["page_load_job_id"]
        assert first_job_id, "expected a job id on the first fetch"
        assert second_job_id == first_job_id, (
            f"expected the second fetch to reuse the in-flight job, got a different one: "
            f"{first_job_id!r} vs {second_job_id!r}"
        )

        runner = c.app.state.job_runner  # type: ignore[attr-defined]
        assert len(runner.list_jobs()) == 1, "expected exactly one load_page job, not two"
        assert loader.calls == [0], f"expected run_ocr to run once, ran for: {loader.calls}"


def test_a_fetch_after_the_job_fails_submits_a_new_job(tmp_path: Path, projects_root: Path) -> None:
    """A failed load must not permanently block every later attempt at the
    same page: once the in-flight job reaches a terminal ``error`` state,
    the next fetch submits a fresh one."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _StoreMissPageLoader(raise_on_run=RuntimeError("doctr exploded"))
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text

        first = c.get("/api/projects/book1/pages/0")
        assert first.status_code == 200, first.text
        first_job_id = first.json()["page_load_job_id"]
        assert first_job_id

        _wait_for_terminal(recorded)
        assert recorded[-1].get("event") == "error", recorded[-1]

        second = c.get("/api/projects/book1/pages/0")
        assert second.status_code == 200, second.text
        second_job_id = second.json()["page_load_job_id"]
        assert second_job_id, "expected a fresh job after the first one failed"
        assert second_job_id != first_job_id

        runner = c.app.state.job_runner  # type: ignore[attr-defined]
        assert len(runner.list_jobs()) == 2, "expected two distinct load_page jobs"


# ── Path-leak regression: an OCR failure carrying a filesystem path ───────


def test_ocr_failure_message_does_not_leak_filesystem_path(
    tmp_path: Path, projects_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The job's terminal ``error_message`` and its notification are curated
    exactly like the synchronous ``ocr_load_failed`` branch in
    ``api/pages.py`` — the exception type name only, never ``str(exc)`` — so
    a path from an exception like ``LocalDoctrPageLoader.run_ocr``'s
    ``PageImageNotFoundError`` never reaches the client on an ordinary first
    page open. Full detail stays in the server log.
    """
    path_fragment = "/var/lib/pdomain/models/db_resnet50/weights.pt"
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    loader = _StoreMissPageLoader(raise_on_run=RuntimeError(f"failed to read weights at {path_fragment}"))
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text

        with caplog.at_level(logging.WARNING, logger="pdomain_ocr_labeler_spa.core.jobs.handlers.load_page"):
            page_resp = c.get("/api/projects/book1/pages/0")
            assert page_resp.status_code == 200, page_resp.text

            _wait_for_terminal(recorded)

        terminal = recorded[-1]
        assert terminal.get("event") == "error", terminal
        error_message = terminal.get("error_message") or ""
        assert path_fragment not in error_message, (
            f"filesystem path leaked into error_message: {error_message!r}"
        )
        assert "RuntimeError" in error_message, "curated message should still name the exception type"

        notif_queue = c.app.state.notification_queue  # type: ignore[attr-defined]
        notifications = notif_queue.snapshot()
        assert notifications, "expected at least one notification"
        assert all(path_fragment not in n.message for n in notifications), (
            f"filesystem path leaked into a notification: {[n.message for n in notifications]}"
        )

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "expected a WARNING-level log record for the OCR failure"
        record = warnings[0]
        assert record.exc_info is not None, "the WARNING must keep exc_info for the traceback"
        exc = record.exc_info[1]
        assert exc is not None and path_fragment in str(exc), (
            "full detail (the path) must still be recoverable from the WARNING's exc_info"
        )

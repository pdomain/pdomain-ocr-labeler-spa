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

``JobEventBroker`` has no event buffering by design (``core/jobs/events.py``
module docstring): events published before a subscriber registers are gone
for good, so only a subscriber already listening when the job runs sees its
full progress sequence. A late subscriber — the common case for a job this
fast, run against a fake loader — only ever gets the job's current terminal
snapshot via ``GET .../events``, never the intermediate 0.1/0.9 fractions
these tests assert on. (A related but distinct bug — the SSE handler could
hang forever by re-checking a stale, captured-once job reference instead of
a fresh one, subscribing to an already-closed broker channel — was fixed
2026-09-18 by splitting ``subscribe`` into ``listen``/``drain``/``unlisten``;
see ``docs/context/decisions.md``. That fix makes late subscription safe,
not retroactive — it still can't replay history no one recorded.) We
instead wrap ``broker.publish`` to collect every event at the publish site,
which matches what a subscriber registered before the job started would
have seen.
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
        self.page_kind_calls: list[object] = []
        self._raise = raise_on_run

    def run_ocr(
        self,
        page_index: int,
        *,
        edited_image_bytes: bytes | None = None,
        page_kind: object | None = None,
    ) -> PageLoadOutcome:
        self.calls.append(page_index)
        self.page_kind_calls.append(page_kind)
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
        if any(e.get("event") in ("complete", "error", "cancelled") for e in events):
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

    progress_events = [e for e in events if e.get("event") == "progress"]
    fractions = [
        e["progress"]["current"] / e["progress"]["total"] for e in progress_events if e["progress"]["total"]
    ]
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

    assert events[-1].get("event") == "complete", events[-1]
    assert loader.calls == [0]


def test_reload_ocr_passes_the_prior_confirmed_kind_to_run_ocr(
    loaded_client_with_loader: tuple[TestClient, _FakePageLoader, list[dict[str, Any]]],
) -> None:
    """pdomain-ocr-synth's 2026-09-17-page-kind-review-design.md "Re-OCR and
    rotation keep the confirmed kind": reload OCR reads the page's prior
    confirmed kind from state before it runs OCR and passes it through.
    """
    from types import SimpleNamespace

    from pdomain_book_contracts.annotation import PageKind

    c, loader, events = loaded_client_with_loader
    project_state = c.app.state.project_state  # type: ignore[attr-defined]
    from pdomain_ocr_labeler_spa.core.project_state import PageState

    pstate = PageState(
        page_index=0,
        page_record=PageLoadOutcome(
            page_index=0, source=PageSource.OCR, payload=SimpleNamespace(page_kind=PageKind.BODY)
        ),
    )
    project_state._page_states[0] = pstate

    ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
    assert ocr_resp.status_code == 202

    _wait_for_terminal(events)
    assert events[-1].get("event") == "complete", events[-1]
    assert loader.page_kind_calls == [PageKind.BODY]


def test_reload_ocr_passes_none_when_the_page_has_no_confirmed_kind(
    loaded_client_with_loader: tuple[TestClient, _FakePageLoader, list[dict[str, Any]]],
) -> None:
    c, loader, events = loaded_client_with_loader

    ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
    assert ocr_resp.status_code == 202

    _wait_for_terminal(events)
    assert events[-1].get("event") == "complete", events[-1]
    assert loader.page_kind_calls == [None]


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
    assert events[-1].get("event") == "complete", events[-1]

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
        assert terminal.get("event") == "error", terminal
        assert "doctr exploded" in (terminal.get("error_message") or ""), terminal

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
        assert recorded[-1].get("event") == "complete", recorded[-1]
        assert loader.calls == [0]


# OCR timeout contract: docs/architecture/02-backend.md


class _SlowPageLoader:
    """Stand-in ``PageLoader`` whose ``run_ocr`` sleeps past a tiny timeout."""

    def __init__(self, *, sleep_s: float) -> None:
        self._sleep_s = sleep_s
        self.calls: list[int] = []

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
        assert terminal.get("event") == "error", terminal
        assert "timed out" in (terminal.get("error_message") or "").lower(), terminal

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


def test_reload_ocr_recheck_saves_a_confirm_that_landed_during_ocr(
    tmp_path: Path, projects_root: Path
) -> None:
    """pdomain-ocr-synth's 2026-09-17-page-kind-review-design.md "Re-OCR and
    rotation keep the confirmed kind" — the re-OCR race (finding 1): a confirm
    that lands on the OLD page while ``run_ocr`` is in flight (no lock held)
    must still be reflected in the fresh page's stored content, so the page
    blob's kind and the latest reviewed marker agree afterward.

    The fake loader's ``run_ocr`` confirms the OLD page (via the same shared
    ``_confirm_page_kind_locked`` the routes use) before it returns the fresh
    OCR outcome carrying the STALE kind — simulating a confirm request that
    completed while OCR ran.
    """
    from pdomain_book_contracts.annotation import PageKind
    from pdomain_book_tools.ocr.page import Page

    from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
    from pdomain_ocr_labeler_spa.api._page_content import load_page_from_store
    from pdomain_ocr_labeler_spa.api.pages import _confirm_page_kind_locked
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
    from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
    from pdomain_ocr_labeler_spa.core.project_state import PageState

    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    recorded: list[dict[str, Any]] = []

    with TestClient(app) as c:
        _wrap_broker_publish(c.app.state.job_events, recorded)  # type: ignore[attr-defined]
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text

        project_state: ProjectState = c.app.state.project_state  # type: ignore[attr-defined]
        page_store: LabelerPageStore = c.app.state.page_store  # type: ignore[attr-defined]
        project = project_state.loaded_project
        assert project is not None

        # Seed page 0 as already OCR'd + confirmed "body", store-backed.
        old_page = Page(width=100, height=100, page_index=0, blocks=[])
        old_page.page_kind = PageKind.BODY
        old_agg = _ingest_ocr_result(
            page=old_page,
            image_bytes=b"\x89PNG\r\n",
            page_index=0,
            store=page_store,
            project=project,
        )
        old_pstate = PageState(
            page_index=0,
            page_record=PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=old_page),
        )
        old_pstate.page_id = old_agg.record.page_id
        project_state._page_states[0] = old_pstate

        class _RaceLoader:
            """``PageLoader`` double that confirms the OLD page mid-``run_ocr``."""

            def __init__(self) -> None:
                self.calls: list[int] = []

            def run_ocr(
                self,
                page_index: int,
                *,
                edited_image_bytes: bytes | None = None,
                page_kind: PageKind | None = None,
            ) -> PageLoadOutcome:
                self.calls.append(page_index)

                # A confirm lands on the OLD page while this "OCR" is in flight.
                error = _confirm_page_kind_locked(
                    project_root=project.project_root,
                    project_state=project_state,
                    page_index=page_index,
                    page_store=page_store,
                    kind=PageKind.TITLE_PAGE,
                    note=None,
                    method="single",
                )
                assert error is None, error

                # The fresh OCR result still carries the STALE kind read
                # before OCR started — exactly the race this test simulates.
                fresh_page = Page(width=100, height=100, page_index=page_index, blocks=[])
                fresh_page.page_kind = page_kind
                agg = _ingest_ocr_result(
                    page=fresh_page,
                    image_bytes=b"\x89PNG\r\n",
                    page_index=page_index,
                    store=page_store,
                    project=project,
                )
                object.__setattr__(fresh_page, "_labeler_page_id", agg.record.page_id)
                return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=fresh_page)

            def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
                return None

            def load_cached(self, page_index: int) -> PageLoadOutcome | None:
                return None

        loader = _RaceLoader()
        c.app.state.job_runner.context["page_loader"] = loader  # type: ignore[attr-defined]

        ocr_resp = c.post("/api/projects/book1/pages/0/reload-ocr", json={})
        assert ocr_resp.status_code == 202, ocr_resp.text

        _wait_for_terminal(recorded)
        assert recorded[-1].get("event") == "complete", recorded[-1]

        pstate_after = project_state.page_states.get(0)
        assert pstate_after is not None
        new_page_id = pstate_after.page_id
        assert new_page_id is not None
        assert new_page_id != old_agg.record.page_id

        marker = PageKindReviewedStore(projects_root / "book1").latest_for_page(0)
        assert marker is not None
        assert marker.kind == PageKind.TITLE_PAGE

        fresh_store = LabelerPageStore(project_dir=projects_root / "book1")
        try:
            reloaded = load_page_from_store(fresh_store, new_page_id)
        finally:
            fresh_store.close()
        assert reloaded is not None
        assert reloaded.page_kind == PageKind.TITLE_PAGE, (
            "the fresh page's stored content must agree with the latest reviewed marker"
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

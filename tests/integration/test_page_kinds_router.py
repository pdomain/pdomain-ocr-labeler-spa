"""Integration tests for the book-wide page-kinds routes.

Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
"One route lists every page's kind" / "One route confirms many pages".

Pattern mirrors ``tests/unit/api/test_b1_b3_f1.py``: a ``_FakePageLoader`` is
injected onto ``runner.context["page_loader"]`` so tests stay fast and
network-free, and ``tests/unit/api/test_page_kind_endpoint.py``'s
``_ingest_ocr_result`` seeding for store-backed pages.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pdomain_book_contracts.annotation import PageKind
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog
from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState
from pdomain_ocr_labeler_spa.settings import Settings

_TOTAL_PAGES = 4


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
    for i in range(1, _TOTAL_PAGES + 1):
        (proj / f"{i:03d}.png").write_bytes(b"\x89PNG\r\n")
    return root


class _FakePageLoader:
    """Records calls; ``load_cached``/``load_labeled`` answer from fixed maps.

    ``run_ocr`` must never be called by the bulk-confirm route
    (``allow_ocr=False``) — it raises if it ever is, so a bug shows up as a
    loud test failure rather than a silent GPU-OCR side effect.
    """

    def __init__(self) -> None:
        self.run_ocr_calls: list[int] = []
        self.load_labeled_calls: list[int] = []
        self.load_cached_calls: list[int] = []
        self.cached_hits: dict[int, PageLoadOutcome] = {}

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        self.load_labeled_calls.append(page_index)
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        self.load_cached_calls.append(page_index)
        return self.cached_hits.get(page_index)

    def run_ocr(
        self, page_index: int, *, edited_image_bytes: bytes | None = None, page_kind: PageKind | None = None
    ) -> PageLoadOutcome:
        self.run_ocr_calls.append(page_index)
        raise RuntimeError("run_ocr must never be called by the bulk page-kind confirm route")


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        c.app.state.job_runner.context["page_loader"] = _FakePageLoader()  # type: ignore[attr-defined]
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / "book1")})
        assert resp.status_code == 200, resp.text
        yield c


def _loader(client: TestClient) -> _FakePageLoader:
    return client.app.state.job_runner.context["page_loader"]  # type: ignore[attr-defined,no-any-return]


def _project_state(client: TestClient) -> ProjectState:
    return client.app.state.project_state  # type: ignore[attr-defined,no-any-return]


def _page_store(client: TestClient) -> LabelerPageStore:
    return client.app.state.page_store  # type: ignore[attr-defined,no-any-return]


def _seed_store_backed_page(client: TestClient, page_index: int) -> tuple[Page, UUID]:
    """Ingest a real page into the store and return it (not yet in-memory)."""
    project_state = _project_state(client)
    store = _page_store(client)
    page = Page(width=100, height=100, page_index=page_index, blocks=[])
    aggregate = _ingest_ocr_result(
        page=page,
        image_bytes=b"\x89PNG\r\n",
        page_index=page_index,
        store=store,
        project=project_state.loaded_project,
    )
    page_id = aggregate.id
    return page, page_id


def _seed_loaded_page(client: TestClient, page_index: int) -> PageState:
    """A page already in memory, store-backed, ready to confirm directly."""
    project_state = _project_state(client)
    page, page_id = _seed_store_backed_page(client, page_index)
    outcome = PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=page)
    pstate = PageState(page_index=page_index, page_record=outcome)
    pstate.page_id = page_id
    project_state._page_states[page_index] = pstate
    return pstate


def _seed_cache_hit_store_backed(client: TestClient, page_index: int) -> None:
    """A page not yet in memory, but loadable via the cache lane and store-backed."""
    page, page_id = _seed_store_backed_page(client, page_index)
    object.__setattr__(page, "_labeler_page_id", page_id)
    _loader(client).cached_hits[page_index] = PageLoadOutcome(
        page_index=page_index, source=PageSource.CACHED_OCR, payload=page
    )


def _seed_cache_hit_not_store_backed(client: TestClient, page_index: int) -> None:
    """A page loadable via the cache lane, but with no page_id stamped."""
    page = Page(width=100, height=100, page_index=page_index, blocks=[])
    _loader(client).cached_hits[page_index] = PageLoadOutcome(
        page_index=page_index, source=PageSource.CACHED_OCR, payload=page
    )


# ── GET /page-kinds ───────────────────────────────────────────────────────


def test_every_page_appears_including_pages_with_no_proposal(loaded_client: TestClient) -> None:
    resp = loaded_client.get("/api/projects/book1/page-kinds")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_pages"] == _TOTAL_PAGES
    assert [row["page_index"] for row in body["pages"]] == list(range(_TOTAL_PAGES))


def test_confirmed_kind_comes_from_the_live_page_when_loaded(loaded_client: TestClient) -> None:
    project_state = _project_state(loaded_client)
    pstate = _seed_loaded_page(loaded_client, 0)
    page = pstate.page_record.payload
    assert isinstance(page, Page)
    page.page_kind = PageKind.TITLE_PAGE
    PageKindReviewedStore(project_state.loaded_project.project_root).mark_reviewed(
        0, "2026-09-08T10:00:00+00:00", kind=PageKind.TITLE_PAGE, method="single"
    )

    resp = loaded_client.get("/api/projects/book1/page-kinds")
    row = next(r for r in resp.json()["pages"] if r["page_index"] == 0)
    assert row["confirmed_kind"] == "title page"
    assert row["reviewed"] is True


def test_a_reviewed_unloaded_page_reports_kind_from_the_marker(loaded_client: TestClient) -> None:
    project_state = _project_state(loaded_client)
    PageKindReviewedStore(project_state.loaded_project.project_root).mark_reviewed(
        1, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="bulk"
    )

    resp = loaded_client.get("/api/projects/book1/page-kinds")
    row = next(r for r in resp.json()["pages"] if r["page_index"] == 1)
    assert row["confirmed_kind"] == "body"
    assert row["reviewed"] is True


def test_a_reviewed_unloaded_page_with_no_kind_on_its_marker_reports_kind_not_recorded(
    loaded_client: TestClient,
) -> None:
    """pdomain-ocr-synth's 2026-09-17-page-kind-review-design.md: a reviewed
    marker predating the ``kind`` field, on an unloaded page, reports
    ``confirmed_kind: null`` with ``reviewed: true``.
    """
    project_state = _project_state(loaded_client)
    PageKindReviewedStore(project_state.loaded_project.project_root).mark_reviewed(
        1, "2026-09-08T10:00:00+00:00"
    )

    resp = loaded_client.get("/api/projects/book1/page-kinds")
    row = next(r for r in resp.json()["pages"] if r["page_index"] == 1)
    assert row["confirmed_kind"] is None
    assert row["reviewed"] is True


def test_a_withdrawn_review_reports_unreviewed(loaded_client: TestClient) -> None:
    project_state = _project_state(loaded_client)
    store = PageKindReviewedStore(project_state.loaded_project.project_root)
    store.mark_reviewed(1, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single")
    store.mark_reviewed(1, "2026-09-08T11:00:00+00:00", kind=None, method="history")

    resp = loaded_client.get("/api/projects/book1/page-kinds")
    row = next(r for r in resp.json()["pages"] if r["page_index"] == 1)
    assert row["confirmed_kind"] is None
    assert row["reviewed"] is False


def test_reviewed_count_counts_only_live_reviews(loaded_client: TestClient) -> None:
    project_state = _project_state(loaded_client)
    store = PageKindReviewedStore(project_state.loaded_project.project_root)
    store.mark_reviewed(0, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single")
    store.mark_reviewed(1, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single")
    store.mark_reviewed(1, "2026-09-08T11:00:00+00:00", kind=None, method="history")

    resp = loaded_client.get("/api/projects/book1/page-kinds")
    assert resp.json()["reviewed_count"] == 1


def test_a_proposed_page_reports_its_proposal(loaded_client: TestClient) -> None:
    from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal, PageKindProposalRun

    project_state = _project_state(loaded_client)
    log = PageKindProposalLog(project_state.loaded_project.project_root)
    log.append_run(
        PageKindProposalRun(
            run_id="r1",
            model_id="m",
            model_version="v1",
            created_at="2026-09-08T10:00:00+00:00",
            page_count=1,
        )
    )
    log.append_proposals(
        [
            PageKindProposal(
                proposal_id="p1", run_id="r1", page_index=2, kind=PageKind.BODY, confidence=0.7, evidence={}
            )
        ]
    )

    resp = loaded_client.get("/api/projects/book1/page-kinds")
    row = next(r for r in resp.json()["pages"] if r["page_index"] == 2)
    assert row["proposed_kind"] == "body"
    assert row["confidence"] == 0.7
    assert row["run_id"] == "r1"


def test_a_page_with_no_proposal_reports_nulls(loaded_client: TestClient) -> None:
    resp = loaded_client.get("/api/projects/book1/page-kinds")
    row = next(r for r in resp.json()["pages"] if r["page_index"] == 3)
    assert row["proposed_kind"] is None
    assert row["confidence"] is None
    assert row["run_id"] is None


def test_page_kinds_reads_each_journal_once_per_request(
    loaded_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Follows ``test_review_queue_reads_each_journal_once_per_request`` in
    tests/integration/test_region_proposals_router.py.
    """
    project_state = _project_state(loaded_client)
    project_root = project_state.loaded_project.project_root
    PageKindReviewedStore(project_root).mark_reviewed(0, "2026-09-08T10:00:00+00:00")

    from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal, PageKindProposalRun

    log = PageKindProposalLog(project_root)
    log.append_run(
        PageKindProposalRun(
            run_id="r1",
            model_id="m",
            model_version="v1",
            created_at="2026-09-08T10:00:00+00:00",
            page_count=1,
        )
    )
    log.append_proposals(
        [
            PageKindProposal(
                proposal_id="p1", run_id="r1", page_index=1, kind=PageKind.BODY, confidence=0.7, evidence={}
            )
        ]
    )

    proposal_reads = 0
    original_proposal_read = PageKindProposalLog._read

    def _counting_proposal_read(self: PageKindProposalLog) -> list[Any]:
        nonlocal proposal_reads
        proposal_reads += 1
        return original_proposal_read(self)

    monkeypatch.setattr(PageKindProposalLog, "_read", _counting_proposal_read)

    reviewed_reads = 0
    original_reviewed_read = PageKindReviewedStore._read

    def _counting_reviewed_read(self: PageKindReviewedStore) -> list[Any]:
        nonlocal reviewed_reads
        reviewed_reads += 1
        return original_reviewed_read(self)

    monkeypatch.setattr(PageKindReviewedStore, "_read", _counting_reviewed_read)

    resp = loaded_client.get("/api/projects/book1/page-kinds")

    assert resp.status_code == 200, resp.text
    assert proposal_reads == 1
    assert reviewed_reads == 1


def test_page_kinds_returns_404_for_an_unloaded_project(loaded_client: TestClient) -> None:
    resp = loaded_client.get("/api/projects/other_book/page-kinds")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "project_not_found"


# ── POST /page-kinds/confirm ────────────────────────────────────────────


def test_bulk_confirm_marks_an_already_loaded_page(loaded_client: TestClient, projects_root: Path) -> None:
    _seed_loaded_page(loaded_client, 0)

    resp = loaded_client.post(
        "/api/projects/book1/page-kinds/confirm",
        json={"pages": [{"page_index": 0, "kind": "body"}], "note": "batch 1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["confirmed_count"] == 1
    assert body["results"] == [{"page_index": 0, "status": "confirmed"}]

    marker = PageKindReviewedStore(projects_root / "book1").latest_for_page(0)
    assert marker is not None
    assert marker.kind == PageKind.BODY
    assert marker.method == "bulk"
    assert marker.note == "batch 1"


def test_bulk_confirm_loads_an_unloaded_page_via_the_cache_lane(loaded_client: TestClient) -> None:
    _seed_cache_hit_store_backed(loaded_client, 2)

    resp = loaded_client.post(
        "/api/projects/book1/page-kinds/confirm",
        json={"pages": [{"page_index": 2, "kind": "body"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"] == [{"page_index": 2, "status": "confirmed"}]
    assert _loader(loaded_client).run_ocr_calls == []


def test_bulk_confirm_reports_not_loaded_when_neither_lane_has_content(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/page-kinds/confirm",
        json={"pages": [{"page_index": 3, "kind": "body"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"] == [{"page_index": 3, "status": "not_loaded"}]
    assert _loader(loaded_client).run_ocr_calls == []


def test_bulk_confirm_reports_store_unavailable_when_loaded_page_has_no_page_id(
    loaded_client: TestClient,
) -> None:
    _seed_cache_hit_not_store_backed(loaded_client, 1)

    resp = loaded_client.post(
        "/api/projects/book1/page-kinds/confirm",
        json={"pages": [{"page_index": 1, "kind": "body"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"] == [{"page_index": 1, "status": "store_unavailable"}]


def test_bulk_confirm_reports_persist_failed_and_restores_the_prior_kind(
    loaded_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pdomain_ocr_labeler_spa.api.pages as pages_module

    pstate = _seed_loaded_page(loaded_client, 0)
    page = pstate.page_record.payload
    assert isinstance(page, Page)
    prior_kind = page.page_kind

    def _raise(**_kwargs: object) -> str:
        raise RuntimeError("simulated store failure")

    monkeypatch.setattr(pages_module, "save_page_content_to_store", _raise)

    resp = loaded_client.post(
        "/api/projects/book1/page-kinds/confirm",
        json={"pages": [{"page_index": 0, "kind": "body"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"] == [{"page_index": 0, "status": "persist_failed"}]
    assert page.page_kind == prior_kind
    assert (
        PageKindReviewedStore(_project_state(loaded_client).loaded_project.project_root).latest_for_page(0)
        is None
    )


def test_bulk_confirm_runs_every_page_and_never_calls_run_ocr(loaded_client: TestClient) -> None:
    """The one mixed-batch test covering all four statuses in one request."""
    _seed_loaded_page(loaded_client, 0)
    _seed_cache_hit_not_store_backed(loaded_client, 1)
    _seed_cache_hit_store_backed(loaded_client, 2)
    # page 3: neither lane has content.

    resp = loaded_client.post(
        "/api/projects/book1/page-kinds/confirm",
        json={
            "pages": [
                {"page_index": 0, "kind": "body"},
                {"page_index": 1, "kind": "body"},
                {"page_index": 2, "kind": "body"},
                {"page_index": 3, "kind": "body"},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    statuses = {row["page_index"]: row["status"] for row in resp.json()["results"]}
    assert statuses == {0: "confirmed", 1: "store_unavailable", 2: "confirmed", 3: "not_loaded"}
    assert resp.json()["confirmed_count"] == 2
    assert _loader(loaded_client).run_ocr_calls == []


def test_bulk_confirm_rejects_an_out_of_range_index_before_any_write(
    loaded_client: TestClient, projects_root: Path
) -> None:
    _seed_loaded_page(loaded_client, 0)

    resp = loaded_client.post(
        "/api/projects/book1/page-kinds/confirm",
        json={"pages": [{"page_index": 0, "kind": "body"}, {"page_index": 99, "kind": "body"}]},
    )
    assert resp.status_code == 400, resp.text
    assert PageKindReviewedStore(projects_root / "book1").latest_for_page(0) is None


def test_bulk_confirm_rejects_a_duplicate_index_before_any_write(
    loaded_client: TestClient, projects_root: Path
) -> None:
    _seed_loaded_page(loaded_client, 0)

    resp = loaded_client.post(
        "/api/projects/book1/page-kinds/confirm",
        json={"pages": [{"page_index": 0, "kind": "body"}, {"page_index": 0, "kind": "unknown"}]},
    )
    assert resp.status_code == 400, resp.text
    assert PageKindReviewedStore(projects_root / "book1").latest_for_page(0) is None


def test_bulk_confirm_returns_404_for_an_unloaded_project(loaded_client: TestClient) -> None:
    resp = loaded_client.post(
        "/api/projects/other_book/page-kinds/confirm",
        json={"pages": [{"page_index": 0, "kind": "body"}]},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "project_not_found"

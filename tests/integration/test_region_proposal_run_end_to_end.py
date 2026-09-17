"""The whole chain: page kinds proposed, one confirmed, regions proposed, proposals listed.

Nothing else exercises the page-kind job and the region job together, and they
are ordered: a page whose kind was never proposed or confirmed gets no region
proposals. This is the test that fails if that ordering breaks.
"""

from __future__ import annotations

from typing import Any


def test_the_default_detector_is_the_furniture_detector(toolbar_loaded: Any) -> None:
    from pdomain_ocr_labeler_spa.core.regions.furniture import FurnitureDetector

    client, _project_state, _page = toolbar_loaded
    runner = client.app.state.job_runner
    assert isinstance(runner.context["region_detector"], FurnitureDetector)


def test_a_confirmed_page_kind_lets_a_region_run_reach_that_page(toolbar_loaded: Any) -> None:
    """The ordering the design depends on, exercised through the real routes."""
    import asyncio
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
    from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog

    client, project_state, _page = toolbar_loaded
    runner = client.app.state.job_runner
    project = project_state.loaded_project
    assert project is not None

    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    job = Job(
        job_id="e2e-job",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    asyncio.run(handle_propose_regions(runner, job))

    runs = RegionProposalLog(project.project_root).runs()
    assert len(runs) == 1
    assert 0 in runs[0].page_facet_digests


def test_listing_proposals_returns_what_the_run_wrote(toolbar_loaded: Any) -> None:
    import asyncio
    from datetime import UTC, datetime

    from pdomain_book_contracts.annotation import RegionRole

    from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobStatus
    from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
    from pdomain_ocr_labeler_spa.core.regions.detector import DetectedRegion, DetectorInput

    client, project_state, _page = toolbar_loaded
    runner = client.app.state.job_runner
    project = project_state.loaded_project
    assert project is not None
    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())

    def _one_header(detector_input: DetectorInput) -> list[DetectedRegion]:
        del detector_input
        return [
            DetectedRegion(
                role=RegionRole.PAGE_HEADER,
                box=(10, 5, 90, 20),
                confidence=0.7,
                evidence={"signal": "end-to-end"},
            )
        ]

    runner.context["region_detector"] = _one_header
    job = Job(
        job_id="e2e-job-2",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    asyncio.run(handle_propose_regions(runner, job))

    response = client.get("/api/projects/book1/pages/0/regions/proposals")
    assert response.status_code == 200, response.text
    proposals = response.json()["proposals"]
    assert len(proposals) == 1
    assert proposals[0]["role"] == "page header"
    assert proposals[0]["confidence"] == 0.7
    assert proposals[0]["disposition"] is None

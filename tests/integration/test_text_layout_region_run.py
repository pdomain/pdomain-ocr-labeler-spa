"""Text evidence uses the existing book-scoped journal and browser payload."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
from pdomain_ocr_labeler_spa.core.jobs.runner import Job, JobRunner, JobStatus
from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
from pdomain_ocr_labeler_spa.core.regions.models import FACET_LAYOUT_EVIDENCE, FACET_WORD_TEXT
from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog
from pdomain_ocr_labeler_spa.core.regions.text_layout import TextLayoutDetector

if TYPE_CHECKING:
    from pathlib import Path


def test_f2_job_and_page_payload_use_the_real_evidence_resolver(
    toolbar_loaded: tuple[TestClient, ProjectState, Page],
    tmp_path: Path,
) -> None:
    client, state, page = toolbar_loaded
    project = state.loaded_project
    assert project is not None
    # Source words are taken directly from the real loaded OCR hierarchy.
    text = " ".join(word.ground_truth_text or word.text for word in page.words)
    assert text
    rounds = project.project_root / "rounds"
    rounds.mkdir()
    (rounds / "F2.json").write_text(json.dumps({project.image_paths[0].name: f"/*{text}*/"}))
    state.page_states[0].page_record = PageLoadOutcome(page_index=0, source=PageSource.OCR, payload=page)
    PageKindReviewedStore(project.project_root).mark_reviewed(0, datetime.now(UTC).isoformat())
    app = client.app
    assert isinstance(app, FastAPI)
    runner = app.state.job_runner
    assert isinstance(runner, JobRunner)
    runner.context["region_detector"] = TextLayoutDetector()
    job = Job(
        job_id="text-layout-run",
        job_type="propose_regions",
        status=JobStatus.RUNNING,
        project_id=project.project_id,
        payload={"project_id": project.project_id},
        created_at=datetime.now(UTC),
    )
    runner._jobs[job.job_id] = job
    asyncio.run(handle_propose_regions(runner, job))
    journal = RegionProposalLog(project.project_root)
    assert len(journal.runs()) == 1
    assert {FACET_WORD_TEXT, FACET_LAYOUT_EVIDENCE} <= journal.runs()[0].depends_on
    proposal = journal.proposals()[0]
    assert proposal.evidence["layout_hints"][0]["source"] == "f2"
    assert proposal.evidence["structure_supported"] is False
    response = client.get(f"/api/projects/{project.project_id}/pages/0")
    assert response.status_code == 200
    assert response.json()["layout_hints"][0]["source"] == "f2"
    # Changing source evidence, without touching OCR, invalidates the run.
    (rounds / "F2.json").write_text(json.dumps({project.image_paths[0].name: "plain text"}))
    proposals = client.get(f"/api/projects/{project.project_id}/pages/0")
    assert proposals.status_code == 200
    assert proposals.json()["regions"][0]["stale"] is True

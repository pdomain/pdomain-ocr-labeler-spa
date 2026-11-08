"""Bounded source/OCR matching outside locks, with a checked durable final commit."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import TYPE_CHECKING

from pdomain_book_tools.ocr.page import Page

from ...automation.service import AutomationService
from ...persistence.page_store import LabelerPageStore
from ...project_state import ProjectState
from ...source_alignment import (
    align_source_page,
    carry_group_reviews,
    load_source_evidence,
    ocr_signature,
    persist_alignment,
)
from ._labeling_page_lease import leased_labeling_page

if TYPE_CHECKING:
    from ..runner import Job, JobRunner


async def handle_source_alignment(runner: JobRunner, job: Job) -> None:
    project_state: object = runner.context.get("project_state")
    if not isinstance(project_state, ProjectState):
        raise RuntimeError("source_alignment requires project_state")
    page_index: object = job.payload.get("page_index")
    expected: object = job.payload.get("expected_generation")
    if not isinstance(page_index, int) or not isinstance(expected, int):
        raise ValueError("source_alignment requires page_index and expected_generation")
    if runner.is_cancelled(job.job_id):
        return
    with project_state.mutation_lock, project_state.get_page_lock(page_index):
        project = project_state.loaded_project
        pstate = project_state.get_page_state(page_index)
        if (
            project is None
            or project.project_id != job.project_id
            or pstate is None
            or pstate.page_record is None
        ):
            raise ValueError("Project/page changed before source alignment started")
        if pstate.generation != expected:
            raise ValueError("Page generation changed before source alignment started")
        page = pstate.page_record.payload
        if not isinstance(page, Page):
            raise ValueError("Load OCR before starting source alignment")
        with leased_labeling_page(project_state, page_index):
            evidence = load_source_evidence(project_state, page_index)
        if evidence is None:
            raise ValueError("Prepared F2/P3 source alignment evidence is unavailable")
        project_generation = project_state.generation
        previous = pstate.source_alignment
        signature = ocr_signature(page)
        snapshot = Page.from_dict(page.to_dict())
    await runner.update_progress(job.job_id, current=0, total=1, message="Matching P3 to current scan OCR")
    result = await asyncio.to_thread(align_source_page, evidence, page=snapshot, generation=expected)
    result = carry_group_reviews(previous, result)
    if runner.is_cancelled(job.job_id):
        return
    automation: object = runner.context.get("automation")
    broker = automation.broker if isinstance(automation, AutomationService) else None
    store: object = runner.context.get("page_store")
    with (
        broker.lock if broker is not None else nullcontext(),
        project_state.mutation_lock,
        project_state.get_page_lock(page_index),
    ):
        current = project_state.get_page_state(page_index)
        if runner.is_cancelled(job.job_id):
            return
        if (
            project_state.loaded_project is not project
            or project_state.generation != project_generation
            or current is not pstate
        ):
            raise ValueError("Project changed while source alignment was running")
        if pstate.generation != expected or ocr_signature(page) != signature:
            raise ValueError("Page generation/OCR changed while source alignment was running")
        persist_alignment(
            state=pstate,
            page=page,
            result=result,
            store=store if isinstance(store, LabelerPageStore) else None,
        )
        generation = pstate.generation
        if broker is not None:
            _ = broker.publish(
                "page_changed", project_id=job.project_id, page_index=page_index, generation=generation
            )
    await runner.update_progress(
        job.job_id,
        current=1,
        total=1,
        message="Source alignment ready for review",
        result={
            "result_id": result.result_id,
            "generation": generation,
            "disposition": result.alignment.disposition.value,
            "group_count": len(result.groups),
            "unresolved_count": len(result.projection.unresolved),
            "warnings": list(result.warnings),
        },
    )

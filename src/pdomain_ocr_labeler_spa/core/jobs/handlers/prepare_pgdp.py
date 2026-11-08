"""Prepare selected real corpus pages through the configured JSON bridge."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, JsonValue, TypeAdapter

from ....adapters.source_data import SourceDataBridge, SourceDataError

if TYPE_CHECKING:
    from ..runner import Job, JobRunner


class PreparationResult(BaseModel):
    project_id: str
    book_path: str
    manifest_path: str
    page_keys: list[str]
    alignment_summaries: list[dict[str, JsonValue]]
    warnings: list[str]


async def handle_prepare_pgdp(runner: JobRunner, job: Job) -> None:
    bridge: object = runner.context.get("source_data")
    if not isinstance(bridge, SourceDataBridge):
        raise RuntimeError("source_data bridge is not configured")
    project_id: object = job.payload.get("project_id")
    if not isinstance(project_id, str):
        raise ValueError("invalid preparation job payload")
    keys = TypeAdapter[list[str]](list[str]).validate_python(job.payload.get("page_keys"))
    if runner.is_cancelled(job.job_id):
        return
    await runner.update_progress(job.job_id, current=0, total=1, message="Preparing selected PGDP pages")
    try:
        result = await bridge.call(
            {"command": "prepare", "project_id": project_id, "page_keys": keys},
            cancelled=lambda: runner.is_cancelled(job.job_id),
        )
    except SourceDataError as exc:
        if not runner.is_cancelled(job.job_id):
            await runner.update_progress(
                job.job_id,
                current=0,
                total=1,
                result={"source_error": {"error": exc.code, "message": str(exc), "details": exc.details}},
            )
        raise
    prepared = PreparationResult.model_validate(result)
    if runner.is_cancelled(job.job_id):
        return
    await runner.update_progress(
        job.job_id, current=1, total=1, message="PGDP book prepared", result=prepared.model_dump(mode="json")
    )

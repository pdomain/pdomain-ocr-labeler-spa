"""Export frozen confirmed-region review without exporting OCR training crops."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from pdomain_book_tools.ocr.page import Page
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from ....settings import Settings

if TYPE_CHECKING:
    from typing import ClassVar

    from ..runner import Job, JobRunner


class RegionExportPage(BaseModel):
    """A saved page snapshot captured under its page lock at submission."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
    prefix: str
    page_json: str

    @classmethod
    def from_page(cls, page: Page, *, prefix: str) -> RegionExportPage:
        return cls(prefix=prefix, page_json=json.dumps(page.to_dict()))


async def handle_region_export(runner: JobRunner, job: Job) -> None:
    """Replace exported page entries with their current confirmed review."""
    from .export import append_confirmed_regions, export_output_dir

    settings = runner.context.get("settings")
    if not isinstance(settings, Settings):
        raise RuntimeError("Region export requires settings")
    snapshots = TypeAdapter(list[RegionExportPage]).validate_python(job.payload.get("region_pages"))
    output = export_output_dir(settings.data_root, job.project_id or "", "all")
    count = 0
    for index, snapshot in enumerate(snapshots):
        if runner.is_cancelled(job.job_id):
            return
        page_data = TypeAdapter(dict[str, JsonValue]).validate_json(snapshot.page_json)
        page = Page.from_dict(page_data)
        count += append_confirmed_regions(page, output, prefix=snapshot.prefix)
        await runner.update_progress(
            job.job_id,
            current=index + 1,
            total=len(snapshots),
            message=f"Exported reviewed regions for {index + 1} pages",
            result={"regions": count, "output_dir": str(output)},
        )
        await asyncio.sleep(0)

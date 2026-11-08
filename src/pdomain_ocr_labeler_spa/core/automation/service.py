"""Application snapshots over the shared successful-mutation boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from pydantic import BaseModel, Field, JsonValue

from ..jobs.runner import JobRunner, to_public_job
from ..models import Job, Project
from ..project_state import ProjectState
from .events import AutomationBroker
from .viewers import ReadyView, ViewerRegistry, ViewerState

if TYPE_CHECKING:
    from collections.abc import Callable


class PageReadiness(BaseModel):
    page_index: int
    generation: int
    ready: bool
    page_load_job_id: str | None = None


class AutomationState(BaseModel):
    revision: int
    project: Project | None
    current_page_index: int | None
    project_generation: int
    pages: list[PageReadiness]
    jobs: list[Job]
    capabilities: dict[str, JsonValue] = Field(default_factory=dict)
    viewers: list[ViewerState]


@final
class AutomationService:
    def __init__(
        self,
        *,
        project_state: ProjectState,
        runner: JobRunner,
        ready_view: Callable[[str, int], ReadyView | None] | None = None,
        capabilities: dict[str, JsonValue] | Callable[[], dict[str, JsonValue]] | None = None,
    ) -> None:
        self.broker = AutomationBroker()
        self.project_state = project_state
        self.runner = runner
        self.capabilities: dict[str, JsonValue] | Callable[[], dict[str, JsonValue]] = capabilities or {}
        self.viewers = ViewerRegistry(self.broker, ready_view or self._ready_view)

    def _ready_view(self, project_id: str, page_index: int) -> ReadyView | None:
        project = self.project_state.loaded_project
        if project is None or project.project_id != project_id or not 0 <= page_index < project.total_pages:
            return None
        state = self.project_state.get_page_state(page_index)
        return ReadyView(
            project_id=project_id,
            page_index=page_index,
            generation=state.generation if state is not None else 0,
            ready=state is not None and state.page_record is not None,
        )

    def snapshot(self) -> AutomationState:
        # Domain writers must hold this same lock across commit + publish.
        # Do not acquire it while already holding a page/project lock.
        with self.broker.lock:
            before = self.broker.revision
            project = self.project_state.loaded_project
            jobs = self.runner.list_jobs()
            pages: list[PageReadiness] = []
            if project is not None:
                pending = {
                    job.payload.get("page_index"): job.job_id
                    for job in jobs
                    if job.job_type == "load_page"
                    and job.project_id == project.project_id
                    and job.status.value in {"queued", "running"}
                }
                for index in range(project.total_pages):
                    state = self.project_state.get_page_state(index)
                    pages.append(
                        PageReadiness(
                            page_index=index,
                            generation=state.generation if state is not None else 0,
                            ready=state is not None and state.page_record is not None,
                            page_load_job_id=pending.get(index),
                        )
                    )
            result = AutomationState(
                revision=before,
                project=None if project is None else project.model_copy(deep=True),
                current_page_index=self.project_state.current_page_index if project else None,
                project_generation=self.project_state.generation,
                pages=pages,
                jobs=[to_public_job(job) for job in jobs],
                capabilities=self.capabilities() if callable(self.capabilities) else self.capabilities,
                viewers=self.viewers.list_viewers(),
            )
            if self.broker.revision != before:
                return self.snapshot()
            return result

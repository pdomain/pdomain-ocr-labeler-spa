"""Targeted viewer intent and independently observed acknowledgements."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Literal, final
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .events import AutomationBroker

if TYPE_CHECKING:
    from collections.abc import Callable


class ViewerError(BaseModel):
    error: str
    message: str
    details: JsonValue = None


@final
class ViewerConflictError(ValueError):
    def __init__(
        self, message: str, *, error: str = "viewer_observation_conflict", status: int = 409
    ) -> None:
        super().__init__(message)
        self.error = error
        self.status = status


class ViewerSelection(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    word_ids: list[str] = Field(default_factory=list)
    region_id: str | None = None
    proposal_id: str | None = None
    alignment_group_id: str | None = None
    alignment_id: str | None = None


class ViewerCommandRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    viewer_id: str
    project_id: str
    page_index: int = Field(ge=0)
    panel: Literal["closed", "selection", "source_alignment"] = "selection"
    selection: ViewerSelection = Field(default_factory=ViewerSelection)


class ViewerCommand(ViewerCommandRequest):
    command_seq: int = Field(ge=1)


class ViewerAck(ViewerCommand):
    generation: int = Field(ge=0)
    status: Literal["applied", "failed"] = "applied"
    error: ViewerError | None = None


class ViewerState(BaseModel):
    viewer_id: str
    connected: bool
    desired: ViewerCommand | None = None
    acknowledged: ViewerAck | None = None
    pending: bool = False
    last_observation: ViewerAck | None = None


@dataclass
class ReadyView:
    project_id: str
    page_index: int
    generation: int
    ready: bool = True
    word_ids: set[str] = field(default_factory=set)
    region_ids: set[str] = field(default_factory=set)
    proposal_ids: set[str] = field(default_factory=set)
    alignment_id: str | None = None
    alignment_group_ids: set[str] = field(default_factory=set)


@final
class ViewerRegistry:
    def __init__(self, broker: AutomationBroker, ready_view: Callable[[str, int], ReadyView | None]) -> None:
        self.broker = broker
        self.ready_view = ready_view
        self._states: dict[str, ViewerState] = {}

    def register(self, viewer_id: str | None = None) -> ViewerState:
        with self.broker.lock:
            if viewer_id is not None:
                return self.get(viewer_id)
            viewer_id = uuid4().hex
            self._states[viewer_id] = ViewerState(viewer_id=viewer_id, connected=False)
            return self.get(viewer_id)

    def get(self, viewer_id: str) -> ViewerState:
        with self.broker.lock:
            state = self._states.get(viewer_id)
            if state is None:
                raise ViewerConflictError(
                    "unknown viewer_id; register this tab first", error="viewer_not_found", status=404
                )
            return state.model_copy(deep=True, update={"connected": self.broker.connected(viewer_id)})

    def list_viewers(self) -> list[ViewerState]:
        with self.broker.lock:
            return [self.get(viewer_id) for viewer_id in self._states]

    def _validate_target(self, command: ViewerCommandRequest) -> ReadyView:
        ready = self.ready_view(command.project_id, command.page_index)
        if ready is None:
            raise ViewerConflictError("target project is not loaded or page is outside the loaded project")
        selection = command.selection
        if not set(selection.word_ids) <= ready.word_ids:
            raise ViewerConflictError("selected word IDs are not present on the current page")
        if selection.region_id is not None and selection.region_id not in ready.region_ids:
            raise ViewerConflictError("selected region is not present on the current page")
        if selection.proposal_id is not None and selection.proposal_id not in ready.proposal_ids:
            raise ViewerConflictError("selected proposal is not present on the current page")
        if selection.alignment_group_id is not None:
            if (
                selection.alignment_id is None
                or selection.alignment_id != ready.alignment_id
                or selection.alignment_group_id not in ready.alignment_group_ids
            ):
                raise ViewerConflictError("selected alignment group is not current or unavailable")
        elif selection.alignment_id is not None and selection.alignment_id != ready.alignment_id:
            raise ViewerConflictError("alignment identity is not current")
        return ready

    def command(self, request: ViewerCommandRequest) -> ViewerState:
        with self.broker.lock:
            state = self.get(request.viewer_id)
            _ = self._validate_target(request)
            sequence = 1 if state.desired is None else state.desired.command_seq + 1
            command = ViewerCommand(
                viewer_id=request.viewer_id,
                project_id=request.project_id,
                page_index=request.page_index,
                panel=request.panel,
                selection=request.selection.model_copy(deep=True),
                command_seq=sequence,
            )
            self._states[state.viewer_id] = state.model_copy(update={"desired": command, "pending": True})
            _ = self.broker.publish(
                "viewer_command",
                project_id=command.project_id,
                page_index=command.page_index,
                viewer_id=command.viewer_id,
                command_seq=sequence,
            )
            return self.get(state.viewer_id)

    def ack(self, observation: ViewerAck) -> ViewerState:
        with self.broker.lock:
            state = self.get(observation.viewer_id)
            desired = state.desired
            try:
                ready = self._validate_target(observation)
                if desired is None:
                    raise ViewerConflictError("this tab has no desired command")
                observed_fields = observation.model_dump(exclude={"generation", "status", "error"})
                desired_fields = desired.model_dump()
                # Word order is not meaningful for the selected set.
                observed_fields["selection"]["word_ids"] = sorted(set(observation.selection.word_ids))
                desired_fields["selection"]["word_ids"] = sorted(set(desired.selection.word_ids))
                if observed_fields != desired_fields:
                    raise ViewerConflictError(
                        "observed view or command sequence differs from current desired view"
                    )
                if not ready.ready or observation.generation != ready.generation:
                    raise ViewerConflictError("observation does not name the CURRENT ready page generation")
            except ViewerConflictError as exc:
                failed = observation.model_copy(
                    update={"status": "failed", "error": ViewerError(error=exc.error, message=str(exc))}
                )
                self._states[state.viewer_id] = state.model_copy(update={"last_observation": failed})
                _ = self.broker.publish(
                    "viewer_ack", viewer_id=state.viewer_id, command_seq=observation.command_seq
                )
                raise
            applied = observation.status == "applied"
            self._states[state.viewer_id] = state.model_copy(
                update={
                    "last_observation": observation,
                    "pending": not applied,
                    "acknowledged": observation if applied else state.acknowledged,
                }
            )
            _ = self.broker.publish(
                "viewer_ack",
                project_id=observation.project_id,
                page_index=observation.page_index,
                generation=observation.generation,
                viewer_id=state.viewer_id,
                command_seq=observation.command_seq,
            )
            return self.get(state.viewer_id)

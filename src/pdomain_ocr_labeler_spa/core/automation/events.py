"""Thread-safe revision journal and atomic replay subscriptions."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from contextlib import contextmanager
from typing import TYPE_CHECKING, Literal, final

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Generator

EventKind = Literal["project_changed", "page_changed", "job_changed", "viewer_command", "viewer_ack", "reset"]


class AutomationEvent(BaseModel):
    revision: int
    kind: EventKind
    project_id: str | None = None
    page_index: int | None = None
    generation: int | None = None
    job_id: str | None = None
    viewer_id: str | None = None
    command_seq: int | None = None


@final
class Subscription:
    def __init__(self, broker: AutomationBroker, *, viewer_id: str | None) -> None:
        self.broker = broker
        self.viewer_id = viewer_id
        self.queue: deque[AutomationEvent] = deque()
        self.loop = asyncio.get_running_loop()
        self.signal = asyncio.Event()
        self.closed = False

    async def receive(self) -> AutomationEvent:
        while True:
            with self.broker.lock:
                if self.queue:
                    return self.queue.popleft()
                if self.closed:
                    raise RuntimeError("subscription closed")
                self.signal.clear()
            _ = await self.signal.wait()

    def close(self) -> None:
        with self.broker.lock:
            self.closed = True
            self.broker.subscribers.discard(self)
            _ = self.loop.call_soon_threadsafe(self.signal.set)


@final
class AutomationBroker:
    def __init__(self, *, history_size: int = 512, subscriber_size: int = 128) -> None:
        if history_size < 1 or subscriber_size < 1:
            raise ValueError("buffer sizes must be positive")
        self.lock = threading.RLock()
        self._revision = 0
        self.history: deque[AutomationEvent] = deque(maxlen=history_size)
        self.subscriber_size = subscriber_size
        self.subscribers: set[Subscription] = set()

    @property
    def revision(self) -> int:
        with self.lock:
            return self._revision

    def connected(self, viewer_id: str) -> bool:
        with self.lock:
            return any(sub.viewer_id == viewer_id for sub in self.subscribers)

    @contextmanager
    def transaction(
        self,
        kind: EventKind | None = None,
        *,
        project_id: str | None = None,
        page_index: int | None = None,
        generation: int | None = None,
    ) -> Generator[None]:
        """Hold across a synchronous mutation and its successful publication.

        Callers must never await while holding this thread lock. Snapshots acquire
        this same lock. Failed operations leave the journal unchanged.
        """
        with self.lock:
            yield
            if kind is not None:
                _ = self.publish(kind, project_id=project_id, page_index=page_index, generation=generation)

    def publish(
        self,
        kind: EventKind,
        *,
        project_id: str | None = None,
        page_index: int | None = None,
        generation: int | None = None,
        job_id: str | None = None,
        viewer_id: str | None = None,
        command_seq: int | None = None,
    ) -> AutomationEvent:
        with self.lock:
            self._revision += 1
            event = AutomationEvent(
                revision=self._revision,
                kind=kind,
                project_id=project_id,
                page_index=page_index,
                generation=generation,
                job_id=job_id,
                viewer_id=viewer_id,
                command_seq=command_seq,
            )
            self.history.append(event)
            for sub in self.subscribers:
                if len(sub.queue) >= self.subscriber_size:
                    sub.queue.clear()
                    sub.queue.append(AutomationEvent(revision=self._revision, kind="reset"))
                else:
                    sub.queue.append(event)
                _ = sub.loop.call_soon_threadsafe(sub.signal.set)
            return event

    def subscribe(self, *, after: int | None, viewer_id: str | None = None) -> Subscription:
        with self.lock:
            sub = Subscription(self, viewer_id=viewer_id)
            oldest = self.history[0].revision if self.history else self._revision + 1
            if after is None or after < oldest - 1 or after > self._revision:
                sub.queue.append(AutomationEvent(revision=self._revision, kind="reset"))
            else:
                replay = [event for event in self.history if event.revision > after]
                if len(replay) > self.subscriber_size:
                    sub.queue.append(AutomationEvent(revision=self._revision, kind="reset"))
                else:
                    sub.queue.extend(replay)
            self.subscribers.add(sub)
            return sub

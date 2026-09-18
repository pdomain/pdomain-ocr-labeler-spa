"""In-memory pub/sub broker for job progress events.

Spec: ``docs/architecture/02-backend.md §11``. Verbatim port of
``pdomain-prep-for-pgdp/core/job_events.py:27-67`` with no meaningful changes —
same fan-out model, same ``_CLOSED`` sentinel, same subscribe/publish/close
contract.

Events published before any subscriber is listening are dropped. New
subscribers see only events that arrive after ``subscribe()`` returns.
The SSE handler compensates by emitting an initial job-snapshot before
subscribing (so a late subscriber still sees the terminal state if the
job completed synchronously).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any


class _Sentinel:
    """Marker pushed by ``close()`` so subscribers know the channel ended."""


_CLOSED = _Sentinel()


class JobEventBroker:
    """Per-job_id async fan-out without buffering.

    Spec §11: "per-job ``asyncio.Queue``". Each call to
    ``subscribe(job_id)`` returns an async iterator that yields dict
    events until ``close(job_id)`` is called.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._queues.get(job_id, ()))
        for q in queues:
            await q.put(event)

    async def close(self, job_id: str) -> None:
        """Signal every active subscriber for ``job_id`` that the channel ended."""
        async with self._lock:
            queues = self._queues.pop(job_id, [])
        for q in queues:
            await q.put(_CLOSED)

    async def listen(self, job_id: str) -> asyncio.Queue[Any]:
        """Register a new subscriber queue for ``job_id`` and return it.

        Split out of ``subscribe`` so a caller can register *before*
        reading the job's current status. Registration happens
        synchronously under ``self._lock`` relative to ``publish``/
        ``close`` (both also lock), so a caller that reads status only
        after this returns is guaranteed one of two outcomes: it observes
        a terminal status directly (``publish``+``close`` already ran and
        this queue was never in their snapshot), or it observes a
        non-terminal status and will still receive the terminal event
        through the returned queue (``publish`` snapshots subscribers
        under the same lock, so this queue is in it or the write already
        landed). It can never observe non-terminal status *and* miss the
        event — the race ``job_events`` (``api/jobs.py``) used to hit when
        it read status once, yielded, and only then called ``subscribe``.
        """
        q: asyncio.Queue[Any] = asyncio.Queue()
        async with self._lock:
            self._queues[job_id].append(q)
        return q

    async def unlisten(self, job_id: str, q: asyncio.Queue[Any]) -> None:
        """Remove a queue registered via ``listen``. Idempotent."""
        async with self._lock:
            if q in self._queues.get(job_id, ()):
                self._queues[job_id].remove(q)
            if not self._queues.get(job_id):
                self._queues.pop(job_id, None)

    async def drain(self, q: asyncio.Queue[Any]) -> AsyncIterator[dict[str, Any]]:
        """Yield events from a queue registered via ``listen`` until closed.

        Does not unregister the queue itself — callers own that (typically
        in a ``finally`` alongside ``listen``, e.g. ``subscribe`` below).
        """
        while True:
            event = await q.get()
            if event is _CLOSED:
                return
            yield event

    async def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        """Register + drain in one step: events published after this call.

        Convenience for callers that don't need to read the job's current
        status in between registering and draining — see ``listen`` for
        why that ordering matters for a caller (``job_events``) that does.
        """
        q = await self.listen(job_id)
        try:
            async for event in self.drain(q):
                yield event
        finally:
            await self.unlisten(job_id, q)


__all__ = ["JobEventBroker"]

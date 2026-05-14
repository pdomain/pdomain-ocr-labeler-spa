"""In-memory pub/sub broker for job progress events.

Spec: ``docs/architecture/02-backend.md §11``. Verbatim port of
``pd-prep-for-pgdp/core/job_events.py:27-67`` with no meaningful changes —
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

    async def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue[Any] = asyncio.Queue()
        async with self._lock:
            self._queues[job_id].append(q)
        try:
            while True:
                event = await q.get()
                if event is _CLOSED:
                    return
                yield event
        finally:
            async with self._lock:
                if q in self._queues.get(job_id, ()):
                    self._queues[job_id].remove(q)
                if not self._queues.get(job_id):
                    self._queues.pop(job_id, None)


__all__ = ["JobEventBroker"]

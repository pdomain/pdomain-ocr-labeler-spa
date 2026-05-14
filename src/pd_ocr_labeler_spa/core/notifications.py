"""In-memory notification queue with ring-buffer and SSE fan-out.

Spec authority:
- ``docs/architecture/01-data-models.md §2 Notifications`` — ``NotificationKind``,
  ``Notification`` shapes.
- ``docs/architecture/11-notifications.md §2`` — ring buffer cap (~100), ``queue_once``
  dedupe, snapshot-on-connect semantics.
- Legacy parity: ``pd-ocr-labeler/pd_ocr_labeler/state/app_state.py``
  ``queue_notification`` / ``pop_notification`` / ``_safe_notify_once``.

Design contract:
- ``NotificationQueue.queue`` appends a new notification and broadcasts
  it to all active subscribers.
- ``queue_once(key, kind, message)`` deduplicates by ``key`` within the
  current project session (reset by ``reset_once_keys()``).
- The ring buffer keeps the last ``_MAX_NOTIFICATIONS`` entries so a
  late SSE subscriber sees recent history on connect.
- ``subscribe()`` is an async generator that yields the current snapshot
  then live events. It is safe to call from multiple concurrent
  coroutines.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

_MAX_NOTIFICATIONS = 100


class NotificationKind(StrEnum):
    """Notification severity — ``docs/architecture/01-data-models.md §2``."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    WARNING = "warning"
    INFO = "info"


class Notification(BaseModel):
    """A single server-pushed notification — ``docs/architecture/01-data-models.md §2``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: NotificationKind
    message: str
    created_at: datetime


class _Sentinel:
    """Marker pushed by the queue when a subscriber should unblock."""


_CLOSED = _Sentinel()


class NotificationQueue:
    """Thread-safe (asyncio) notification queue with ring buffer + fan-out.

    Lifecycle:
    - One ``NotificationQueue`` per ``build_app`` instance.
    - ``queue(kind, message)`` appends and broadcasts.
    - ``queue_once(key, kind, message)`` dedupes within the session.
    - ``reset_once_keys()`` clears the dedupe set on project change.
    - ``dismiss(id)`` removes from buffer (for tests; no-op on unknown id).
    - ``subscribe()`` is an async generator; connect yields snapshot then
      live events; ``close()`` signals all subscribers to stop.
    """

    def __init__(self) -> None:
        self._ring: list[Notification] = []
        self._seen_keys: set[str] = set()
        self._queues: list[asyncio.Queue[Any]] = []
        self._lock = asyncio.Lock()

    def queue(self, kind: NotificationKind, message: str) -> Notification:
        """Append a notification and broadcast to subscribers.

        Returns the new ``Notification`` so callers can log or test the id.
        """
        notif = Notification(
            id=uuid.uuid4().hex,
            kind=kind,
            message=message,
            created_at=datetime.now(UTC),
        )
        # Ring buffer eviction — drop the oldest entry when full.
        if len(self._ring) >= _MAX_NOTIFICATIONS:
            self._ring.pop(0)
        self._ring.append(notif)
        # Broadcast to every active subscriber; put_nowait is safe because
        # each queue is consumed by a single coroutine and we never overflow
        # (each subscriber has an unbounded queue).
        for q in list(self._queues):
            q.put_nowait(notif)
        return notif

    def queue_once(self, key: str, kind: NotificationKind, message: str) -> Notification | None:
        """Deduplicated ``queue``.

        If ``key`` has already been queued since the last ``reset_once_keys()``
        call, this is a no-op and returns ``None``. Otherwise queues and
        returns the new ``Notification``.

        Spec parity: legacy ``_safe_notify_once`` in
        ``pd-ocr-labeler/pd_ocr_labeler/state/app_state.py``.
        """
        if key in self._seen_keys:
            return None
        self._seen_keys.add(key)
        return self.queue(kind, message)

    def reset_once_keys(self) -> None:
        """Clear the dedupe set.

        Call on project change so per-session ``queue_once`` keys don't
        bleed into the next project.
        """
        self._seen_keys.clear()

    def dismiss(self, notification_id: str) -> bool:
        """Remove a notification from the ring buffer by id.

        Returns ``True`` if found and removed; ``False`` if not found.
        This is spec §5.11 ``POST /api/notifications/{id}/dismiss`` — for
        test purposes only. Subscribers do not see a retraction event.
        """
        for i, n in enumerate(self._ring):
            if n.id == notification_id:
                self._ring.pop(i)
                return True
        return False

    def snapshot(self) -> list[Notification]:
        """Return a copy of the current ring buffer."""
        return list(self._ring)

    async def subscribe(self) -> AsyncIterator[Notification]:
        """Async generator yielding notifications.

        First iteration yields all buffered notifications (snapshot);
        subsequent iterations yield new ones as they arrive.
        Close the generator to unsubscribe.
        """
        q: asyncio.Queue[Any] = asyncio.Queue()
        async with self._lock:
            # Capture a snapshot under the lock so we don't miss any
            # notifications queued between the snapshot and the queue
            # registration — though in practice that race window is tiny
            # in asyncio's cooperative model.
            current = list(self._ring)
            self._queues.append(q)
        try:
            for notif in current:
                yield notif
            while True:
                item = await q.get()
                if item is _CLOSED:
                    return
                yield item
        finally:
            async with self._lock:
                if q in self._queues:
                    self._queues.remove(q)

    async def close(self) -> None:
        """Signal all active subscribers to stop iterating."""
        async with self._lock:
            queues = list(self._queues)
        for q in queues:
            await q.put(_CLOSED)


__all__ = [
    "Notification",
    "NotificationKind",
    "NotificationQueue",
]

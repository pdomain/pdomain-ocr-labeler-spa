"""Unit tests for ``core/notifications.py`` — ``NotificationQueue``.

Spec authority:
- ``docs/architecture/11-notifications.md §2`` — ring buffer cap (~100), ``queue_once``
  dedupe, snapshot-on-connect semantics.
- ``specs/07-notifications.md`` (referenced as §7 in spec set) and
  ``docs/architecture/11-notifications.md §2.3`` — SSE shape.
"""

from __future__ import annotations

import asyncio

import pytest

from pd_ocr_labeler_spa.core.notifications import (
    Notification,
    NotificationKind,
    NotificationQueue,
)

# ── queue() basics ───────────────────────────────────────────────────────────


def test_queue_returns_notification() -> None:
    q = NotificationQueue()
    n = q.queue(NotificationKind.POSITIVE, "hello")
    assert isinstance(n, Notification)
    assert n.kind == NotificationKind.POSITIVE
    assert n.message == "hello"
    assert n.id


def test_queue_appends_to_ring() -> None:
    q = NotificationQueue()
    q.queue(NotificationKind.INFO, "a")
    q.queue(NotificationKind.INFO, "b")
    snap = q.snapshot()
    assert len(snap) == 2
    assert snap[0].message == "a"
    assert snap[1].message == "b"


def test_queue_ring_buffer_evicts_oldest_when_full() -> None:
    """Ring buffer must cap at _MAX_NOTIFICATIONS (100)."""
    from pd_ocr_labeler_spa.core.notifications import _MAX_NOTIFICATIONS

    q = NotificationQueue()
    for i in range(_MAX_NOTIFICATIONS + 5):
        q.queue(NotificationKind.INFO, str(i))
    snap = q.snapshot()
    assert len(snap) == _MAX_NOTIFICATIONS
    # Oldest entries (0..4) should have been evicted.
    assert snap[0].message == "5"
    assert snap[-1].message == str(_MAX_NOTIFICATIONS + 4)


# ── queue_once() ─────────────────────────────────────────────────────────────


def test_queue_once_first_call_queues() -> None:
    q = NotificationQueue()
    n = q.queue_once("key1", NotificationKind.INFO, "msg")
    assert n is not None
    assert len(q.snapshot()) == 1


def test_queue_once_duplicate_key_is_noop() -> None:
    q = NotificationQueue()
    q.queue_once("key1", NotificationKind.INFO, "first")
    result = q.queue_once("key1", NotificationKind.INFO, "second")
    assert result is None
    assert len(q.snapshot()) == 1
    assert q.snapshot()[0].message == "first"


def test_queue_once_different_keys_both_queue() -> None:
    q = NotificationQueue()
    q.queue_once("key1", NotificationKind.INFO, "a")
    q.queue_once("key2", NotificationKind.INFO, "b")
    assert len(q.snapshot()) == 2


def test_reset_once_keys_allows_requeue() -> None:
    q = NotificationQueue()
    q.queue_once("key1", NotificationKind.INFO, "first")
    q.reset_once_keys()
    n = q.queue_once("key1", NotificationKind.INFO, "second")
    assert n is not None
    assert len(q.snapshot()) == 2


# ── dismiss() ────────────────────────────────────────────────────────────────


def test_dismiss_removes_by_id() -> None:
    q = NotificationQueue()
    n = q.queue(NotificationKind.INFO, "remove me")
    assert q.dismiss(n.id) is True
    assert q.snapshot() == []


def test_dismiss_unknown_id_returns_false() -> None:
    q = NotificationQueue()
    q.queue(NotificationKind.INFO, "keep me")
    assert q.dismiss("no-such-id") is False
    assert len(q.snapshot()) == 1


# ── subscribe() — async generator ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_yields_snapshot_then_live() -> None:
    """A late subscriber sees buffered notifications first, then new ones."""
    q = NotificationQueue()
    q.queue(NotificationKind.INFO, "buffered-1")
    q.queue(NotificationKind.INFO, "buffered-2")

    received: list[str] = []

    async def consume() -> None:
        async for notif in q.subscribe():
            received.append(notif.message)
            if len(received) == 3:
                break

    task = asyncio.create_task(consume())
    # Give the task a chance to drain the snapshot.
    await asyncio.sleep(0)
    q.queue(NotificationKind.INFO, "live-3")
    await asyncio.wait_for(task, timeout=1.0)
    assert received == ["buffered-1", "buffered-2", "live-3"]


@pytest.mark.asyncio
async def test_subscribe_multiple_subscribers_all_receive() -> None:
    """Fan-out: two concurrent subscribers both receive the same live event."""
    q = NotificationQueue()
    received_a: list[str] = []
    received_b: list[str] = []

    async def consume(store: list[str]) -> None:
        async for notif in q.subscribe():
            store.append(notif.message)
            break  # stop after one live event

    task_a = asyncio.create_task(consume(received_a))
    task_b = asyncio.create_task(consume(received_b))
    await asyncio.sleep(0)

    q.queue(NotificationKind.POSITIVE, "broadcast")

    await asyncio.wait_for(task_a, timeout=1.0)
    await asyncio.wait_for(task_b, timeout=1.0)

    assert received_a == ["broadcast"]
    assert received_b == ["broadcast"]


@pytest.mark.asyncio
async def test_close_signals_all_subscribers() -> None:
    """``close()`` must unblock all waiting subscribers."""
    q = NotificationQueue()
    messages: list[str] = []

    async def consume() -> None:
        async for notif in q.subscribe():
            messages.append(notif.message)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await q.close()
    await asyncio.wait_for(task, timeout=1.0)
    # No messages queued — subscriber just stopped cleanly.
    assert messages == []

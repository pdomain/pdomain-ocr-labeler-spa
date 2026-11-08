from __future__ import annotations

import asyncio

import pytest

from pdomain_ocr_labeler_spa.core.automation.events import AutomationBroker


async def test_atomic_replay_live_and_cursor_resets() -> None:
    broker = AutomationBroker(history_size=2, subscriber_size=4)
    _ = broker.publish("page_changed", generation=1)
    _ = broker.publish("page_changed", generation=2)
    subscription = broker.subscribe(after=1)
    _ = broker.publish("page_changed", generation=3)
    assert (await subscription.receive()).revision == 2
    assert (await subscription.receive()).revision == 3
    expired = broker.subscribe(after=0)
    assert (await expired.receive()).kind == "reset"
    assert (await broker.subscribe(after=None).receive()).kind == "reset"
    assert (await broker.subscribe(after=999).receive()).kind == "reset"
    subscription.close()


async def test_overflow_is_explicit_reset_and_worker_publish_is_safe() -> None:
    broker = AutomationBroker(subscriber_size=1)
    sub = broker.subscribe(after=0)
    _ = await asyncio.to_thread(broker.publish, "page_changed", generation=1)
    _ = await asyncio.to_thread(broker.publish, "page_changed", generation=2)
    event = await sub.receive()
    assert event.kind == "reset"
    assert event.revision == 2
    sub.close()


def test_transaction_publishes_only_on_success() -> None:
    broker = AutomationBroker()
    with pytest.raises(ValueError), broker.transaction("page_changed"):
        raise ValueError("persistence failed")
    assert broker.revision == 0
    with broker.transaction("page_changed"):
        pass
    assert broker.revision == 1

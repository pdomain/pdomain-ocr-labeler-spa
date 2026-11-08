"""Resolve the application mutation boundary for background page commits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..automation.service import AutomationService

if TYPE_CHECKING:
    from ..automation.events import AutomationBroker
    from .runner import JobRunner


def job_change_broker(runner: JobRunner) -> AutomationBroker | None:
    service = runner.context.get("automation")
    return service.broker if isinstance(service, AutomationService) else None

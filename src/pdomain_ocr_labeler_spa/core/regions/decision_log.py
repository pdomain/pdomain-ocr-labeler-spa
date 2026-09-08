"""Append-only journal of what a person decided about each region proposal.

This is the store that makes a rejection a fact rather than an absence. Without
it, a proposal nobody accepted and a proposal somebody refused look identical,
and a trainer needs to tell them apart.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from typing import TYPE_CHECKING, Any, ClassVar

from pdomain_ocr_labeler_spa.core.regions.models import RegionDecision

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class RegionDecisionLog:
    """Project-local JSONL journal of immutable region decisions."""

    _RELATIVE_PATH: ClassVar[str] = ".pd-pages/region-decisions.jsonl"

    def __init__(self, project_root: Path) -> None:
        self._path = project_root / self._RELATIVE_PATH

    @property
    def path(self) -> Path:
        """The on-disk location of this journal."""
        return self._path

    def append(self, decision: RegionDecision) -> None:
        """Append one decision. Existing records are never rewritten."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(decision.to_dict(), sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    def decisions(self) -> list[RegionDecision]:
        """Every decision recorded, in the order they were written."""
        if not self._path.exists():
            return []
        found: list[RegionDecision] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    loaded: Any = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.warning("region-decisions.jsonl: skipping malformed line %d", line_number)
                    continue
                if isinstance(loaded, dict):
                    found.append(RegionDecision.from_dict(loaded))
        return found

    def decision_for(self, proposal_id: str, *, run_id: str) -> RegionDecision | None:
        """The most recent decision about one proposal within one run.

        Later records supersede earlier ones. Both stay on disk, so a change of
        mind is itself reviewable.
        """
        current: RegionDecision | None = None
        for decision in self.decisions():
            if decision.proposal_id == proposal_id and decision.run_id == run_id:
                current = decision
        return current

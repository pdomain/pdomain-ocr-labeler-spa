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

    def latest_by_proposal(self) -> dict[tuple[str, str], RegionDecision]:
        """Every proposal's most recent decision, keyed by ``(proposal_id, run_id)``.

        One pass over the journal for a whole page. ``decision_for`` re-reads and
        re-parses the entire file per call, and the page payload asks about every
        proposal on the page on every load and after every mutating route — that
        is O(proposals x journal) full-file reads on the hottest read path. A
        caller resolving more than one proposal reads the journal once through
        this method instead.

        Later records supersede earlier ones, exactly as in ``decision_for``.
        """
        latest: dict[tuple[str, str], RegionDecision] = {}
        for decision in self.decisions():
            latest[decision.proposal_id, decision.run_id] = decision
        return latest

    def decision_for(self, proposal_id: str, *, run_id: str) -> RegionDecision | None:
        """The most recent decision about one proposal within one run.

        Later records supersede earlier ones. Both stay on disk, so a change of
        mind is itself reviewable.

        Single-lookup convenience: a caller resolving several proposals at once
        should use ``latest_by_proposal`` and index it, so the journal is read
        once rather than once per proposal.
        """
        return self.latest_by_proposal().get((proposal_id, run_id))

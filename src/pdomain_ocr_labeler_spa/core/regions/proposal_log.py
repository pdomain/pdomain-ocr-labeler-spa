"""Append-only journal of region proposals and the runs that produced them.

Proposals never enter the page content blob. That blob is written only by a
human action, and a proposal is a machine's claim. Keeping them apart is what
makes the page blob trustworthy as ground truth.

Records are never rewritten. A later run supersedes an earlier one for display
purposes only; both stay on disk, because scoring a replacement model against
the one it replaces needs what each of them said.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from typing import TYPE_CHECKING, Any, ClassVar

from pdomain_ocr_labeler_spa.core.regions.models import ProposalRun, RegionProposal

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

logger = logging.getLogger(__name__)


class RegionProposalLog:
    """Project-local JSONL journal of immutable region proposals."""

    _RELATIVE_PATH: ClassVar[str] = ".pd-pages/region-proposals.jsonl"

    def __init__(self, project_root: Path) -> None:
        self._path = project_root / self._RELATIVE_PATH

    @property
    def path(self) -> Path:
        """The on-disk location of this journal."""
        return self._path

    def _append(self, records: Sequence[dict[str, Any]]) -> None:
        if not records:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records).encode("utf-8")
        # O_APPEND alone is only atomic below PIPE_BUF, and a batch of proposals
        # goes well past that. Take the same exclusive lock TypographyCorrectionLog
        # takes so writers across worker processes serialize.
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    def append_run(self, run: ProposalRun) -> None:
        """Record one proposal run before its proposals are written."""
        self._append([{"kind": "run", "record": run.to_dict()}])

    def append_proposals(self, proposals: Sequence[RegionProposal]) -> None:
        """Append proposals. Existing records are never touched."""
        self._append([{"kind": "proposal", "record": p.to_dict()} for p in proposals])

    def _read(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    loaded: Any = json.loads(stripped)
                except json.JSONDecodeError:
                    # A torn tail from a killed writer must not hide the records
                    # before it. Skip and keep reading.
                    logger.warning("region-proposals.jsonl: skipping malformed line %d", line_number)
                    continue
                if isinstance(loaded, dict):
                    records.append(loaded)
        return records

    def runs(self) -> list[ProposalRun]:
        """Every run recorded, in the order they were written."""
        return [
            ProposalRun.from_dict(entry["record"]) for entry in self._read() if entry.get("kind") == "run"
        ]

    def proposals_for_page(self, page_index: int, *, run_id: str | None = None) -> list[RegionProposal]:
        """Proposals for one page, optionally narrowed to a single run."""
        found: list[RegionProposal] = []
        for entry in self._read():
            if entry.get("kind") != "proposal":
                continue
            proposal = RegionProposal.from_dict(entry["record"])
            if proposal.page_index != page_index:
                continue
            if run_id is not None and proposal.run_id != run_id:
                continue
            found.append(proposal)
        return found

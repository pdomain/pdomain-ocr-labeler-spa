"""Append-only journal of page-kind proposals and the runs that produced them.

Mirrors ``core/regions/proposal_log.py``'s ``RegionProposalLog``: one run
record per book-scoped pass, one record per proposed page kind, and the same
discipline as ``TypographyCorrectionLog`` — an OS append lock, fsync before
``append`` returns, and no record ever rewritten.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal, PageKindProposalRun

log = logging.getLogger(__name__)


class PageKindProposalLog:
    """Project-local JSONL journal of immutable page-kind proposals."""

    _RELATIVE_PATH: ClassVar[Path] = Path(".pd-pages") / "page-kind-proposals.jsonl"

    def __init__(self, project_root: Path) -> None:
        self._path = Path(project_root) / self._RELATIVE_PATH

    @property
    def path(self) -> Path:
        """The on-disk location of this journal."""
        return self._path

    def _append(self, records: Sequence[dict[str, Any]]) -> None:
        if not records:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records).encode("utf-8")
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    def append_run(self, run: PageKindProposalRun) -> None:
        """Record one proposal run before its proposals are written."""
        self._append([{"kind": "run", "record": run.to_dict()}])

    def append_proposals(self, proposals: Sequence[PageKindProposal]) -> None:
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
                    loaded = json.loads(stripped)
                except json.JSONDecodeError:
                    log.warning("page-kind-proposals.jsonl: skipping malformed line %d", line_number)
                    continue
                if isinstance(loaded, dict):
                    records.append(loaded)
        return records

    def runs(self) -> list[PageKindProposalRun]:
        """Every run recorded, in the order they were written."""
        return [
            PageKindProposalRun.from_dict(entry["record"])
            for entry in self._read()
            if entry.get("kind") == "run"
        ]

    def proposals_for_run(self, run_id: str) -> list[PageKindProposal]:
        """Every proposal written by one run."""
        return [
            PageKindProposal.from_dict(entry["record"])
            for entry in self._read()
            if entry.get("kind") == "proposal" and entry["record"].get("run_id") == run_id
        ]

    def latest_proposal_for_page(self, page_index: int) -> PageKindProposal | None:
        """The most recent proposal for one page, across every run.

        The confirm route diffs the human's answer against this to tell an
        acceptance from a change — no decision log needed at this level.
        """
        latest: PageKindProposal | None = None
        for entry in self._read():
            if entry.get("kind") != "proposal":
                continue
            proposal = PageKindProposal.from_dict(entry["record"])
            if proposal.page_index == page_index:
                latest = proposal
        return latest

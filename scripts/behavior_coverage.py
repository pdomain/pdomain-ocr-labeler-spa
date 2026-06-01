"""Behavior coverage audit: cross-check declared behavior IDs vs cited IDs."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ID_RE = re.compile(r"\b([BF]-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+)\b")
RECORD_HEADING_RE = re.compile(r"^###\s+([BF]-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+)\b", re.MULTILINE)
_SELF_TEST = "test_behavior_coverage.py"
_FRONTEND_TEST_PATTERNS = ("*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx")


@dataclass(frozen=True)
class Record:
    id: str
    regression: bool


def scan_declared(docs_dir: Path) -> dict[str, Record]:
    """Find every behavior/flow record declared as an H3 heading."""
    declared: dict[str, Record] = {}
    for md in sorted(docs_dir.glob("*.md")):
        if md.name in {"coverage.md", "README.md"}:
            continue
        text = md.read_text(encoding="utf-8")
        matches = list(RECORD_HEADING_RE.finditer(text))
        for i, match in enumerate(matches):
            record_id = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block = text[start:end]
            regression = bool(re.search(r"\*\*Regression:\*\*\s*yes", block, re.IGNORECASE))
            declared[record_id] = Record(id=record_id, regression=regression)
    return declared


def scan_cited(tests_dir: Path) -> set[str]:
    """Find behavior IDs cited by tests via Covers lines or @behavior markers."""
    cited: set[str] = set()
    for py in tests_dir.rglob("*.py"):
        if py.name == _SELF_TEST:
            continue
        text = py.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "Covers:" in line or "@behavior" in line:
                cited.update(ID_RE.findall(line))
    return cited


def scan_frontend_cited(frontend_src_dir: Path) -> set[str]:
    """Find behavior IDs cited by frontend Vitest files."""
    cited: set[str] = set()
    if not frontend_src_dir.exists():
        return cited
    for pattern in _FRONTEND_TEST_PATTERNS:
        for test_file in frontend_src_dir.rglob(pattern):
            text = test_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "Covers:" in line or "@behavior" in line:
                    cited.update(ID_RE.findall(line))
    return cited


@dataclass(frozen=True)
class Report:
    declared: dict[str, Record]
    cited: set[str]
    orphans: set[str]
    unlinked: set[str]
    uncovered_regressions: set[str]

    @property
    def ok(self) -> bool:
        return not self.unlinked and not self.uncovered_regressions


def build_report(declared: dict[str, Record], cited: set[str]) -> Report:
    declared_ids = set(declared)
    orphans = declared_ids - cited
    unlinked = cited - declared_ids
    uncovered_regressions = {record_id for record_id in orphans if declared[record_id].regression}
    return Report(
        declared=declared,
        cited=cited,
        orphans=orphans,
        unlinked=unlinked,
        uncovered_regressions=uncovered_regressions,
    )


def render_markdown(report: Report) -> str:
    lines = [
        "# Behavior coverage (generated - do not edit)",
        "",
        "Run `make behavior-coverage` to regenerate.",
        "",
        "| ID | Regression | Status |",
        "|----|------------|--------|",
    ]
    for record_id in sorted(report.declared):
        record = report.declared[record_id]
        status = "test-written" if record_id in report.cited else "specified"
        regression = "yes" if record.regression else "no"
        lines.append(f"| {record_id} | {regression} | {status} |")
    if report.unlinked:
        lines += ["", "## Unlinked citations (FAIL - typo/stale)", ""]
        lines += [f"- {record_id}" for record_id in sorted(report.unlinked)]
    if report.uncovered_regressions:
        lines += ["", "## Uncovered regressions (FAIL)", ""]
        lines += [f"- {record_id}" for record_id in sorted(report.uncovered_regressions)]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    docs_dir = root / "docs" / "specs" / "behavior"
    tests_dir = root / "tests"
    frontend_src_dir = root / "frontend" / "src"
    declared = scan_declared(docs_dir)
    cited = scan_cited(tests_dir) | scan_frontend_cited(frontend_src_dir)
    report = build_report(declared, cited)
    (docs_dir / "coverage.md").write_text(render_markdown(report), encoding="utf-8")
    if not report.ok:
        print("BEHAVIOR COVERAGE GATE FAILED", file=sys.stderr)
        if report.unlinked:
            print(f"  unlinked citations: {sorted(report.unlinked)}", file=sys.stderr)
        if report.uncovered_regressions:
            print(f"  uncovered regressions: {sorted(report.uncovered_regressions)}", file=sys.stderr)
        return 1
    print(f"behavior coverage OK: {len(declared)} records, {len(cited)} cited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

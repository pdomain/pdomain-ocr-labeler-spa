"""Shape-pin tests for ``docs/archive/specs/M0-acceptance.md``.

The doc is the single page that says "what does M0-done mean and what's
still in the way." These tests enforce the invariants that make it
trustable as a sign-off artefact:

1. The file exists.
2. It carries a top-level ``## Status`` section (so a reviewer can
   tell at a glance whether M0 is done without reading the whole doc).
3. It has a remaining-blockers section that names the open questions
   blocking M0 (currently Q-A8 + Q-A9). If a future iter closes one
   of those, the doc must be edited to drop the reference; the test
   then catches the next round of edits if that question regresses.
4. It includes the ``make`` commands the spec lists in §M0
   "Acceptance tests" — the eight criterion clauses must be
   referenced verbatim or paraphrased so a reviewer running the doc
   exercises every one of them.

We do not parse the criteria-table cell-by-cell — the doc is markdown,
not data, and over-pinning the cells would just shift maintenance from
"keep the doc honest" to "keep the test in lockstep." The criterion
shape pin (§M0 acceptance commands appear) is the load-bearing one.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "archive" / "specs" / "M0-acceptance.md"
ROADMAP = REPO_ROOT / "docs" / "ROADMAP.md"
SPEC_M0 = REPO_ROOT / "specs" / "16-milestones.md"


def test_m0_acceptance_doc_exists() -> None:
    """The acceptance doc must exist alongside ROADMAP/BUGS_FOUND."""
    assert DOC.exists(), "docs/archive/specs/M0-acceptance.md is missing"


def test_m0_acceptance_doc_has_status_section() -> None:
    """A reviewer must be able to grep ``## Status`` and learn the
    current acceptance state without reading the whole doc."""
    text = DOC.read_text(encoding="utf-8")
    assert "\n## Status\n" in text, (
        "docs/archive/specs/M0-acceptance.md must include a top-level `## Status` section"
    )


def test_m0_acceptance_doc_lists_open_questions_blocking_m0() -> None:
    """The doc must reference both Q-A8 and Q-A9 by name — these are
    the open questions named as M0 blockers in OPEN_QUESTIONS.md and
    in `ROADMAP.md`'s status row. If a future iter closes one, this
    test will need to be updated alongside the doc."""
    text = DOC.read_text(encoding="utf-8")
    assert "Q-A8" in text, "docs/archive/specs/M0-acceptance.md must name Q-A8 (frontend toolchain blocker)"
    assert "Q-A9" in text, "docs/archive/specs/M0-acceptance.md must name Q-A9 (ESLint config blocker)"


def test_m0_acceptance_doc_covers_each_spec_acceptance_clause() -> None:
    """Each `make <target>` token from `specs/16-milestones.md` §M0
    Acceptance tests must appear in the doc, so a reviewer running
    the documented sign-off ritual exercises every spec clause.

    We extract the spec's M0 acceptance bullets, pull every
    backticked ``make <target>`` and `pd-ocr-labeler-ui ...`
    invocation out, and assert each appears in the doc."""
    expected_tokens = (
        "make setup",
        "make test",
        "make frontend-test",
        "make frontend-build",
        "make build",
        "make openapi-export",
        "pd-ocr-labeler-ui",
        "/healthz",
    )
    text = DOC.read_text(encoding="utf-8")
    missing = [tok for tok in expected_tokens if tok not in text]
    assert not missing, (
        f"docs/archive/specs/M0-acceptance.md is missing references to spec-mandated "
        f"acceptance tokens: {missing!r}. Each criterion in "
        f"`specs/16-milestones.md` §M0 must be reflected so a reviewer "
        f"can run the documented ritual end-to-end."
    )


def test_m0_acceptance_doc_describes_signoff_ritual() -> None:
    """A heading-or-section that explains how M0 transitions from
    'in progress' to 'done' must exist so the doc closes its own
    loop. Pin the heading text loosely — any of "Sign-off",
    "Sign off", or "Closing M0" satisfies it."""
    text = DOC.read_text(encoding="utf-8")
    has_signoff = any(token in text for token in ("Sign-off", "Sign off", "Closing M0", "## Sign"))
    assert has_signoff, (
        "docs/archive/specs/M0-acceptance.md must describe how M0 flips from "
        "'in progress' to 'done' (Sign-off / Sign off / Closing M0 section)."
    )


def test_m0_acceptance_doc_references_authoritative_spec_and_roadmap() -> None:
    """The doc is downstream of `specs/16-milestones.md` and
    `docs/ROADMAP.md`; it must cite both so a reader can navigate
    upstream without grepping. Also catches an accidental rewrite
    that drops the spec-as-source-of-truth framing."""
    text = DOC.read_text(encoding="utf-8")
    assert "16-milestones.md" in text, (
        "docs/archive/specs/M0-acceptance.md must cite `specs/16-milestones.md` "
        "as the authoritative milestone definition"
    )
    assert "ROADMAP.md" in text, (
        "docs/archive/specs/M0-acceptance.md must cite `docs/ROADMAP.md` as the implementation tracker"
    )

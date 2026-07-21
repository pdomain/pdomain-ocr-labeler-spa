---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# GitHub E2E is non-blocking and soft-skips hide broken UI paths

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — merge CI can stay green while Playwright or soft-skipped UI paths fail
- **Affected version:** deep code review 2026-07-21 (`P0-CI-SOFT`, `P2-E2E-GATE`)
- **Read when:** changing CI jobs, Playwright e2e policy, hierarchy coverage, or soft-skip inventory.
- **Search terms:** continue-on-error, test-e2e, soft-skip, HIER-1, exercise_real_project, P0-CI-SOFT, P2-E2E-GATE.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  [`docs/plans/2026-07-21-open-findings-fixes.md`](../plans/2026-07-21-open-findings-fixes.md),
  [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml),
  [`docs/issues/2026-05-22-gh-430-ci-equivalence.md`](2026-05-22-gh-430-ci-equivalence.md),
  [`docs/issues/2026-05-22-gh-433-openapi-drift.md`](2026-05-22-gh-433-openapi-drift.md)

## Summary

GitHub’s `test-e2e` job runs with `continue-on-error: true`, so a red Playwright
suite does not fail the workflow. Independently, several e2e helpers soft-skip
when hierarchy, worklist, multi-line, or exercise-fixture preconditions fail —
notably HIER-1 paths in `test_ui_coverage.py` and mass `@pytest.mark.skip`
stubs in `exercise_real_project.py` (CU-2.2). Together these produce **false
green merge confidence** without proving the advertised UI paths.

## Impact

- Branch protection can accept PRs while the SPA e2e surface is broken or unrun.
- Soft-skips convert environment/setup failures into “passed with skips,” so
  regressions in hierarchy selection, multi-line detail, and navigation never
  block merge.
- Process risk only (no user data loss). Still ranked **P0-CI-SOFT** in the
  deep-review plan for **merge confidence**; harden as **P2-E2E-GATE** after
  BUG-HIER-1.

## Environment / versions

- Source: multi-agent deep code review, Waves 4–5 of
  `docs/plans/2026-07-21-deep-code-review-continuation.md` (2026-07-21).
- Findings: **P0-CI-SOFT**, **P2-E2E-GATE**.
- Related but separate CI honesty work (do **not** duplicate here):
  pre-commit + knip gate parity →
  [`2026-05-22-gh-430-ci-equivalence.md`](2026-05-22-gh-430-ci-equivalence.md);
  OpenAPI drift target →
  [`2026-05-22-gh-433-openapi-drift.md`](2026-05-22-gh-433-openapi-drift.md);
  plan task packaging → `docs/plans/2026-07-21-ci-openapi-gates.md`.

## Evidence

1. **Non-blocking GH job** — `.github/workflows/ci.yml` `test-e2e` sets
   `continue-on-error: true` with comment “Temporary non-blocking gate pending
   root-cause fix for Playwright flakiness,” then runs
   `uv run --group e2e pytest tests/e2e -v -n auto`.

1. **HIER-1 soft-skips** — `tests/e2e/test_ui_coverage.py`
   `_select_first_word_via_hierarchy` returns `False` when hierarchy nodes are
   missing; callers `pytest.skip("No word-cell found…")` rather than fail.
   Documented as BUG-HIER-1 in
   `docs/plans/2026-07-21-open-findings-fixes.md`.

1. **Broader soft-skip surface** — same file skips on missing worklist rows,
   collapsed drawer, root redirect / empty root. Multi-line and related e2e
   modules use similar environment skips.

1. **Mass skip inventory** — `tests/e2e/exercise_real_project.py` marks multiple
   Phase-1 navigation tests `@pytest.mark.skip("TODO: walk in browser — CU-2.2")`,
   so large CU coverage never runs in CI.

1. **Plan disposition** — Wave 4 CI honesty explicitly **excludes** making e2e
   merge-blocking. After HIER-1, write a mini-plan: stable smoke suite list,
   soft-skip inventory, fail policy (`P2-E2E-GATE`).

## Root-cause hypotheses

1. **(Most likely) Temporary flakiness escape hatch never retired** — e2e was
   marked non-blocking while Playwright/fixture instability was unfixed; no
   follow-up made a smoke subset required.
2. **Soft-skip used as fixture tolerance** — hierarchy/worklist helpers treat
   missing DOM as skip-worthy environment noise instead of fixture or product
   failure, so real empty-hierarchy bugs never fail the suite.
3. **Incomplete CU walkthrough debt** — CU-2.2 stubs left as permanent
   `@pytest.mark.skip` rather than tracked fail-hard TODOs or a separate
   non-blocking suite label.

## Defects to fix

1. GitHub `test-e2e` does not fail the workflow (`continue-on-error: true`).
2. Hierarchy e2e soft-returns / soft-skips instead of failing when the exercise
   fixture should produce structure (BUG-HIER-1 / HIER-1).
3. Additional soft-skips in `test_ui_coverage`, multi-line e2e, and related
   modules convert setup failures into green skips.
4. `exercise_real_project` CU-2.2 mass `@pytest.mark.skip` leaves navigation
   coverage unexecuted without a merge-blocking alternative.

## Next steps

1. Land BUG-HIER-1 (fail-hard hierarchy waits on exercise fixture) from
   `docs/plans/2026-07-21-open-findings-fixes.md` — prerequisite for any hard
   e2e gate.
2. Write a **mini-plan for P2-E2E-GATE**: inventory every soft-skip and
   unconditional skip in `tests/e2e/`; classify as fixture-required fail,
   optional non-blocking, or delete.
3. Define a **stable smoke suite** (subset of e2e) that is merge-blocking;
   leave flaky or long CU walks non-blocking with an explicit job name.
4. Remove or qualify `continue-on-error` once smoke is green and required in
   branch protection.
5. Keep pre-commit/knip and openapi-drift work on their existing issue docs —
   this record only owns e2e honesty.

## What is NOT broken

- Unit and integration pytest jobs that exclude `e2e/` still block on failure.
- Frontend vitest / lint / build gates are independent of this issue.
- Pre-commit-all-files and frontend Knip gaps are tracked in
  [`2026-05-22-gh-430-ci-equivalence.md`](2026-05-22-gh-430-ci-equivalence.md),
  not here.
- OpenAPI drift checks are tracked in
  [`2026-05-22-gh-433-openapi-drift.md`](2026-05-22-gh-433-openapi-drift.md).
- Core product paths may still pass local Playwright when run with a built SPA
  and good fixtures; the defect is gate honesty, not necessarily total absence
  of e2e coverage.

## Resolution

Open. Discovered in the 2026-07-21 deep code review; disposition is Wave 3b
(HIER-1) then a post-HIER-1 mini-plan for P2-E2E-GATE — not part of Wave 4
ci-openapi packaging.

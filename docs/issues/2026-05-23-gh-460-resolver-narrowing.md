---
kind: issue
status: implemented
owner: maintainers
created: 2026-05-23
last_verified: 2026-07-19
level: I2
---

# Confirm the final resolver narrowing policy

## Agent Index

- **Kind:** issue
- **Status:** implemented
- **Level:** I2
- **Last verified:** 2026-07-19
- **Resolution:** Implemented locally; GitHub issue was open at export
- **Severity:** Low — unchecked structural fallback remains
- **Affected version:** commit `656bdf5`
- **Read when:** changing page payload narrowing or duck-typed page test fixtures.
- **Search terms:** Page resolver, isinstance, cast, PageRecord, duck typing, gh-460.
- **Relates to:** `docs/context/decisions.md`, page and word API resolvers

## Summary

GitHub issue #460 asked to replace casts introduced by #459 after PageRecord
landed. Current resolvers use `isinstance(payload, Page)` with a guarded
structural `.lines` fallback for duck-typed test objects. The repository has
accepted and documented that nominal-plus-structural policy.

## Impact

Pure nominal narrowing historically failed exactly 52 tests because the test
suite intentionally uses duck-typed `_StubPage` objects. The guarded structural
fallback preserves that compatibility while keeping the public resolver return
type at `Page | None`.

## Environment / versions

- Original author: `ConcaveTrillion`
- Created and last updated: 2026-05-23T16:25:57Z
- Labels: `kind:chore`, `status:blocked`, `area:refactor`, `priority:low`
- Original node ID: `I_kwDOSY7O8s8AAAABDMAaYQ`
- Raw SHA-256: `61d19b05ad9b33d7714a56aa08f69a0df12af6c3e45958e9a5d78569c0adb466`

## Evidence

Commit `b66fc19` narrowed both resolvers to `Page | None`, changed the payload
boundary from `Any` to `object`, and removed six `reportAny` suppressions. The
current implementations in `api/words.py` and `api/pages.py` use nominal
`isinstance` narrowing plus a `.lines` structural gate. The durable evolution
is recorded in `docs/context/decisions.md`.

The original acceptance criteria are satisfied as follows:

1. Replace casts with `isinstance` or an equivalent safe narrowing: both
   resolvers first use nominal `Page` checks and admit structural test doubles
   only after checking for `.lines`.
2. Preserve the 52-plus stub tests: the original experiment recorded exactly
   52 failures under nominal-only narrowing; the current resolver tests cover
   the compatible boundary.
3. Keep `make ci` green: commit `b66fc19` recorded a green gate apart from two
   stated pre-existing DocTR failures, and the migration reruns the current
   repository gate.
4. Document the decision: `docs/context/decisions.md` records `Page | None`
   with nominal-plus-structural narrowing.

## Root-cause hypotheses

Nominal `Page` checks alone are incompatible with intentionally duck-typed test
pages. The accepted structural fallback is the smallest compatible boundary.

## Defects to fix

No local defect remains from the original report. GitHub issue state needs
reconciliation with the implemented repository state.

## Next steps

Close GitHub issue #460 with commit `b66fc19`, the current resolver tests, and
the durable decision as evidence.

## Resolution

Implemented locally. GitHub issue #460 was still open when exported on
2026-07-19, and it had no public comments. Related history: #459 and
`pdomain-book-tools#206`.

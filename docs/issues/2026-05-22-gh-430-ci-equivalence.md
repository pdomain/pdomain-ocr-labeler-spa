---
kind: issue
status: active
owner: maintainers
created: 2026-05-22
last_verified: 2026-07-19
level: I1
---

# GitHub CI does not run the documented local gate

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-19
- **Resolution:** Open
- **Severity:** Medium — local and remote gates can disagree
- **Affected version:** commit `656bdf5`
- **Read when:** changing CI jobs, `make ci`, pre-commit, or frontend dead-code checks.
- **Search terms:** GitHub CI, make ci, pre-commit-check, frontend-knip, gh-430.
- **Relates to:** `Makefile`, `.github/workflows/ci.yml`

## Summary

GitHub CI does not run every check in the documented `make ci` contract. This
record migrates [GitHub issue #430](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/430).

## Impact

A change can pass remote CI while failing the required local gate, or vice
versa. This weakens the branch-protection signal.

## Environment / versions

- Original author: `ConcaveTrillion`
- Created and last updated: 2026-05-22T20:31:20Z
- Labels: `kind:chore`, `effort:S`, `status:backlog`, `area:ci`, `priority:medium`
- Original node ID: `I_kwDOSY7O8s8AAAABDIuVFA`
- Raw SHA-256: `0650f48f49a2d3d224e8ece28d5e393e66596cf103ac7787ef4a6f5f2139cd71`

## Evidence

`Makefile` defines `pre-commit-check` and `frontend-knip` as blocking parts of
`make ci`. `.github/workflows/ci.yml` has no equivalent job or step for either
gate. The full local contract currently runs setup, frontend dependency
installation, all-files pre-commit, type checking, OpenAPI export, frontend
build, Python lint, Python tests, behavior-coverage validation, frontend
formatting, frontend lint, frontend tests, and frontend Knip.

The original report came from
`docs/research/2026-05-22-deep-code-review-security-scan.md` at commit
`f4363ff`. Its citations to `Makefile:320` and the then-current workflow are
historical locations; the current files above are the verification evidence.

## Root-cause hypotheses

The workflow duplicated selected Make targets instead of invoking or fully
mirroring the canonical `make ci` contract.

## Defects to fix

1. Remote CI omits the all-files pre-commit gate.
2. Remote CI omits the frontend Knip dead-code gate.

## Next steps

Add explicit jobs for both gates or make the workflow invoke the canonical
contract. Verify that required branch checks cover the resulting jobs.

## Resolution

Open. No public comments existed at export time. The original issue recommended
`uv run pre-commit run --all-files` and `make frontend-knip` as explicit CI
steps, or direct use of `make ci`.

---
kind: issue
status: active
owner: maintainers
created: 2026-05-22
last_verified: 2026-07-19
level: I1
---

# OpenAPI drift checks include an ignored schema file

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-19
- **Resolution:** Open
- **Severity:** Medium — schema-file drift is not checked
- **Affected version:** commit `656bdf5`
- **Read when:** changing OpenAPI export, generated frontend types, or CI drift checks.
- **Search terms:** OpenAPI drift, frontend/openapi.json, gitignore, types.ts, gh-433.
- **Relates to:** `.github/workflows/ci.yml`, `.gitignore`, `Makefile`

## Summary

The OpenAPI CI step compares `frontend/openapi.json`, but Git ignores that
file. This record migrates
[GitHub issue #433](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/433).

## Impact

CI checks generated TypeScript drift but cannot detect a committed schema-file
change because no schema file is tracked.

## Environment / versions

- Original author: `ConcaveTrillion`
- Created and last updated: 2026-05-22T20:31:23Z
- Labels: `kind:chore`, `effort:S`, `status:backlog`, `area:ci`, `priority:medium`
- Original node ID: `I_kwDOSY7O8s8AAAABDIuV2w`
- Raw SHA-256: `80fb1593d6b80620ebca1aab368c1764a87585778fc1ba8f98f288bccd7027f0`

## Evidence

`.github/workflows/ci.yml` runs `git diff` against both
`frontend/src/api/types.ts` and `frontend/openapi.json`. `.gitignore` excludes
`frontend/openapi.json`; only the generated TypeScript file is tracked.

The original report came from
`docs/research/2026-05-22-deep-code-review-security-scan.md` at commit
`f4363ff`. It cited `.github/workflows/ci.yml:218` and `.gitignore:36`; those
line numbers describe the historical snapshot, while the current files still
show the same mismatch.

## Root-cause hypotheses

The drift command assumes the intermediate schema artifact is versioned, while
the repository intentionally treats it as generated output.

## Defects to fix

The workflow claims to compare the schema artifact but cannot observe it in a
Git diff.

## Next steps

Either track `frontend/openapi.json`, or compare a temporary exported schema
against an explicit canonical artifact and remove the ineffective diff target.

## Resolution

Open. No public comments existed at export time.

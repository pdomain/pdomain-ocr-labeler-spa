---
kind: issue
status: implemented
owner: maintainers
created: 2026-05-22
last_verified: 2026-07-19
level: I1
---

# Route tests do not enforce OpenAPI schema quality

## Agent Index

- **Kind:** issue
- **Status:** implemented
- **Level:** I1
- **Last verified:** 2026-07-19
- **Resolution:** Implemented locally; GitHub issue was open at export
- **Severity:** Medium — malformed response contracts can pass CI
- **Affected version:** commit `656bdf5`
- **Read when:** changing FastAPI response models, route tests, or OpenAPI conformance.
- **Search terms:** OpenAPI schema, response model, status code, content type, gh-437.
- **Relates to:** `tests/unit/api/test_wire_shapes.py`, route integration tests

## Summary

The repository now enforces the OpenAPI response contracts requested by the
original report. This record preserves the still-open GitHub issue and its
local implementation evidence. It migrates
[GitHub issue #437](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/437).

## Impact

Before the fix, an untyped response schema or incorrect success contract could
pass CI and reach generated clients.

## Environment / versions

- Original author: `ConcaveTrillion`
- Created and last updated: 2026-05-22T20:31:26Z
- Labels: `kind:chore`, `effort:S`, `status:backlog`, `area:tests`, `priority:medium`
- Original node ID: `I_kwDOSY7O8s8AAAABDIuWwA`
- Raw SHA-256: `7ec5792fe8a64b39dbb3d54eb5f0d5174354c15b9f3b68a217dacb05fb7004b9`

## Evidence

The original issue came from
`docs/research/2026-05-22-deep-code-review-security-scan.md` at commit
`f4363ff`. It cited `tests/unit/api/test_wire_shapes.py:16`,
`tests/integration/test_normalize_router.py:28`, and
`tests/integration/test_export_router.py:76` in that historical snapshot.

Current evidence supersedes that diagnosis:

- `tests/conformance/test_response_models.py` rejects missing or empty JSON
  response schemas across API routes.
- `tests/unit/api/test_route_conformance.py` enforces explicit response models,
  202 job-ID responses, JPEG declarations, and streaming response classes.
- Commits `bd3d173`, `e4838a1`, `8a80ce5`, and `7faaa7b` added and hardened the
  route conformance checks and contracts.

## Root-cause hypotheses

Historically, tests grew around individual routes without a repository-wide
OpenAPI quality invariant.

## Defects to fix

No local defect remains from the original report. GitHub issue state needs
reconciliation with the implemented repository state.

## Next steps

Close GitHub issue #437 with the implementation commits and current conformance
tests as evidence.

## Resolution

Implemented locally. GitHub issue #437 was still open when exported on
2026-07-19, and it had no public comments.

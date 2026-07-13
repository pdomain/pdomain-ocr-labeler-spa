---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-13
---

# Intent map

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-13
- **Read when:** deciding what to build next or what remains intentionally parked.
- **Search terms:** active intent, deferred, blocked, rejected, owner decision.

## Active

- Maintain the shipped FastAPI/React labeler and its driver contract.
- Complete the still-relevant items in the
  [PGDP alignment backlog](../plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md)
  without importing PGDP's pipeline-stage product scope.
- Keep behavior contracts and their coverage map aligned with executable tests.
- Implement the approved glyph-annotation design when prioritized; Q-A5–Q-A7
  no longer block it.

## Deferred

- Managed auth, S3, Postgres, and managed-adapter deployment axes remain
  deferred under D-042.
- Global jobs history, export history, and fuller preference persistence remain
  worthwhile alignment work.

## Blocked

No product-direction blocker is established by current repository evidence.

## Rejected

- Do not add the PGDP 24-stage pipeline, stage folders, or submit-check workflow
  to this labeler. Only shared shell, workbench, and operational patterns are in
  scope.
- Do not restore the standalone `WordEditDialog`; persistent right-panel editing
  superseded it.

## Needs owner decision

- Decide which remaining local UI wrappers require upstream `pdomain-ui`
  enhancements versus permanent local ownership.

## Legacy-unverified sweep

The 2026-07-13 checker-derived sweep classified all 118 legacy documents from
code, tests, git history, and graph links. Shipped architecture was declared
`built`; active process, runbook, behavior, milestone, and decision documents
remain live; completed or superseded execution and research artifacts were
retired. The durable changed directions and residual intent are recorded here
and in [`decisions.md`](decisions.md).

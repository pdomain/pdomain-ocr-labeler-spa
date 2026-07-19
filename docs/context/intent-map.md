---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-19
---

# Intent map

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-19
- **Read when:** deciding what to build next, what remains intentionally
  parked, or how shared page-schema convergence should proceed.
- **Search terms:** active intent, deferred, blocked, rejected, owner decision,
  PageRecord convergence, shared lifecycle, labeler extension.

## Active

- Maintain the shipped FastAPI/React labeler and its driver contract.
- Complete the still-relevant items in the
  [PGDP alignment backlog](../plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md)
  without importing PGDP's pipeline-stage product scope.
- Keep behavior contracts and their coverage map aligned with executable tests.
- Implement the approved glyph-annotation design when prioritized; Q-A5–Q-A7
  no longer block it.
- Reconcile driver-contract section 2.11 and its E2E coverage with the shipped
  right-panel editing model before deleting migrated GitHub issue #454.

## Done

- **Converged PageRecord imports without widening the shared schema.** Shared
  lifecycle fields remain owned by `pdomain_ops.pages.PageRecord`; Labeler-only
  view state remains in `extensions["labeler"]`. Production and test callers
  now import shared lifecycle types directly, and the `core.models`
  compatibility exports are removed. Persistence, validation, conversion, and
  rotation tests pass against the shared types.

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
- Do not move Labeler-only view state into the suite-wide PageRecord schema.
- Do not describe the current state as fully converged while both import paths
  remain supported.

## Needs owner decision

- Decide whether the remaining Tabs and Accordion compatibility wrappers need
  upstream `pdomain-ui` enhancements or permanent local ownership. Current
  composition is recorded in `docs/architecture/03-frontend.md` and
  `docs/architecture/26-right-panel-detail.md`.
- Decide whether the broad directory-level RUF002 exceptions in
  `pyproject.toml` are intentional policy. GitHub issue #456 removed the global
  ignore, but the remaining exceptions conflict with `CONVENTIONS.md`, which
  requires escaped ambiguous Unicode and rejects suppression as the remedy.

## Legacy-unverified sweep

The 2026-07-13 checker-derived sweep classified all 118 legacy documents from
code, tests, git history, and graph links. Shipped architecture was declared
`built`; active process, runbook, behavior, milestone, and decision documents
remain live; completed or superseded execution and research artifacts were
retired. The durable changed directions and residual intent are recorded here
and in [`decisions.md`](decisions.md).

---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-11-09
---

# Intent map

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-11-09
- **Read when:** deciding what to build next, what remains intentionally
  parked, or how shared page-schema convergence should proceed.
- **Search terms:** active intent, deferred, blocked, rejected, owner decision,
  PageRecord convergence, shared lifecycle, labeler extension.

## Active

- Finish suggestion accept/edit flows and predecessor-based compensating undo
  for the shipped typography correction journal. Phase-one manual review,
  current-epoch progress, combined completion gates, and immutable export are
  implemented.

- Maintain the shipped FastAPI/React labeler and its driver contract.
- Complete the still-relevant items in the
  [PGDP alignment backlog](../plans/2026-07-21-pgdp-alignment-remaining.md)
  without importing PGDP's pipeline-stage product scope.
- Keep behavior contracts and their coverage map aligned with executable tests.
- Finish the glyph picker enum parity in the [residual plan](../plans/2026-07-21-glyph-annotations-completion.md) .
  Manual review, bulk persistence, and glyph export already ship.
- Reconcile driver-contract section 2.11 and its E2E coverage with the shipped
  right-panel editing model. Its GitHub issue, #454, is already deleted.
- Keep test-project strictness work in its [focused plan](../plans/2026-07-21-tsconfig-test-strictness.md) ;
  `noUncheckedIndexedAccess` is still false. CI workflow equivalence and drift issues were closed as moot when
  workflows were removed.

## Done

- **Converged PageRecord imports without widening the shared schema.** Shared
  lifecycle fields remain owned by `pdomain_ops.pages.PageRecord`; Labeler-only
  view state remains in `extensions["labeler"]`. Production and test callers
  now import shared lifecycle types directly, and the `core.models`
  compatibility exports are removed. Persistence, validation, conversion, and
  rotation tests pass against the shared types.
- **Enforced OpenAPI response contracts.** Repository-wide conformance tests
  reject empty JSON schemas and verify response models, success responses,
  JPEG declarations, and streaming routes. GitHub issue #437 is deleted.
- **Accepted resolver narrowing.** Page resolvers return `Page | None` through
  nominal checks plus a guarded structural fallback for test doubles. GitHub
  issue #460 is deleted.

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

- Preserve the shared primitive and local adapter ownership recorded in `docs/architecture/03-frontend.md`. The
  September decision settles worklist ownership; it does not authorize a pipeline port.
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

## Residual work preserved by the 2026-11-07 consolidation

- U-M6 retains cross-OCR and rotation-boundary history, page-slot lineage, conservative pruning, and its retention
  policy in the [undo spec](../specs/2026-06-12-event-store-undo.md) . U-M7 history listing and jumps ship.
- Finer predictor-load progress needs an upstream callback or structured events. Keep that design in the
  [page-load spec](../specs/2026-08-08-page-load-progress-design.md) ; eager predictor warm-up was rejected.
- The [PGDP residual plan](../plans/2026-07-21-pgdp-alignment-remaining.md) retains export-dialog history
  hydration, the detail-shell comparison, and residual driver/adapter documentation. Server preferences remain
  deferred.
- Glyph enum parity remains required. Per-mark provenance, cross-page bulk marking, a profile registry, and
  prediction-only UI polish remain deferred. No predictor will be built here.
- Mixed-selection and mutation-error browser coverage remains a risk for multi-line editing; the existence of
  browser tests is not a fresh full-suite verification.

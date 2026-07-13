---
Status: active
Owner: CT
Created: 2026-07-13
Last verified: 2026-07-13
Kind: context
---

# Intent map

## Agent Index

- **Kind:** context
- **Status:** active
- **Read when:** planning page-schema or cross-application exchange work.
- **Search terms:** PageRecord convergence, shared lifecycle, labeler
  extension, compatibility facade.

## Active bets

- **Converge PageRecord imports without widening the shared schema.** Shared
  lifecycle fields remain owned by `pdomain_ops.pages.PageRecord`; Labeler-only
  view state remains in `extensions["labeler"]`. The Labeler backend
  maintainers own migration of callers that still use the `core.models`
  compatibility re-export. Completion means production callers import the
  shared type directly and the facade can be removed with persistence,
  validation, and rotation tests passing.

## Deferred work

None.

## Rejected directions

- Do not move Labeler-only view state into the suite-wide PageRecord schema.
- Do not describe the current state as fully converged while both import paths
  remain supported.

## Blocked (waiting on)

None.

## Needs owner decision

None.

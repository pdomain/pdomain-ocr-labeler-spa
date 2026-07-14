---
Status: active
Owner: CT
Created: 2026-07-13
Last verified: 2026-07-13
Kind: decision
---

# Keep PageRecord lifecycle fields shared

## Agent Index

- **Kind:** decision
- **Status:** active
- **Read when:** changing page metadata, rotation state, persistence, or
  Labeler-only page view state.
- **Search terms:** PageRecord, pdomain_ops, labeler extension, rotation,
  shared page schema.

## Context

The Labeler exchanges page lifecycle data with other suite applications. It
also needs view state that has no meaning outside the labeling workflow.
Historically, callers imported `PageRecord` through both the shared package and
the Labeler's local model module.

## Decision

`pdomain_ops.pages.PageRecord` owns cross-application lifecycle fields,
including rotation metadata. Labeler-only state belongs under the namespaced
`extensions["labeler"]` payload. `core.models.PageRecord` remains a temporary
compatibility re-export, not an independent schema.

## Rationale

One lifecycle schema prevents wire and persistence drift. A namespaced
extension keeps application-specific state available without making every
suite consumer depend on Labeler concepts.

## Consequences

Labeler code must import shared lifecycle types from `pdomain_ops.pages`.
Labeler-only state must use the namespaced extension. Removing the temporary
compatibility export does not change persisted data or the API wire shape.

## Supersedes / Superseded-by

This decision supersedes local ownership of the PageRecord lifecycle schema.
No later decision supersedes this boundary.

## Evidence

- `src/pdomain_ocr_labeler_spa/core/models.py` imports and re-exports
  `PageRecord` and `RotationSource` from `pdomain_ops.pages`.
- `src/pdomain_ocr_labeler_spa/core/labeler_extension.py` defines the
  Labeler-owned extension payload.
- `tests/integration/test_validation_persist_round_trip.py` exercises the
  direct shared import.
- `tests/integration/test_rotate_router.py` exercises the compatibility import.

## Remaining work

Move remaining callers to direct `pdomain_ops.pages` imports when doing so
improves ownership clarity, then remove the compatibility re-export in a
separately tested change. The implementation steps are in
[`../plans/2026-07-14-pagerecord-import-convergence.md`](../plans/2026-07-14-pagerecord-import-convergence.md).

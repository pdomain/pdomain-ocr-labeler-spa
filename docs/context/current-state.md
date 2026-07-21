---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-21
---

# Current state

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-21
- **Read when:** orienting on shipped behavior, open work, or repository risk.
- **Search terms:** current state, shipped, open work, risks, roadmap.

## Shipped system

The FastAPI and React SPA is the production labeler. The cut-over, hi-fi work,
selection operations, right-panel editing, event-store undo/redo, manual
rotation, and batch auto-rotation are implemented. Current architecture lives
in [`../architecture/`](../architecture/00-overview.md), with executable
evidence in `src/`, `frontend/src/`, and `tests/`.

Manual rotation and auto-rotation now rotate source images, rerun OCR, and
persist rotation metadata. The implementation is in
`src/pdomain_ocr_labeler_spa/core/jobs/handlers/rotate.py` and
`src/pdomain_ocr_labeler_spa/core/jobs/handlers/auto_rotate_all.py`; browser coverage is in
`tests/e2e/test_rotate_parity.py`. Earlier documentation that called these
handlers stubs was stale.

Page lifecycle types now have one import owner. Production and test callers
import `PageRecord` and `RotationSource` from `pdomain_ops.pages`; the temporary
`core.models` compatibility exports have been removed. Structural, persistence,
validation, conversion, and rotation tests enforce the boundary.

## Open work

Cross-cutting prioritization (deep review Waves 0–6, verified 2026-07-21):
[`../plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md).

**Split work packages (implement by issue):**
[`../issues/README.md`](../issues/README.md) — 17 deep-review issues under
`docs/issues/2026-07-21-*` plus prior #430/#433.

Standing overnight stream index:
[`../plans/2026-07-21-overnight-work-index.md`](../plans/2026-07-21-overnight-work-index.md).

- **Highest product risk (deep review + adversarial recheck):** char/glyph
  sidecar maps and rematch can return 200 without durable event-store write;
  export list API is empty while manifests exist; CLI export is not store-first;
  job SSE FE↔BE shape mismatch; canvas erase unmounted; image_drift banner
  hard-off. See Waves 0–1 and 3a/3b issues.
- PGDP/pdomain-ui alignment is partial. Remaining slices:
  [`../plans/2026-07-21-pgdp-alignment-remaining.md`](../plans/2026-07-21-pgdp-alignment-remaining.md)
  (source backlog:
  [`../plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md`](../plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md)).
- Glyph annotations (M11) are scaffolded (~35% scaffold / ~20% usable path).
  Residual wire-up:
  [`../plans/2026-07-21-glyph-annotations-completion.md`](../plans/2026-07-21-glyph-annotations-completion.md).
  Spec: [`../../specs/20-glyph-annotations.md`](../../specs/20-glyph-annotations.md).
- Active local issues: CI vs `make ci` (#430) and OpenAPI drift (#433) —
  [`../plans/2026-07-21-ci-openapi-gates.md`](../plans/2026-07-21-ci-openapi-gates.md).
- Open findings (keyboard, XDG data root, reload, hierarchy E2E):
  [`open-findings.md`](open-findings.md) and
  [`../plans/2026-07-21-open-findings-fixes.md`](../plans/2026-07-21-open-findings-fixes.md).
- Residual test-tsconfig strictness (#366 leftover):
  [`../plans/2026-07-21-tsconfig-test-strictness.md`](../plans/2026-07-21-tsconfig-test-strictness.md).
- Already done (do not re-plan): #404 lint-deviations catalogue
  (`docs/process/lint-deviations.md`), #437 OpenAPI schema quality tests, #460
  resolver narrowing, BUG-KBD-4 ConfirmDialog Escape.

## Risks

The behavior specification set remains a living contract and includes explicit
stubs or owner questions. Treat [`../specs/behavior/unclear-items.md`](../specs/behavior/unclear-items.md)
as the current ambiguity inventory, not deleted point-in-time parity audits.

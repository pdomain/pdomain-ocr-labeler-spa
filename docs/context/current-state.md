---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-13
---

# Current state

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-13
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

## Open work

- The PGDP/pdomain-ui alignment backlog remains partial. Shared shell and
  primitive migration shipped, while jobs chrome, suite endpoints, preference
  persistence, and several history/export surfaces remain in
  [`../plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md`](../plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md).
- Glyph annotations remain unimplemented backlog. Q-A5–Q-A7 are resolved, and
  the authoritative design is
  [`../../specs/20-glyph-annotations.md`](../../specs/20-glyph-annotations.md).
- The lint-suppression catalogue still has maintenance work tracked as #404.
- The open-finding backlog is maintained in
  [`open-findings.md`](open-findings.md).

## Risks

The behavior specification set remains a living contract and includes explicit
stubs or owner questions. Treat [`../specs/behavior/unclear-items.md`](../specs/behavior/unclear-items.md)
as the current ambiguity inventory, not deleted point-in-time parity audits.

---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-13
---

# Retirement manifest

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-13
- **Read when:** tracing a document removed by the initial docgraph migration.
- **Search terms:** retirement manifest, deleted docs, replacements, tombstones.

## Removal commit

The removal commit is the first docgraph migration commit. Its SHA is recorded
in the follow-up tombstone-completion commit because a commit cannot contain its
own SHA. Every source below remains recoverable with
`git log --all --full-history -- <old path>`.

## Per-document outcomes

Each row records the evidence-backed outcome and current replacement. Execution
checklists and transcripts were disposable; unique rationale remains in Git.

| Old path | Outcome | Current replacement or retained intent |
| --- | --- | --- |
| `docs/archive/plans/2026-05-14-konva-parity-execution-plan.md` | implemented | `docs/architecture/21-konva-renderer.md`, `22-page-surface-wireup.md`, `23-page-payload-backend.md` |
| `docs/archive/plans/2026-05-15-hifi-gaps-plan.md` | implemented | `docs/architecture/24-shell-layout.md` through `28-palettes-pickers.md` |
| `docs/archive/plans/2026-05-15-hifi-redesign-plan.md` | implemented | `docs/architecture/24-shell-layout.md` through `28-palettes-pickers.md` |
| `docs/archive/plans/2026-05-16-complete-labeler-spa.md` | implemented | `docs/architecture/00-overview.md`; cut-over state in `current-state.md` |
| `docs/archive/plans/2026-05-16-spec-open-questions.md` | implemented | current UI architecture; Q-A5–Q-A7 are resolved |
| `docs/archive/plans/2026-05-16-type-safety-silent-failures.md` | implemented | current API and persistence architecture/tests |
| `docs/archive/plans/2026-05-16-wire-missing-connections.md` | implemented | current drawer, search, and right-panel architecture/tests |
| `docs/archive/plans/hifi-followons.md` | implemented | current shell, drawer, and right-panel architecture |
| `docs/archive/plans/integration-session-plan.md` | implemented | `frontend/src/pages/ProjectPage.tsx` and current shell architecture |
| `docs/archive/plans/next-steps-2026-05-15.md` | superseded | `current-state.md` and active plans |
| `docs/archive/plans/plan-to-usable.md` | implemented | cut-over state in `current-state.md` |
| `docs/archive/research/BUGS_FOUND.md` | stale | `open-findings.md`, issue tracker, current state, and tests |
| `docs/archive/research/BUGS_RESOLVED.md` | retired | Git history and regression tests |
| `docs/archive/research/M9.5-keyboard-audit.md` | retired | closed audit; regression coverage remains in `tests/e2e/test_keyboard_only.py` |
| `docs/archive/research/PARITY_GAPS_2026_05_14.md` | superseded | architecture 21–23 and current behavior specs |
| `docs/archive/research/QUESTIONS_RESOLVED.md` | retired | `specs/17-decisions.md` and `decisions.md` |
| `docs/archive/research/legacy-archive-README.md` | superseded | `docs/README.md` |
| `docs/archive/specs/2026-05-12-auto-rotation-design.md` | superseded | `docs/architecture/19-auto-rotation.md` |
| `docs/archive/specs/2026-05-12-backend-design.md` | superseded | `docs/architecture/02-backend.md` and `23-page-payload-backend.md` |
| `docs/archive/specs/2026-05-12-data-models-design.md` | superseded | `docs/architecture/01-data-models.md` |
| `docs/archive/specs/2026-05-12-decisions-design.md` | superseded | `specs/17-decisions.md` |
| `docs/archive/specs/2026-05-12-deployment-dev-design.md` | superseded | `docs/architecture/15-deployment-dev.md` |
| `docs/archive/specs/2026-05-12-driver-contract-design.md` | superseded | `docs/architecture/13-driver-contract.md` |
| `docs/archive/specs/2026-05-12-export-design.md` | superseded | `docs/architecture/10-export.md` |
| `docs/archive/specs/2026-05-12-frontend-shell-design.md` | superseded | `docs/architecture/03-frontend.md` and `24-shell-layout.md` |
| `docs/archive/specs/2026-05-12-glyph-annotations-design.md` | superseded | `specs/20-glyph-annotations.md`; Q-A5–Q-A7 are resolved |
| `docs/archive/specs/2026-05-12-header-bar-design.md` | superseded | `docs/architecture/24-shell-layout.md` |
| `docs/archive/specs/2026-05-12-hotkeys-a11y-design.md` | superseded | `docs/architecture/12-hotkeys-a11y.md` |
| `docs/archive/specs/2026-05-12-image-viewport-design.md` | superseded | `docs/architecture/04-image-viewport.md` and `21-konva-renderer.md` |
| `docs/archive/specs/2026-05-12-milestones-design.md` | superseded | `specs/16-milestones.md` |
| `docs/archive/specs/2026-05-12-notifications-design.md` | superseded | `docs/architecture/11-notifications.md` |
| `docs/archive/specs/2026-05-12-overview-architecture-design.md` | superseded | `docs/architecture/00-overview.md` |
| `docs/archive/specs/2026-05-12-page-actions-design.md` | superseded | `docs/architecture/08-page-actions.md` |
| `docs/archive/specs/2026-05-12-persistence-design.md` | superseded | `docs/architecture/09-persistence.md` |
| `docs/archive/specs/2026-05-12-root-page-design.md` | superseded | `docs/architecture/03-frontend.md` and `24-shell-layout.md` |
| `docs/archive/specs/2026-05-12-testing-design.md` | superseded | `docs/architecture/14-testing.md` |
| `docs/archive/specs/2026-05-12-text-normalization-design.md` | superseded | `docs/architecture/18-text-normalization.md` |
| `docs/archive/specs/2026-05-12-toolbar-actions-design.md` | superseded | `docs/architecture/06-toolbar-actions.md` |
| `docs/archive/specs/2026-05-12-word-edit-dialog-design.md` | superseded | `docs/architecture/26-right-panel-detail.md` |
| `docs/archive/specs/2026-05-12-word-matches-design.md` | superseded | `docs/architecture/05-word-matches.md` and `25-drawer-worklist.md` |
| `docs/archive/specs/2026-05-24-F-001-export-path-traversal.md` | implemented | export containment code/tests and `docs/architecture/10-export.md` |
| `docs/archive/specs/2026-05-24-F-002-cors-and-auth-hardening.md` | implemented | bootstrap middleware and CORS regression tests |
| `docs/archive/specs/M0-acceptance.md` | retained build contract | consumed by `tests/unit/test_m0_acceptance.py`; explicitly excluded from retrieval |
| `docs/plans/2026-06-03-labeler-spa-legacy-parity.md` | superseded | current architecture and behavior specs |
| `docs/research/2026-05-22-deep-code-review-security-scan.md` | stale | current code/tests and issue tracker |
| `docs/research/2026-05-23-ci-e2e-root-cause.md` | implemented | Vite dedupe configuration and troubleshooting runbook |
| `docs/research/2026-05-31-doc-audit.md` | implemented | current runbooks and usage docs |
| `docs/research/2026-06-03-open-plans-specs-review.md` | stale | `current-state.md` and active plans/specs |
| `docs/research/2026-06-14-pgdp-design-handoff-labeler-spa-gap-analysis.md` | implemented | PGDP boundary and residual items in `intent-map.md` and alignment backlog |
| `docs/research/parity-audit/CONTINUE-SWEEP.md` | implemented | completed parity synthesis, now superseded by current behavior specs |
| `docs/research/parity-audit/PARITY-GAP.md` | stale | current behavior specs and `current-state.md` |
| `docs/research/parity-audit/legacy-a-screens.md` | superseded | later sweep and current behavior specs |
| `docs/research/parity-audit/legacy-b-content.md` | superseded | later sweep and current behavior specs |
| `docs/research/parity-audit/legacy-c-system.md` | superseded | later sweep and current behavior specs |
| `docs/research/parity-audit/new-a-screens.md` | superseded | later sweep and current behavior specs |
| `docs/research/parity-audit/new-b-content.md` | superseded | later sweep and current behavior specs |
| `docs/research/parity-audit/new-c-system.md` | superseded | later sweep and current behavior specs |
| `docs/research/parity-audit/sweep-2026-06-12-a-screens.md` | superseded | current behavior specs and architecture |
| `docs/research/parity-audit/sweep-2026-06-12-b-content.md` | superseded | current behavior specs and architecture |
| `docs/research/parity-audit/sweep-2026-06-12-c-system.md` | superseded | current behavior specs and architecture |
| `docs/specs/2026-06-05-selection-operations-parity.md` | implemented | selection store, Rail, and selection tests |
| `docs/specs/2026-06-06-word-edit-dialog-wiring.md` | superseded | right-panel architecture and tests |
| `docs/superpowers/plans/2026-06-14-component-migration-to-pdomain-ui.md` | superseded | upstream-first shell/component architecture |
| `docs/superpowers/plans/2026-06-14-upstream-first-pdomain-ui-component-migration.md` | implemented | current `pdomain-ui` dependencies and shell architecture |
| `docs/architecture/07-word-edit-dialog.md` | superseded | `docs/architecture/26-right-panel-detail.md` and `27-right-panel-sections.md` |
| `docs/plans/2026-06-06-parity-gap-completion.md` | implemented | current behavior specs, rotation architecture, and executable tests |

Non-Markdown archive placeholders and the two audit artifacts were removed with
their parent archive collection. Git history remains their provenance source.

## Classification evidence

The table's outcomes use the following concrete evidence bundles. Each bundle
applies to the named rows; replacement paths in the table provide the narrower
topic evidence.

- The 2026-05-12 archived design rows were moved to the archive by commit
  `33d9337`, which promoted their replacements into `docs/architecture/`.
  Implementations live in `src/pdomain_ocr_labeler_spa/` and `frontend/src/`;
  the corresponding regression suites live in `tests/` and colocated
  `frontend/src/**/*.test.tsx` files.
- The Konva and page-surface plan is proven by commit `33d9337`,
  `frontend/src/components/PageImageCanvas.tsx`,
  `frontend/src/pages/ProjectPage.tsx`, and
  `tests/e2e/test_image_click_selection.py`.
- The hi-fi plan rows are proven by commits `33d9337`, `fd57f8a`, `db42ed0`,
  and `db0441c`, plus the shell, drawer, and right-panel component tests.
- The connection/type-safety plan rows are proven by commits `893f8b5`,
  `afe6fd9`, and `509cfa1`, with router and component tests in `tests/` and
  `frontend/src/`.
- Export path containment is proven by commits `54e7f0f` and `0e44bbb` and
  `tests/unit/test_export_path_containment.py`. CORS/local-trust hardening is
  proven by commits `f2bd81b` and `2b90422` and the CORS/middleware unit tests.
- Rotation completion is proven by
  `src/pdomain_ocr_labeler_spa/core/jobs/handlers/rotate.py`,
  `auto_rotate_all.py`, `tests/integration/test_rotate_job.py`,
  `tests/integration/test_auto_rotate_all_job.py`, and
  `tests/e2e/test_rotate_parity.py`.
- The documentation-audit and CI-root-cause research rows are proven by commits
  `42b1415`, `948abf2`, and `ae0f789`, current runbooks, and
  `frontend/vite.config.ts`.
- The parity inventory/sweep rows are point-in-time evidence from commits
  `c0c6192`, `808eb24`, `02cc77d`, and `e6d610c`. Later commits `94451f5`,
  `db0441c`, and `fd57f8a` changed the product state, so current behavior specs
  and architecture supersede those inventories.
- Selection completion is proven by commit `006fcf3`,
  `frontend/src/stores/selection-store.ts`, and
  `frontend/src/lib/selection-expand.test.ts`. Standalone word-dialog wiring is
  superseded by commit `c5ddd35`, `docs/architecture/26-right-panel-detail.md`,
  and its colocated tests.
- The upstream-first `pdomain-ui` outcome is proven by commits `4dc4424`,
  `fb270a6`, `799fc0b`, `fcab138`, `b312a68`, `cedb967`, `77be4d4`, and
  `120d3ef`, plus the current frontend dependency and shell imports.

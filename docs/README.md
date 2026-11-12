---
kind: process
status: active
owner: maintainers
created: 2026-05-19
last_verified: 2026-11-12
---

# docs/

How documentation is organized in this repo.

| Folder | Purpose | Use when |
| --- | --- | --- |
| `architecture/` | Durable reference — how the system works today. | Capturing current shape (modules, data flow, contracts, current-state diagrams). |
| `context/` | Authored current state, intent, and durable migration decisions. | Orienting work or finding retired-topic tombstones. |
| `decisions/` | ADRs — dated, append-only "we chose X because Y." | Recording a specific design choice with context, alternatives, consequences. |
| `issues/` | Governed records for active defects, investigations, and deferred work. | Replacing tracker issues with durable repository evidence. |
| `plans/` | Active execution — what order to make a spec real. | Sequencing work for an approved spec. |
| `process/` | Cross-cutting workflow conventions (verification rules, merge strategy, release process). | Capturing how the team works, not what the system does. |
| `runbooks/` | Operational reference — something is broken or being operated. | An on-call or ops task needs a recipe. |
| `specs/` | Aspirational, pre-implementation design. | Describing what to build, before code. |
| `templates/` | Issue, spec, plan, ADR boilerplate. | Adding a starter template for a new doc type. |
| `usage/` | Downstream reference — how to consume this app/tool/library. | A user or integrator needs to know how to use it. |

Retired material remains available through Git history instead of live retrieval.

Active docs map to GitHub issues — see this repo's issue tracker for status.
This layout is workspace-standard; see
`/workspaces/ocr-container/docs/README.md` for the master.

---

## Active documents

### runbooks/

- [`runbooks/local-dev.md`](runbooks/local-dev.md) — local development setup and recipes
- [`runbooks/release.md`](runbooks/release.md) — wheel build process, versioning, release workflow
- [`runbooks/troubleshooting.md`](runbooks/troubleshooting.md) — common failure modes and fixes

### usage/

- [`usage/quickstart.md`](usage/quickstart.md) — end-user install and run guide

### architecture/

- [`architecture/module-map.md`](architecture/module-map.md) — source module layout
- [`architecture/runtime-flows.md`](architecture/runtime-flows.md) — major data and control flows
- `architecture/00-overview.md` through `architecture/28-palettes-pickers.md` — per-feature design reference
- [Glyph annotations](architecture/20-glyph-annotations.md) — manual review, persistence, and export.
- [Page loading and history](architecture/29-page-loading-and-history.md) — cold-page jobs and version navigation.
- [Repository boundaries](architecture/30-repository-boundaries.md) — what this SPA owns, and which sibling repo owns
  the rest.
- [Typography review](architecture/31-typography-review.md) — shipped inline-typography contract.

### context/

- [`context/current-state.md`](context/current-state.md) — shipped behavior, open work, and risks
- [`context/intent-map.md`](context/intent-map.md) — the roadmap: now, next, later, and rejected work
- [`context/decisions.md`](context/decisions.md) — durable decisions and retirement tombstones
- [`context/completed-github-issues-ledger.md`](context/completed-github-issues-ledger.md)
  — completed issue provenance, coverage, and deletion status
- [`context/retirement-manifest.md`](context/retirement-manifest.md) — per-document outcomes and replacements
- [`context/open-findings.md`](context/open-findings.md) — six findings, all closed on 2026-09-18

### issues/

- [`issues/README.md`](issues/README.md) — governed issue-record format and lifecycle

### plans/

- [PGDP residual work](plans/2026-07-21-pgdp-alignment-remaining.md) — export history, detail shell, and documentation.
- [Glyph enum parity](plans/2026-07-21-glyph-annotations-completion.md) — remaining picker alignment.
- [Test TypeScript strictness](plans/2026-07-21-tsconfig-test-strictness.md) — test-project compiler checks.

### specs/

Shipped behavior is under `architecture/`. These files keep unfinished design and the executable behavior contracts.

- [Typography design](specs/2026-08-21-typography-review-and-training-export-design.md) — suggestion undo and the open
  owner choices. Shipped phase one is [architecture/31](architecture/31-typography-review.md).
- [Undo across re-OCR](specs/2026-06-12-event-store-undo.md) — U-M6. Shipped undo and U-M7 are [architecture/29](architecture/29-page-loading-and-history.md).
- [Page-load progress](specs/2026-08-08-page-load-progress-design.md) — the finer predictor-build stage. Shipped
  cold-page jobs are [architecture/29](architecture/29-page-loading-and-history.md).
- [Behavior completion design](specs/2026-06-01-ocr-labeler-behavior-completion-design.md) — June design. Do not treat
  its deferred list as the roadmap.
- [`specs/behavior/README.md`](specs/behavior/README.md) — behavior contracts and coverage
- [`../specs/README.md`](../specs/README.md) — historical milestones and the ADR log

### research/

- [CharRange deletion inventory](research/2026-08-22-char-range-deletion-inventory.md) — the clean break found nothing
  to migrate, and the legacy route is gone.

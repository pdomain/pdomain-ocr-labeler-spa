---
kind: process
status: active
owner: maintainers
created: 2026-05-19
last_verified: 2026-07-13
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

### context/

- [`context/current-state.md`](context/current-state.md) — shipped behavior, open work, and risks
- [`context/intent-map.md`](context/intent-map.md) — active, deferred, blocked, and rejected intent
- [`context/decisions.md`](context/decisions.md) — durable decisions and retirement tombstones
- [`context/retirement-manifest.md`](context/retirement-manifest.md) — per-document outcomes and replacements
- [`context/open-findings.md`](context/open-findings.md) — unresolved defects transferred from the retired bug ledger

### issues/

- [`issues/README.md`](issues/README.md) — governed issue-record format and lifecycle

### plans/

- [`plans/2026-06-08-compute-settings-panel.md`](plans/2026-06-08-compute-settings-panel.md)
- [`plans/2026-06-10-export-manifest-and-send-to-trainer.md`](plans/2026-06-10-export-manifest-and-send-to-trainer.md)
- [`plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md`](plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md)
- [`plans/2026-06-16-pdomain-ui-primitive-migration.md`](plans/2026-06-16-pdomain-ui-primitive-migration.md)

### specs/

- [`specs/2026-06-01-ocr-labeler-behavior-completion-design.md`](specs/2026-06-01-ocr-labeler-behavior-completion-design.md)
- [`specs/behavior/README.md`](specs/behavior/README.md) — behavior contracts and coverage
- [`../specs/README.md`](../specs/README.md) — milestone, decision, and glyph specifications

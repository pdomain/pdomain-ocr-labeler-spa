---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-13
---

# Decisions

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-13
- **Read when:** looking for durable migration, lifecycle, or changed-direction rationale.
- **Search terms:** decisions, tombstones, retirement, changed direction, docgraph.

## 2026-07-13 — Retire retrieval-hostile historical scaffolding

### Context

Docgraph initialization found 681 issues across 135 documents. Archived plans,
draft specs, resolved ledgers, and point-in-time research dominated stale,
orphan, missing-section, and dangling-link findings. Read-only reviewers checked
each legacy document against current code, tests, git history, and graph links.

### Decision

Remove the retired `docs/archive/**` tree and completed or superseded research,
plan, and spec artifacts from live retrieval. Git history preserves their exact
text and binary evidence. Present-tense behavior stays in `docs/architecture/`;
residual intent stays in [`intent-map.md`](intent-map.md); current operations stay
in `docs/process/`, `docs/runbooks/`, and `docs/usage/`.

### Consequences

Search results no longer present historical gaps as current truth. Historical
provenance requires Git history, while current readers get a smaller,
evidence-backed graph.

### Supersedes / Superseded-by

This decision supersedes the repository convention of keeping closed bug,
question, plan, and spec ledgers in the live `docs/archive/` retrieval tree.

## Migration tombstones

### Retired archive collection

- Old paths: every tracked file formerly under `docs/archive/`, including the
  11 plan files, 7 research files, 26 spec files, archive placeholders, and two
  research binary artifacts present at migration start.
- Outcome: implemented, superseded, stale, or retired according to the
  evidence-backed 2026-07-13 sweep.
- Replacement: `docs/architecture/00-overview.md` through
  `docs/architecture/28-palettes-pickers.md`, `specs/17-decisions.md`, this
  decision log, and Git history.
- Removal commit: the 2026-07-13 docgraph migration commit.
- Rationale kept: shipped design and changed directions are in current
  architecture and the context docs.
- Remaining work: glyph annotations and other residual items are in
  [`intent-map.md`](intent-map.md).

### Retired point-in-time research collection

- Old paths: `docs/research/2026-05-22-deep-code-review-security-scan.md`,
  `2026-05-23-ci-e2e-root-cause.md`, `2026-05-31-doc-audit.md`,
  `2026-06-03-open-plans-specs-review.md`,
  `2026-06-14-pgdp-design-handoff-labeler-spa-gap-analysis.md`, and every file
  formerly under `docs/research/parity-audit/`.
- Outcome: implemented, superseded, or stale.
- Replacement: current architecture, runbooks, behavior specifications, and
  the partial PGDP alignment backlog.
- Removal commit: the 2026-07-13 docgraph migration commit.
- Rationale kept: the PGDP scope boundary and remaining alignment intent are in
  [`intent-map.md`](intent-map.md).
- Remaining work: see the Active, Deferred, and Blocked intent sections.

### Retired current-tree execution artifacts

- Old paths: `docs/plans/2026-06-03-labeler-spa-legacy-parity.md`,
  `docs/specs/2026-06-05-selection-operations-parity.md`,
  `docs/specs/2026-06-06-word-edit-dialog-wiring.md`,
  `docs/superpowers/plans/2026-06-14-component-migration-to-pdomain-ui.md`, and
  `docs/superpowers/plans/2026-06-14-upstream-first-pdomain-ui-component-migration.md`.
- Outcome: implemented or superseded.
- Replacement: behavior specifications, right-panel architecture, current
  `pdomain-ui` shell architecture, and Git history.
- Removal commit: the 2026-07-13 docgraph migration commit.
- Rationale kept: the right-panel and upstream-first changed directions are
  recorded in current architecture and [`intent-map.md`](intent-map.md).
- Remaining work: the partial PGDP alignment backlog remains active.

## 2026-07-13 — Rotation is shipped behavior

### Context

Older milestone and bug text said manual and batch auto-rotation only had job
and SSE plumbing. Current handlers rotate the image, rerun OCR, persist
metadata, protect manual overrides, and report progress. E2E tests exercise the
round trip.

### Decision

Treat manual and batch auto-rotation as built architecture. Future docs must use
the handlers and `tests/e2e/test_rotate_parity.py` as evidence.

### Consequences

Rotation is no longer listed as stubbed work. Product-level configuration or UI
enhancements may still be planned separately.

### Supersedes / Superseded-by

Supersedes the stale rotation warning formerly in `CLAUDE.md` and the retired
bug/parity ledgers.

## 2026-07-13 — Preserve the behavior flow taxonomy

### Context

`docs/specs/behavior/flows.md` declared `behavior-flow-spec` in its Agent Index
but inherited the generic `spec` kind during metadata normalization.

### Decision

Keep the more specific `behavior-flow-spec` kind in both metadata sources.

### Consequences

Behavior-flow retrieval retains its established taxonomy without changing the
document's lifecycle status.

### Supersedes / Superseded-by

Supersedes the generic kind written during this uncommitted migration batch.

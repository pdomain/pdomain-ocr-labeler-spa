---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-19
---

# Decisions

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-19
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
- Removal commit: `ee95c83`.
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
- Removal commit: `ee95c83`.
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
- Removal commit: `ee95c83`.
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

## 2026-07-14 — Retire the PageRecord import convergence plan

### Context

The PageRecord import convergence plan completed its test-first migration.
Production and test callers now import shared lifecycle types from
`pdomain_ops.pages`, and `core.models` no longer exposes the compatibility
names.

### Decision

Remove the completed execution checklist from live retrieval. Keep the shared
schema boundary and shipped evidence in
[`../architecture/01-data-models.md`](../architecture/01-data-models.md#pagerecord)
and
[`../decisions/2026-07-13-shared-page-record-boundary.md`](../decisions/2026-07-13-shared-page-record-boundary.md).

### Consequences

Docgraph retrieval points readers to present-tense architecture instead of a
completed command checklist. Git history preserves the exact plan.

### Supersedes / Superseded-by

- Old path: `docs/plans/2026-07-14-pagerecord-import-convergence.md`.
- Outcome: implemented and retired.
- Superseded by: `docs/architecture/01-data-models.md`.
- Removal commit: the commit containing this tombstone.
- Rationale kept: shared ownership and evidence are in the architecture and
  decision records linked above.
- Remaining work: none.

## 2026-07-19 — Preserve typed resolver narrowing from GitHub issue #459

### Context

Commit `b66fc19` typed both page resolvers as `Page | None`, changed the loader
payload boundary from `Any` to `object`, and removed six `reportAny`
suppressions. It used casts after the envelope guard because tests supplied
duck-typed page stubs. Later PageRecord work retained the typed boundary but
replaced the cast with runtime and `.lines` narrowing.

### Decision

Keep `Page | None` as the resolver contract and narrow the `object` payload at
the resolver boundary. Treat the historical cast as superseded implementation
detail, not current architecture.

### Consequences

Callers use typed page, line, and word attributes without `reportAny`
suppressions. Duck-typed test objects remain supported by the current `.lines`
gate.

### Supersedes / Superseded-by

This records the durable outcome and later evolution of GitHub issue #459. The
current implementation lives in `src/pdomain_ocr_labeler_spa/api/words.py` and
`src/pdomain_ocr_labeler_spa/api/pages.py`.

## 2026-07-19 — Retire the closed GitHub issues archive

### Context

Commit `5cdb276` captured all 425 closed GitHub issues in one lossless archive.
The archive contains each issue's metadata, full body, public comments, and raw
record digest. Its SHA-256 is
`6f27ae91252d0d0470cab287b4cf184aeca785fdb5c41a1bf5b949ebb55f3e99`.

### Decision

Remove the 852 KB archive from live retrieval after its dedicated commit. Keep
the compact reconciliation ledger live and use Git history for verbatim issue
recovery.

### Consequences

Current docgraph searches avoid 425 historical issue bodies. Migration review
can still recover the exact archive before any GitHub deletion.

### Supersedes / Superseded-by

- Old path: `docs/decisions/2026-07-19-closed-github-issues-archive.md`.
- Outcome: archived in Git and retired from the live tree.
- Superseded by: `docs/context/completed-github-issues-ledger.md`, current
  architecture, and context decisions.
- Archive commit: `5cdb276`.
- Recovery command:
  `git show 5cdb276:docs/decisions/2026-07-19-closed-github-issues-archive.md`.
- Remaining work: complete architecture coverage and deletion readiness for
  every ledger row before remote issue deletion.

## 2026-07-19 — Retire the pdomain-ui primitive migration plan

### Context

All six migration slices shipped. The final implementation kept local
composition boundaries for BusyOverlay, Tabs, and Accordion where the labeler
contract differs from the shared primitives.

### Decision

Remove the completed execution checklist from live retrieval. Keep shared
primitive ownership and the shipped wrapper deviations in current architecture.

### Consequences

Architecture now directs future wrapper work. The unresolved upstream-versus-
local ownership question remains in [`intent-map.md`](intent-map.md).

### Supersedes / Superseded-by

- Old path: `docs/plans/2026-06-16-pdomain-ui-primitive-migration.md`.
- Outcome: implemented and retired.
- Superseded by: `docs/architecture/03-frontend.md`,
  `docs/architecture/11-notifications.md`,
  `docs/architecture/26-right-panel-detail.md`, and
  `docs/architecture/28-palettes-pickers.md`.
- Removal commit: the commit containing this tombstone.
- Rationale kept: current architecture and Git history.
- Remaining work: the wrapper ownership decision in `intent-map.md`.

## 2026-07-19 — Retire the confirmed bug-fixes plan

### Context

The compute-device preference, reload OCR timeout, OCR concurrency cap,
API-client correction, and dependency-pin follow-up all shipped. The temporary
dependency deferral was later resolved by the current dependency floor.

### Decision

Remove the completed execution checklist from live retrieval. Keep the device,
timeout, concurrency, and API contracts in current architecture.

### Consequences

Source and test provenance now points to architecture instead of a completed
plan. No residual plan work remains.

### Supersedes / Superseded-by

- Old path: `docs/plans/2026-07-14-review-fixes.md`.
- Outcome: implemented and retired.
- Superseded by: `docs/architecture/02-backend.md` and
  `docs/architecture/03-frontend.md`.
- Removal commit: the commit containing this tombstone.
- Rationale kept: current architecture and Git history.
- Remaining work: none.

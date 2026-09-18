---
Status: active
Owner: maintainers
Created: 2026-07-19
Last verified: 2026-09-18
Kind: process
Level: I1
---

# Issues

## Agent Index

- **Kind:** process
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-09-18
- **Read when:** filing a bug / defect / investigation report, or looking up an
  open issue's status, evidence, or resolution.
- **Search terms:** issues folder, bug report, defect report, issue template,
  issue lifecycle, kind issue.

## Purpose

`docs/issues/` holds **governed, evidence-bearing issue reports** — bugs, silent
failures, regressions, and investigations that need a durable, citable record
(not a throwaway chat summary). Each report is a docgraph node so it is
retrievable, linkable from specs/plans/context, and carried in the repo rather
than in per-machine harness memory.

**There are no open issues right now.** The last one was retired on
2026-09-18. Every report ever filed here — the 18 deep-review reports, the
two migrated GitHub records, and every report filed and closed the same day —
is resolved and deleted; each retirement's reasoning is a tombstone in
[`../context/decisions.md`](../context/decisions.md). See
[`../context/current-state.md`](../context/current-state.md) for what is
actually still open in the product, most of it found rather than filed as a
governed report.

## Convention

- **Location:** `docs/issues/`
- **Filename:** `YYYY-MM-DD-short-slug.md` (creation date + a terse kebab slug).
- **Metadata:** YAML frontmatter **and** a matching `## Agent Index` block. Keep
  frontmatter `Status:` and Agent Index `Status:` identical — a mismatch trips a
  `field_conflict` (→ `status-reconciler`).
  - `Kind: issue`
  - `Level:` informational scope — `I1` repo-wide, `I2` narrow/local.
  - `Status:` governed lifecycle, **not** the issue's open/closed state (see below).
- **Issue state vs governed status:** the docgraph lifecycle is
  `draft → active → implemented → retired`. Express the *issue's* resolution state
  as a separate **`Resolution:`** line in the Agent Index (`Open` / `Resolved` /
  `Won't fix` / `Duplicate`) and a final `## Resolution` section. Map the governed
  `Status:`:
  - **Open** → `Status: active`.
  - **Resolved / Won't fix / Duplicate** → route through `doc-retirer`, which
    **deletes** the report. Promote any specific a reader still needs into the
    architecture or process doc that owns it, repoint inbound references at the
    resolving commit, drop the pointer below, and append a tombstone to
    `docs/context/decisions.md`. Git history keeps the report, so no resolved
    file stays in the tree and there is no resolved index to maintain.
- **Link it (no orphans):** reference every new issue from a governed doc — by
  default an **Open issues** bullet in `docs/context/intent-map.md`, or a Risk in
  `docs/context/current-state.md`. When this folder holds a live issue again, list
  it below too, which satisfies the no-orphan rule.
- **Stage + reindex:** under `mode = "git"` a new doc is invisible until
  `git add`ed; stage it, then `docgraph reindex` and `docgraph check --strict` the
  same turn (a new `dangling` blocks completion).
- **Template:** copy `TEMPLATE.md` in this folder. It is index-excluded (a
  top-of-file `<!-- docgraph: ignore -->` marker), so **do not markdown-link to
  it** from a governed doc — the link would dangle. Refer to it by path / inline
  code.

## Recommended structure

Summary · Impact · Environment/versions · Evidence (reproduction & diagnosis,
with commands/output) · Root-cause hypotheses (ranked) · Defects to fix ·
Recommended next steps · What is NOT broken (scopes the fix) · Resolution.

Lead with the **smallest decisive evidence**, separate **observation** from
**hypothesis**, and always include a **What is NOT broken** section.

## GitHub-migrated issue records

The 430 CI-equivalence and 433 OpenAPI-drift records are retired as moot: the
GitHub workflows they describe were deleted on 2026-09-13 in `df3f5ff`. See the
2026-09-18 tombstone in [`../context/decisions.md`](../context/decisions.md).

The 437 schema-quality and 460 resolver-narrowing records were implemented and
are retired; see the 2026-09-18 tombstone in
[`../context/decisions.md`](../context/decisions.md). Their upstream GitHub
issues may still be open.

## Deep-review split issues (2026-07-21)

Prioritization authority:
[`../plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md).

Open findings (XDG, RELOAD, HIER — the keyboard entries closed 2026-09-18)
remain in [`../context/open-findings.md`](../context/open-findings.md) + plan
[`../plans/2026-07-21-open-findings-fixes.md`](../plans/2026-07-21-open-findings-fixes.md)
— not re-filed as separate issues.

### Wave 0 — data integrity

All four reports are resolved and deleted. See the 2026-08-08 tombstones in
[`../context/decisions.md`](../context/decisions.md).

### Wave 1 — export loop

All three reports are resolved and deleted: the export-list and store-first-CLI
ones in the 2026-08-08 tombstones, and the normalize flag in the 2026-09-18
tombstone. See [`../context/decisions.md`](../context/decisions.md).

### Wave 2 — M11 glyph

Resolved and deleted. See the 2026-09-18 tombstone in
[`../context/decisions.md`](../context/decisions.md).

### Wave 4–5 — CI confidence + suite chrome

All reports are resolved and deleted. The project-list one is in the
2026-09-18 tombstones. See [`../context/decisions.md`](../context/decisions.md).

Resolved reports are deleted, so this index tracks open work only — right now
that is nothing. Past resolutions live in the `docs/context/decisions.md`
tombstones and in git history.

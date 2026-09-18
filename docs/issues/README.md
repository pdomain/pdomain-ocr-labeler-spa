---
Status: active
Owner: maintainers
Created: 2026-07-19
Last verified: 2026-07-21
Kind: process
Level: I1
---

# Issues

## Agent Index

- **Kind:** process
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
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
  `docs/context/current-state.md`. This `README` also links the live issues below,
  which satisfies the no-orphan rule.
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

- [`2026-05-22-gh-430-ci-equivalence.md`](2026-05-22-gh-430-ci-equivalence.md)
  — open (pre-commit + knip missing from GH).
- [`2026-05-22-gh-433-openapi-drift.md`](2026-05-22-gh-433-openapi-drift.md)
  — open (drift job vs gitignored openapi.json).
- [`2026-05-22-gh-437-openapi-schema-quality.md`](2026-05-22-gh-437-openapi-schema-quality.md)
  — implemented locally; GitHub closure may lag.
- [`2026-05-23-gh-460-resolver-narrowing.md`](2026-05-23-gh-460-resolver-narrowing.md)
  — implemented locally; GitHub closure may lag.

## Deep-review split issues (2026-07-21)

Prioritization authority:
[`../plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md).

Open findings (keyboard, XDG, RELOAD, HIER) remain in
[`../context/open-findings.md`](../context/open-findings.md) + plan
[`../plans/2026-07-21-open-findings-fixes.md`](../plans/2026-07-21-open-findings-fixes.md)
— not re-filed as separate issues.

### Wave 0 — data integrity

All four reports are resolved and deleted. See the 2026-08-08 tombstones in
[`../context/decisions.md`](../context/decisions.md).

### Wave 1 — export loop

| Issue | ID | Sev |
| --- | --- | --- |

The export-list and store-first-CLI reports are resolved and deleted; see the
2026-08-08 tombstones in [`../context/decisions.md`](../context/decisions.md).
The normalize report stays open on its frontend half.

### Wave 2 — M11 glyph

| Issue | ID | Sev |
| --- | --- | --- |
| [`2026-07-21-glyph-m11-usable-path-incomplete.md`](2026-07-21-glyph-m11-usable-path-incomplete.md) | P0-GLYPH-* | High |

### Wave 3a — job SSE

| Issue | ID | Sev |
| --- | --- | --- |

### Wave 3b — product honesty

| Issue | ID | Sev |
| --- | --- | --- |

### Wave 4–5 — CI confidence + suite chrome

| Issue | ID | Sev |
| --- | --- | --- |
| [`2026-07-21-project-list-metadata-filters-noop.md`](2026-07-21-project-list-metadata-filters-noop.md) | P2-ROOT | Medium |

## Page-load status (2026-08-08)

| Issue | ID | Sev |
| --- | --- | --- |

## Tooling (2026-08-08)

| Issue | ID | Sev |
| --- | --- | --- |
| [`2026-08-08-ruff-version-skew.md`](2026-08-08-ruff-version-skew.md) | P1-RUFF-SKEW | Medium |
| [`2026-08-08-dep-refresh-cannot-auto-land.md`](2026-08-08-dep-refresh-cannot-auto-land.md) | P2-DEP-REFRESH | Medium |

## Word editing (2026-09-18)

| Issue | ID | Sev |
| --- | --- | --- |
| [`2026-09-18-the-word-edit-dialog-the-driver-contract-documents-does-not-exist.md`](2026-09-18-the-word-edit-dialog-the-driver-contract-documents-does-not-exist.md) | P2-WORD-EDIT | Low |
| [`2026-09-18-the-per-word-validate-button-can-never-validate-a-word.md`](2026-09-18-the-per-word-validate-button-can-never-validate-a-word.md) | P1-VALIDATE-GATE | Medium |
| [`2026-09-18-text-normalization-waits-on-a-module-that-has-never-existed.md`](2026-09-18-text-normalization-waits-on-a-module-that-has-never-existed.md) | P2-NORMALIZE-DEAD | Low |

## Selection (2026-09-17)

| Issue | ID | Sev |
| --- | --- | --- |
| [`2026-09-17-a-word-or-line-selection-jumps-to-another-item-on-page-change.md`](2026-09-17-a-word-or-line-selection-jumps-to-another-item-on-page-change.md) | P2-SELECTION-PAGE | Low |

Resolved reports are deleted, so this index tracks open work only. Past
resolutions live in the `docs/context/decisions.md` tombstones and in git
history.

---
kind: handoff
status: "active"
created: "2026-07-21"
created_at: "2026-07-21T14:26:45Z"
owner: maintainers
branch: master
scope: deep-review-continuation
worktree: /workspaces/pdomain/pdomain-ocr-labeler-spa
base_commit: 6e9770ce5e9121b8169b0abab3e9e019efbfdd1c
supersedes: ""
---

# Deep-review residual implementation — handoff

## Agent Index

- Kind: handoff
- Status: active
- Read when: picking up residual product work from the 2026-07-21 multi-agent
  deep code review (data integrity, export, glyph, job SSE, product honesty).
- Search terms: deep review, Wave 0, sidecar durability, rematch, export CLI,
  glyph M11, job SSE, docs/issues 2026-07-21

## Goal

Continue implementation from the deep code review prioritization plan. Core
labeling is substantially shipped; next session should close **silent data
loss** first (Wave 0), then export loop, glyph M11, job SSE / product honesty,
CI, and suite chrome — preferably by **issue work package**, not by re-auditing
the whole tree.

## Done this session

1. Multi-agent deep review (8 explore agents + adversarial rechecks).
2. Prioritization plan:
   `docs/plans/2026-07-21-deep-code-review-continuation.md` (Waves 0–6, issue
   index, adversarial recheck section).
3. Overnight stream index with hard gate vs Wave 0:
   `docs/plans/2026-07-21-overnight-work-index.md`.
4. Sibling residual plans present (glyph, open-findings, CI/openapi, PGDP,
   tsconfig).
5. **18 governed issues** under `docs/issues/2026-07-21-*` + catalogue in
   `docs/issues/README.md`.
6. Linked from `docs/context/current-state.md` and `AGENTS.md` open work.
7. Commits on `master` (not pushed):
   - `ac270ba` — deep-review plan, residual issues, work packages
   - `6e9770c` — AGENTS open-work pointers
8. Working tree clean at handoff `base_commit`.

## Not done (next session owns)

Prefer Wave 0 first — implement via issue files:

| Priority | Issue | Wave |
| --- | --- | --- |
| 1 | `docs/issues/2026-07-21-sidecar-char-maps-not-durable.md` | 0.1–0.2, 0.6 |
| 2 | `docs/issues/2026-07-21-rematch-gt-not-durable.md` | 0.3 |
| 3 | `docs/issues/2026-07-21-save-project-false-clean.md` | 0.4 (+ `save_page`) |
| 4 | `docs/issues/2026-07-21-mutation-store-silent-200.md` | 0.5 |
| 5 | `docs/issues/2026-07-21-export-list-api-empty.md` | 1.0–1.1 |
| 6 | `docs/issues/2026-07-21-cli-export-not-store-first.md` | 1.2–1.5 |
| 7 | `docs/issues/2026-07-21-job-sse-fe-be-shape-mismatch.md` | 3a (parallel-safe) |
| 8 | `docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md` | 2 (T1 anytime; T3 after 0.1) |

Also open (parallel-safe / later): canvas erase, image-drift, job cancel, match
nav, bbox refine labels, suite launcher, jobs API OpenAPI, e2e soft-skips,
open-findings (KBD/XDG/RELOAD/HIER), CI #430/#433.

**Not started:** any production code fix for the above issues.

## Failed approaches

1. Adversarial-review subagent once hit free-tier rate limit (429); re-ran after
   login and applied four medium/low doc fixes before commit.
2. Pre-commit markdownlint failed on first commit attempt (line length, ol-prefix
   style); bulk-fixed issue markdown then re-committed successfully.

## Decisions

1. **Prioritization authority** is the deep-review plan; overnight index is the
   parallel stream map only.
2. **Wave 0 before chrome** when data-loss P0s remain open.
3. **Char sidecars vs glyph:** char durability is Wave 0 issue; glyph share STUB
   but owned by glyph M11 issue / T3 after Wave 0.1 strategy decision.
4. **Sidecar strategy options A/B/C** recorded in plan (default A embed in
   content blob if book-tools allows); must cover **undo** coherence.
5. **D-042 / PGDP 24-stage** stay out of scope without explicit OK.
6. Do **not** rebuild glyph UI components — mount and wire existing ones.
7. Separate handoff scope from `issue-tracker-migration` (still active; different
   workstream).

## Current state

- Branch: `master`, ahead of `origin/master` by 2 commits (not pushed).
- `base_commit`: `6e9770ce5e9121b8169b0abab3e9e019efbfdd1c`.
- Tree clean.
- Other active handoff on same worktree (do not retire):
  `docs/handoff/2026-07-17-issue-tracker-migration.md` (scope
  `issue-tracker-migration`) — largely done for the four GH issues migrated to
  `docs/issues/`; not this workstream.

## Pointers

- `docs/plans/2026-07-21-deep-code-review-continuation.md`
- `docs/plans/2026-07-21-overnight-work-index.md`
- `docs/issues/README.md`
- `docs/issues/2026-07-21-sidecar-char-maps-not-durable.md`
- `docs/issues/2026-07-21-rematch-gt-not-durable.md`
- `docs/issues/2026-07-21-save-project-false-clean.md`
- `docs/issues/2026-07-21-mutation-store-silent-200.md`
- `docs/issues/2026-07-21-export-list-api-empty.md`
- `docs/issues/2026-07-21-cli-export-not-store-first.md`
- `docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md`
- `docs/issues/2026-07-21-job-sse-fe-be-shape-mismatch.md`
- `docs/plans/2026-07-21-glyph-annotations-completion.md`
- `docs/plans/2026-07-21-open-findings-fixes.md`
- `docs/plans/2026-07-21-ci-openapi-gates.md`
- `docs/context/current-state.md`
- `docs/context/open-findings.md`
- `AGENTS.md`
- `src/pdomain_ocr_labeler_spa/api/words.py` (char STUBs, best-effort save)
- `src/pdomain_ocr_labeler_spa/api/pages.py` (rematch, save_page dirty bit, payload)
- `src/pdomain_ocr_labeler_spa/core/jobs/handlers/save_project.py`
- `src/pdomain_ocr_labeler_spa/core/jobs/handlers/export_cli.py`
- `src/pdomain_ocr_labeler_spa/api/export.py` (list_exports stub)
- `frontend/src/hooks/useJobProgress.ts`
- `frontend/src/pages/ProjectPage.tsx`

## Resume steps

1. Checkout this worktree; confirm `git rev-parse HEAD` is at or after
   `base_commit` and tree is clean (or re-apply only intentional local edits).
2. Read `docs/plans/2026-07-21-deep-code-review-continuation.md` § Issue index
   and Wave 0.
3. Start Wave 0.1: decide sidecar durability (A/B/C + undo) — short note in
   `docs/context/decisions.md` if non-obvious.
4. TDD implement issues in order:
   - sidecar char maps durable
   - rematch durable
   - save_project + save_page false-clean
   - mutation store silent 200
5. Parallel if capacity: job SSE issue (Wave 3a); export list contract (Wave 1.0).
6. Glyph T1 (payload inject) anytime; **T3 persist only after 0.1**.
7. Always `make ci AI=1` before commit. Do not push unless asked.
8. Use worktrees for parallel streams; avoid concurrent `ProjectPage` /
   store-serialization conflicts without one owner.

## Pickup prompt (after /clear)

Use the docgraph:pickup-handoff skill for scope "deep-review-continuation" in
worktree "/workspaces/pdomain/pdomain-ocr-labeler-spa".

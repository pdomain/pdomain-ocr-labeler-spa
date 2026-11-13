---
kind: decision
status: active
owner: maintainers
created: 2026-11-13
last_verified: 2026-11-13
---

# Retire completed documentation inventories and the old page assembly plan

## Context

The architecture migration reviewed source, tests and commit history before removing completed snapshots
from active retrieval. The retained architecture describes current operation; this receipt preserves why
the old documents can leave the live tree. It authorizes no code change, corpus write or remote issue deletion.

## Decision

Retire the completed CharRange inventory, closed findings snapshot and obsolete ProjectPage assembly plan after
promoting their
durable facts. Preserve the genuinely partial typography, loading and undo designs and their residual intent.

### CharRange inventory

- Old path: `docs/research/2026-08-22-char-range-deletion-inventory.md`.
- Outcome: implemented research, superseded by [typography review](../architecture/31-typography-review.md).
- Historical scope: 22 SPA fixtures, 1,729 JSON/JSONL corpus files, 6 output projects, 286 corpus projects,
  and event-store project `projectID629292e7559a8` with 62 events, 19 heads, 0 snapshots and 39 blobs.
- Observation: no `char_ranges` or `char_ranges_map` payloads or range items were found; every scanned JSON
  file parsed. The byte scan covered event state and content blobs. No corpus or event record was changed.
- Limitation: `/home/vscode/pdomain-ocr-labeler-spa` was absent. The scan used discovered roots under
  `/workspaces/pdomain-data`; unavailable or undisclosed roots were outside its evidence. These counts are
  the historical scan, not a fresh scan of today's machine.
- Rationale kept: the implemented replacement rejects old typography payloads rather than migrating,
  dual-writing or adding a fallback reader. CharFixer behavior was outside that change.
- Evidence: inventory commit `71a952bd`; backend removal `7725fea1`;
  `tests/unit/api/test_typography_clean_break.py` covers removed schema/routes and legacy-payload rejection.
- Remaining work: none for the inventory; suggestion acceptance and predecessor undo remain in the live
  typography design and roadmap.

### ProjectPage assembly plan

- Old path: `docs/architecture/22-page-surface-wireup.md`.
- Outcome: superseded by [shell composition](../architecture/24-shell-layout.md),
  [frontend ownership](../architecture/03-frontend.md) and the [driver contract](../architecture/13-driver-contract.md).
- Historical proof: issue #290 and the spec-22 children were recorded closed on 2026-05-15.
  The old document's acceptance checklist and future-tense scaffold are execution history, not architecture.
- Rationale kept: real page callbacks, query refresh after mutations, navigation, dialogs, selection and
  local image/loading/error surfaces now belong to ProjectPage and its mounted adapters. The removed
  Splitter layout, word-edit modal and hidden source-folder stubs are not new work to recreate.
- Evidence: `frontend/src/pages/ProjectPage.tsx`, `App.tsx`, `useToolbarDispatch.ts`,
  `ProjectPage.test.tsx`, `ProjectPage.editWord.test.tsx`, `ProjectPage.pageLoadProgress.test.tsx`,
  and `tests/e2e/test_project_page_smoke.py`; implementation alignment commits `8391cddc` and `66d878c8`.
- Remaining work: none unique to this assembly plan.

### Closed findings snapshot

- Old path: `docs/context/open-findings.md`; outcome: completed historical snapshot, retired behind a
  compatibility tombstone because source/test comments and dated references still cite it.
- All six findings closed on 2026-09-18; no new bug closure or fresh browser exercise is asserted here.
- BUG-KBD-1: Mod+, is registered, with the delimiter caveat recorded in App.
- BUG-KBD-4: real-browser verification covered Escape cancel, Enter confirm, Tab and restored focus
  against server state. Radix initially focuses Cancel, not Confirm; immediate Enter cancels, and one Tab
  reaches Confirm. No extra scoped hotkey implementation was needed.
- BUG-KBD-5: Mod+J is registered for jump-to-page.
- BUG-SMOKE-3: platform-aware data roots preserve a populated pre-XDG application root when the new root
  does not exist. The NiceGUI application's separate directory is not automatically imported; explicit
  data-root overrides still take precedence.
- BUG-RELOAD-1: zero-area unmatched placeholders are excluded from overlays. A successful OCR result with
  no words requires explicit review rather than appearing complete.
- BUG-HIER-1: the fixture hierarchy is present. Tests wait for attached nodes instead of fixed sleeps;
  an unexpectedly empty tree fails instead of soft-skipping.
- Evidence: the 2026-09-18 decision-log entries, `tests/e2e/test_confirm_dialog_keyboard.py`,
  `tests/unit/test_settings.py`, the review-queue implementation and existing hierarchy tests.
- Remaining work: none unique to this closed inventory. New defects belong in the issue tracker.

## Rationale

A completed inventory and an obsolete assembly checklist should not compete with current architecture.
Their durable scope and limitations are retained here; Git history retains their complete original text.
The architecture promotion does not turn partial feature requirements into completed product decisions.

## Consequences

Live links point to the current architecture or this receipt. Existing decision-log entries remain append-only.
The July per-document retirement manifest remains a historical audit reference because its full classification
table is useful provenance. Remote GitHub issue-deletion prerequisites remain separate from this local action.

## Supersedes / Superseded-by

This receipt supersedes the three named completed documents for retrieval. It does not supersede owner
choices about typography, retention, source ingestion, managed adapters or remote issue deletion.

## Evidence

Fresh read-only analyzer records are in the migration manifest. The controller inspected graph neighbors,
verified the existing metadata and replacement architecture, and used the direct doc-retirer skill procedure.
The optional planner/apply engine was not used; its known canonical-CLAUDE-symlink limitation was reported
by the coordinator in `retirement-planner-tool-limitation.json`. No symlink or tool safety check was changed.

Removal commit: the commit that adds this receipt and deletes the old paths, recoverable with
`git log --diff-filter=A -- docs/decisions/2026-11-13-retire-completed-doc-inventories.md`.

Verification dates from this pass mean source/test/history inspection of current truth or bounded historical
provenance. They do not imply a fresh complete browser exercise, a repeated corpus scan, or owner approval
of unresolved policy choices. Fresh analyzer records and the final review/check manifest identify that scope.

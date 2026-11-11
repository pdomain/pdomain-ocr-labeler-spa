---
kind: handoff
status: "active"
created: "2026-11-11"
created_at: "2026-11-11T08:23:17Z"
owner: "CT"
branch: "feature/typography-suggestion-undo"
scope: "typography-suggestion-undo"
worktree: "/mnt/work/projects/pdomain/pdomain-ocr-labeler-spa/.worktrees/typography-suggestion-undo"
base_commit: "d0940bfed4dcb14a9fe877ea8045ed33b69b4e4b"
supersedes: "2026-11-11-075408-glyph-parity-and-shared-ui-alignment-done.md"
handoff_reason: "stopping"
host: "claude-code"
---

# Typography suggestion accept/edit and predecessor undo need owner design before code

## Goal

Build typography suggestion acceptance and editing, and predecessor-based compensating undo, test first with Chromium
verification. The task said to stop if no spec defines the behaviour. No spec does, so no code was written.

## Done

- Created worktree `.worktrees/typography-suggestion-undo` on branch `feature/typography-suggestion-undo`, cut from
  local `feature/glyph-pgdp-completion` at `b708b2f5`. That branch and `feature/memfd-tsconfig-state` under it remain
  unmerged.
- Found the governing spec: `docs/specs/2026-08-21-typography-review-and-training-export-design.md`, status partial.
  Its summary says suggestion acceptance and editing and predecessor undo "remain design work". It lists them under
  planned acceptance work, not under "Unresolved owner decisions", so they are not marked as owner decisions. They are
  simply undefined.
- Recorded two open questions in `OPEN_QUESTIONS.md`, OQ-TYPO-1 and OQ-TYPO-2, in commit `d0940bfe`.
- `make ci AI=1` exited 0 before that commit: backend pytest had 2273 passed and 2 skipped, and
  vitest passed 2314 tests in 164 files. The status came from `make` itself, with output redirected to a file and no pipe.

## Not done

- Suggestion accept and edit controls. Nothing produces or stores a typography suggestion. The SPA has no F2,
  Gutenberg, rule or model typography projection. `pdomain-book-contracts` 0.3.0 has no suggestion or prediction
  record, only `prediction_id` on a span and a `CorrectionDecision.ACCEPT` value. The spec says model suggestions
  arrive only after the manual path passes end-to-end tests.
- Predecessor undo and redo. The spec names the behaviour but does not define it. Open points: undoing revision 1 has
  no predecessor and no decision returns a word to unreviewed; a compensating record must rebind to current hashes and
  may not fit changed text; nothing in `TypographyCorrection` or `TypographyReviewMetadata` links a record to the one
  it reverses; the UI control and driver test IDs are unspecified.
- No Chromium verification ran, because no behaviour changed.
- The spec's correction-bundle acceptance test of edit, reload, undo, redo, export and record equality stays blocked by
  OQ-TYPO-2.

## Failed approaches

- The first gate run exited 2 with 35 failures, all `unsupported_runtime`. `make setup` built `.venv` on uv's CPython
  3.13.14, which lacks `os.memfd_create`. Rebuilding with `UV_PYTHON` set to the mise 3.13.18 interpreter fixed it, as
  the predecessor handoff warned. Any new worktree hits this.

## Decisions

- Stopped rather than invent a suggestion store or an undo convention. Both would be new design, and specs are the
  source of truth here.
- Recommended options are in `OPEN_QUESTIONS.md`: a portable suggestion record in `pdomain-book-contracts` with a
  read-only SPA sidecar imported from `pdomain-source-data`, and an `undo_of` field plus a revert decision in the
  contract. Both need the owner, and both touch `pdomain-book-contracts`, outside this repo.

## State

- Branch `feature/typography-suggestion-undo` has two commits on `b708b2f5`: the open questions and this handoff.
  Nothing was pushed, merged, tagged or released.
- The worktree `.venv` uses mise CPython 3.13.18.
- `TMPDIR` for gates was `/mnt/work/pdt/labeler4`, and `CUDA_VISIBLE_DEVICES` was empty.

## Pointers

- `docs/specs/2026-08-21-typography-review-and-training-export-design.md`
- `OPEN_QUESTIONS.md`
- `frontend/src/components/right-panel/sections/TypographySection.tsx`
- `src/pdomain_ocr_labeler_spa/core/typography_review.py`
- `src/pdomain_ocr_labeler_spa/api/typography.py`
- `docs/context/intent-map.md`

## Resume

1. Get the owner's answers to OQ-TYPO-1 and OQ-TYPO-2.
2. Update the spec with the chosen design, then change `pdomain-book-contracts` if the answer needs new fields.
3. Build undo first, since it needs no suggestion source, test first, then verify in Chromium.
4. Merge `feature/memfd-tsconfig-state`, then `feature/glyph-pgdp-completion`, then this branch, when the owner approves.

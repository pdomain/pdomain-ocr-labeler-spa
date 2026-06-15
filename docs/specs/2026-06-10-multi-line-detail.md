---
repo: pdomain/pdomain-ocr-labeler-spa
status: approved
date: 2026-06-10
---

# Multi-line selection detail (MultiLineDetail) — spec + implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> or superpowers:executing-plans to implement this plan task-by-task. Slices use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selecting multiple lines shows every selected line's words in an
editable word view in the right panel — closing the last selection-parity gap
against the legacy NiceGUI labeler.

**Architecture:** New `MultiLineDetail` component in
`frontend/src/components/right-panel/`, routed from `RightPanel.tsx` when
`level === "line" && selectedLines.length > 1` (after the existing
multi-word branch, before the single-line `LineDetail` branch). Pure
client-side rendering from `PagePayload.line_matches[]`; mutations reuse the
existing line/word hooks. No new backend endpoints.

**Tech Stack:** React 19 + TS, zustand-style `selection-store`, TanStack
Query mutation hooks (`useLineMutations.ts`, the word-GT mutation used by
LineDetail's Words tab), Tailwind, vitest, Playwright e2e.

## Why (spec-gap record)

CT decision 2026-06-10. The 2026-06-05 selection-operations-parity spec
covered multi-word selection (`MultiWordDetail`) but never defined a right-
panel view for multiple selected **lines**: `selection-store.ts`
`applyLineSelection()` supports N lines, but `RightPanel.tsx` routes
`level === "line"` to `LineDetail`, which renders only `path.lineId` (the
first line). Live validation 2026-06-10 confirmed: multi-line drag leaves
the user with no way to see or edit the selected lines' words.

Legacy parity target (`pd-ocr-labeler` docs): checkbox multi-select on
lines; the Matches view shows each line side-by-side with its words; GT text
inputs inline per word; Enter commits; Tab/Shift-Tab moves between words.

CT chose a dedicated **MultiLineDetail** (per-line cards with full inline
word-edit grids) over expanding lines to words into `MultiWordDetail`.

## Capability matrix

| ID | Capability | Acceptance criterion (observable behavior — never "testid exists") |
|------|------------|--------------------------------------------------------------------|
| ML-1 | Multi-line drag selects lines | With rail target = Line, drag a box intersecting ≥2 lines → all intersected lines enter `selectedLines`, all get canvas highlight. If the existing hit-test fails this, fixing it is in scope. |
| ML-2 | MultiLineDetail renders | `level === "line" && selectedLines.length > 1` → `multi-line-detail` renders one card per selected line, ascending `line_index`. The level-"none" placeholder and single-`LineDetail` must NOT render. |
| ML-3 | Card shows line identity + words | Each `multi-line-card-{lineIdx}` shows: line index, block/para badge, validated count (e.g. "3 / 5"), `ocr_line_text`, and a word grid — per word: word image cell, OCR label, GT text input, validate button (reuse `gt-text-input-{l}-{w}`, `word-validate-button-{l}-{w}`, `word-image-cell`, `ocr-text-label` testids/components from LineDetail's Words tab). |
| ML-4 | Inline GT editing commits | Typing in a GT input + Enter fires the same word-GT mutation LineDetail's Words tab uses; the card's match status / validated count refreshes from the query invalidation. |
| ML-5 | Tab traversal crosses lines | Tab/Shift-Tab in a GT input moves focus to the next/previous word's GT input, crossing card boundaries (last word of line N → first word of line N+1). |
| ML-6 | Per-line ops on each card | Each card has Validate-all, Copy GT→OCR, Copy OCR→GT, Delete buttons wired to `useValidateLine` / `useCopyLineGt` / `useDeleteLine` for THAT line (reuse `line-validate-button-{n}` / `line-gt-to-ocr-button-{n}` / `line-ocr-to-gt-button-{n}` / `line-delete-button-{n}` testids). Delete asks ConfirmDialog. |
| ML-7 | Bulk bar across selected lines | Sticky `multi-line-bulk-bar`: "N lines selected" + Validate all / Unvalidate all / Copy OCR→GT (all) / Delete (ConfirmDialog) acting on every selected line. |
| ML-8 | Selection survives ops | After any per-line or bulk mutation (except Delete), `selectedLines` is preserved and cards re-render with fresh data; after Delete, deleted lines leave the selection. |

## Out of scope

- Multi-paragraph / multi-block detail views (no spec; raise as a follow-up
  if CT asks).
- New backend endpoints (everything maps onto existing line/word mutations).
- Changes to `MultiWordDetail` beyond the AG-1 slice below.

## Slices

### Slice ML-A — routing + read-only cards (ML-2, ML-3)

**Files:**

- Create: `frontend/src/components/right-panel/MultiLineDetail.tsx`
- Create: `frontend/src/components/right-panel/MultiLineDetail.test.tsx`
- Modify: `frontend/src/components/shell/RightPanel.tsx` (insert branch
  between the multi-word check and the `level === "line"` branch)
- Modify: `frontend/src/components/shell/RightPanel.test.tsx` (routing cases)

- [ ] Failing tests first: routing test (2 lines selected → `multi-line-detail`
      visible, `line-detail` absent; 1 line → `LineDetail` unchanged;
      multi-word still wins when `selectedWords.length > 1`), card-content
      test (cards ascending by `line_index`, each shows ocr_line_text +
      word rows from a fixture `PagePayload`).
- [ ] Implement; extract/reuse LineDetail's Words-tab word-row rendering
      rather than duplicating it (factor a shared `LineWordsGrid` if LineDetail's
      markup is reusable; otherwise compose its existing word-row component).
- [ ] `pnpm vitest run` green; commit.

### Slice ML-B — editing + traversal (ML-4, ML-5)

- [ ] Failing tests: GT input Enter fires the word-GT mutation with the right
      (lineIdx, wordIdx); Tab from last word of card N focuses first input of
      card N+1 (jsdom focus assertions).
- [ ] Implement (reuse the exact commit-on-Enter handler from LineDetail's
      Words tab; traversal via a flat ordered ref list of inputs).
- [ ] Green; commit.

### Slice ML-C — per-line ops + bulk bar (ML-6, ML-7, ML-8)

- [ ] Failing tests: each card button calls its mutation with that card's
      lineIndex; bulk Validate-all issues per-line validate (or batch endpoint
      if one exists — check `useLineMutations.ts` first); Delete routes through
      ConfirmDialog; selection preserved post-mutation (ML-8).
- [ ] Implement; green; commit.

### Slice ML-D — canvas multi-line selection hardening (ML-1)

- [ ] Reproduce first: with rail target = Line, does drag-select over ≥2 lines
      populate `selectedLines` (unit test on `applyBoxSelect` with line target +
      real fixture bboxes already exists — extend with a regression case mirroring
      the live failure: drag rect covering multiple line bboxes at display scale).
- [ ] If hit-test or routing is broken, fix in `box-select-handler.ts` /
      `ProjectPage.handleBoxSelect`; if it only failed on the stale bundle,
      record that in the PR-less commit message and keep the regression test.
- [ ] Green; commit.

### Slice AG — adjacent confirmed gaps (same arc, separate commits)

Fresh-bundle browser validation (2026-06-10, post-refactor tree) resolved
the open conditions:

- [ ] AG-1 (verify-only): MUL-3 bulk bar is CONFIRMED PRESENT on the current
      tree (`multi-word-validate/-unvalidate/-delete/-style-apply/
      -component-apply`); the earlier FAIL was a stale bundle. Just keep the
      e2e regression in Slice BV.
- [ ] AG-2: LineDetail Words-tab bulk bar — "Validate selected" fires
      validate mutations for checked words (today it only clears checkboxes);
      "Skip selected" either gets a real behavior or is removed (decide by
      reading the legacy parity docs — do not leave a dead button).
- [ ] AG-3: Wire the empty Refine / Expand+Refine hotkey handlers in
      `ProjectPage.tsx` (~lines 406-411) to the same dispatch the toolbar
      grid's refine cells use.
- [ ] AG-4 (CONFIRMED, root cause of the multi-line failure): selection
      granularity has two disagreeing sources of truth. Observed on fresh
      bundle: page LOADS with `rail-target-line` `data-active=true` while
      `uiPrefs.selectionMode` defaulted to "word"; clicking rail targets never updated
      that pref; and box-select drag routing follows `selectionMode`
      (`selectionMode`), so "line mode" drags select WORDS. Fix: make one
      store the single source of truth (rail target ⇄ selectionMode
      reconciled on mount AND on every change, both directions), and make
      `handleBoxSelect` route by that single value. Acceptance: fresh page
      load shows rail and radio agreeing; toggling either updates the other;
      a line-target drag selects lines (feeds ML-1).
- [ ] AG-5 (NEW, regression vs 2026-06-05 SEL-4): Ctrl-click on a second
      word REPLACES the selection instead of adding to it (drag-based
      multi-word select works; click-modifier path is broken). Reproduce
      first in a unit test on the canvas click handler (modifier → toggle
      mode → `toggleWord`), then fix. Acceptance: Ctrl-click on a word in a
      different block yields `multi-word-detail` with both words; Shift-click
      removes.

### Slice BV — Browser Verification (MANDATORY, last)

- [ ] e2e (tests/e2e, existing Playwright harness + exercise fixture):
      - rail target Line → drag across ≥2 lines → `multi-line-detail` visible
        with ≥2 `multi-line-card-*`, each listing its words.
      - edit one GT input + Enter → value persists after reload.
      - bulk Validate all → validated counts update on every card.
      - regression: single-line selection still shows `LineDetail`;
        multi-word selection still shows `multi-word-detail`.
- [ ] Update `docs/architecture/13-driver-contract.md` with the new testids
      (`multi-line-detail`, `multi-line-card-{n}`, `multi-line-bulk-bar`).
- [ ] Update `docs/architecture/26-right-panel-detail.md` routing table.
- [ ] `make ci AI=1` green (includes frontend build); `make e2e AI=1` for the
      new tests.

## Verification gate

Done means: a human (or driver agent) can open the app, drag across three
lines, see three cards with every word editable, fix a GT word with Enter,
validate a whole line from its card, and bulk-validate the rest — with no
placeholder, no first-line-only view, and no console errors.

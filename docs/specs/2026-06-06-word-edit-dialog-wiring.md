# WordEditDialog Wiring Parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development +
> test-driven-development. Each capability below is a TDD slice (failing test first), committed
> independently. Acceptance is **observable user behavior** — a dialog button is only "done" when
> it is visible, enabled, and **produces its persisted effect**, verified in a real browser.
> A `data-testid` existing in the DOM is NOT acceptance.

**Goal:** Restore the legacy word-edit dialog as a working editing surface. The dialog renders all
its controls but is mounted with **no mutation callbacks**, so every button is a silent no-op
(`?? Promise.resolve()`). Wire each callback in `ProjectPage.tsx` to the mutation hooks the
RightPanel already uses, so the full dialog workflow performs and persists.

**Architecture:** No new components or backend routes — this is a *wiring* slice. `WordEditDialog`'s
child rows (`WordActionRows`, `WordTagRow`, `WordRefineNudgeRows`) already accept and fire the
callbacks; `ProjectPage` must inject the same `useWordMutations` / line-mutation hooks that
`WordDetail` / `WordFooter` / `BBoxSection` call. Where a dialog-only op lacks an existing hook
(crop, delete, refine, apply-nudge), add it to `useWordMutations.ts` against the existing backend route.

**Tech Stack:** React 19, Zustand (`dialogStore`), TanStack Query mutation hooks, Vitest, Playwright.

---

## Why this format

This gap is the same anti-pattern that produced the selection/operations gap: the controls exist
and satisfy the driver contract, but are **unreachable as effects**. `ProjectPage.tsx:1048` passes
only `open/target/lineWords/onNavigate/onApply/onClose` and `wordImageUrl={undefined}`. Every
content callback is omitted, so the child buttons fall through to `?? Promise.resolve()`. Tests that
assert the button renders pass; the user clicks and nothing happens. The fix and its acceptance are
phrased as observable, persisted behavior so a no-op cannot pass the gate.

## Capability matrix (in scope)

| ID | Capability | Surface | Trigger | Observable acceptance | Current |
|----|-----------|---------|---------|-----------------------|---------|
| WED-1 | Merge word prev/next | `dialog-merge-prev/next-button` | click | Adjacent word merges; page reflects merged word; persists across reload | ✗ `onMerge` not passed |
| WED-2 | Split word (H) | `dialog-split-h-button` | click | Word splits at chosen fraction into two words; persists | ✗ `onSplit` not passed |
| WED-3 | Delete word | `dialog-delete-word-button` | click | Word removed from line; persists | ✗ `onDelete` not passed |
| WED-4 | Crop bbox (4 dir) | `dialog-crop-*-button` | click | Word bbox shrinks on chosen side by padding; persists | ✗ `onCrop` not passed |
| WED-5 | Apply / clear style | `dialog-apply-style-button` | click | Style chip applied to word (whole/part scope); persists | ✗ `onApplyStyle` not passed |
| WED-6 | Apply / clear component | `dialog-apply-component-button` / `dialog-clear-component-button` | click | Component tag toggled on word; persists | ✗ `onApplyComponent` not passed |
| WED-7 | Refine / expand+refine | `dialog-refine-button` / `dialog-apply-refine-button` | click | Bbox refined to ink; persists (no-op gracefully if page image absent — see note) | ✗ `onRefine`/`onExpandRefine` not passed |
| WED-8 | Apply accumulated nudge | `dialog-apply-button` (+`dialog-nudge-display`) | accumulate → apply | Pending nudge deltas commit to the bbox; persists; display resets | ✗ `onApplyNudge` not passed |
| WED-9 | GT edit commit | `dialog-gt-input` | type + blur/Enter | Typed GT persists to the word; reflected in WordDetail and metrics | ✗ `onGtChange`/`onGtCommit` not passed |
| WED-10 | Word image renders in dialog | `WordImageCanvas` | open dialog | The dialog shows the word's cropped image (not blank) | ✗ `wordImageUrl={undefined}` |

Legend: ✗ broken/no-op · ⚠ partial · ✓ working.

## Key references (grounded)

- Dead mount: `frontend/src/pages/ProjectPage.tsx:1048-1063` — only 6 props + `wordImageUrl={undefined}`.
- Dialog props (all optional, default to `?? Promise.resolve()`): `components/WordEditDialog.tsx:55-94`
  — `onMerge, onSplit, onDelete, onCrop, onRefine, onExpandRefine, onApplyNudge, onApplyStyle,
  onApplyComponent, onGtChange, onGtCommit`. Child wiring already present:
  `WordActionRows.tsx`, `WordTagRow.tsx`, `WordRefineNudgeRows.tsx`.
- Reusable mutation hooks (same ones WordDetail uses): `hooks/useWordMutations.ts`
  — `useMergeWord:90`, `useSplitWord:118`, `useApplyStyle:153`, `useUpdateWordGroundTruth:180`,
  `useApplyComponent:204`, `useReboxWord:65`, `useErasePixels:275`.
  Add `useDeleteWord`, `useCropWord`, `useRefineWord`, `useApplyNudge` against existing backend
  routes (delete: see `WordFooter.tsx`; refine/nudge: see `BBoxSection.tsx`; crop: backend
  `words.py` crop route). Reuse, do not re-implement.
- WordDetail reference for hook usage patterns: `components/right-panel/WordDetail.tsx`,
  `WordFooter.tsx`, `sections/BBoxSection.tsx`.

> **Backend note (carry into the spec, do not silently absorb):** V-split (`dialog-split-v-button`)
> returns HTTP 400 by design (`words.py:1080`, horizontal only). WED-2 covers H-split only;
> V-split stays disabled with a tooltip until the backend exposes it. Refine (WED-7) raises when
> the page image is absent — handle as a user-visible "load the page image first" message, not a
> silent failure.

---

## Slice A — Word image + GT commit (WED-10, WED-9)

**Files:** `ProjectPage.tsx`, `components/WordEditDialog.tsx` (if URL plumbing needed), tests.

- Compute and pass `wordImageUrl` for the dialog target (same per-word crop URL WordDetail uses).
  Acceptance: WED-10 — opening the dialog shows the word image, not a blank canvas.
- Wire `onGtChange` (local controlled value) + `onGtCommit` → `useUpdateWordGroundTruth`.
  Acceptance: WED-9 — typed GT persists and shows in WordDetail + metrics after close.

## Slice B — Structural edits (WED-1, WED-2, WED-3)

**Files:** `ProjectPage.tsx`, `hooks/useWordMutations.ts` (add `useDeleteWord` if absent), tests.

- `onMerge("prev"|"next")` → `useMergeWord`. `onSplit(fraction,"h")` → `useSplitWord`.
  `onDelete()` → delete mutation (reuse WordFooter's). V-split button disabled (backend 400).
- Acceptance: WED-1..3 — each performs and persists across reload.

## Slice C — Tags (WED-5, WED-6)

**Files:** `ProjectPage.tsx`, tests.

- `onApplyStyle(style, scope)` → `useApplyStyle`. `onApplyComponent(component, enabled)` →
  `useApplyComponent`. Acceptance: WED-5, WED-6 — chips toggle on the word and persist.

## Slice D — Bbox ops (WED-4, WED-7, WED-8)

**Files:** `ProjectPage.tsx`, `hooks/useWordMutations.ts` (add `useCropWord`, `useRefineWord`,
`useApplyNudge` against existing routes), tests.

- `onCrop(dir, padding)` → crop mutation. `onRefine`/`onExpandRefine` → refine mutation (surface
  the image-absent error). `onApplyNudge(pending, refineAfter)` → rebox/nudge mutation; reset
  `dialog-nudge-display` on success. Acceptance: WED-4, WED-7, WED-8.

---

## Browser Verification milestone (MANDATORY — FastAPI+SPA)

Playwright e2e in `tests/e2e/` against the running server (`CI=true`), using the
`_seed_event_store` / `_ingest_ocr_result` seeding in `helpers.py` / `fixtures/`. Assert observable,
**persisted** behavior — the anti-no-op gate:

- **Open dialog:** word image is visible (WED-10); no `console.error`.
- **WED-9:** type GT, blur, close dialog → WordDetail shows the new GT; reopen page → still there.
- **WED-1:** merge next → line word count decreases by 1; persists after `page` refetch.
- **WED-3:** delete word → word gone from line; persists.
- **WED-5:** apply a style → style chip appears on the word in WordDetail.
- **WED-4/WED-8:** crop/nudge → the word bbox numeric values in BBoxSection change accordingly.
- Each assertion refetches/reloads to prove **persistence**, not just optimistic UI (a prior
  sweep shipped green while a backend bug made per-word validate silently not persist).

## Self-review notes

- Every capability-matrix row maps to a slice task; no row left unimplemented.
- Acceptance is observable + persisted behavior, not testid presence.
- No new backend routes; hooks reused from `useWordMutations` (grounded in real exports).
- Backend constraints (V-split 400, refine image-absent) are carried explicitly, not absorbed.
- FastAPI+SPA browser-verification milestone present and asserts persistence.

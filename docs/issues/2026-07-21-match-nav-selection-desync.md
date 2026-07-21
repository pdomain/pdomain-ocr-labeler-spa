---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Matches J/K navigation does not call selectLine

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** Medium — worklist highlight and canvas/right-panel selection
  desync on J/K
- **Affected version:** verified 2026-07-21 (Wave 3b code review)
- **Read when:** changing matches hotkeys, worklist navigation, or selection
  store sync between worklist and canvas.
- **Search terms:** P1-MATCH-NAV, onLineNav, selectLine, worklistStore,
  useMatchesHotkeys, J K navigation, selectedLineIndex.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  `frontend/src/pages/ProjectPage.tsx`,
  `frontend/src/components/drawer/Worklist.tsx`,
  `frontend/src/stores/selection-store.ts`,
  `frontend/src/stores/worklist-store.ts`

## Summary

Matches hotkeys J/K call `onLineNav`, which only updates
`worklistStore.selectedLineIndex`. Worklist row clicks update both
`worklistStore.setSelectedLineIndex` and `selectLine(...)` so the hierarchical
selection store (canvas, breadcrumb, right panel) stays aligned. Keyboard nav
therefore moves the worklist “current line” without selecting that line for
editing surfaces, and action hotkeys that read `selectedLineIndex` may act on a
line the rest of the UI does not treat as selected.

Finding ID: **P1-MATCH-NAV** (Wave 3b).

## Impact

- J/K advance the matches queue highlight without selecting the line on canvas /
  right panel / breadcrumb.
- User can believe line N is active (worklist) while `selectionStore` still
  holds another path or none.
- Validate/delete/merge/copy hotkeys keyed off `worklistStore.selectedLineIndex`
  can mutate a line that is not the hierarchical selection — surprising edits.
- Click vs keyboard parity is broken for the same control surface.

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Verified by static read + existing ProjectPage tests, 2026-07-21
- Hooks: `useMatchesHotkeys` on ProjectPage (BUG-KBD-3 wiring)
- Source plan:
  `docs/plans/2026-07-21-deep-code-review-continuation.md` (P1-MATCH-NAV)

## Evidence

1. **ProjectPage `onLineNav` only touches worklistStore:**

```413:422:frontend/src/pages/ProjectPage.tsx
  // ── Matches hotkeys (BUG-KBD-3) ─────────────────────────────────────────
  // Wired at the page level — operates on worklistStore.selectedLineIndex to
  // know which line is "current" for all action hotkeys (V/U/D/O/G/M/R).
  useMatchesHotkeys({
    onLineNav: (delta) => {
      const { selectedLineIndex } = worklistStore.getState();
      const nextIdx = (selectedLineIndex ?? -1) + delta;
      const clampedIdx = Math.max(0, Math.min(lines.length - 1, nextIdx));
      worklistStore.setSelectedLineIndex(clampedIdx);
    },
```

   No `selectLine` import usage in this handler.

1. **Worklist click path keeps both stores in sync:**

```422:428:frontend/src/components/drawer/Worklist.tsx
            onSelect={(idx) => {
              const item = wordItems[idx];
              if (!item) return;
              worklistStore.setSelectedLineIndex(item._lineMatch.line_index);
              selectLine(item._lineMatch.line_index);
              // STB-4: reveal the right panel when collapsed so operations are visible.
              useUiPrefs.setState({ rightPanelOpen: true });
            }}
```

1. **`selectLine` is the hierarchical selection entry point** — sets
   `selectedLines`, `level: "line"`, and `path.lineId` in `selection-store.ts`.
   Canvas overlays, breadcrumb, and right-panel routing consume that store, not
   `worklistStore.selectedLineIndex` alone.

1. **Tests encode the incomplete contract.** `ProjectPage.test.tsx` only
   asserts J/K change `worklistStore.selectedLineIndex`; they do not assert
   `selectLine` / `selectionStore`. Worklist tests do assert `selectLine` on
   row click — proving the dual-update expectation for pointer input only.

1. **Plan disposition.** Wave 3b: “P1-MATCH-NAV — J/K → `selectLine`.”

## Root-cause hypotheses

1. **(Most likely) BUG-KBD-3 scoped to worklist index only.** Action hotkeys
   were wired against `selectedLineIndex`; navigation was implemented as a pure
   index clamp without mirroring the Worklist click dual-write.
2. **Two stores by design without a sync helper.** Pointer paths manually dual-
   write; keyboard path omitted the second write rather than a shared
   `focusLine(index)` helper.

## Defects to fix

1. **`onLineNav` does not call `selectLine(clampedIdx)`** (or equivalent) —
   primary.
2. **Missing shared “focus line” helper** used by both Worklist click and J/K
   (optional cleanup, prevents re-desync).
3. **Tests do not guard selection-store sync** for matches navigation.

## Next steps

1. In `onLineNav`, after clamping, call `selectLine(clampedIdx)` when
   `lines.length > 0` (and define behavior when the page has no lines).
2. Optionally open the right panel on keyboard nav for parity with Worklist
   STB-4.
3. Extend ProjectPage / hotkey tests: after J/K, assert `selectionStore`
   `selectedLines` / `level` / `path.lineId` match the worklist index.
4. Consider one `focusWorklistLine(lineIndex)` used by Worklist + ProjectPage.

## What is NOT broken

- `useMatchesHotkeys` J/K invoking `onLineNav(±1)`.
- Worklist row click dual-write (`setSelectedLineIndex` + `selectLine`).
- Action hotkeys (V/U/D/…) reading `worklistStore.selectedLineIndex` once that
   index is set (they fire mutations; the defect is selection UX desync, not
   missing key bindings).
- `selectLine` implementation in `selection-store`.

## Resolution

Open. Filed from deep code review Wave 3b (**P1-MATCH-NAV**). No fix landed in
this documentation pass.

# Next steps — 2026-05-15

State as of end of day. Everything in this file is open work; anything not listed is done.

---

## What just shipped (today)

- **Hi-fi redesign Slices 0–27** (Phases 0–6): full component library — StudioShell, Rail,
  Drawer+Worklist+Hierarchy, HeaderBar, RightPanel+Breadcrumb, WordDetail 6-section accordion,
  LineDetail, BlockDetail, BulkActions, theme toggle, hotkey overlay, toast wrappers, RootPage refresh.
- **Integration session IS-1–6**: wired the components into the running app — double header fixed,
  nav controls visible, Drawer live, canvas stripped to image-only, project-not-found redirects.
- **Follow-on catalogue**: `docs/hifi-followons.md` (FO-1–9).
- **Loop fix session (2026-05-15 evening)**: three commits fixing RootPage→ProjectPage→RootPage
  infinite redirect loop (`655bbf2`, `516d3cb`). Root cause: `GET /api/projects/{id}` returns 404
  after a restart (project not in memory); `GET /api/projects` lists from disk unconditionally. Fix:
  RootPage now validates project ID against the disk list before navigating; ProjectPage passes
  `state: { skipSessionRedirect: true }` on 404 redirect so RootPage falls through to project list.

---

## 1 — Test first (do before anything else)

Start the app and load a real project:

```bash
# terminal 1
make dev

# terminal 2  (or browser)
open http://localhost:5173
```

**Golden path to verify:**

1. Root page shows project list (or redirect to last project).
2. Load a project via "Open source folder" → project loads → image visible in canvas.
3. Prev / Next page navigation works (buttons now in HeaderBar).
4. Drawer opens and shows Worklist with lines.
5. Click a word on the canvas → RightPanel shows WordDetail.
6. Drawer collapse / expand button works.

**Known remaining rough edges (don't file bugs yet):**

- Block-level selection in RightPanel shows placeholder (no block layer in PagePayload yet, FO-7).
- Erase Pixels "Apply" button is permanently disabled (FO-9).
- Merge-with-line buttons in LineDetail are disabled (FO-3).

---

## 2 — Quick fixes (1–2 hours, can do same day)

All immediate quick fixes shipped (2026-05-15 evening):

- ✅ I-8 — breadcrumb + icon replaces legacy select in HeaderBar (#326)
- ✅ FO-5 — Chip forwards data-testid; CharRangesSection uses Chip (#325)
- ✅ FO-8 — Drawer subscriber bridge removed; uses useUiPrefs.subscribe directly (#324)
- ✅ CLAUDE.md — milestone section updated
- ✅ auto-resume after restart — RootPage POSTs /api/projects/load (#327)

---

## 3 — Backend gaps (unblock FO items)

These require new FastAPI endpoints before the frontend stubs can be wired:

| FO | What | Backend change needed |
|----|------|-----------------------|
| FO-1 | BlockDetail layout-type save | `PATCH /api/projects/{id}/pages/{idx}/paragraph/{para_idx}` with `layout_type` field |
| FO-2 | Char-range positions | New endpoint accepting `{line_idx, word_idx, ranges: [{start,end,styles}]}` |
| FO-3 | Merge-with-line | `POST /api/projects/{id}/pages/{idx}/merge-lines` |
| FO-9 | Erase pixels availability | Either a capability flag in `/api/session-state` or a `/api/refine/available` probe |

### Auto-resume after restart

✅ Shipped in #327 (2026-05-15). RootPage now fires `POST /api/projects/load` before
navigating; falls through to project list on failure.

---

## 4 — Frontend polish (after testing confirms wiring is stable)

| FO | What | Effort | Status |
|----|------|--------|--------|
| FO-4 | Migrate `BBoxOverlay` stroke colors from hardcoded hex to `useLayerColors()` CSS vars | S | ✅ #328 |
| FO-6 | Bridge legacy `hotkeyMap.ts` entries into `hotkey-registry.ts` so the modal is complete | S | ✅ #329 |
| FO-7 | Block-level sibling walk (no-op until `PagePayload` grows `block_index`) | depends on backend | ⬜ |

---

## 5 — Milestone work still open

| Milestone | Status | What's left |
|-----------|--------|-------------|
| M9.5 | 🟡 partial | Keyboard-only end-to-end editing audit (#286) — verify every labeling action is reachable without a mouse |
| M11 | ⬜ blocked | Glyph-level annotations (#267–#270) — 4 issues, all `status:blocked`; needs design decision before implementation |

M2–M10, M9.1, M9.2 are all ✅ done.

---

## 6 — Driver compatibility check

`IS-4` stripped `ToolbarActionGrid`, `Splitter`, and `TextTabs` from the live canvas and
moved them to hidden stubs. The E2E driver test (`make e2e`) should confirm the
`data-testid` contract is intact. Run this before declaring the integration done:

```bash
make e2e AI=1
```

If any driver-contract testids are now unreachable, add stubs in `ProjectPage.tsx`
following the same hidden-stub pattern already used for `PageActions` (IS-2).

---

## 7 — Backlog (low priority, no blocker)

- `#87` spec alignment: root redirect to first vs last page inconsistency.
- `#58` Q-A7: per-mark provenance granularity question.
- `#94` delete `ROADMAP.md` + `PARITY_STATUS.md` once issue migration complete.
- `#286` keyboard-only audit (M9.5).
- `#295` ImageTabs sub-tabs scope question.

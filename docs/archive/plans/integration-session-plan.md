# Integration session plan — post hi-fi redesign

Captured from screenshot `docs/Screenshot from 2026-05-15 13-15-02.png` taken after
Phases 0–6 (Slices 0–27) shipped. The component library is complete but the
**wiring into `ProjectPage` / `App.tsx` was never finished** — slices were built in
isolation and the integration pass did not happen.

---

## Screenshot diagnosis

### What the layout actually is (not what it should be)

```
┌─────────────────────────────────────────────────────────────┐
│ App.tsx: <HeaderBar /> — "OCR Labeler" logo + LOAD input    │  40px
├──┬──────────────────────────────────────────────────────────┤
│  │ StudioShell header zone (40px, overflow-hidden)          │
│  │  → ProjectNavigationControls + PageActions CLIPPED       │  40px
│ R│                                                          │  (invisible)
│ a│ StudioShell canvas zone                                  │
│ i│  ┌─ ToolbarActionGrid (big button table) ──────────────┐ │
│ l│  │  Page / Para / Line / Word × 12 action columns      │ │
│  │  └──────────────────────────────────────────────────────┘ │
│  │  ┌─ Splitter ───────────────────────────────────────┐    │
│  │  │ image pane (BLANK — project failed) │ TextTabs   │    │
│  │  └────────────────────────────────────────────────────    │
├──┴──────────────────────────────────────────────────────────┤
│ Error banner: "Project not found: 'projectID629292e7559a8'" │
└─────────────────────────────────────────────────────────────┘
```

Drawer zone: completely empty stub div.
Right zone: RightPanel placeholder ("Select a block…") — the only hi-fi piece visible.

---

## Issues

### P0 — Blockers (nothing works)

**I-1: Stale session redirect — user stuck on broken URL**
`RootPage` calls `navigate` to `last_project_path` from `/api/session-state` on
mount. If that project no longer exists (path moved, DB cleared, new dev
environment), the app navigates to
`/projects/<stale-id>/pages/pageno/1` and shows only a red inline error banner
with no escape route. The router's catch-all `*` route goes to `/` but
`ProjectNotFoundBanner` doesn't trigger any navigation — user is stuck.

Fix: in `ProjectPage`, when `projectNotFound === true`, call
`navigate('/', { replace: true })` (with a brief toast, not silently).

**I-2: Double header bar + nav controls invisible**
`App.tsx` mounts `<HeaderBar />` globally (40px). `ProjectPage` then renders
`StudioShell` with a `header` slot containing `ProjectNavigationControls +
PageActions`. That slot is also 40px with `overflow-hidden` — so the nav controls
are clipped and invisible. Result: no Prev/Next/Go buttons visible anywhere.

Fix: move `ProjectNavigationControls + PageActions` into the App-level `HeaderBar`
(contextually, when on a project route). The StudioShell `header` zone should be
removed from `ProjectPage`; the App-level `HeaderBar` handles the full top bar.

**I-3: Drawer slot is an empty div — Worklist / Hierarchy never appear**
`drawerSlot = <div data-testid="drawer-placeholder" className="h-full" />` in
`ProjectPage.tsx:389`. The `Drawer` component from Slice 11 was built but never
wired. The Worklist (unvalidated/mismatched lines) is therefore invisible.

Fix: replace the placeholder with
`<Drawer lineMatches={lines} page={pagePayload ?? undefined} />` and pass
`drawerCollapsed` from `useUiPrefs().drawerOpen`.

### P1 — Layout broken even when a project loads

**I-4: ToolbarActionGrid still dominates the canvas zone**
The big row × column action table occupies the top of the canvas zone. In the
hi-fi design the toolbar is gone — word/line/para operations live in RightPanel
(WordDetail Slice 16–18) and the canvas zone shows only the image. The
ToolbarActionGrid should be hidden behind a toggle or fully replaced.

Proposed fix: gate it behind a dev/compat toggle in `useUiPrefs` initially, then
remove once RightPanel word operations are confirmed working end-to-end.

**I-5: Image + text splitter in canvas is wrong**
The canvas slot has a `Splitter` with image pane (left) and text pane (right,
`TextTabs + WordMatchView`). In the hi-fi layout:

- **Image pane** → should be the full canvas zone (no splitter)
- **TextTabs / WordMatchView** → the Worklist in the Drawer already covers this;
  the text pane is now redundant

Fix: remove the `Splitter` from the canvas slot. The canvas slot should be just
the `PageImageCanvas` (with `ImageTabsHeader` controls above it, or folded into
HeaderBar). Move or remove `TextTabs`.

**I-6: `main` wrapper in `App.tsx` has `overflow-auto`**
`<main className="flex-1 overflow-auto">` means the StudioShell (which is
designed to be `h-full` and handle overflow per-zone) scrolls as a whole instead
of having the canvas zone scroll independently. Causes the whole page to scroll
instead of individual zones.

Fix: change to `overflow-hidden` (or `overflow-hidden flex flex-col`) so
StudioShell fills the viewport and zones manage their own scroll.

**I-7: `PageActions` bar has too many buttons for the header chrome**
`PageActions` renders ~8 icon buttons (reload OCR, save page, save project,
rematch, export, rotation…). These don't fit in the 40px HeaderBar chrome. In the
hi-fi design some of these move to dialogs triggered from the header, and others
move into the RightPanel context.

Fix for this session: move the most-used actions (reload OCR, save) into
`HeaderBar` as icon buttons on the project route; put the rest behind a `…` menu
or context menu triggered from HeaderBar.

### P2 — Follow-on quality issues (do after P0/P1 are resolved)

**I-8: `ProjectLoadControls` input/LOAD in HeaderBar is oversized** ✅ DONE (#326)
Replaced with breadcrumb text + compact FolderOpen icon button on project routes.
Driver-contract testids preserved via sr-only hidden elements.

**I-9: Right panel 320px column always visible — no collapse wired**
`RightPanel` has an `onCollapse` prop but nothing calls it. The collapse button
renders but clicking it does nothing because `ProjectPage` doesn't pass a handler.

**I-10: `StudioShell` `drawerCollapsed` prop never toggled**
`drawerCollapsed` is passed as `false` always. The Drawer's own collapse button
(Slice 11) calls `setDrawerOpen(false)` via `useUiPrefs`, but `StudioShell`
doesn't subscribe to that value.

---

## Integration session plan

### Session goal
Get to a state where: project loads correctly → StudioShell renders all 5 zones
→ image is visible → Drawer shows Worklist → RightPanel responds to selection.
No new features; pure wiring + layout fixes.

### Slices (all small, estimated haiku/sonnet)

---

**IS-1 — Project-not-found auto-redirect** `(S)`

- In `ProjectPage`, add `useEffect` watching `projectNotFound`; when true call
  `navigate('/', { replace: true })` and fire `toast.warn('Project not found…')`.
- Remove `ProjectNotFoundBanner` from the inline banners (now redundant).
- Test: mock 404 project response → assert `navigate` called with `'/'`.

---

**IS-2 — Reconcile App.tsx HeaderBar with StudioShell header zone** `(M)`

- Remove the `header` slot content from `ProjectPage`'s `StudioShell` call.
  Pass `header={null}` or an empty fragment so StudioShell still reserves the row.
- Extend `HeaderBar` to accept optional `navSlot?: React.ReactNode` and
  `actionsSlot?: React.ReactNode` props.
- In `App.tsx` (or a new `ProjectHeaderBar` wrapper), pass
  `navSlot={<ProjectNavigationControls />}` and
  `actionsSlot={<PageActionsCompact />}` when on a project route (use `useMatch`).
- `PageActionsCompact` = the 2–3 highest-frequency buttons (reload OCR, save);
  rest moved to a `…` overflow menu.
- Test: on project route, nav prev/next and save button appear in header.

---

**IS-3 — Wire Drawer into ProjectPage** `(S)`

- Replace `drawerSlot = <div …placeholder… />` with
  `<Drawer lineMatches={lines} page={pagePayload ?? undefined} />`.
- Subscribe to `useUiPrefs` in `ProjectPage` (or pass as prop) to read `drawerOpen`;
  pass to `StudioShell drawerCollapsed={!drawerOpen}`.
- Wire RightPanel `onCollapse` to toggle `useUiPrefs.drawerOpen` (or a new
  `rightPanelOpen` pref).
- Test: Drawer renders Worklist; collapsing sets `drawerCollapsed` on StudioShell.

---

**IS-4 — Strip canvas slot down to image + controls** `(M)`

- Remove `ToolbarActionGrid` from canvas slot entirely (or gate with
  `showLegacyToolbar` useUiPrefs flag initially).
- Remove the `Splitter` and `TextTabs` / `WordMatchView` from canvas slot.
- Canvas slot becomes: `ImageTabsHeader` (layer/mode toggles) + `PageImageCanvas`.
- Move `ImageTabsHeader` controls into a thin 36px bar above `PageImageCanvas`
  inside the canvas zone.
- Keep all `data-testid` values intact — driver contract must not break.
- Test: canvas zone renders `PageImageCanvas` without splitter; no ToolbarActionGrid.

---

**IS-5 — Fix `main` overflow so StudioShell is viewport-locked** `(S)`

- Change `<main className="flex-1 overflow-auto">` to
  `<main className="flex-1 min-h-0 overflow-hidden">` in `App.tsx`.
- StudioShell already sets `h-full`; this lets the grid own overflow per-zone.
- Test: window at 800px height — canvas zone scrolls independently; header stays fixed.

---

**IS-6 — Wire `drawerCollapsed` ↔ `StudioShell` from `ui-prefs`** `(S)`

- `ProjectPage` reads `useUiPrefs.getState().drawerOpen` via
  `useSyncExternalStore`; passes `drawerCollapsed={!drawerOpen}` to `StudioShell`.
- Already partially done: `Drawer` calls `setDrawerOpen(false)` on collapse.
  This slice closes the loop so StudioShell actually reacts.
- Add collapse/expand for right panel (`rightPanelOpen` pref) with same pattern.

---

### Order of attack

```
IS-1 → IS-5 → IS-2 → IS-3 → IS-6 → IS-4
 fix    fix    fix    fix    fix     fix
 nav    scroll dbl    drawer prefs   canvas
 stuck  lock   hdr    wire   wire    strip
```

IS-1 and IS-5 are independent; do them first — they unblock manual testing.
IS-2 and IS-3 depend on IS-5 (need stable layout to see the result).
IS-6 depends on IS-3.
IS-4 last — highest risk of breaking existing driver-contract testids.

---

### What to NOT touch in this session

- The component library (Slices 0–27) — do not re-implement or rename.
- `data-testid` contracts — driver tests must still pass after IS-4.
- Backend — no API changes.
- `OPEN_QUESTIONS.md` / `docs/hifi-followons.md` items — those are separate.

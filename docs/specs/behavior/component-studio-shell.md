# Behavior unit spec - Studio shell

- **Unit type:** component
- **Address:** `StudioShell`, `Rail`, `Breadcrumb`, `QuickSearch`, `Drawer`
- **UI definition:** none - existing stable UI documented in
  `docs/architecture/24-shell-layout.md`
- **Parent unit(s):** `screen-project-page.md`
- **Child unit(s):** drawer worklist, canvas, right panel
- **Shared unit:** yes
- **Implementation:** `frontend/src/components/shell/StudioShell.tsx`,
  `Rail.tsx`, `Breadcrumb.tsx`, `QuickSearch.tsx`, `Drawer.tsx`,
  `frontend/src/stores/rail-store.ts`, `frontend/src/stores/ui-prefs.ts`
- **Backend / collaborators touched:** localStorage-backed UI prefs;
  `dialog-store` for hotkey help

## Behavior records

### B-SHELL-001 - Rail target and mode selection update active state

- **Flow(s):** -
- **Composed by:** B-PROJECT-001
- **Trigger:** User clicks `rail-target-*` or `rail-mode-*`.
- **Preconditions:** Project page is loaded.
- **Observable output:** Clicked cell gains `data-active="true"` and the shell
  remains stable; target selection affects breadcrumb/right-panel context, mode
  affects available canvas/edit affordances.
- **Backend / side-effects:** Target persists to localStorage key
  `pdl.rail.target`; mode is client-only and resets to `view` on reload; no API
  request occurs.
- **Bad-state / error:** Reload restores target but not mode; invalid stored
  target falls back to `word`.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-002 - Breadcrumb clears or narrows selection by ancestor

- **Flow(s):** -
- **Composed by:** B-CANVAS-002, B-DRAWER-002, B-RIGHT-001
- **Trigger:** User clicks `breadcrumb-chip-root`, `breadcrumb-chip-block`,
  `breadcrumb-chip-para`, or `breadcrumb-chip-line`.
- **Preconditions:** A selection path exists.
- **Observable output:** Terminal chip changes to the clicked level; right panel
  changes to the matching detail view or project empty state.
- **Backend / side-effects:** Selection store mutates in memory; no API request
  or disk write occurs.
- **Bad-state / error:** Clicking the terminal active chip is a no-op.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-003 - Drawer collapse and tab selection persist through UI prefs

- **Flow(s):** -
- **Composed by:** B-PROJECT-001
- **Trigger:** User clicks `drawer-collapse-btn`, `drawer-expand-btn`, or
  drawer tab buttons.
- **Preconditions:** Project page is loaded.
- **Observable output:** Drawer `data-open` and shell drawer column state update;
  selected tab content switches between `worklist` and `hierarchy`.
- **Backend / side-effects:** `useUiPrefs` stores `drawerOpen` and `drawerTab`
  in browser-local persisted UI prefs; no backend write occurs.
- **Bad-state / error:** On invalid persisted tab, drawer falls back to the
  default worklist tab.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-004 - Hotkey help opens from rail or quick-search keycap

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User clicks `rail-hotkeys-button` or `quick-search-keycap`.
- **Preconditions:** Project page is loaded.
- **Observable output:** `hotkey-help-dialog` appears with registered shortcut
  groups; closing returns focus to the previous workflow area.
- **Backend / side-effects:** Pure client-side `dialog-store` transition; no
  API request occurs.
- **Bad-state / error:** If no shortcut group is registered, dialog still opens
  with an empty or minimal list rather than crashing.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-005 - StudioShell zones and layout props keep page stable

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-PROJECT-001
- **Trigger:** Project page renders shell with drawer/header/right-panel layout
  props.
- **Preconditions:** Project route mounted.
- **Observable output:** Rail, drawer, canvas, right panel, and header slots
  render; collapsed drawer uses a zero-width column while canvas/right panel
  remain mounted.
- **Backend / side-effects:** None.
- **Bad-state / error:** Hidden header or collapsed drawer must not unmount the
  active canvas or right panel.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-006 - Rail layer toggles update overlay visibility prefs

- **Flow(s):** -
- **Composed by:** B-CANVAS-012
- **Trigger:** User clicks a `rail-layer-*` toggle.
- **Preconditions:** Rail mounted.
- **Observable output:** Toggle pressed state changes and overlay/layer
  visibility follows the preference.
- **Backend / side-effects:** `useUiPrefs.layerVisibility` mutates; no API.
- **Bad-state / error:** Toggling the active target layer does not change rail
  target or edit mode.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-007 - Rail Bulk opens drawer to Worklist

- **Flow(s):** -
- **Composed by:** B-DRAWER-003
- **Trigger:** User clicks `rail-bulk-button`.
- **Preconditions:** Drawer may be collapsed or showing Hierarchy.
- **Observable output:** Drawer opens with Worklist tab active.
- **Backend / side-effects:** `useUiPrefs.drawerOpen=true` and
  `drawerTab=worklist`; no API.
- **Bad-state / error:** Opening bulk controls does not select any worklist rows
  by itself.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-008 - Rail hotkeys set target and mode

- **Flow(s):** -
- **Composed by:** -
- **Trigger:** User presses registered unmodified rail shortcut keys.
- **Preconditions:** Project page mounted and focus is not in input or
  contenteditable text.
- **Observable output:** Matching rail button becomes active.
- **Backend / side-effects:** Target persists via `pdl.rail.target`; mode is
  memory-only.
- **Bad-state / error:** Modifier keys, unrelated keys, and input-focused keys
  are ignored.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-009 - Breadcrumb Alt-arrow hotkeys walk hierarchy

- **Flow(s):** -
- **Composed by:** B-SHELL-002
- **Trigger:** User presses Alt+ArrowLeft/Right/Up/Down.
- **Preconditions:** Page payload exists, hook enabled, and no input owns focus.
- **Observable output:** Breadcrumb/right panel move to sibling, parent, or
  first child where such a node exists.
- **Backend / side-effects:** Selection store only.
- **Bad-state / error:** Disabled/no-page/boundary navigation is a no-op.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-010 - Quick search filters Worklist text and Escape clears

- **Flow(s):** -
- **Composed by:** B-DRAWER-001
- **Trigger:** User types in `quick-search-input` or presses Escape.
- **Preconditions:** Worklist has page data.
- **Observable output:** Queue narrows by OCR/GT text; no-match state appears
  when appropriate; Escape clears and blurs the input.
- **Backend / side-effects:** `worklistStore.searchQuery` mutates; no API.
- **Bad-state / error:** Blank or whitespace query restores the current
  filter/sort result.
- **Tier(s):** A
- **Regression:** no
- **Test:** -

### B-SHELL-011 - Drawer tab count badges render only for positive counts

- **Flow(s):** F-LABEL-SAVE-EXPORT-01
- **Composed by:** B-SHELL-003
- **Trigger:** Drawer receives Worklist/Hierarchy tab counts.
- **Preconditions:** Drawer open.
- **Observable output:** Positive count badges render; zero/undefined badges are
  absent.
- **Backend / side-effects:** None.
- **Bad-state / error:** Missing count data does not prevent tab switching.
- **Tier(s):** B
- **Regression:** no
- **Test:** -

## Known regressions

- None captured yet.

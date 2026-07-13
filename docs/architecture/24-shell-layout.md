---
kind: architecture
status: built
owner: maintainers
created: 2026-05-16
last_verified: 2026-07-13
---

# 24 — Studio Shell / Layout

> **Status**: Active (shipped — FO-1–FO-9 follow-ons)
> **Last updated**: 2026-05-16
> **Components documented**: `StudioShell`, `Rail`, `Drawer`, `Breadcrumb`,
> `QuickSearch`, `rail-store`, `useRailHotkeys`, `useBreadcrumbHotkeys`

## 1. Overview

The Studio shell is the five-zone grid that frames the entire labeling
workflow on the `/project/:id/page/:n` route. It divides the viewport into a
header band, a 64 px icon rail, a collapsible drawer, the main canvas area,
and a variable-width right panel. The rail selects both the annotation target
level (Block / Para / Line / Word) and the interaction mode (View / Refine /
Annotate / Erase). The breadcrumb at the top of the right panel shows and
navigates the current selection path. Together these components give labelers
instant visual context about what they are looking at and one-keystroke
switching between task modes.

## 2. User-facing goals

- I need to switch the annotation target (word, line, para, block) instantly
  without hunting through menus so I can stay in a keyboard-driven flow.
- I need the side drawer to collapse out of the way when I want more canvas
  space, and to re-open with one click.
- I need to see exactly where I am in the document hierarchy (project → block
  → para → line → word) and to navigate up by clicking a breadcrumb chip.
- I need a quick way to look up keyboard shortcuts without breaking my editing
  flow.
- I need the layout to be stable across viewport resizes — no overlapping
  panels or content clipping.

## 3. Component tree / layout

> **D-047 (2026-06-14):** The shipped shell is the pdomain-ui `AppShell` (in
> `App.tsx`) plus `ProjectPage`'s own body grid. `StudioShell` (below) remains a
> tested layout primitive but is not in the live render path; the tree shown
> here reflects what `ProjectPage` actually renders. The AppShell chrome header
> is document-control-free; the `WorkspaceToolbar` band carries the
> document/page-scoped controls, and the ⌘K `QuickSearch` lives in the Drawer
> worklist header.

```
App (pdomain-ui AppShell)
├── [header zone]  chrome only
│   ├── HeaderBar                     data-testid="header-bar"
│   │   (logo, app name, project breadcrumb, project-root label)
│   ├── LauncherSlot                  (pdomain-ui)
│   └── SettingsSlot ⚙                (pdomain-ui; Appearance panel owns theme — D-048)
├── [rail zone]                       data-testid="rail"  (project route)
└── [main zone]
    └── ProjectPage                   data-testid="project-page"
        ├── WorkspaceToolbar          data-testid="workspace-toolbar"
        │   ├── leftSlot   = ProjectNavigationControls  (nav-*)
        │   ├── centerSlot = PageActionsCompact         (page-actions-compact-*)
        │   └── rightSlot  = WorkspaceMetrics           (header-metrics-strip)
        └── project-workspace         data-testid="project-workspace"
            ├── canvas column         (ImageViewport / BBoxOverlay)
            ├── worklist column
            │   └── Drawer            data-testid="drawer"
            │       └── worklist-header  data-testid="drawer-worklist-header"
            │           └── QuickSearch  data-testid="quick-search" (⌘K focus)
            └── detail column         (WordDetail / LineDetail / BlockDetail)
```

The `StudioShell` 5-zone grid primitive (below) is retained for its tests and
potential reuse; it is not currently mounted by `ProjectPage`.

### CSS grid template

```
"header header header header"
"rail   drawer  canvas right"
```

- Column widths: `64px | var(--drawer-w, 320px) | 1fr | var(--right-w, 520px)`
- Row heights: `{headerHeight}px | 1fr` (default `headerHeight = 56`)
- When `drawerCollapsed = true`, the drawer column collapses to `0px`.
- When `rightWidth` is explicitly provided (e.g. 640 for block/line views),
  `--right-w` is overridden inline.

The entire grid fills the browser viewport (`h-full w-full`).

## 4. Data model

### StudioShell props

| Prop | Type | Description |
|---|---|---|
| `header` | `ReactNode` | Header zone content |
| `headerHeight` | `number` (default 56) | Header row height in px; set to 0 to hide |
| `rail` | `ReactNode` | 64px rail content |
| `drawer` | `ReactNode` | Drawer panel content |
| `canvas` | `ReactNode` | Main canvas content |
| `right` | `ReactNode` | Right panel content |
| `drawerCollapsed` | `boolean` | When true the drawer column is `0px` |
| `rightWidth` | `number` | Override right panel width in px |

### rail-store state

```typescript
interface RailState {
  target: "block" | "para" | "line" | "word";  // persisted to localStorage
  mode:   "view" | "region" | "annotate" | "erase";  // NOT persisted
  setTarget: (target: RailTarget) => void;
  setMode:   (mode: RailMode) => void;
}
```

Storage key: `pdl.rail.target` (defaults to `"word"` on first load).
Mode always resets to `"view"` on page reload.

### Breadcrumb / selection-store integration

Breadcrumb reads from `selectionStore` (the same store used by
`BBoxOverlay` and the right-panel detail views). The relevant slice:

```typescript
interface SelectionPath {
  blockId?: string;
  paraId?:  number | null;
  lineId?:  number;
  wordId?:  [lineIndex: number, wordIndex: number];
}
type SelectionLevel = "none" | "block" | "para" | "line" | "word";
```

`Breadcrumb` also accepts an optional `page?: PagePayload` prop to resolve
ancestor labels (e.g. derive `paraId` from a line's `paragraph_index`).

### ui-prefs integration (Drawer)

The Drawer reads and writes two keys on `useUiPrefs` (Zustand store):

| Key | Type | Default |
|---|---|---|
| `drawerOpen` | `boolean` | — |
| `drawerTab` | `"worklist" \| "hierarchy"` | — |

These are persisted to localStorage by `useUiPrefs`.

## 5. Interactions and behaviors

### StudioShell

- The grid is purely layout — no interactive behavior of its own.
- `data-collapsed` attribute on the drawer zone reflects the collapsed state
  (`"true"` when collapsed, attribute absent when open).

### Rail

#### Target selection

- Click a TargetCell button → `railStore.setTarget(target)` → the clicked cell
  gains `data-active="true"`, a 2px left accent stripe, and layer-color text.
- All four targets are always visible (Block / Para / Line / Word) with their
  layer-color swatches.

#### Mode selection

- Click a ModeCard button → `railStore.setMode(mode)` → active cell gains
  `data-active="true"` and a 2px left accent stripe.
- Modes: View (Eye icon), Refine (Square icon), Annotate (Plus icon),
  Erase (Eraser icon).

#### Footer buttons

- "Bulk" button (`rail-bulk-button`) — does not currently open anything
  (stub affordance; BulkActions lives in the Drawer).
- "Hotkeys" button (`rail-hotkeys-button`) → `dialogStore.open("hotkeyHelp")`.

#### LAYERS section

- Read-only color swatches matching the four layer CSS tokens. Static — no
  interaction.

### Breadcrumb

- Renders a horizontal chip chain: Project (root) › Block N › Para N › Line N › Word N.
- Only chips for levels that are in the current selection path are rendered.
- **Ancestor chips** (`data-active="false"`): clicking re-selects at that level
  (calls `clearSelection()`, `selectBlock()`, `selectPara()`, or `selectLine()`).
- **Terminal chip** (`data-active="true"`): colored with layer-specific
  background (`bg-layer-{kind}/10 + text-layer-{kind}`). Clicking is a no-op.
- **Root "Project" chip**: `data-active="true"` when no selection, otherwise
  clicking calls `clearSelection()`.
- `resolveAncestors()` backfills missing ancestor IDs from `page.line_matches`
  so the chain renders fully even when a leaf-level selection action only
  set the deepest path key.

### QuickSearch

- The wrapper `div` click handler focuses the inner `<input>`.
- The `<input>` is currently `readOnly` — search submission is not yet
  implemented.
- The "⌘K" keycap button → `dialogStore.open("hotkeyHelp")`.

### Drawer

- When open (`data-open="true"`): renders a 320px panel with a tab strip
  (Worklist / Hierarchy), tab icons and optional count badges, and a
  collapse chevron button.
- Clicking a tab → `useUiPrefs.setState({ drawerTab: tab.id })`.
- Clicking the collapse button → `useUiPrefs.setState({ drawerOpen: false })`.
- When collapsed (`data-open="false"`): renders a narrow strip with an expand
  chevron button → `useUiPrefs.setState({ drawerOpen: true })`.
- Count badge (`drawer-tab-count-{tab}`) appears only when `tabCounts?.[tab] > 0`.

## 6. data-testid contract

| testid | element | description |
|---|---|---|
| `studio-shell` | div | Top-level grid container |
| `studio-shell-header` | div | Header zone (hidden when `headerHeight=0`) |
| `studio-shell-rail` | div | Rail zone |
| `studio-shell-drawer` | div | Drawer zone; `data-collapsed="true"` when collapsed |
| `studio-shell-canvas` | div | Main canvas zone |
| `studio-shell-right` | div | Right panel zone |
| `rail` | div | 64px rail container |
| `rail-mode-view` | button | View mode card |
| `rail-mode-region` | button | Refine mode card |
| `rail-mode-annotate` | button | Annotate mode card |
| `rail-mode-erase` | button | Erase mode card |
| `rail-target-block` | button | Block target cell |
| `rail-target-para` | button | Para target cell |
| `rail-target-line` | button | Line target cell |
| `rail-target-word` | button | Word target cell |
| `rail-bulk-button` | button | Bulk actions button (stub) |
| `rail-hotkeys-button` | button | Opens hotkey help dialog |
| `breadcrumb` | div | Breadcrumb container |
| `breadcrumb-chip-root` | button | "Project" root chip |
| `breadcrumb-chip-block` | button | Block-level chip (when in path) |
| `breadcrumb-chip-para` | button | Para-level chip (when in path) |
| `breadcrumb-chip-line` | button | Line-level chip (when in path) |
| `breadcrumb-chip-word` | button | Word-level chip (when in path) |
| `quick-search` | div | Quick search container |
| `quick-search-input` | input | Search text input (currently read-only) |
| `quick-search-keycap` | button | ⌘K keycap button, opens hotkey help |
| `drawer` | div | Drawer panel; `data-open="true\|false"` |
| `drawer-header` | div | Tab strip + collapse button |
| `drawer-tab-worklist` | button | Worklist tab trigger |
| `drawer-tab-hierarchy` | button | Hierarchy tab trigger |
| `drawer-tab-icon-worklist` | span | Worklist tab icon (List icon) |
| `drawer-tab-icon-hierarchy` | span | Hierarchy tab icon (GitBranch icon) |
| `drawer-tab-count-worklist` | span | Worklist count badge (when count > 0) |
| `drawer-tab-count-hierarchy` | span | Hierarchy count badge (when count > 0) |
| `drawer-collapse-btn` | button | Collapse drawer (ChevronLeft) |
| `drawer-expand-btn` | button | Expand drawer (ChevronRight, shown when collapsed) |

All `data-active` attributes are `"true"` (when active) or absent (when not
active) — never `"false"`.

## 7. Keyboard shortcuts

### Rail hotkeys (useRailHotkeys)

Active when no `<input>`, `<textarea>`, or `contentEditable` element is focused.
Modifier keys (Ctrl, Meta, Alt) suppress all rail hotkeys.

| Key | Action |
|---|---|
| `1` | Set target = block |
| `2` | Set target = para |
| `3` | Set target = line |
| `4` | Set target = word |
| `v` / `V` | Set mode = view |
| `r` / `R` | Set mode = region (Refine) |
| `a` / `A` | Set mode = annotate |
| `e` / `E` | Set mode = erase |

### Breadcrumb hotkeys (useBreadcrumbHotkeys)

Active when `enabled = true` and a `page` prop is provided. Suppressed when
any input is focused, or when Ctrl/Meta is held.

| Key | Action |
|---|---|
| `Alt+ArrowLeft` | `walkSibling("prev", page)` — select previous sibling at current level |
| `Alt+ArrowRight` | `walkSibling("next", page)` — select next sibling at current level |
| `Alt+ArrowUp` | `walkLevel("up", page)` — navigate to parent level |
| `Alt+ArrowDown` | `walkLevel("down", page)` — navigate to first child level |

The hook is a no-op when `page` is undefined (no page loaded).

## 8. Edge cases

- **No selection**: Breadcrumb shows only the "Project" root chip with
  `data-active="true"`.
- **Drawer collapsed**: The `studio-shell-drawer` zone has `data-collapsed="true"`;
  the grid column is `0px`; the Drawer renders only the expand chevron button.
- **`headerHeight = 0`**: The `studio-shell-header` div is hidden (`hidden` class).
  Used when the app-level header handles the top chrome independently.
- **localStorage unavailable**: `railStore` falls back to `"word"` as the
  default target (handled via try/catch in `readPersistedTarget`).
- **Page not loaded** (`useBreadcrumbHotkeys`): the hook returns early; no event
  listener is registered.
- **Tab count badges**: `drawer-tab-count-{tab}` elements are only rendered when
  the count is `> 0`. When no `tabCounts` prop is provided they are always absent.

## 9. Open questions

1. **QuickSearch submit**: The input is currently `readOnly`. The search submit
   callback and result-set are not implemented. The spec for a future slice
   should define: debounce delay, what is searched (OCR text? GT text? both?),
   how results are displayed (inline dropdown? filter Worklist?), and whether
   the search clears the current selection.

2. **Rail "Bulk" button wiring**: The `rail-bulk-button` has no click handler.
   It is presumably intended to toggle bulk-selection mode on the Worklist or
   to open the BulkActions panel. The relationship between this button and
   `BulkActions.tsx` (which lives inside the Drawer) is not currently specified.

3. **Mode wiring**: `mode` (view / region / annotate / erase) is stored in
   `railStore` and reflected in the Rail UI, but nothing currently reads it to
   change canvas behavior. The ImageViewport / BBoxOverlay components use their
   own `selectionMode` prop. How the rail mode maps to viewport behavior is not
   yet defined.

4. **Block layer in Breadcrumb**: The `blockId` slot in `SelectionPath` accepts
   a synthetic string ID, but `PagePayload` has no `block_index`. The label
   rendered is the raw string ID rather than "Block N". When the page model
   gains an explicit block layer this should be resolved to a 1-based number.

5. **Drawer tab count source**: The `tabCounts` prop on `Drawer` must be
   computed by the parent (currently `ProjectPage`). The spec does not define
   which counts are meaningful — for the Worklist tab, total line count vs.
   filtered/unvalidated count are both plausible.

# pd-ocr-labeler-spa UI Redesign — Implementation Plan

**Status:** ✅ SHIPPED — All Slices 0–27 (Phases 0–6) completed as of 2026-05-15.

**Source:** Design handoff in `ocr labeler.zip` (`design_handoff_hifi/`).
**Date:** 2026-05-15
**Scope:** Transforms the existing M2–M7 surface area into the hi-fi Studio design.
**Out of scope:** M8 persistence, M9 export, Postgres (deferred), real PGDP monospace font asset.

Each slice targets one subagent session (~200–400 LOC). Run `make ci` after every slice.

**Conventions:**
- File paths are relative to repo root.
- Token names (`bgPage`, `ink2`, etc.) expose as CSS custom properties (`--bg-page`, `--ink-2`).
- "Existing → evolves" tags identify components being grown, not replaced.
- New components live under `frontend/src/components/{ui,shell,drawer,right-panel}/`.

---

## Phase 0 — Tooling bootstrap

### Slice 0 — Add shadcn components, Lucide, CVA, tailwind-merge
- **Why:** shadcn/ui is already initialized (`frontend/components.json` exists with `baseColor: slate`). No components or Radix deps have been added yet. Installing these now means Slices 4–7 configure existing accessible primitives rather than building from scratch.
- **What to implement:**
  - `cd frontend` then add shadcn components via the CLI — each `add` installs its Radix peer deps and (first time) adds `class-variance-authority`, `tailwind-merge`, `clsx` to `package.json`:
    ```
    npx shadcn@latest add button
    npx shadcn@latest add accordion
    npx shadcn@latest add tabs
    npx shadcn@latest add dropdown-menu
    npx shadcn@latest add tooltip
    npx shadcn@latest add dialog
    ```
  - Add Lucide directly: `npm install lucide-react`
  - shadcn's `add` command creates `frontend/src/lib/utils.ts` with the `cn()` helper (clsx + tailwind-merge). If the file already exists, leave it.
  - shadcn will also inject its own CSS variable block into `frontend/src/index.css` (`--background`, `--foreground`, `--primary`, etc.). **Do not use these variables in any component** — they will be replaced wholesale by our token system in Slice 1. Add a comment block above them: `/* shadcn bootstrap vars — replaced by tokens.css in Slice 1 */`.
  - shadcn will add entries to `tailwind.config.js` (the `borderRadius` key and a `theme.extend.colors` block using `hsl(var(--…))`). These entries are fine to keep as a starting point; Slice 2 overlays our semantic tokens on top.
  - The generated component files land in `frontend/src/components/ui/` — do not edit them yet. Slices 4–7 restyle them to use our tokens.
- **What to test:** `npm run build` (or `make frontend-build AI=1`) succeeds with the new deps; no TypeScript errors from the generated components. No new vitest tests needed for this slice.
- **Dependencies:** none.
- **Model:** haiku.

> **Sonner note:** `sonner` is already in `package.json`. Slice 26's toast work is wiring into Sonner, not building a custom component.

---

## Phase 1 — Foundation (tokens + primitives)

### Slice 1 — CSS custom-property token layer (dark default + light scheme)
- **Why:** Every later slice consumes these tokens. Dual dark/light without ripping out Tailwind.
- **What to implement:**
  - New `frontend/src/styles/tokens.css` — `:root { … }` (dark = default) plus `[data-theme="light"] { … }`. Full token set from DESIGN_LANGUAGE.md: bg (page/surface/raised/sunk), border (1/2/3), ink (1/2/3/4), accent + accentInk, status (exact/fuzzy/mismatch/ocr/gt), layer (block/para/line/word).
  - Import `tokens.css` from `frontend/src/index.css` *before* the `@tailwind` directives.
  - Add `prefers-color-scheme: light` media block that flips to light tokens only when `data-theme` is unset on `<html>`.
  - Set `<html data-theme="dark">` as default in `frontend/index.html`.
- **What to test:** `frontend/src/styles/tokens.test.ts` — render a div using `var(--ink-1)`, assert dark hex; flip `data-theme="light"`, assert light hex.
- **Dependencies:** none.
- **Model:** haiku.

### Slice 2 — Wire Tailwind theme.extend to CSS variables
- **Why:** Lets components use `bg-surface text-ink-2` utilities while the variable system carries the theme.
- **What to implement:**
  - Edit `frontend/tailwind.config.js` — populate `theme.extend.colors` with semantic keys (`bg.page`, `bg.surface`, `bg.raised`, `bg.sunk`, `border.1/2/3`, `ink.1/2/3/4`, `accent.DEFAULT`, `accent.ink`, `status.exact/fuzzy/mismatch/ocr/gt`, `layer.block/para/line/word`) all referencing `var(--…)`.
  - Add `theme.extend.fontFamily.ui` (Inter) and `theme.extend.fontFamily.mono` (JetBrains Mono, ui-monospace).
  - Add custom `fontSize` keys: `label` (9.5px/1.1), `hint` (10px/1.2), `btn-sm` (11px/1.2), `body` (12px/1.4), `heading` (13px/1.3).
  - Update `tests/unit/test_tailwind_config.py` if it asserts a literal empty `extend` — relax to content-glob assertion only.
- **What to test:** Vitest: `<div className="bg-surface text-ink-1">` resolves to `var(--bg-surface)` / `var(--ink-1)`.
- **Dependencies:** Slice 1.
- **Model:** haiku.

### Slice 3 — Load Inter + JetBrains Mono fonts; set body defaults
- **Why:** Typography is load-bearing in the hi-fi — code-shaped content must render in mono.
- **What to implement:**
  - Add `@fontsource/inter` and `@fontsource/jetbrains-mono` (npm). Import in `frontend/src/main.tsx`.
  - `frontend/src/index.css` — replace body `font-family` with `Inter, …`; set `font-size: 12px; color: var(--ink-1); background: var(--bg-page)`.
  - Add `.font-pgdp` utility as alias for `font-mono` (stable name for later real-font swap).
- **What to test:** Assert `body` computedStyle `font-family` contains `Inter`.
- **Dependencies:** Slices 1–2.
- **Model:** haiku.

### Slice 4 — Primitive: Button (3 sizes × 4 variants)
- **Why:** Used everywhere in shell, drawer, right panel, dialogs.
- **What to implement:**
  - Shadcn added `frontend/src/components/ui/button.tsx` in Slice 0 — restyle it to use our tokens rather than shadcn's `--primary` etc.
  - Map variants to our tokens: primary = `bg-accent text-accent-ink`; secondary = `bg-raised border border-border-2 text-ink-1`; ghost = transparent + hover `bg-raised`; danger = `bg-status-mismatch`. Add `"danger"` to the CVA variant map (shadcn ships primary/secondary/ghost/destructive; rename `destructive` → `danger` or add as alias).
  - Sizes: sm (24px), default (30px), lg (34px). Match the CVA `size` variants.
  - Focus ring: `focus-visible:ring-1 ring-accent`.
  - Export as `Button` (capital-B re-export) from `frontend/src/components/ui/Button.tsx` for consistent naming.
- **What to test:** `Button.test.tsx` — each variant×size; click fires; disabled blocks.
- **Dependencies:** Slices 0, 2.
- **Model:** haiku.

### Slice 5 — Primitives: StatusPip, KeyCap, Input
- **Why:** StatusPip in every word card; KeyCap drives every hotkey label; Input is base for bbox, char-fixer, etc.
- **What to implement:**
  - `frontend/src/components/ui/StatusPip.tsx`: prop `status: "exact"|"fuzzy"|"mismatch"`. 8px round dot in `--status-*` token. Optional `label` prop.
  - `frontend/src/components/ui/KeyCap.tsx`: prop `keys: string | string[]`. Compact pills with `bg-sunk border border-border-2 text-ink-2 font-mono text-hint`.
  - `frontend/src/components/ui/Input.tsx`: `bg-sunk border border-border-2 focus:border-accent`, `size: "sm"|"md"`.
- **What to test:** One `.test.tsx` per primitive — render variants, assert class/structure.
- **Dependencies:** Slices 2, 3.
- **Model:** haiku.

### Slice 6 — Primitives: Chip (static + tri-state) and Tab (underline)
- **Why:** Tri-state chips drive style/component pickers; underline Tabs drive Line/Words and Layout/Items toggles.
- **What to implement:**
  - `frontend/src/components/ui/Chip.tsx` — build new (no shadcn equivalent). `variant: "static"|"tristate"`. Tri-state value: `"off"|"on"|"mixed"`. Cycles on click. Mixed = dashed border + `ink-3`.
  - `frontend/src/components/ui/Tabs.tsx` — restyle shadcn's `tabs.tsx` (added in Slice 0). Underline style: active = 2px `--accent` bottom border + `ink-1`; inactive = `ink-3`. Expose a simple controlled API: `tabs: {id, label}[]`, `value`, `onChange`.
- **What to test:** `Chip.test.tsx` — tri-state cycle; `Tabs.test.tsx` — keyboard left/right, click changes value.
- **Dependencies:** Slices 2, 5.
- **Model:** sonnet.

### Slice 7 — Primitive: Accordion with accent-tagged variants
- **Why:** Word Detail editor is 5+ stacked accordions; some carry `accent` (Rebox) or `mismatch` (Erase) left-edge stripe.
- **What to implement:**
  - `frontend/src/components/ui/Accordion.tsx` — wrap shadcn's `accordion.tsx` (Radix-backed, keyboard-accessible). Extend the `<Accordion.Item>` with a `tag?: "accent"|"mismatch"` prop that adds a 2px left-edge colored stripe via a CSS class.
  - Header row: restyle shadcn defaults to `bg-raised` + chevron using our tokens.
  - Re-export with API: `<Accordion><Accordion.Item id title tag defaultOpen>{…}</Accordion.Item></Accordion>`.
  - Keyboard (Up/Down, Enter/Space) comes free from Radix — just verify it works.
- **What to test:** `Accordion.test.tsx` — open/close, keyboard nav, tag stripe renders.
- **Dependencies:** Slices 2, 5.
- **Model:** sonnet.

---

## Phase 2 — Studio shell (layout chrome)

### Slice 8 — Studio shell skeleton: 5-zone grid layout
- **Why:** Header / Rail / Drawer / Canvas / RightPanel is the hi-fi shell. Today `ProjectPage` is roughly a 2-pane splitter.
- **What to implement:**
  - New `frontend/src/components/shell/StudioShell.tsx` — CSS grid: `grid-template-areas: "header header header header" "rail drawer canvas right"`, `grid-template-columns: 40px var(--drawer-w,260px) 1fr 320px`, `grid-template-rows: 40px 1fr`.
  - Children via slots: `<StudioShell header rail drawer canvas right />`. Drawer slot supports `collapsed` prop (`--drawer-w: 0px`).
  - `frontend/src/pages/ProjectPage.tsx` — keep data fetching (`useProject`, `usePage`); wrap return JSX in `<StudioShell>` mapping existing children into slots. Remove existing `Splitter` from this level.
- **What to test:** `StudioShell.test.tsx` — all five slots render, grid-area assigned. `ProjectPage.test.tsx` — update for StudioShell wrapper.
- **Dependencies:** Slices 1–3.
- **Model:** sonnet.

### Slice 9 — HeaderBar evolution: 40px top chrome
- **Why:** Existing `HeaderBar` needs: 40px height, `bg-page`, logo + project name, user menu with theme toggle stub.
- **What to implement:**
  - Evolve `frontend/src/components/HeaderBar.tsx`:
    - Left: logo glyph + project name (clickable → RootPage).
    - Center: project nav controls (`ProjectNavigationControls`) at small size.
    - Right: new `UserMenu` button (avatar circle + caret); dropdown: Theme row (stubbed) + Sign out row.
  - Height 40px, `bg-page`, `border-b border-border-1`.
- **What to test:** Extend `HeaderBar.test.tsx` — height class, logo click, user menu opens.
- **Dependencies:** Slice 8.
- **Model:** sonnet.

### Slice 10 — Rail: B/L/W target selector + V/R/A/E mode icons
- **Why:** Selection target governs canvas drag-select scope and right-panel context.
- **What to implement:**
  - New `frontend/src/components/shell/Rail.tsx`. 40px vertical column. Two groups:
    - **Target** (top): B / L / W icon buttons. Active = `bg-raised` + 2px left `accent` stripe + layer-color glyph.
    - **Mode** (below): V / R / A / E toggle group.
  - New `frontend/src/stores/rail-store.ts`: `{target: "block"|"line"|"word"; mode: "view"|"region"|"annotate"|"erase"; setTarget; setMode}`. Persist `target` to localStorage (`pdl.rail.target`).
  - Hotkeys `1`/`2`/`3` cycle target; `V`/`R`/`A`/`E` set mode. New hook `frontend/src/hooks/useRailHotkeys.ts`.
  - Wire into StudioShell `rail` slot in `ProjectPage`.
- **What to test:** `Rail.test.tsx` — click updates store, active styling reflects store. `useRailHotkeys.test.ts` — shortcut coverage. `rail-store.test.ts` — persistence round-trip.
- **Dependencies:** Slices 4, 5, 8.
- **Model:** sonnet.

### Slice 11 — Drawer shell + Worklist tab (wraps existing FilterToggle logic)
- **Why:** Formalizes worklist chips and queue navigation inside a Drawer.
- **What to implement:**
  - New `frontend/src/components/shell/Drawer.tsx` — 260px panel, header with tabs "Worklist" | "Hierarchy", collapse button (`useUIPrefs` key `drawerOpen`).
  - New `frontend/src/components/drawer/Worklist.tsx`:
    - Filter chip row (Exact/Fuzzy/Mismatch/All) using `Chip variant="static"`. State in new `frontend/src/stores/worklist-store.ts` (`activeFilters: Set<Status>`).
    - Queue list with StatusPip + label + KeyCap for jump hotkey.
    - Extract `FilterToggle.tsx` filter predicate into `frontend/src/lib/filter-predicates.ts`; mark `FilterToggle` as legacy.
  - Hierarchy tab: "Coming soon" placeholder (filled Slice 12).
  - `useUIPrefs` new keys: `drawerOpen` (bool, default true), `drawerTab` ("worklist"|"hierarchy", default "worklist").
- **What to test:** `Drawer.test.tsx` — tab switch, collapse persists. `Worklist.test.tsx` — chip filter updates queue; click row updates selection store.
- **Dependencies:** Slices 4, 5, 6, 8.
- **Model:** sonnet.

### Slice 12 — Drawer Hierarchy tab (block/para/line/word tree)
- **Why:** Alternative drawer surface for structural navigation.
- **What to implement:**
  - New `frontend/src/components/drawer/Hierarchy.tsx` — tree view of page structure (blocks → paras → lines → words). Each node: 6px layer-color square + label. Reads from `usePage`.
  - Click selects node (updates `selection-store`). Keyboard: Up/Down/Left/Right navigate (collapse/expand on Left/Right at branch nodes).
  - Drawer reads `useUIPrefs.drawerTab` to mount Worklist or Hierarchy.
- **What to test:** `Hierarchy.test.tsx` — given mock page payload, expected nesting; arrow-key nav; click selects; layer color squares present.
- **Dependencies:** Slice 11.
- **Model:** sonnet.

### Slice 13 — Canvas: layer-colored bbox overlays + target-scoped drag-select
- **Why:** Canvas must reflect the Rail's B/L/W target — drag rectangle selects within scope.
- **What to implement:**
  - Evolve `frontend/src/components/BBoxOverlay.tsx`:
    - Stroke color from `--layer-*` tokens (read via `getComputedStyle(document.documentElement)` in a new `useLayerColors()` hook).
    - Active target layer renders full opacity; others dimmed.
    - Drag-select intersects only bboxes of active target layer. Pure helper: `frontend/src/lib/bbox-select.ts`.
  - `frontend/src/components/PageImageCanvas.tsx` subscribes to `rail-store.target`, passes to BBoxOverlay.
- **What to test:** `bbox-select.test.ts` — pure function: given target="line", drag rect picks lines not words; stroke color tokens.
- **Dependencies:** Slice 10.
- **Model:** sonnet.

---

## Phase 3 — Right Panel context routing

> **Note:** Do Slice 15 before Slice 14 (15 extends the store that 14 consumes).

### Slice 15 — selection-store: hierarchical selection
- **Why:** Existing `selection-store.ts` tracks only word selection; Breadcrumb + Rail need a unified hierarchical model.
- **What to implement:**
  - Extend `frontend/src/stores/selection-store.ts`: add `level: "none"|"block"|"para"|"line"|"word"` and `path: {blockId?, paraId?, lineId?, wordId?}`. Keep `selectedWordId` etc. as derived getters for backwards compat.
  - Actions: `selectBlock(id)`, `selectPara(id)`, `selectLine(id)`, `selectWord(id)`, `walkSibling(direction)`, `walkLevel(direction)`.
  - Pure helper `frontend/src/lib/selection-walk.ts`: `nextSibling(path, page, dir)` and `walkUp/Down(path, page)`. Full unit tests.
  - Migrate `useMatchesHotkeys` and other call sites from legacy word-only API.
- **What to test:** `selection-walk.test.ts` — first/last sibling, missing levels, walking up hierarchy. `selection-store.test.ts` — actions update level + path.
- **Dependencies:** none structurally.
- **Model:** opus.

### Slice 14 — RightPanel router + Breadcrumb header
- **Why:** Right panel must swap between Word Detail / Line tabs / Block tabs based on selection.
- **What to implement:**
  - New `frontend/src/components/shell/RightPanel.tsx` — header with `Breadcrumb` + collapse button; body slot rendered from `selection-store.level`.
  - New `frontend/src/components/shell/Breadcrumb.tsx` — renders path chips `Project › Block 2 › Para 3 › Line 7 › Word 1` from `selection-store` + `usePage`. Each chip is a `<button>` with layer color glyph. Last chip = `ink-1`; ancestors = `ink-3`.
  - Keyboard: `⌥←/→` walk siblings at deepest level; `⌥↑/↓` move up/down hierarchy. New hook `frontend/src/hooks/useBreadcrumbHotkeys.ts`.
  - Mount RightPanel in StudioShell `right` slot. Initial routing: level="word" renders existing `WordMatchView`; others render "Coming soon" placeholders.
- **What to test:** `Breadcrumb.test.tsx` — chip count from selection state; click ancestor changes selection; `⌥` hotkeys. `RightPanel.test.tsx` — level switch swaps body.
- **Dependencies:** Slices 4, 5, 8, 15.
- **Model:** opus.

---

## Phase 4 — Word Detail editor

### Slice 16 — Word Detail editor scaffold + Bounding Box accordion
- **Why:** First slice of the densest screen. Proves the Accordion pattern.
- **What to implement:**
  - New `frontend/src/components/right-panel/WordDetail.tsx` — mounted when `level === "word"`. `<Accordion>` with 6 items (Bounding Box wired; Rebox/Erase/Structure/Char Ranges/Char Fixer stubbed).
  - `frontend/src/components/right-panel/sections/BBoxSection.tsx` — 4 numeric `Input size="sm"` for x/y/w/h; saves via word PATCH mutation. If `useWordMutations` doesn't exist, create `frontend/src/hooks/useWordMutations.ts`. "Reset" `Button variant="ghost" size="sm"`.
  - Replace placeholder `WordMatchView` in RightPanel word-level with `WordDetail`.
- **What to test:** `WordDetail.test.tsx` — 6 accordion items render. `BBoxSection.test.tsx` — edits trigger word PATCH; Reset restores original.
- **Dependencies:** Slices 7, 14, 15.
- **Model:** sonnet.

### Slice 17 — Rebox accordion (accent-tagged) + Erase Pixels (mismatch-tagged)
- **Why:** Two highest-affordance geometry edits; accent tagging proves the Accordion variant visually.
- **What to implement:**
  - `frontend/src/components/right-panel/sections/ReboxSection.tsx` — wraps existing `WordRefineNudgeRows` + `WordActionRows` inside `<Accordion.Item tag="accent">`.
  - `frontend/src/components/right-panel/sections/ErasePixelsSection.tsx` — "Mark pixels for erasure" toggle + "Apply" button wired to `api/refine` erase action (disable with tooltip "Backend not wired" if endpoint absent). `<Accordion.Item tag="mismatch">`.
- **What to test:** ReboxSection: nudge controls still operate. ErasePixels: disabled button when backend absent.
- **Dependencies:** Slice 16.
- **Model:** sonnet.

### Slice 18 — Structure accordion (neighbors + merge/split)
- **Why:** Word boundary restructuring is a core labeling task.
- **What to implement:**
  - `frontend/src/components/right-panel/sections/StructureSection.tsx`:
    - Prev/next-word neighbor preview chips using `WordCell`.
    - "Merge with previous", "Merge with next", "Split at cursor" buttons. Wire to `useLineMutations` / `useWordMutations`.
    - Destructive merges confirm via existing `ConfirmDialog`.
- **What to test:** `StructureSection.test.tsx` — buttons disabled when no neighbor; click Merge calls mutation.
- **Dependencies:** Slice 16.
- **Model:** sonnet.

### Slice 19 — Char Ranges accordion (multi-range)
- **Why:** Partial-word style tagging (italic, drop-cap, subscript, etc.) per the hi-fi.
- **What to implement:**
  - `frontend/src/components/right-panel/sections/CharRangesSection.tsx`:
    - Per-character clickable cells for the word string.
    - "Add range" → sub-row with start/end + tri-state Chip style selectors (italic/bold/sub/super/drop-cap).
    - Existing ranges as compact rows with delete buttons.
    - Persist via word PATCH.
- **What to test:** Click char to select range; chip cycles styles; delete removes range.
- **Dependencies:** Slices 6, 16.
- **Model:** opus.

### Slice 20 — Character Fixer accordion + Unicode picker
- **Why:** Final right-panel section; Unicode picker is its own widget.
- **What to implement:**
  - `frontend/src/components/right-panel/sections/CharFixerSection.tsx` — per-character grid (original char + editable input); OCR/GT mismatches get `--status-mismatch` left edge. "Open Unicode picker" button.
  - New `frontend/src/components/right-panel/UnicodePicker.tsx` — searchable list of common glyphs grouped in Accordion sub-sections (em-dash, curly quotes, fractions, ligatures, etc.). Click inserts at last-focused input.
  - Save via word PATCH. Demote `WordEditDialog` to Esc-fallback for now (keep mountable).
- **What to test:** Cell edit triggers debounced save; Unicode picker insert works; mismatch highlight.
- **Dependencies:** Slices 7, 16, 19.
- **Model:** opus.

---

## Phase 5 — Bulk views (Line, Block)

### Slice 21 — Line-level Right Panel: Line / Words tabs
- **Why:** Line selection should show Line tab + Words tab (dense word grid).
- **What to implement:**
  - New `frontend/src/components/right-panel/LineDetail.tsx` — `<Tabs>` with "Line" and "Words".
  - "Line" tab: `LineCard` content + merge-with-line affordance (`useLineMutations`).
  - "Words" tab: word list using `WordMatchView` styling. Density toggle (Cards|Rows) via `useUIPrefs` key `lineWordsDensity`.
  - RightPanel router: `level === "line"` mounts `LineDetail`.
- **What to test:** `LineDetail.test.tsx` — tab switch; density toggle persists.
- **Dependencies:** Slices 6, 14, 15.
- **Model:** sonnet.

### Slice 22 — Block-level Right Panel: Layout / Items tabs
- **Why:** Block selection: layout-type picker + structural child list.
- **What to implement:**
  - New `frontend/src/components/right-panel/BlockDetail.tsx` — `<Tabs>` with "Layout" and "Items".
  - "Layout" tab: layout-type picker (Body/Heading/Caption/Footnote/Quote/Other radio chips) + "Model suggested: X (confidence Y%)" callout with "Accept" button. Wire PATCH to `lines_paragraphs` route.
  - "Items" tab: tree of paras + lines, density toggle; click sets selection.
  - `level === "block"` mounts `BlockDetail`; `level === "para"` mounts thin para view reusing Items rendering.
- **What to test:** `BlockDetail.test.tsx` — layout chip triggers save; Accept applies suggested type; Items click navigates selection.
- **Dependencies:** Slices 6, 21.
- **Model:** sonnet.

### Slice 23 — Bulk actions bar (multi-select from Worklist)
- **Why:** Filter chips drive bulk operations per hi-fi.
- **What to implement:**
  - New `frontend/src/components/drawer/BulkActions.tsx` — appears at bottom of Worklist when selection > 0. Shows count + "Mark all reviewed", "Re-run match", "Export filtered" buttons. Fires jobs via `jobs` route; progress via `useJobProgress`.
  - Add `selectAll`, `clear`, `toggle(id)` to `worklist-store.ts`.
- **What to test:** `BulkActions.test.tsx` — disabled at 0 selection; click triggers job mutation with selected ids.
- **Dependencies:** Slice 11.
- **Model:** sonnet.

---

## Phase 6 — Polish

### Slice 24 — Theme toggle in user menu (dark ↔ light ↔ system)
- **Why:** Tokens exist (Slice 1); now expose the switch.
- **What to implement:**
  - User menu (Slice 9): Theme row with 3-state selector (Dark | Light | System).
  - `frontend/src/stores/ui-prefs.ts` — add `theme: "dark"|"light"|"system"`. On change: `document.documentElement.dataset.theme = effectiveTheme`. Subscribe to `prefers-color-scheme` media query for System mode.
- **What to test:** `ui-prefs.test.ts` — theme updates documentElement; system mode reflects media query; persists.
- **Dependencies:** Slices 1, 9.
- **Model:** sonnet.

### Slice 25 — Hotkey overlay refresh (KeyCap-powered + hotkey registry)
- **Why:** Existing `HotkeyHelpModal` is functional but doesn't use `KeyCap`; needs grouped sections.
- **What to implement:**
  - New `frontend/src/lib/hotkey-registry.ts` — each `useXHotkeys` hook registers its hotkeys here; modal reads from it.
  - Evolve `frontend/src/components/HotkeyHelpModal.tsx`: replace inline text with `<KeyCap>` components. Groups: Selection (1/2/3, V/R/A/E), Navigation (←/→ pages, `⌥` arrows breadcrumb), Editing (Enter/Esc), View (theme toggle, drawer collapse).
- **What to test:** `HotkeyHelpModal.test.tsx` — every registered hotkey appears; KeyCap renders.
- **Dependencies:** Slices 5, 14, 15.
- **Model:** sonnet.

### Slice 26 — Toast/banner styling (Sonner + token colors)
- **Why:** Hi-fi shows a fixed bottom-right toast stack with status-colored left edges. Sonner is already installed — this slice just wires it to our token system and migrates callers.
- **What to implement:**
  - `frontend/src/lib/toast.ts` — thin wrapper around `sonner`'s `toast()` with typed helpers: `toast.info(msg)`, `toast.success(msg)`, `toast.warn(msg)`, `toast.error(msg)`. Maps each level to the matching Sonner style option using our token colors (info=`--status-ocr`, success=`--status-exact`, warn=`--status-fuzzy`, error=`--status-mismatch`) via `style: {borderLeft: "3px solid var(--status-…)"}`.
  - In `App.tsx`, ensure `<Toaster position="bottom-right" />` from Sonner is mounted. Set the Sonner theme via `data-theme` to match our `[data-theme="light"]` toggle.
  - Migrate transient `InlineBanners` calls to `toast.*()`. `InlineBanners` stays for sticky page-level banners.
- **What to test:** `toast.test.ts` — each helper calls `sonner.toast` with correct style options. Snapshot existing `InlineBanners.test.tsx` to confirm sticky banners unaffected.
- **Dependencies:** Slice 5.
- **Model:** haiku.

### Slice 27 — RootPage refresh
- **Why:** Project picker needs the same token/chrome treatment as ProjectPage.
- **What to implement:**
  - Evolve `frontend/src/pages/RootPage.tsx`:
    - `HeaderBar` (no Rail/Drawer/RightPanel — single pane).
    - Project cards with aggregate StatusPip (e.g., "82% reviewed").
    - "Open source folder" uses `Button variant="primary"`; `SourceFolderDialog` via dialog-store.
- **What to test:** Extend `RootPage.test.tsx` — header renders; project cards show StatusPips; open-folder flow unchanged.
- **Dependencies:** Slices 4, 5, 9.
- **Model:** haiku.

---

## Dependency graph

```
0 → 1 → 2 → 3 ─┐
               ├─ 4 ─────────────────── 8 ─┬─ 9 ─┬─ 24
               │                           │     └─ 27
               ├─ 5 ─┬─ 6 ─── 7           ├─ 10 ─ 13
               │     │                     ├─ 11 ─ 12, 23
               │     └────────────────────→└─ 14 ← 15 ─┬─ 16 ─┬─ 17
               │                                        │      ├─ 18
               │                                        │      ├─ 19 ─ 20
               │                                        │      └─ (→25)
               │                                        └─ 21 ─ 22
               └──────────────────────────────────────────────── 26
```

Slice 0 installs deps; everything else depends on it.
Phase 1 slices 4/5/6/7 can run in parallel once 1→2→3 is done.
Phase 2 is sequential (each slice installs into StudioShell).
Do Slice 15 before Slice 14.

---

## Existing → new component mapping

| Existing component | Becomes / lands in |
|---|---|
| `HeaderBar` | Evolves: Slice 9 (40px chrome + user menu) |
| `ProjectNavigationControls` | Nested into HeaderBar center cluster (Slice 9) |
| `ImageTabsHeader` | Stays as-is under HeaderBar in canvas slot |
| `Splitter` | Removed from ProjectPage shell; available inside panels if needed |
| `FilterToggle` | Predicate extracted to `filter-predicates.ts`; UI absorbed into Worklist (Slice 11) |
| `WordMatchView` | Used in Words tab (Slice 21) and fallback in WordDetail (Slice 16) |
| `WordEditDialog` | Demoted to Esc-fallback; primary edit path is CharFixerSection (Slice 20) |
| `WordRefineNudgeRows` + `WordActionRows` | Body of ReboxSection (Slice 17) |
| `LineCard` | Body of Line tab (Slice 21) |
| `PlaintextEditor` | Stays in Line tab as sub-mode |
| `BBoxOverlay` / `PageImageCanvas` | Layer-color tokens + target-scoped marquee (Slice 13) |
| `HotkeyHelpModal` | Refreshed with KeyCap + grouped sections (Slice 25) |
| `InlineBanners` | Sticky banners stay; transient toasts move to ToastStack (Slice 26) |
| `useUIPrefs` | Extended: `drawerOpen`, `drawerTab`, `lineWordsDensity`, `theme` |
| `selection-store` | Extended: hierarchical level + path (Slice 15) |
| `dialog-store`, `viewport-store` | Unchanged |
| Backend routes | Unchanged; new mutations via `useWordMutations` (Slice 16) + existing hooks |

---

## Notes for subagents

- Phase 1 slices 1→2→3 must be sequential; 4/5/6/7 can be parallel.
- Phase 2 must be sequential (each slice plants something into StudioShell).
- Slice 15 before Slice 14.
- All new components under `frontend/src/components/{ui,shell,drawer,right-panel}/` — keeps legacy `components/` recognizable as old surface.
- Every slice must add or update tests. `make ci` must stay green after every slice.
- Follow repo conventions: ESM, `import type` separation, no default exports for components, props interfaces as `<Component>Props`.

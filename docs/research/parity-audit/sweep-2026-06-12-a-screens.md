# Parity sweep 2026-06-12 — Dimension A (screens / nav / chrome / global hotkeys)

Live-verified browser audit at commit `d0ba846` (includes SEL-3 rail↔radio fix).
Server: standalone uvicorn seeded via `_ingest_ocr_result` event-store pattern
(exercise-fixture, 8 pages, real line_matches). Fresh `make frontend-build`
confirmed (`/healthz` → `0.2.1.dev63+gd0ba846d6`).

Verdict key: PASS = visible + enabled + real effect observed.
PARTIAL = reachable but degraded/incomplete. FAIL = no working reachable path.
N-A = not applicable (capability retired/moved by design with CT sign-off).

| # | Capability | Verdict | Evidence |
|---|---|---|---|
| A-01 | Session restore (GET `/` → last project/page) | PASS | Fresh browser → `/` redirected to `/projects/exercise-fixture/pages/pageno/1` (POST load + navigate). |
| A-02 | Reach project list from a project page ("Projects" header link) | FAIL | Clicked "Projects" link → landed on `/` → session-redirect immediately bounced back to the project page. `HeaderBar.tsx:146` `Link to="/"` passes no `skipSessionRedirect`; `RootPage.tsx:501` redirects whenever a session exists. **Project list is unreachable via UI while a session exists** (only the 404 path or a failed load shows it) — so switching projects via the card grid is impossible in normal use. Legacy header dropdown was always reachable (`project_load_controls.py:91`). |
| A-03 | Unknown project route → toast + redirect to root | PASS | `/projects/does-not-exist/pages/pageno/1` → redirected to `/` (~5–10 s, query retries) with 1 sonner toast; grid rendered (skipSessionRedirect honored). |
| A-04 | RootPage project grid + project cards | PASS | `root-projects-grid` + `project-card-exercise-fixture` visible. |
| A-05 | Hero band | PASS | `root-hero-band` visible. |
| A-06 | Project search filters grid + empty-search state | PASS | "zzz-no-match" → `root-empty-search` shown; "exercise" restores card. |
| A-07 | Project filter chips (all/active/complete/archived) | PARTIAL | Chips render and toggle, but `RootPage.tsx:316-319` comment: non-"all" status filters **show all projects** (no API status field) — chips are cosmetic no-ops. |
| A-08 | Project card action menu (Delete / Archive entries) | PASS | Menu opens; `project-card-delete/archive-exercise-fixture` visible+enabled (effects = dim C). |
| A-09 | OCR config from root / no-project context (#405) | PASS | `ocr-config-trigger-button` visible on root; click opens the modal. S6 fix confirmed live — #405 can close. |
| A-10 | Source-folder dialog (open, browse, Use Current, Cancel) | PASS | "Open source folder" button on grid opens dialog; all 8 `source-folder-*` controls visible; Up changed path `/tmp/.../source` → `/tmp/...`; Use Current copied current path into input; Cancel closed. Note: trigger button itself has **no testid**. |
| A-11 | Legacy project select dropdown + LOAD button | PASS (re-mapped) | Capability (pick project + load) lives in the card grid (`project-card-open-*`, verified A-13). The legacy surface `ProjectLoadControls.tsx` is **dead code — never imported/mounted**, yet driver-contract §2.1 (13-driver-contract.md:89-97) still lists `project-select` / `load-project-button` / `source-folder-button` as "real". Contract-doc gap. |
| A-12 | Theme chips Dark/Light/System | PASS | Clicking Light/Dark flips `document.documentElement.dataset.theme` `light` ↔ `dark`. |
| A-13 | Project card Open → project page | PASS | Click `project-card-open-exercise-fixture` → navigated to `/projects/exercise-fixture/pages/pageno/1`, loading overlay cleared. |
| A-14 | Resolved project path label in header (S6.2) | PASS | `project-root-label` visible on project route, text `/tmp/.../source/exercise-fixture`. (Renders only after projectQ settles — briefly absent right after navigation.) |

### Cross-cutting findings (batch 1)

- **NEW — duplicate testids: hidden HeaderBar driver stubs shadow real dialog controls.** `HeaderBar.tsx` hidden-stub block renders `source-folder-up-button` etc. with `data-testid-stub="true"`; when the real SourceFolderDialog is open, page-level `[data-testid=…]` matches 2 elements and `.first` resolves to the invisible stub (Playwright click times out). Driver must scope queries inside `source-folder-dialog`. Contract should either drop the stubs or document the scoping requirement.
- **NEW — console error spam on project page:** `Konva has no node with the type div. Group will be used instead.` repeated ≥5× on every project-page load — a DOM `<div>` is being rendered inside a react-konva tree somewhere. Not user-visible but indicates a real rendering bug.

## Batch 2 — project page shell, navigation, URL shapes, nav hotkeys

| # | Capability | Verdict | Evidence |
|---|---|---|---|
| A-15 | ProjectPage shell (workspace / canvas / worklist / detail columns, image-pane) | PASS | All six layout testids visible. |
| A-16 | Page "N / M" indicator (legacy nav bar + project-top-toolbar) | PASS (re-mapped) | `project-top-toolbar` / `project-toolbar-page` no longer exist in ProjectPage (inventory `new-a-screens.md` is stale). Indicator = header `nav-page-input` (shows current page) + `nav-page-total-label` ("/ 8"), both visible and live. |
| A-17 | Prev / Next page buttons | PASS | `nav-next-button` → pageno/2, `nav-prev-button` → pageno/1; prev correctly disabled on page 1. |
| A-18 | Go To page (input + button) | PARTIAL | Enter in `nav-page-input` navigates (1→5 verified). **NEW BUG: the visible Go button (S6.1) is a guaranteed no-op** — `ProjectNavigationControls.tsx:122-124` `onBlur={() => setGotoValue("")}` clears the typed value when the click blurs the input, so `onGoTo` (line 71-76) falls back to `currentPageNo`. Verified live: typed 3, clicked Go, stayed on page 1, input reset. Mouse-only Go-To is still broken (it was the very gap S6.1 set out to fix). |
| A-19 | Out-of-range page number rejected | PASS | Enter on "99" (total 8): no navigation, input restored — matches legacy silent-reject. |
| A-20 | Mod+ArrowLeft / Mod+ArrowRight page nav | PASS | From settled p4: Ctrl+ArrowLeft → 3, Ctrl+ArrowRight → 4. (Hotkey is ignored if pressed during the immediately-post-nav busy window — transient, by design via `enabled`.) |
| A-21 | Mod+Home / Mod+End first/last page | PASS | Ctrl+End → pageno/8, Ctrl+Home → pageno/1. |
| A-22 | URL shapes: `/pages/index/{idx0}` redirect + bare `/projects/:id` | PASS | `index/2` → `pageno/3`; bare project → `pageno/1`. |
| A-23 | Catch-all unknown route → `/` | PASS | `/garbage/route/xyz` → root → session-restore landed back on the project page (handled, no crash). |
| A-24 | Deep-link straight to `pageno/3` | PASS | Page 3 rendered; nav input shows 3. |
| A-25 | Header metrics strip (word/match/validated counts) | PASS | "33 words·32 exact·1 fuzzy·0 ✗·…" visible, page-specific. |
| A-26 | Header project-name breadcrumb chip | PASS | `header-project-name` = "exercise-fixture". |
| A-27 | Total-pages label | PASS | `nav-page-total-label` = "/ 8". |


## Batch 3 — Rail, SEL-3, layers, drawer, right panel, QuickSearch, hotkey help

| # | Capability | Verdict | Evidence |
|---|---|---|---|
| A-28 | Rail structure (4 mode cards, 4 target swatches, 4 layer toggles, Bulk + Hotkeys footer) | PASS | All of `rail-mode-{view,region,annotate,erase}`, `rail-target-{block,para,line,word}`, `rail-layer-{block,para,line,word}`, `rail-bulk-button`, `rail-hotkeys-button` visible. |
| A-29 | Rail target click sets active granularity | PASS | Click `rail-target-line`/`-word` → `data-active="true"` moves accordingly (AG-4 syncs `selectionMode`). |
| A-30 | SEL-3 Shift+1/2/3 selection-mode hotkeys sync rail | PASS | Shift+1 → para active, Shift+2 → line, Shift+3 → word (radio→rail direction of d0ba846 confirmed live). |
| A-31 | Rail digit hotkeys 1/2/3/4 (target) | PASS | `1` → block active, `3` → line active. |
| A-32 | Rail mode hotkeys V/R/A + mode click | PASS | `r`→region, `v`→view, `a`→annotate active; clicking the View card also works. |
| A-33 | Layer toggle click hides/shows overlay layer | PASS | `rail-layer-block` `aria-pressed` true→false on click, restored on second click. |
| A-34 | Shift+P/L/W layer visibility hotkeys | PASS | Shift+P flipped `rail-layer-para` aria-pressed. |
| A-35 | Rail "Bulk" footer button opens drawer worklist | PASS | Worklist visible after click (also reopens a collapsed drawer — see A-36). |
| A-36 | Drawer tabs + collapse/expand | PARTIAL | Worklist/Hierarchy/Text tabs all switch correctly. **NEW BUG: collapsed drawer is 1px wide and `drawer-expand-btn` has width 0 — invisible and mouse-unclickable** (`Drawer.tsx:187-199` renders it, but the collapsed container gets no width; `project-worklist-column` keeps 32px but the drawer div doesn't fill it). Workaround exists: Rail "Bulk" button reopens. |
| A-37 | Worklist row click → right-panel line detail | PASS | Click `worklist-row-1` → `line-detail` visible. (Rows are indexed by `line_index`, may not start at 0.) |
| A-38 | Right-panel header breadcrumb chips | PASS | `breadcrumb`, `breadcrumb-chip-root` present in `right-panel-header`. |
| A-38b | Right-panel collapse / re-expand | PARTIAL | `right-panel-collapse` hides the body and the detail column collapses to width 0 with **no expand control**. Re-expand only happens implicitly via a new selection (worklist row or canvas click — STB-4 `Worklist.tsx:428`, `PageImageCanvas.tsx:589`). No-selection-change path back is keyboard/selection only. |
| A-39 | QuickSearch: Mod+K focus + worklist filter (S6.4) | PASS | Ctrl+K focuses `quick-search-input`; typing junk filtered visible worklist rows 6 → 0; clearing restores. |
| A-40 | Hotkey help (`?` opens, Escape closes, Rail button opens) | PASS | All three paths verified; dialog titled "Keyboard Shortcuts". |
| A-41 | Legacy selection-mode radios (`selection-mode-paragraph/line/word`) | PASS (re-mapped) | Capability = Shift+1/2/3 + rail targets (A-30/A-29). DOM counts are **0** — ImageTabsHeader is dead code since IS-4, but `13-driver-contract.md:171-173` still lists the testids. **Contract-doc gap; explains the pre-existing red in `test_paragraph_mode_selection_opens_paragraph_detail`.** |
| A-42 | Legacy TextTabs (Matches / Ground Truth / OCR right pane) | PASS (re-mapped) | GT/OCR full-page text → drawer **Text** tab (S2.2 `PlaintextGtOcrView`, shows real page text); Matches list → drawer Worklist. Old `text-pane`/`text-tabs` stubs remain hidden (count 1, visible False); `matches-tab`/`ground-truth-tab`/`ocr-tab` testids no longer exist. |
| A-43 | ToolbarActionGrid visible above canvas | PASS | `toolbar-action-grid` count 1, visible (v0.2.0 claim re-confirmed at d0ba846). |
| A-44 | Theme persistence across reload | PASS | Light selected → reload → `data-theme="light"` retained (localStorage). |
| A-45 | Erase-mode hotkey `e` | PARTIAL | `e` activates rail erase mode, **but ALSO opens the Export dialog**: hidden `PageActions` (IS-2 stub mount) still registers `useHotkey("e", onExport)` (`PageActions.tsx:132`) alongside `useRailHotkeys` MODE_KEYS `e→erase`. Verified live: one keypress → erase active AND "Export Training Data" dialog open. **NEW BUG (hotkey collision).** Shift+E erase-canvas toggle is separate (viewport hotkeys) and untested here (dim B). |

## Batch 4 — modals, page-action chrome, remaining global hotkeys

| # | Capability | Verdict | Evidence |
|---|---|---|---|
| A-46 | PageActionsCompact header actions (Reload OCR / Rematch / Save / Export / OCR-config / overflow / Bulk glyphs) | PASS | All 8 testids visible+enabled in header on project route. |
| A-47 | Overflow menu (Reload OCR Edited / Save Project / Load Page) | PASS | All three entries visible after opening `page-actions-compact-overflow`. Minor: the menu does **not** close on Escape (outside-click only). |
| A-48 | OCR Configuration modal interaction | FAIL (regression) | Modal opens (trigger on both root and project routes) **but the entire modal content is mouse-dead**: local `.dialog-overlay` (`frontend/src/styles/primitives.css:552`, `z-index:49`) is a *sibling* rendered before the content, and the content (`pdomain-ui` `.dialog` class) has `z-index:auto` → overlay paints on top; `elementFromPoint` over Cancel returns the overlay; Playwright clicks time out. Keyboard path works (focus lands inside, Tab cycles controls, Escape closes). Dialogs that pass their own `fixed … z-50` className (SourceFolderDialog, HotkeyHelpModal, ConfirmDialog) are unaffected. Likely regressed with the pdomain-ui Dialog markup (overlay-as-sibling) in the 0.7.x bump. |
| A-49 | Export dialog (open via button + Mod+E; close via Escape) | PARTIAL | Opens both ways; Escape closes. **Content is mouse-dead — same overlay z-bug as A-48** (`export-button` blocked by `.dialog-overlay`). Export execution impact belongs to dim C — flagged. |
| A-50 | Mod+S save page hotkey | PASS | Fires immediately; toast feedback "Project exercise-fixture: nothing to save." (pristine page; text comes from `save_project.py:126` — wording oddity for a page-save, noted for dim C). |
| A-51 | Mod+Shift+S save project hotkey | PASS | Toast "Project exercise-fixture: nothing to save." |
| A-52 | Mod+L load page → confirm dialog | PASS | "Load page?" AlertDialog opens; `confirm-dialog-cancel` clickable (ConfirmDialog carries its own `z-50`); closes. Note: ConfirmDialog is `role="alertdialog"`, not `role="dialog"` — drivers beware. |
| A-53 | Mod+G rematch GT → confirm dialog | PASS | "Rematch GT?" AlertDialog opens; Confirm button clickable and fires the mutation (toast feedback arrives). |
| A-54 | Advertised hotkeys Mod+, (OCR config), Mod+O (source folder), Mod+J (jump to page) | FAIL | All three listed in `hotkeyMap.ts:28-37` and shown in the help modal, but **none is bound** — no `useHotkey` registration exists; pressing them does nothing. Mod+, is BUG-KBD-1 (M9.5, still open); Mod+O / Mod+J are additional advertised-but-dead entries. |
| A-55 | Word editing surface reachable (legacy WordEditDialog) | PASS (re-mapped) | WordEditDialog was deleted in `c5ddd35` ("replace WordEditDialog with WordDetail sections"). Canvas click on a word bbox (rail target=word) opens the WordDetail right panel (verified live). **Contract-doc gap: `13-driver-contract.md:265-283` still lists `word-edit-dialog` + ~20 `dialog-*` testids that no longer exist anywhere**; `edit-word-button-{l}-{w}` also returned 0 in the DOM. |
| A-56 | `/__perf-test` dev route | PASS | Loads; 6 canvas elements rendered. |

## Batch 5 — confirm effect, announcers, breadcrumb hotkeys

| # | Capability | Verdict | Evidence |
|---|---|---|---|
| A-57 | ConfirmDialog Confirm button fires the guarded mutation | PASS | Mod+G → Confirm click → mutation runs, toast feedback arrives. (Toast text was "nothing to save" — rematch feedback wording for dim C to review.) |
| A-58 | sr-only status/error announcers | PASS | `[role=status][aria-live=polite]` and `[role=alert][aria-live=assertive]` both present. |
| A-59 | Alt+Arrow breadcrumb hierarchy walk | PARTIAL | Alt+ArrowDown line→word and Alt+ArrowUp word→line verified live. Walking above line (para/block) left the right panel with no detail component visible (empty-state), and Alt+ArrowRight from there showed none — upper-level walk needs a closer look (possibly fixture-shape dependent). |
| A-60 | Busy overlay during long mutations | NOT-TESTED | Reload-OCR (cold CPU OCR) deliberately not exercised in this sweep; `project-loading-overlay` behavior verified throughout. Dim C owns job-progress UX. |

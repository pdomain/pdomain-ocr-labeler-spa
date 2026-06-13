# Legacy → New Parity Gap Matrix (master synthesis)

**Legacy:** `pd-ocr-labeler` (NiceGUI) · **New:** `pdomain-ocr-labeler-spa` (FastAPI + React/Vite/TS)
**Verified:** 2026-06-12, live Playwright against seeded event-store fixtures at commit `d0ba846`.
**Re-verified:** 2026-06-13 at commit `94451f5`, after the post-sweep fix batch
(P1.x data-loss fixes, P2 rotate arc, P4 reachability fixes, undo/redo arc) — see §1a.
**Supersedes** the 2026-06-06 matrix in this file. That matrix was code-read synthesis;
every verdict below was re-established by driving a real browser. Where the two disagree,
this one wins.

**Method.** Three parallel sweeps, one per dimension:

- [Dim A — screens / nav / chrome / hotkeys](sweep-2026-06-12-a-screens.md) (60 rows)
- [Dim B — OCR content actions](sweep-2026-06-12-b-content.md) (90 rows)
- [Dim C — document / project / system](sweep-2026-06-12-c-system.md) (57 rows)

Acceptance bar per row: **visible + enabled + real effect**, durable where applicable,
checked by API re-fetch or files on disk. A `data-testid` existing is not parity.
Servers were standalone uvicorn instances seeded via the `_ingest_ocr_result`
event-store pattern from `tests/e2e/`.

---

## 1. Executive summary

| Dimension | Rows | PASS | PARTIAL | FAIL | N-A / untested |
|---|---:|---:|---:|---:|---:|
| A — screens / nav / chrome | 60 | 47 | 7 | 5 | 1 |
| B — OCR content actions | 90 | 64 | 8 | 12 | 3 |
| C — document / project / system | 57 | 36 | 6 + 1 mixed | 13 | 1 |
| **Total** | **207** | **147** | **~22** | **30** | **5** |

**True parity: ~73%** strict (147 PASS of 202 scoreable rows). Counting PARTIALs at
half credit: ~78%. The 2026-06-06 estimate of "~80% capability reachability" was
roughly right in aggregate but wrong in composition — several things it called
broken have since shipped (WordEditDialog superseded by WordDetail, ToolbarActionGrid
visible, rotate pixels real), and several things it called working are broken in ways
only a live browser exposes (export lane, validation persistence, dead deletes).

**The one-paragraph story.** The backend capability layer is largely real and durable:
content mutations auto-persist through the event store and survive server restart,
OCR / refine / rematch / rotate-pixels / export-mechanism / suite plumbing all execute.
The failures cluster in three shapes: **(1) wiring stubs** — visible controls whose
callback chain was never connected (LineDetail word cells, project delete/archive,
suite launcher shims) or that post to backend routes that are documented stubs
(word/line `/delete`); **(2) dead or wrong routes** — export reads a retired
persistence lane, export-cancel posts a URL that 405s, deep links to unloaded projects
bounce; and **(3) a few systemic bugs** — the pdomain-ui 0.7.x dialog overlay z-bug
that makes two modals mouse-dead, a parallel-mutation race that silently loses
updates, and validation state that never reaches disk. None of these are visible from
unit tests or testid checks; all were caught by the visible+enabled+effect bar.

---

## 1a. Post-fix re-verification (2026-06-13, commit `94451f5`)

Between the 2026-06-12 synthesis (`d0ba846`) and `94451f5`, a fix batch landed for
most P1/P2/P4 slices plus the event-store undo/redo arc. Every claim below was
re-verified **live** (fresh `make frontend-build`, standalone seeded uvicorn on a
non-default port, scripted headless Playwright, effects checked by API re-fetch,
server restart, or files on disk). Items marked *code-confirmed* were checked by
grep only because no fix commit touched them.

### Fixed and verified live

| Item | Fix commit(s) | Live evidence (2026-06-13) |
|---|---|---|
| F1 validation persistence | `56e4a7b` | validate word → Save → **real server restart** → `is_validated` still true. |
| F2 export exports 0 pages | `142ed30` | UI export (all-validated) → crops on disk + `manifest.json` `page_count: 1`, det/rec `item_count: 7` — store-first read works. ⚠ new minor bug below. |
| F3 export style filter | `142ed30` | `GET /export/styles` → `["bold","regular","underline"]`; scope=all renders `export-style-checkbox-*` per style. |
| F4 export cancel 405 | `bbce201` | `export-cancel-button` testid exists; code posts canonical `/api/jobs/{id}/cancel` (ExportDialog.tsx:228). Not catchable live — tiny-fixture job finishes in <1 s. |
| F5 dead word/line deletes | `8531bf5` | WordFooter delete: word count 7→6 via `words/delete-batch`. LineDetail card delete: line removed (note: **no confirm dialog** on this surface, unlike WordFooter/bulk). Bulk delete: see §1a-partial. |
| F6 style removal | `f576a5a` | All 3 surfaces remove the label (API re-fetch): toolbar `clear-style-button` (`italics`→`regular`), WordDetail chip off-toggle, `word-tag-clear-button-*` × (bold removed). |
| F7 LineDetail word grid | `db5b172` | Grid `word-validate-button-{l}-{w}` False→True (validate-batch route); `gt-text-input-{l}-{w}` Enter persisted `"BETA-GRID"`. |
| F8 toolbar resolver nulls | `42ddf7d` | Word selection + `toolbar-line-split-after` → `lines/0/split-after-word` 200, line count 3→4 (no more silent null). |
| F10 rotate surface | `e30460a`, `b17bbe5`, `df7ae6b` | All four rotate buttons **visible** in the overflow menu; CW rotate: on-disk PNG 1200×1600→1600×1200 (durable), payload `page_record.rotation_degrees=90/manual`, `rotation-badge` renders; re-OCR re-runs in new pixel space (sideways text → 0 words; rotating back re-found "Rotate Test"). ⚠ round-trip metadata bug below. |
| F11 auto-rotate-all | `e30460a` + detection fix | `auto-rotate-all-button` visible; `auto_rotate_all` job **completes** (no per-page detection crash). |
| F12 project switching | `db712e9` | From a loaded project, `projects-home-link` renders the grid (no session-redirect bounce). |
| F13 project delete stub | `df9f941` | Card menu Delete → confirm → `/api/projects` returns `projects: []`; Archive item dropped. |
| F14 deep-link bounce | `743a5ba` | Fresh server, project **not** loaded, page deep-link → auto-loads and renders `pageno/1`. |
| P6 LocalTrustMiddleware 403 | `2b90422` | Browser-origin `POST /api/projects/source-root` on port 8431 → **200**. |
| P7 Load-Page semantics | `3074798`…`94451f5` | Button is now "Reload" + ConfirmDialog; undo/redo: GT edit → `undo-button` reverts (API) → `redo-button` re-applies, via `/pages/0/undo|redo`. |
| F21 erase-to-marker | `00447c8` | RETIRED by CT decision (already reflected in §3/§7). |

### Still failing (re-verified live at `94451f5`)

| Item | Evidence |
|---|---|
| F9 line ctrl-click not additive | Line target: click line A, ctrl-click line B → `line-detail` (replace), `multi-line-detail` never opens. |
| F18 OCR-config modal mouse-dead | Modal opens; `ocr-rescan-models-button` click times out (overlay intercepts). §5.1 unchanged (still present with pdomain-ui 0.7.2). |
| P5 export dialog mouse-dead | Scope radio click times out; whole batch driven via JS clicks. |
| F19 Go button no-op | Typed "2" + clicked `nav-goto-button` → URL stayed `pageno/1` (Enter still works). |
| §5.2 parallel-mutation race | Two fresh observations: (1) MultiWordDetail bulk style/component apply on 2 words — one word's POST **404s** (page-version conflict in the new history chain; second concurrent mutation targets a stale version) → only one word updated, no UI error; (2) MultiLineDetail bulk delete on 2 lines → only 1 deleted (`handleBulkDelete` still loops `mutate()` per line — now also index-shift hazardous since deletes renumber lines). |
| P8 export history | `GET /api/projects/{id}/exports` still returns `[]` while manifests exist on disk. |
| §5.4 Konva div errors | 14 `Konva has no node with the type div` console errors on one project-page load. |

### Still failing (code-confirmed unchanged, not re-driven)

F15 jobs panel (no `JobsPanel`/`jobs-panel` in frontend), F16 suite launcher
(GAP-3 shims still in App.tsx:476-484), F17 compute/settings trigger
(`settingsPanels` passed but no visible dock trigger renders), F20 unbound
hotkeys (`mod+,`/`mod+o`/`mod+j` still have no `useHotkey` registration; the
undo arc added `mod+z`/`mod+shift+z`), F22 rebox-on-main-canvas (nothing sets
viewport mode `"rebox"`), F23 glyph panel (blocked, M11/Q-A7), F24 testid rot.
PARTIALs P3, P4, P10, P12–P18 were not re-checked (no fix commits touched them).

### New defects found during re-verification

1. **Export run-history row shows "0 pages"** while the export actually wrote
   crops and `manifest.json` says `page_count: 1` — `pagesExported` is read from
   `progress.progress?.total ?? 0` at completion (ExportDialog.tsx:155). Display
   bug only, but it re-creates the old "looks broken / looks like 0 pages"
   confusion that F2 was about.
2. **Rotate round-trip metadata drift**: CW (90) then CCW leaves
   `page_record.rotation_degrees=270` instead of 0; the header badge shows
   "↻ 270° manual" on a page whose pixels and OCR are back to the original
   orientation. Pixels/OCR are correct; only the accounting is wrong.
3. **MultiWordDetail bulk apply can 404 server-side** (see §5.2 above): the
   race is no longer purely a lost client update — with the version-chain
   history (H-A), the second concurrent mutation can be rejected with 404 and
   the UI swallows it. Same fix shape as P3.2 (serialize or batch).
4. **LineDetail card delete has no confirm dialog** — WordFooter delete and
   bulk delete confirm; the single-line delete fires immediately. Inconsistent
   destruction guard, worth folding into P1.3 follow-up.

### Updated standing (scoreable rows, after fix batch)

Of the 30 FAILs in §3: **13 fixed-and-verified, 1 retired (F21), 10 still
failing, F23 still blocked** (F5 counts as fixed with its bulk surface demoted
to the §5.2 race; F24 is doc debt). Strict true parity moves from ~73% to
**~81%**, with the remaining mass concentrated in: the dialog overlay z-bug
(§5.1), the mutation-loop race (§5.2), reachability chrome (jobs panel, suite
launcher, settings dock), and small polish items (Go button, line ctrl-click,
unbound hotkeys).

---

## 2. Critical-path broken pipelines

> **2026-06-13 status:** both pipelines below are **repaired and live-verified**
> at `94451f5` (see §1a): validate→save→export now produces real crops + manifest
> after a restart-durable validate, and rotate→re-OCR works end-to-end with a
> visible surface. Kept verbatim as the record of what was broken at `d0ba846`.

### 2a. validate → save → export (training-data pipeline) — broken at three independent points

This is the app's reason to exist, and it cannot produce output today:

1. **Validation is never persisted** (C55). Validation lives in the in-memory
   `PageState.validated_words` map, documented "lossy" (`api/words.py:21-24`).
   Save serializes the Page payload, which never receives the flags. Verified
   three times: validate-all + explicit Save → restart → count reverts to the
   fixture seed. Silent data loss of the export gate itself.
2. **Export reads a retired lane** (C35/C36/C37). The export handler scans
   `<data_root>/labeled-projects/` (`handlers/export.py:509-517`), but Save
   writes only the event store; `persist_page_to_file` raises
   `NotImplementedError`. Every export exports **0 pages and reports success**.
   Positive control: hand-planting a legacy envelope in the dead lane exports
   correctly — the pipeline is sound, the lanes are disconnected. The style
   filter (C37) scans the same dead lane, so it always renders empty.
3. **Export cancel posts a dead URL** (C40). The cancel button POSTs
   `/api/projects/{id}/jobs/{id}/cancel` → **405**, then resets local UI state
   while the job keeps running. The canonical `POST /api/jobs/{id}/cancel`
   works. The button also has no testid (`export-cancel-button` never existed).

### 2b. rotate → re-OCR (M9.1/M9.2 follow-through) — pixels rotate, everything downstream doesn't

1. **Buttons are invisible** (C28). `rotate-cw/ccw/180-button` exist only inside
   the `display:none` PageActions wrapper (ProjectPage.tsx:797-800). No visible
   surface renders them.
2. **Pixel rotation itself works and is durable** — on-disk PNG rotated, served
   image follows. But **rotation metadata never surfaces**: the store records
   `rotation_degrees=90, rotation_source="manual"`, while the API payload keeps
   `rotation_degrees=0`, so the rotation badge can never render.
3. **Re-OCR after rotate has no effect** — words/bboxes stay byte-identical to
   pre-rotate portrait coords; overlays are misaligned with the rotated pixels.
4. **Auto-rotate-all** (C29) has **no UI trigger at all**, and the backend
   detection path crashes per page ("all pages are expected to be multi-channel
   2D images") on a plain RGB PNG — result is always `rotated=[]`.

---

## 3. Consolidated FAIL table

One row per distinct failure. Cross-dimension duplicates merged (refs kept).
Refs point into the three sweep docs.

> **2026-06-13:** F1–F8, F10–F14 fixed and live-verified; F21 retired — see §1a.
> Still failing: F9, F15–F20, F22 (F23 blocked, F24 doc debt).

| # | Failure | Rows | What breaks |
|---|---|---|---|
| F1 | Validation not persisted across restart | C55 | In-memory map, Save never serializes flags; export gate lost on restart. |
| F2 | Export exports 0 pages (current + all-validated) | C35, C36 | Handler scans retired `labeled-projects/` lane; event store never feeds it; success toast on empty output. |
| F3 | Export style filter unreachable | C37 | `_collect_style_labels` scans the same dead lane → always `[]`; only "All" renders. |
| F4 | Export cancel → 405, job keeps running | C40 | Wrong URL (`/projects/{id}/jobs/{id}/cancel` doesn't exist); button has no testid. |
| F5 | Delete word / delete line silently no-op (4 surfaces) | B-61, B-62, B-65 | WordFooter delete, LineDetail card delete, MultiLineDetail card + bulk delete all POST the documented backend stub `/delete` (lines_paragraphs.py:1764) → ConfirmDialog, HTTP 200, nothing deleted. Batch routes (toolbar, MultiWordDetail) are real. |
| F6 | Style removal missing end-to-end (3 surfaces) | B-39, B-41, B-43 | Backend's only style route is add-only (`apply_style_scope`); no route calls book-tools `remove_style_label`. `clear-style-button`, WordDetail chip off-toggle, and tag-chip × all silently no-op. |
| F7 | LineDetail word-grid validate + GT inputs unwired | B-21, B-22 | LineDetail.tsx:277 mounts LineCard without `onValidateWord` / `onCommitGt`; visible, editable, no effect. Alternates exist (WordDetail, MultiLineDetail). |
| F8 | Toolbar cells silently no-op on word selection | B-55, B-66 | `resolveToolbarRequest` returns null when `{lineIndex}` can't fill from `selected_lines` → no request, no toast, cell enabled. Hits `line-split-after`, `line-split-selected`, `word-w-to-l` (so S4's form-new-line backend is unreachable from its own toolbar cell). |
| F9 | Ctrl-click not additive at LINE level | B-56 | Second ctrl-click replaces the selection; only drag-box accumulates lines. Word-level additive works. |
| F10 | Rotate surface broken (3 of 5 links) | C28 | Buttons invisible; rotation metadata not in API payload; re-OCR after rotate ineffective. Pixel rotation itself works. |
| F11 | Auto-rotate-all: no UI + detection crash | C29 | Zero frontend references; backend detection crashes per page on RGB PNGs; always `rotated=[]`. Manual-rotation skip honor works. |
| F12 | Project switching unreachable with an active session | A-02 ≡ C13 | "Projects" link → `/` → session redirect bounces back. No project-select control on project routes. Grid only reachable via the 404 error path. |
| F13 | Project delete / archive menu items are pure stubs | C14 | `onClick` only closes the menu (RootPage.tsx:265-281); `DELETE /api/projects/{id}` exists but is never called from UI. |
| F14 | Deep link to a not-yet-loaded project bounces | C57 | `GET /api/projects/{id}` 404 → RootPage; no `POST /load` attempted. Legacy auto-loaded from URL. Session-resume covers restarts only. |
| F15 | Jobs list / queue UI missing | C32 | `GET /api/jobs` is backend-only; no jobs panel anywhere; progress visible only as toasts + ExportDialog. |
| F16 | Suite sibling launcher never wired to real endpoints | C51 | App.tsx:472-488 GAP-3 shims return `[]` / `requires-host-config` though `/api/suite/*` is mounted and works (proven by send-to-trainer chain, C42). |
| F17 | Compute-device picker UI unreachable | C52 | `ComputePanelContent` wired into `settingsPanels` but no settings / utility-dock trigger renders; backend PUT works. |
| F18 | OCR-config modal mouse-dead | A-48 | pdomain-ui 0.7.x dialog overlay z-bug (see §5.1). Keyboard path works. |
| F19 | Go button is a guaranteed no-op | A-18 ≡ C16 | `onBlur` clears the typed value before the button's `onClick` reads it (ProjectNavigationControls.tsx:122-124). Enter-in-input works. |
| F20 | Advertised-but-unbound hotkeys | A-54 | Mod+, (BUG-KBD-1), Mod+O, Mod+J listed in hotkeyMap + help modal; no `useHotkey` registration exists. |
| F21 | Erase-to-marker (4-direction) — RETIRED | B-74 | CT decision 2026-06-12: retired, superseded by brush/lasso/rect erase. Revisit only if real labeling sessions show margin-cleanup pain. |
| F22 | Rebox-on-main-canvas unreachable | B-76 | Canvas handles `mode==="rebox"` but nothing ever sets it; rail modes map only to erase/add-word/select. Alt: ReboxSection mini-canvas. |
| F23 | Glyph annotation panel unmounted | B-82 | Known-blocked (M11 / Q-A7). Unchanged. |
| F24 | Driver-contract testid rot | A-41, A-55, A-11 | Contract lists testids of dead surfaces; see §5.3. Doc/test debt, not user-facing. |

## 4. Consolidated PARTIAL table

| # | Degradation | Rows | Nature |
|---|---|---|---|
| P1 | Multi-line bulk unvalidate loses updates intermittently | B-28 | Parallel `mutate()` loop race (§5.2); 2 of 3 runs lost one line, no error. |
| P2 | Bulk style apply loses updates | B-79 | Same race, third surface observed: 2 words selected, one got the style. |
| P3 | Hardcoded split points | B-51, B-52, B-58 | Line split-after-word, split-by-words, para split-after-line all hardcode index 0; legacy let you pick. |
| P4 | Add-word draw dispatch flaky | B-75 | Backend `words/add` works; UI drag dispatched 1 of 3 attempts and didn't persist. Needs focused e2e. |
| P5 | Export dialog content mouse-dead | A-49 | Same overlay z-bug as F18 (§5.1); opens, Escape works, content unclickable. |
| P6 | Source-root apply 403s on non-default ports | C09 | `LocalTrustMiddleware` rejects any Origin off a fixed 8080/5173 allowlist even when `Sec-Fetch-Site: same-origin`. Works on :8080; e2e misses it (httpx, random ports). |
| P7 | Load Page lost its revert semantic | C20 | RESOLVED BY DESIGN (CT 2026-06-12): `docs/specs/2026-06-12-event-store-undo.md` — "Load Page" renamed "Reload" (honest refresh, testid unchanged) and real per-page undo/redo ships from the event-store version history (v1 slices H-A…H-D + BV). |
| P8 | Export run history is client-state only | C43 | `GET /exports` is a hardcoded `[]` stub though manifests exist on disk; history lost on dialog unmount. |
| P9 | Component filter / output-mode effect unobservable | C38 | Controls render and POST; effect masked while F2 holds. |
| P10 | Legacy envelope read-compat is export-only | C56 | Planted `UserPageEnvelope` is consumed by export, but page load ignores it once an event-store head exists. |
| P11 | Generic job cancel UI only in ExportDialog | C33 | Backend cancel route fine; no surface for other job types (pairs with F15). |
| P12 | Status filter chips are cosmetic | A-07 | Non-"all" chips show all projects (no API status field). |
| P13 | Collapsed drawer expand chevron has 0 width | A-36 | Invisible/unclickable; Rail "Bulk" is the only mouse path back. |
| P14 | Right panel re-expand only via new selection | A-38b | Collapse leaves no expand control. |
| P15 | `e` hotkey collision: erase + Export dialog | A-45 | Hidden PageActions stub still registers `useHotkey("e", onExport)` alongside rail erase. |
| P16 | Breadcrumb walk above line level shows empty panel | A-59 | Alt+Arrow line↔word fine; para/block walk renders no detail. |
| P17 | CharFixer bbox apply not fully driven | B-46 | Renders; bbox-drag path not exercised this sweep. |
| P18 | Match-filter via alternate surface only | B-84 | Legacy `match-filter-*` hidden in stub; visible Worklist filter chips work. |

---

## 5. Systemic / upstream issues

These cut across rows; fixing them clears multiple verdicts at once.

### 5.1 pdomain-ui 0.7.x dialog overlay z-bug (upstream fix needed)

Dialogs whose content relies on the pdomain-ui `.dialog` class render the
`.dialog-overlay` (z-index 49, `frontend/src/styles/primitives.css:552`) as a
*sibling on top of* the content (z-index auto) — the whole modal is mouse-dead;
`elementFromPoint` returns the overlay. Keyboard paths still work. Affected:
OCRConfigModal (F18), ExportDialog (P5). Dialogs that pass their own
`fixed … z-50` className (SourceFolderDialog, HotkeyHelpModal, ConfirmDialog)
are unaffected. Likely from the pdomain-ui Dialog overlay-as-sibling markup in
the 0.7.x bump → fix belongs upstream in `pdomain-ui`; a local z-index override
can bridge.

### 5.2 Parallel `for … mutate()` loops silently lose updates

`handleBulkValidate` (MultiLineDetail.tsx:92) and siblings fire one mutation per
item in a sync loop; with 2+ items, an update is intermittently lost — both
POSTs sent, no 4xx/5xx, final state reflects only the first. Observed on three
surfaces (B-28, B-79, multi-line bulk); the same pattern exists in
`handleBulkCopyOcrToGt`, MultiWordDetail bulk ops, BulkWordActions loops, and
ProjectPage clear-component loops. Fix shape: use the batch endpoints where they
exist, or serialize/await the loop.

### 5.3 Driver-contract testid rot (`docs/architecture/13-driver-contract.md`)

- §2.1 `project-select` / `load-project-button` / `source-folder-button`:
  `ProjectLoadControls.tsx` is dead code, never mounted. Real surface = RootPage
  card grid; the grid's "Open source folder" button has **no testid**.
- `selection-mode-paragraph/line/word` (lines 171-173): ImageTabsHeader dead
  since IS-4, DOM count 0 — this is why
  `tests/e2e/test_parity_chrome.py::test_paragraph_mode_selection_opens_paragraph_detail`
  is red. Real surface: rail targets + Shift+1/2/3.
- `word-edit-dialog` + ~20 `dialog-*` testids (lines 265-283): WordEditDialog
  deleted in `c5ddd35`; equivalents live in WordDetail sections.
- `export-cancel-button` never existed in code (C40).
- SplitPicker buttons have no testids; the inventory's
  `glyph-panel-charspan-cell-*` claim points at the unmounted panel.
- **Hidden `data-testid-stub="true"` duplicates** (HeaderBar, canvas-hidden-stubs)
  shadow real controls — unscoped `[data-testid=…]` selectors resolve to
  invisible stubs and time out. Either drop the stubs or mandate
  `:not([data-testid-stub])` scoping in the contract.

### 5.4 Konva div-in-tree console errors

`Konva has no node with the type div. Group will be used instead.` — 3-5× on
every project-page load (both A and B sweeps). A DOM `<div>` is rendered inside
a react-konva tree. Benign fallback, real `console.error`, worth a cleanup.

---

## 6. Present & wired (condensed)

≈147 of 207 rows PASS — the app is far from "everything is broken". Confirmed
live, one line per area:

- **Shell & nav:** routing + deep links + redirects, session restore across
  restart, prev/next/Enter-goto + all four nav hotkeys, drawer tabs, rail
  (modes/targets/layers + hotkeys incl. SEL-3 sync), worklist + Ctrl+K
  quick-search, hotkey help, theme persistence, breadcrumbs, metrics strip.
- **Selection:** click / drag-box / ctrl-click additive (word) / shift-click
  remove; multi-word + multi-line detail views; granularity sync.
- **GT editing:** word/line GT inputs persist; copy GT↔OCR at word, line, para,
  page scope; Tab traversal across cards; Ω picker; CharFixer per-char GT;
  char-range styling.
- **Validation (in-session):** word / line / para / page validate + unvalidate
  across WordDetail, LineDetail bulk, toolbar, BulkWordActions — all persist
  via API (durability across restart is F1).
- **Structure ops:** word merge / split / gap slider; line merge (panel +
  toolbar) + batch delete; para split / merge / delete; words→new-paragraph.
- **BBox / image:** numeric inputs, nudges, refine / expand+refine at all
  scopes (202 jobs complete), rebox mini-canvas, erase brush + apply,
  crop/reset.
- **Styles/components (apply-side):** apply style + scope, component chips
  incl. drop cap, layout-type assignment, bulk glyph-mark recipe dry-run.
- **Page/project ops:** save page, auto-save (cross-restart durable for
  content), save-project with dirty-only + skip warning, reload OCR (real
  DocTR, correct words on a real-text project), rematch GT, reload-OCR-edited
  gating.
- **Config & suite:** OCR config modal full snapshot/cancel semantics, model
  select + HF revision pin durable on disk, rescan, normalization gating,
  auto-rotate config persistence; all `/api/suite/*` routes live; full
  send-to-trainer launch chain (registry → spawn → healthz → tab).
- **Export mechanism:** dialog, scope/filters/output-mode controls, SSE
  progress text, manifest merge-write, suite shared-paths publication — the
  machinery works end-to-end once fed (planted-envelope control exported 32
  crops + labels).

---

## 7. Prioritized slice plan

> **2026-06-13 status:** P1.1–P1.7, P2.1–P2.3, P4.1–P4.3, P4.6 **shipped and
> live-verified** (§1a); P7's design resolution (undo/redo + Reload) shipped.
> Open: P3.1 (overlay z-bug), P3.2 (mutation-loop race — now also 404s, §1a),
> P4.4 (jobs panel), P4.5 (suite launcher/settings dock), all of P5, plus the
> four new defects in §1a.

Each slice should get a capability-matrix spec
(format: [`docs/specs/2026-06-05-selection-operations-parity.md`](../../specs/2026-06-05-selection-operations-parity.md))
with observable-behavior acceptance and a mandatory Playwright verification
milestone. Effort tags: S / M / L. "CT" = needs a CT design decision first;
"mech" = mechanical, spec can be written directly.

### P1 — silent data-loss / data-op failures (highest urgency: every one reports success)

| Slice | Covers | Effort | CT? | Acceptance bar |
|---|---|---|---|---|
| P1.1 Validation persistence | F1 (C55) | M | CT (where flags live in the persisted payload / envelope) | validate → Save → server restart → counts identical. |
| P1.2 Export lane reconnect | F2, F3, P8, P9 (C35-C38, C43) | M | CT (export reads event store vs. Save also writes labeled lane; affects UserPageEnvelope compat C56) | validate+save a page in the UI → export → crops + labels on disk; style filter lists real styles. |
| P1.3 Real deletes for word/line surfaces | F5 (B-61/62/65) | S | mech (point `useDeleteWord`/`useDeleteLine` at batch routes, or implement D2/D3) | each delete surface removes the item, persisted via API re-fetch. |
| P1.4 Style removal end-to-end | F6 (B-39/41/43) | S | mech (backend route calling `remove_style_label` + off-state wiring) | toolbar clear, chip off-toggle, tag-× each remove the style, persisted. |
| P1.5 Export cancel + testid | F4 (C40) | S | mech | cancel during a run → job state cancelled server-side; partial output removed. |
| P1.6 LineDetail word-grid wiring | F7 (B-21/22) | S | mech (pass two props) | grid validate + GT Enter persist via API. |
| P1.7 Toolbar resolver honesty | F8 (B-55/66) | S | mech (derive line from word selection, or disable cell + toast) | cells either work from a word selection or are visibly disabled; never silent. |

### P2 — rotate surface (completes M9.1/M9.2 follow-through)

| Slice | Covers | Effort | CT? | Acceptance bar |
|---|---|---|---|---|
| P2.1 Rotate buttons visible + metadata surfaced | F10 (C28 links 1+3) | S | mech | visible rotate buttons; API payload carries `rotation_degrees`; badge renders. |
| P2.2 Re-OCR after rotate | F10 (C28 link 4) | M | mech (investigate why re-OCR output isn't applied post-rotate) | post-rotate re-OCR yields landscape-coord words aligned with pixels. |
| P2.3 Auto-rotate detection fix + UI trigger | F11 (C29) | M | mech, likely cross-repo (input-shape crash may sit in pdomain-book-tools detection path) | auto-rotate-all on a skewed fixture rotates pages; UI trigger exists; manual-skip honored. |

### P3 — systemic bugs

| Slice | Covers | Effort | CT? | Acceptance bar |
|---|---|---|---|---|
| P3.1 Dialog overlay z-fix | F18, P5 (§5.1) | S | mech; upstream pdomain-ui fix + local bridge override | OCR-config and Export dialog content clickable with a mouse. |
| P3.2 Batch/serialize mutation loops | P1, P2 (§5.2) | S-M | mech | bulk ops on N items always land N updates (loop e2e, 5+ runs green). |

### P4 — reachability: project switching, jobs, suite UI

| Slice | Covers | Effort | CT? | Acceptance bar |
|---|---|---|---|---|
| P4.1 Project switching | F12 (A-02/C13) | S | CT-light (skipSessionRedirect on the Projects link vs. header project switcher) | from a loaded project, reach the grid and open a different project. |
| P4.2 Project delete/archive wiring | F13 (C14) | S | mech (+ confirm dialog) | delete removes the project (API + grid); archive does whatever the API defines. |
| P4.3 Deep-link auto-load | F14 (C57) | S | mech (404 → attempt `POST /load` before bouncing) | fresh server + pasted page URL lands on that page. |
| P4.4 Jobs panel UI | F15, P11 (C32/C33) | M | CT (placement/shape; pdomain-ui utility dock is the likely home) | running jobs visible with progress + cancel outside ExportDialog. |
| P4.5 Suite launcher + settings dock | F16, F17 (C51/C52) | S-M | CT-light (dock trigger placement) | sibling apps listed + launchable; compute-device picker reachable and applies. |
| P4.6 LocalTrustMiddleware origin check | P6 (C09) | S | mech (honor `Sec-Fetch-Site: same-origin` or derive allowlist from bound port) | source-root apply succeeds on a non-default port from the browser. |

### P5 — polish tail

| Slice | Covers | Effort | CT? | Acceptance bar |
|---|---|---|---|---|
| P5.1 Go button fix | F19 | S | mech (read value before blur reset) | type N + click Go → page N. |
| P5.2 Hotkey cleanup | F20, P15 (A-54/A-45) | S | mech (bind Mod+,/O/J or delist; remove stub `e` registration) | every hotkey in the help modal does what it says; `e` only toggles erase. |
| P5.3 Line ctrl-click additive | F9 (B-56) | S | mech | ctrl-click accumulates lines into multi-line detail. |
| P5.4 Split-point pick UX | P3 (B-51/52/58) | M | CT (picker UX for split position) | user picks the split word/line; result persisted. |
| P5.5 Drawer/panel re-expand affordances | P13, P14 (A-36/A-38b) | S | mech | collapsed drawer + right panel each have a visible click target to reopen. |
| P5.6 Contract-doc + dead-code cleanup | F24 (§5.3) | S | mech | contract matches DOM; delete ImageTabsHeader + ProjectLoadControls dead code; fix or delete stale e2e (`test_paragraph_mode_selection_opens_paragraph_detail`); add missing testids (source-folder trigger, export-cancel, SplitPicker); drop or document `data-testid-stub` shadowing. |
| P5.7 Konva div cleanup | §5.4 | S | mech | zero Konva type-div console errors on page load. |

### Deliberately not sliced

- **F21 erase-to-marker** — RETIRED (CT decision 2026-06-12): superseded by
  brush/lasso/rect erase. Revisit only if real labeling sessions show
  margin-cleanup pain.
- **F23 glyph panel** — blocked on M11 / Q-A7, unchanged.
- **P7 Load-Page revert semantics** — RESOLVED BY DESIGN (CT 2026-06-12):
  `docs/specs/2026-06-12-event-store-undo.md` builds event-store-powered
  per-page undo/redo and renames "Load Page" to an honest "Reload"
  (`load-page-button` testid unchanged). v1 (slices H-A…H-D + BV) shipped.
- **P12 status filter chips** — needs an API status field; fold into whatever
  project-metadata work comes later.

---

## 8. Corrections to the 2026-06-06 matrix (for the record)

- **WordEditDialog "unwired callbacks" (old S1) is moot** — the dialog was
  deleted in `c5ddd35`; WordDetail sections are the surface and they pass
  (except style-clear, F6).
- **Matches-pane decision (old S2)** landed as retire-and-replace: drawer Text
  tab + LineDetail/MultiLineDetail editing; the `display:none` stubs remain
  only as driver-contract debt (F24).
- **Rotate "stub" (old S8)** is no longer a stub: pixel rotation is real and
  durable; the remaining breaks are surfacing + re-OCR (F10/F11).
- **"Export handler is real"** was true but incomplete — the handler is real
  *and disconnected from the save path* (F2). Code-reading verdicts missed it;
  only the live pipeline run caught it.
- Old S3 (main-canvas rebox), S4 (form-new-line), S5 (skip warning), S6 (chrome
  bundle) shipped; S3's mode-entry wiring regressed/never landed an entry point
  (F22) and S4's toolbar cell can't reach its own backend (F8). S6's Go button
  shipped visibly but broken (F19).

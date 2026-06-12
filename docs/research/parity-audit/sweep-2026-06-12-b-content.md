# Parity sweep 2026-06-12 — Dimension B (OCR content actions)

**Auditor:** dimension-B agent (1 of 3 parallel). **Tree:** worktree
`agent-a2bf727009facfe3a` rebased onto local main `d0ba846`. **Bundle:** fresh
`make frontend-build AI=1` this session. **Method:** live browser drive of a
seeded event-store fixture (`/tmp/audit-b/serve.py`, 2 blocks / 3 paras /
6 lines / 24 words, 2 GT mismatches) + API persistence re-fetch after every
mutating op. Acceptance = VISIBLE + ENABLED + real EFFECT (persisted).

> Status legend: PASS / PARTIAL / FAIL / N-A (superseded or out of dimension).

## Architectural deltas since PARITY-GAP.md (2026-06-06)

- **WordEditDialog deleted entirely** (`c5ddd35`, 2026-06-10): all
  `dialog-*` capabilities are superseded by WordDetail right-panel sections
  (Structure / BBox / Rebox / Erase / CharFixer / CharRanges). Legacy
  dialog rows are judged against the WordDetail equivalent.
- **MultiWordDetail + MultiLineDetail** routed in RightPanel (specs
  2026-06-05 + 2026-06-10).
- **Matches pane (WordMatchView/TextTabs) still `display:none`**
  (ProjectPage.tsx:956 `canvas-hidden-stubs`) — retained for driver-contract
  testids only; S2 decision shipped a visible Text drawer tab
  (PlaintextGtOcrView) instead.

## Verdict table

| # | Capability (legacy ref) | SPA surface | Verdict | Evidence |
|---|---|---|---|---|
| 1 | SEL-1 click selects + highlights word | Canvas → WordDetail | PASS | Plain click word(0,0) → `word-header-id` "Line 1 · Word 1" visible; highlight layer drawn (screenshot b1_sel1) |
| 2 | SEL-2 drag-box selects words | Canvas drag (word target) | PASS | Partial drag over 2 words → `multi-word-detail` "2 WORDS SELECTED"; Ctrl-drag adds block-1 word ("3 WORDS SELECTED"). Note: full-line drag promotes to LINE selection (`promoteCompleteWordLines`, by design) |
| 3 | SEL-3 granularity sync (Shift+1/2/3 ↔ rail) | Viewport hotkeys + Rail | PASS | Shift+1 → `rail-target-para[data-active=true]`; Shift+3 → word target active |
| 4 | SEL-4 Ctrl-click additive cross-block | Canvas | PASS | word(0,0) then Ctrl-click word(4,0) → `multi-word-detail`, ≥2 `multi-word-block-*` groups (AG-5 regression is FIXED) |
| 5 | SEL-5 Shift-click removes from selection | Canvas | PASS | Shift-click selected word(4,0) → multi view closes, single WordDetail returns |
| 6 | MUL-1/2 multi-block words listed w/ line context | RightPanel MultiWordDetail | PASS | Both blocks' `ocr_line_text` rendered above their words |
| 7 | MUL-3 ops on multi-selection | MultiWordDetail bulk bar | PASS (visible) | `multi-word-validate/-unvalidate/-delete/-style-apply/-component-apply` all visible (effect verified row 20) |
| 8 | ML-1/2 multi-line drag → per-line cards | RightPanel MultiLineDetail | PASS | Line-target drag over lines 0–1 → `multi-line-detail` with 2 `multi-line-card-*` |
| 9 | ML-7 multi-line bulk bar | MultiLineDetail | PASS (visible) | `multi-line-bulk-bar` visible (effect verified later) |
| 10 | Click line/para/block opens its detail panel | Rail target + canvas click | PASS | line→`line-detail`, para→`paragraph-detail`, block→`block-detail` all visible |

| 11 | Word GT edit, commit on Enter/blur (legacy #1/#2) | WordDetail `ocr-gt-input` | PASS | Set "quicker" → API `ground_truth_text` updated |
| 12 | Per-word Copy OCR→GT (legacy #13) | WordDetail `ocr-gt-copy-btn` | PASS | GT became OCR text "qu1ck", persisted |
| 13 | Unicode/Ω picker insert (new-only) | WordDetail `ocr-gt-omega-btn` | PASS | Picker opens, glyph inserts into GT input, Enter persists |
| 14 | Word validate toggle (legacy #23) | WordDetail `word-footer-validate` | PASS | `is_validated` False→True via API after click |
| 15 | Line GT set (line-level GT input) | LineDetail `line-detail-gt-input` | PASS | "jumps over lazy hounds" persisted to `ground_truth_line_text` |
| 16 | Line Copy GT→OCR (legacy #8/#10) | LineDetail `line-copy-gt-to-ocr` | PASS | `ocr_line_text` became GT text |
| 17 | Line Copy OCR→GT (legacy #9/#11) | LineDetail `line-copy-ocr-to-gt` | PASS | GT == OCR after click |
| 18 | Line validate-all (legacy #18/#20) | LineDetail `line-detail-validate-all` | PASS | All 4 words of line 1 `is_validated` |
| 19 | Bulk validate checked words (legacy #21) | LineDetail Words-tab `line-detail-bulk-validate` | PASS | word(2,0) validated, unchecked sibling untouched |
| 20 | Bulk skip/unvalidate checked words (legacy #22) | LineDetail Words-tab `line-detail-bulk-skip` | PASS | word(2,0) unvalidated |
| 21 | Per-word validate in LineDetail word grid (legacy #23 surface) | LineDetail Line-tab WordCell `word-validate-button-{l}-{w}` | **FAIL** | Visible + enabled, click has NO effect — LineDetail.tsx:277 mounts LineCard without `onValidateWord`; silent no-op. Alternates: word-footer-validate, MultiLineDetail grid |
| 22 | Per-word GT input in LineDetail word grid (legacy #1 surface) | LineDetail Line-tab WordCell `gt-text-input-{l}-{w}` | **FAIL** | Visible + editable, Enter does NOT persist — `onCommitGt` not passed to LineCard in LineDetail.tsx:277. Alternates: WordDetail input, MultiLineDetail grid |
| 23 | Paragraph validate / unvalidate (legacy #16/#17) | ParagraphDetail `para-validate`/`para-unvalidate` | PASS | Lines 2+3 all validated then all cleared via API |
| 24 | Paragraph Copy OCR→GT / GT→OCR (legacy #6/#7) | ParagraphDetail `para-copy-ocr-to-gt`/`para-copy-gt-to-ocr` | PASS | word(3,2) gt←"tw0"; line3 ocr==gt after reverse copy |
| 25 | ML-4 inline GT edit in multi-line cards | MultiLineDetail `gt-text-input-{l}-{w}` | PASS | word(3,0) gt "AND" persisted |
| 26 | ML-5 Tab traversal crosses line cards (legacy #3 Tab GT nav) | MultiLineDetail | PASS | Tab from gt-text-input-2-3 focuses gt-text-input-3-0 |
| 27 | ML-6 per-line validate on card | MultiLineDetail `line-validate-button-{n}` | PASS | Line 3 all words validated; button disables when fully validated (one-way; unvalidate via bulk bar) |
| 28 | ML-7 bulk bar ops across selected lines | MultiLineDetail `multi-line-bulk-*` | **PARTIAL** | Validate-all persisted both lines; **Unvalidate-all intermittently loses one line** (2 of 3 runs: only 1st of 2 parallel `validateLine.mutate` loop POSTs took effect; both return no error — silent lost update). Race in N-parallel-mutation loops |

| 29 | GRID-1 ToolbarActionGrid visible + collapsible | Canvas column | PASS | `toolbar-action-grid` visible, not display:none |
| 30 | GRID-2 cells enable/disable per selection | ToolbarActionGrid | PASS | No selection: page cells enabled, word cells disabled; word click enables word cells |
| 31 | Page validate / unvalidate all (legacy #14/#15) | `toolbar-page-validate`/`-unvalidate` | PASS | All 24 words validated then cleared via API |
| 32 | Word validate selected (legacy #21/#22) | `toolbar-word-validate`/`-unvalidate` | PASS | word(0,0) toggled, persisted |
| 33 | Word Copy OCR→GT (legacy #13) | `toolbar-word-ocr-to-gt` | PASS | word(0,1) gt←"qu1ck" persisted |
| 34 | Word Copy GT→OCR (legacy #12) | `toolbar-word-gt-to-ocr` | PASS | word(0,1) `ocr_text` became GT ("quick") |
| 35 | Line validate (toolbar, legacy #18/#19) | `toolbar-line-validate` | PASS | line 4 all words validated, persisted |
| 36 | Line Copy OCR→GT (toolbar, legacy #9) | `toolbar-line-ocr-to-gt` | PASS | line 4 gt==ocr after click |
| 37 | Para validate (toolbar, legacy #16/#17) | `toolbar-para-validate` | PASS | para 2 (lines 4+5) all validated |
| 38 | Apply style + scope select (legacy #84/#85) | `apply-style-select`+`apply-style-button`, `scope-select` | PASS | italics persisted to `text_style_labels`; scope-select whole/part present |
| 39 | Clear style (toolbar, legacy chip-clear path) | `clear-style-button` | **FAIL** | Click sends `style:"regular"` (ProjectPage.tsx:681) but backend `/style` only calls add-only `apply_style_scope` — italics NOT removed (styles stayed `['italics','regular']`) |
| 40 | Apply/clear component incl. drop cap (legacy #88/#89) | `apply-component-select` etc. | PASS | footnote marker applied + cleared via `enabled:false`; options include drop cap / drop cap unrecovered / subscript / superscript |
| 41 | WordDetail style chip toggle OFF (legacy #92-equivalent) | `style-chip-italics` | **FAIL** | Chip click re-sends `applyStyle` with the same styleKey regardless of off-state (WordDetail.tsx:179) — italics never removed |
| 42 | WordDetail component chip toggle (legacy #90/#91) | `component-chip-drop-cap` | PASS | drop cap on → `word_components=['drop cap']` → off again |
| 43 | Tag-chip × remove (legacy #92) | WordCell `word-tag-clear-button-*` (LineDetail surface) | **FAIL** | Click has no effect: LineDetail passes no `onClearWordTag`, ProjectPage has no clearTag handler, and backend has NO style-remove route at all |
| 44 | Char-range add/delete (new-only) | CharRangesSection | PASS | anchor+end click, italics chip, Add → `char_ranges=[{start:0,end:2,styles:['italics']}]` persisted; delete cleared |
| 45 | CharFixer per-char GT edit (new-only) | `char-fixer-input-{i}` | PASS | "J" persisted to gt after 500ms debounce |
| 46 | CharFixer per-char bbox apply | `charfixer-apply` | PARTIAL (not fully driven) | Section + apply button render (disabled until canvas drag marks dirty); bbox-drag path not driven this sweep |
| 47 | CharFixer unicode picker entry | `char-fixer-open-picker-button` | PASS (visible) | Button present + visible |

| 48 | Word merge prev/next (legacy #32/#33) | WordDetail StructureSection `structure-merge-next` + confirm | PASS | "right"+"here" → "righthere" persisted (first run mis-scored by counting `word_index=None` GT-orphan slots) |
| 49 | Word split at picked position (legacy #40/#42) | StructureSection SplitPicker + `structure-split-button` | PASS | Split "jumps" after pos 2 → `ju`/`mps` persisted. NOTE: SplitPicker char buttons have NO testids (inventory's `glyph-panel-charspan-cell-*` claim is stale — that's GlyphAnnotationPanel) |
| 50 | Inter-word gap slider (new-only) | `structure-gap-slider` | PASS | Next word's bbox.x moved 446→453 after slider drag, persisted |
| 51 | Line split-after-word (legacy #36) | LineDetail `line-split-after-word` | PARTIAL | Works (lines+1) but hardcoded `wordIndex: 0` — titled "after its first word"; legacy let you pick the word |
| 52 | Split line by selected words (legacy #37) | LineDetail `line-split-by-words` | PARTIAL | Works but hardcoded `wordKeys [[li,0]]` — extracts first word only |
| 53 | Merge lines prev/next (legacy #24) | LineDetail `line-detail-merge-next` | PASS | Split line re-merged, line count restored |
| 54 | Merge selected lines (toolbar, legacy #24) | `toolbar-line-merge` after 2-line DRAG select | PASS | `POST lines/merge` 200, lines 5→4 |
| 55 | Toolbar line split-after / split-selected / W→L cells | `toolbar-line-split-after`, `toolbar-line-split-selected`, `toolbar-word-w-to-l` | **FAIL** | All three ENABLED with a word selection but click fires ZERO network requests: endpoints template `{lineIndex}` resolved from `selection.selected_lines[0]` (useToolbarDispatch.ts:113) which is empty for word-level selections → `resolveToolbarRequest` returns null → silent no-op, no toast |
| 56 | Ctrl-click additive at LINE level | Canvas | **FAIL** | Ctrl-click a second line REPLACES selection (no multi-line-detail); only drag-box accumulates lines. Word-level ctrl-click additive works (row 4) |
| 57 | Form new paragraph from selected words (legacy #39) | `toolbar-word-to-para` | PASS | 2 selected words moved to a new paragraph (paras 3→4), persisted |
| 58 | Split paragraph after line (legacy #27) | ParagraphDetail `para-split-after-line` | PARTIAL | Works (paras+1) but `afterLineIndex: 0` hardcoded — always splits after the para's first line |
| 59 | Merge paragraphs (legacy #29) | ParagraphDetail `para-merge` | PASS | Split para re-merged, count restored |
| 60 | Delete paragraph (legacy #30) | ParagraphDetail `para-delete` + confirm | PASS | Real route `/paragraphs/{pi}/delete`; lines removed |
| 61 | Delete word (legacy #34/#35) | WordFooter `word-footer-delete` + ConfirmDialog | **FAIL** | Confirm dialog shows, POST fires to page-scope `/delete` — an explicit BACKEND STUB (lines_paragraphs.py:1764 "Stays a stub", returns empty payload, HTTP 200) — word NOT deleted, no error shown |
| 62 | Delete line from LineCard button | LineDetail Line tab + MultiLineDetail cards (`line-delete-button-{n}`) | **FAIL** | `useDeleteLine` (useLineMutations.ts:105) also POSTs the stub `/delete` → silent no-op on both surfaces (confirmed live, lines unchanged) |
| 63 | Delete selected lines (toolbar, legacy #25) | `toolbar-line-delete` | PASS | Uses real `lines/delete-batch`; line removed |
| 64 | Delete selected words (bulk) | MultiWordDetail `multi-word-delete` + confirm | PASS | Uses real `words/delete-batch`; 2 words removed |
| 65 | ML-7 bulk Delete lines | `multi-line-bulk-delete` + confirm | **FAIL** | Loops `useDeleteLine` → stub `/delete` → confirm then nothing deleted |
| 66 | Form new LINE from selected words (legacy #38, slice S4) | `toolbar-word-w-to-l` | **FAIL** | Same resolver null as row 55 — S4 implemented the backend route but the toolbar cell can never reach it from a word selection |

| 67 | Page-scope Copy OCR→GT / GT→OCR (legacy #4/#5) | `toolbar-page-ocr-to-gt`/`-gt-to-ocr` | PASS | Mismatched word's gt←ocr then ocr←gt, both persisted |
| 68 | BBox numeric inputs (rebox) | BBoxSection `bbox-input-x/y/w/h` | PASS | x blur-commit persisted (96→101) |
| 69 | BBox nudge buttons (legacy #46–#53) | `bbox-nudge-left/right/top/bottom` + step | PASS | x 97→96 persisted via `/rebox` (a first batched run failed due to a toast/ordering artifact; isolated run clean) |
| 70 | BBox Refine / Expand+Refine (legacy #72/#73) | `bbox-refine-button`/`bbox-expand-refine-button` | PASS | Each fires `/rebox` commit, HTTP 200 |
| 71 | BBox Crop / Reset (legacy #58–#61/#54 analog) | `bbox-crop-button`/`bbox-reset-button` | PASS | Crop fires `/rebox`; Reset present (new model: numeric crop, no marker-based 4-dir crop) |
| 72 | Rebox mini-canvas draw + Apply (legacy #43/#44 alt) | ReboxSection `rebox-tool-draw` + `rebox-apply` | PASS | Drew rect on Konva mini-canvas; bbox 134×64→155×77 persisted; snap/draw/pan + zoom controls present |
| 73 | Erase pixels brush + Apply (legacy #62–#64 alt) | ErasePixelsSection | PASS | Brush stroke staged → `erase-apply` fired `/erase-pixels` ops; lasso/rect tools + op-remove/clear rendered (only brush driven) |
| 74 | Erase-to-marker 4-dir (legacy #65–#68) | — | **FAIL (still missing)** | No directional erase surface; brush/lasso/rect is the only model (unchanged since 06-06 audit) |
| 75 | Add word from drawn bbox (legacy #45) | `word-add-button` + canvas draw | **PARTIAL** | Mode toggles (cursor→copy); backend `POST words/add` works (direct call adds word). But the UI draw dispatched only 1 of 3 attempted drags, and that one did not persist a word. Flaky dispatch — needs e2e attention |
| 76 | Rebox word on MAIN canvas (S3) | viewport mode "rebox" | **FAIL** | `handleRebox` + canvas mode case exist, but NOTHING sets `viewportStore.mode="rebox"` (rail modes map only to erase/add-word/select, PageImageCanvas.tsx:355). No UI entry point → unreachable. Alt: ReboxSection mini-canvas |
| 77 | Refine/Expand+Refine/Expand toolbar cells, all scopes (legacy #69–#71, #76–#83) | `toolbar-{scope}-refine` etc. | PASS | All cells POST `/refine` (mode refine / expand_then_refine / expand_only), 202 + `refine_bboxes` jobs complete without error |
| 78 | Page validate/unvalidate via BulkWordActions (legacy #14/#15 alt) | `rail-bulk-button` → `page-validate-all` | PASS | All real words validated then cleared |
| 79 | Bulk style/component apply to selection (legacy #84/#88 alt) | BulkWordActions `bulk-word-style-apply` | **PARTIAL** | With 2 words selected, only ONE got `bold` — same parallel-mutation-loop lost-update race (3rd surface observed) |
| 80 | Multi-word bulk validate/unvalidate (MUL-3 effect) | `multi-word-validate` | PASS | Both selected words validated via API |
| 81 | Bulk glyph-mark recipe dialog (new-only) | `bulk-glyph-mark-button` (PageActionsCompact) → dialog | PASS | Dialog opens; dry-run round-trips and renders "0 words will be modified" |
| 82 | Per-word glyph annotation panel (M11) | GlyphAnnotationPanel | **FAIL (known/blocked)** | Component still mounted nowhere (only its own file); M11 blocked on Q-A7 — unchanged |
| 83 | Block/paragraph layout-type assignment | BlockDetail `block-detail-layout-chip-*` + save | PASS | PATCHed `layout_type:"heading"` to all 3 paragraphs of the block |
| 84 | Filter lines All/Unvalidated/Mismatched (legacy #104) | legacy `match-filter-*` hidden; Worklist `worklist-filter-*` chips | PARTIAL (alt surface) | match-filter-* exist only inside display:none stub; worklist filter chips are visible + clickable (working alternative) |
| 85 | Full-page GT/OCR text view (S2) | Drawer Text tab → `drawer-text-panel-ground-truth`/`-ocr` | PASS | Both panels visible after clicking `drawer-tab-text` |
| 86 | Tab/Shift-Tab GT navigation (legacy #3) | MultiLineDetail flat input order; WordDetail `onTab`→`walkSibling` | PASS | Row 26 (cross-card Tab) verified live |
| 87 | Edit-word pencil opens word editor (legacy #128) | WordCell `edit-word-button-{l}-{w}` in LineDetail | PASS | Click opened WordDetail "Line 2 · Word 2" |
| 88 | WordEditDialog capabilities (legacy #2, #32–#35, #40–#42, #46–#68, #86–#93 dialog surfaces) | — | N-A (superseded) | Dialog deleted in `c5ddd35` (2026-06-10); equivalents live in WordDetail sections (rows 48–49, 68–73) and are PASS except style-clear (row 41) |
| 89 | Matches pane (WordMatchView inline editing) | `canvas-hidden-stubs` | N-A (retired surface) | Still display:none, driver-contract testids only; S2 decision replaced it with Drawer Text tab + LineDetail/MultiLineDetail editing |
| 90 | Rematch GT (legacy #98) | PageActionsCompact | N-A here | Dimension C scope (page-level op) — left to the C auditor |

## Summary counts

- **PASS: 64** (rows 1–13 sel/GT, 14–20, 23–27, 29–38, 40, 42, 44–45, 47–50, 53–54, 57, 59–60, 63–64, 67–73, 77–78, 80–81, 83, 85–87)
- **PARTIAL: 8** — 28 (multi-line bulk unvalidate race), 46 (charfixer apply not fully driven), 51/52/58 (hardcoded split points), 75 (add-word flaky), 79 (bulk style race), 84 (filter via alt surface)
- **FAIL: 12** — 21, 22 (LineDetail WordCell validate/GT unwired), 39, 41, 43 (style removal missing end-to-end), 55/66 (toolbar resolver silent nulls incl. W→L), 56 (line ctrl-click additive), 61, 62, 65 (stub `/delete` deletes), 74 (erase-to-marker), 76 (main-canvas rebox), 82 (glyph panel, known-blocked)
- **N-A: 3** — 88 (dialog superseded), 89 (matches pane retired), 90 (dim C)

## New findings (not in inventories)

- **`promoteCompleteWordLines`** (ProjectPage.tsx ~757): a word-target drag
  that covers every word of a line promotes the selection to LINE level
  (LineDetail opens instead of MultiWordDetail). Deliberate, but surprising
  if you expected per-word rows; not documented in the inventories.
- **Konva console error on every page load:** `Konva has no node with the
  type div. Group will be used instead.` — something renders a `<div>`
  inside the react-konva tree (3× per load). Benign fallback but a real
  console.error; worth a cleanup issue.
- **Parallel-mutation loops silently lose updates.** `handleBulkValidate`
  (MultiLineDetail.tsx:92) fires `validateLine.mutate` per selected line in
  a sync loop; with 2 lines selected, one POST's effect was intermittently
  lost (observed 2 of 3 runs; both requests sent, no 4xx/5xx in server log,
  final state only reflected the first). Same loop pattern exists in
  `handleBulkCopyOcrToGt`, MultiWordDetail bulk ops, BulkWordActions
  style/component loops, and ProjectPage clear-component loops — all are
  exposed to the same race. Single-mutation paths are unaffected.
- **Style tag REMOVAL is missing end-to-end.** The SPA backend's only style
  route (`POST .../words/{li}/{wi}/style`, words.py:517) calls book-tools
  `apply_style_scope` which is ADD-ONLY (word.py:313–338). book-tools has
  `remove_style_label` (word.py:357) but no SPA route calls it
  (`grep remove_style_label src/` → zero hits). Consequence: all three
  clear-style surfaces silently no-op (toolbar `clear-style-button`,
  WordDetail chip off-toggle, WordCell tag-×). Legacy could remove a style
  via chip × (`_clear_word_tag` → `clear_style_on_word`). Component removal
  is fine (has `enabled:false`). Needs a backend route + frontend off-state
  wiring.
- **Page-scope `/delete` (and `/merge`) are still backend STUBS** —
  lines_paragraphs.py:1764/1785, docstring "Stays a stub… D2/D3", return
  `_stub_page_payload` with HTTP 200. Frontend callers that hit them:
  `WordFooter` local deleteWord, `useDeleteWord` (useWordMutations.ts:395),
  `useDeleteLine` (useLineMutations.ts:105). Result: **Delete word
  (WordFooter), Delete line (LineDetail LineCard), MultiLineDetail card
  Delete and bulk Delete all show a ConfirmDialog and then silently delete
  nothing.** Working delete paths use the real routes: `lines/delete-batch`
  / `paragraphs/delete-batch` (toolbar), `words/delete-batch`
  (MultiWordDetail/BulkWordActions), `/paragraphs/{pi}/delete`
  (ParagraphDetail). Fix = point useDeleteWord/useDeleteLine at the batch
  routes (or implement D2/D3).
- **Toolbar resolver fails silently on null.** `useToolbarDispatch`'s
  `resolveToolbarRequest` returns null when a templated `{lineIndex}` can't
  be filled, and the mutation then resolves `null` with **no toast and no
  request** — while the grid cell is enabled. Affects `line-split-after`,
  `line-split-selected`, `word-w-to-l` whenever the selection is word-level
  (`selected_lines` empty). Cell-enablement logic and resolver requirements
  disagree.
- **Rebox-on-main-canvas has no entry point.** S3 wired `onRebox` +
  `handleRebox` and the canvas handles `mode==="rebox"`, but no component
  ever sets `viewportStore.mode = "rebox"` — the rail-mode subscription
  (PageImageCanvas.tsx:355) maps rail modes only to erase/add-word/select.
  Dead mode.
- **Add-word draw dispatch is flaky.** `POST words/add` works (direct call
  adds a word); the button toggles mode (cursor becomes `copy`); but only
  1 of 3 live drag attempts dispatched the POST, and that one didn't
  persist. Needs a focused e2e + investigation (drag threshold vs.
  pointer-capture in add-word mode).
- **SplitPicker buttons have no testids** (StructureSection.tsx:106) — the
  06-05 inventory cited `glyph-panel-charspan-cell-{i}` for word split, but
  those belong to the unmounted GlyphAnnotationPanel. Driver contract gap
  if the driver ever needs to split words (workaround: `button[title=
  "Split after position N"]`).

## Worktree / branch

- Worktree: `/workspaces/ocr-container/pdomain-ocr-labeler-spa/.claude/worktrees/agent-a2bf727009facfe3a`
- Branch: `worktree-agent-a2bf727009facfe3a` (rebased onto local main `d0ba846`)
- Harness: `/tmp/audit-b/serve.py` (event-store seeded fixture) + scripted
  Playwright batches `/tmp/audit-b/batch*.py`; screenshots `/tmp/audit-b/shots/`.

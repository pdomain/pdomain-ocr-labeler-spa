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

(further rows appended as verified)

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

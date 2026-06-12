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

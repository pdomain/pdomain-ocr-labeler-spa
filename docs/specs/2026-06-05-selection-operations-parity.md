# Selection & Operations Parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan slice-by-slice. Each slice is TDD (failing test first), committed
> independently. Acceptance criteria are written as **observable user behavior** — a control
> is only "done" when it is **visible, enabled, and produces its effect**, verified in a real
> browser. A `data-testid` existing in the DOM is NOT acceptance (see "Why this format").

**Goal:** Make word/line selection produce visible feedback, make multi-selected words
(across blocks) visible with their line context, surface operations on a selection through the
RightPanel, and un-hide the working `ToolbarActionGrid`.

**Architecture:** Selection is client UI state — drive the canvas highlight and all operation
surfaces from the local `selection-store`, not the server `page.selection` round-trip. RightPanel
is the primary operation surface (single + new multi-word view). `ToolbarActionGrid` (already
fully wired) becomes a visible collapsible bar in the canvas column.

**Tech Stack:** React 19, Zustand stores, Konva canvas, TanStack Query, Vitest, Playwright.

---

## Why this format (the "better spec" answer)

The parity gap traces to a spec anti-pattern: the driver-contract specced *"element with
`data-testid=X` must exist"*, and that was satisfied by mounting real components under
`style={{display:"none"}}` (`ProjectPage.tsx:862`). Testids present → CI green → feature
unreachable. **Fix the spec format, not just the bug:** every capability below has an
acceptance criterion phrased as observable behavior, and the Browser Verification milestone
asserts *visible + enabled + effect*. A hidden stub fails this gate by construction.

## Capability matrix (in scope)

| ID | Capability | Scope | Surface | Trigger | Observable acceptance | Current |
|----|-----------|-------|---------|---------|-----------------------|---------|
| SEL-1 | Click selects + highlights | word/line/para/block | Canvas | point-click | A visible highlight box draws around the clicked item immediately | ✗ no highlight |
| SEL-2 | Drag-box select | word | Canvas | mouse drag | Words intersecting the rect become selected + highlighted | ✗ `onBoxSelect` unwired |
| SEL-3 | Granularity governs click target | all | Rail TARGET + header radio | toggle | Changing granularity changes what a click selects; the two controls agree | ✓ bidirectional (block target leaves radio unchanged — no radio counterpart) |
| SEL-4 | Additive select (cross-block) | word | Canvas/list | Ctrl/Cmd-click | Clicking a word in another block ADDS it; prior selection retained | ✗ resets each click |
| SEL-5 | Range / remove from selection | word | Canvas | Shift-click / Shift-drag | Shift extends or removes from the current set | ✗ |
| MUL-1 | Multi-block selection is fully visible | word | RightPanel | ≥2 words selected | Every selected word is listed, grouped by Block → Line, including words from different blocks | ✗ no multi view |
| MUL-2 | Line context shown per word | word | RightPanel | multi-select | Each selected word shows its **line text**, block #, para #, and match status | ✗ |
| MUL-3 | Operations on the multi-selection | word | RightPanel | multi-select | Validate / Unvalidate / Delete / Apply style / Apply component act on all selected words | ⚠ flat strip only |
| GRID-1 | ToolbarActionGrid visible | all | Canvas column | always (collapsible) | The 4-scope × action grid is visible and collapsible, not `display:none` | ✗ hidden |
| GRID-2 | Grid enable/disable reflects selection | all | grid | selection change | Cells enable/disable based on current selection scope | ✓ logic exists (hidden) |
| GRID-3 | Grid cells perform their mutation | all | grid | click cell | Each enabled cell runs its real mutation and the page updates | ✓ wired (hidden) |
| STB-1 | Per-word validate button works | word | WordCell | click | `word-validate-button` toggles validation | ✗ no `onClick` |
| STB-2 | Clear word tag works | word | WordCell | click × on chip | `word-tag-clear-button` removes that style/component chip | ✗ no `onClick` |
| STB-3 | LineDetail's LineCard buttons work | line/word | LineDetail | click | Delete / Copy GT→OCR / Copy OCR→GT / Edit-word perform | ✗ props not passed |
| STB-4 | List row click reveals operations | line | Worklist | click row | Selecting a row opens RightPanel (even if previously collapsed) | ✗ |
| STB-5 | No "coming soon" for implemented scopes | all | RightPanel | select | RightPanel never shows the placeholder for word/line/para/block | ⚠ placeholder shown |

Legend: ✗ broken/missing · ⚠ partial · ✓ implemented (may be hidden).

## Key references (grounded)

- Selection store: `frontend/src/stores/selection-store.ts` — `level`, `path`,
  `selectedWords:[lineIdx,wordIdx][]`, `selectedLines:number[]`, `selectedParagraphs:number[]`;
  setters `selectWord/selectLine/selectPara/selectBlock` **reset** (no accumulation).
- Canvas: `frontend/src/components/.../PageImageCanvas.tsx` — click handlers `:536-558` (wired
  to setters), highlight from server `page.selection` `:392-401` (the bug), `onBoxSelect`
  declared `:150-154` / called `:565-566` but **not passed** by `ProjectPage.tsx:838-845`.
  `resolveModifier()` `:113-121` already maps Ctrl/Meta→toggle, Shift→remove.
- Page data: `PagePayload.line_matches[]` (flat); each `LineMatch` has `line_index`,
  `paragraph_index`, `block_index?`, `ocr_line_text`, `ground_truth_line_text`, `word_matches[]`.
  Word→line→block by scanning `line_matches` (see `selection-walk.ts:91-93`).
- RightPanel routing: `frontend/src/components/right-panel/RightPanel.tsx:105-121` (by `level`).
- BulkWordActions: `frontend/src/components/BulkWordActions.tsx` — reads `selectedWords`, flat ops.
- ToolbarActionGrid: `frontend/src/components/ToolbarActionGrid.tsx` (4×14 grid, fully wired);
  hidden mount `ProjectPage.tsx:862-873`; layout grid `ProjectPage.tsx:919-934`.

---

## Slice A — Selection feedback (SEL-1, SEL-2, SEL-3)

**Files:** `PageImageCanvas.tsx`, `ProjectPage.tsx`, `stores/ui-prefs.ts`, `stores/rail-store.ts`,
their tests under `frontend/src/**/__tests__` (mirror existing test layout).

- Drive the canvas selection-highlight layer from `selection-store` (level/path/selectedWords),
  not from `page.selection`. Acceptance: clicking a word draws a highlight with no network call.
- Pass `onBoxSelect` (and `onRebox`, `onErasePixels`) from `ProjectPage` to `PageImageCanvas`;
  `onBoxSelect(rect, modifier)` computes intersecting words and sets `selectedWords` with
  replace semantics (toggle/remove deferred to Slice B). Acceptance: drag draws + selects.
- Reconcile granularity: header selection-mode radios set `railStore.target` (single source of
  truth the canvas reads); rail-target buttons also update `uiPrefs.selectionMode` so both
  controls agree (bidirectional). Block target has no radio counterpart — clicking block leaves
  `selectionMode` unchanged. Acceptance: SEL-3 row. **DONE.**

**TDD:** test highlight derives from store (mock store, assert overlay rects); test `onBoxSelect`
intersection math; test radio→railStore.target wiring; test rail→radio wiring (bidirectional).
Commit per capability.

## Slice B — Additive multi-select + RightPanel multi-word view (SEL-4, SEL-5, MUL-1..3)

**Files:** `selection-store.ts` (+test), `PageImageCanvas.tsx`, `RightPanel.tsx`,
new `right-panel/MultiWordDetail.tsx` (+test).

- Add `toggleWord(lineIdx, wordIdx, mode: "replace"|"toggle"|"remove")` to the store; wire
  `resolveModifier()` output on single-click and drag-box. Acceptance: SEL-4, SEL-5.
- New `MultiWordDetail` view: render when `selectedWords.length > 1`. Group selected words by
  `block_index` → `line_index`, render each group header (Block N), each line as its
  `ocr_line_text`, and each selected word beneath with OCR/GT + match status. Acceptance:
  MUL-1 (words from ≥2 different blocks all appear), MUL-2 (line text + block/para shown).
- Route it in `RightPanel.tsx` (new branch before single-level routing).
- Operation controls in the multi-view (or reuse BulkWordActions logic): validate/unvalidate/
  delete/apply-style/apply-component over `selectedWords`. Acceptance: MUL-3.

## Slice C — Un-hide ToolbarActionGrid (GRID-1..3)

**Files:** `ProjectPage.tsx` (+test).

- Remove the `display:none` wrapper at `:862`; mount `ToolbarActionGrid` visibly in the canvas
  column above the image, wrapped in a collapsible container (chevron toggle, default collapsed
  or open per a `uiPrefs` flag). Preserve all existing `data-testid`s. Acceptance: GRID-1.
- Keep existing props (`selection`, `pageData`, handlers) — wiring already complete. Add a test
  asserting the grid is rendered **without** `display:none` and a cell click still dispatches.
  Acceptance: GRID-2, GRID-3.

## Slice D — Wire stub buttons + discoverability (STB-1..5)

**Files:** `WordCell.tsx`, `LineCard.tsx`, `right-panel/LineDetail.tsx`, `RightPanel.tsx`,
`Worklist.tsx` / row component, tests.

- STB-1: `word-validate-button` → call validate mutation for `[lineIdx,wordIdx]`.
- STB-2: `word-tag-clear-button` → clear that style/component chip via existing clear mutation.
- STB-3: pass `onDelete`/`onCopyGtToOcr`/`onCopyOcrToGt`/`onEditWord` into `LineCard` from
  `LineDetail` (handlers already exist in `LineDetail` footer).
- STB-4: Worklist row click also sets `uiPrefs.rightPanelOpen = true`.
- STB-5: replace the RightPanel `LEVEL_PLACEHOLDER` for word/line/para/block with the real
  views (placeholder only for `level === "none"`).

Each = failing test asserting the click performs the effect, then wire, then pass, then commit.

## Browser Verification milestone (MANDATORY — FastAPI+SPA)

Playwright e2e against the running server (`frontend/e2e/` or `tests/e2e/`, per repo convention),
asserting observable behavior — the anti-surface gate:

- **App loads:** ProjectPage renders, no `console.error` resource failures.
- **SEL-1:** click a word → a selection-highlight element is **visible** on the canvas.
- **SEL-4 / MUL-1+2:** select a word, Ctrl-click a word in a different block → RightPanel multi
  view shows **both** blocks, each word under its **line text**.
- **GRID-1+3:** ToolbarActionGrid is **visible** (not `display:none`); clicking an enabled
  validate cell changes a word's validated state.
- **STB-1:** per-word validate button toggles validation (visible state change).
- Wire `make e2e` (or `make e2e-browser`) into `make ci` if not already.

## Self-review notes

- Every capability-matrix row maps to a slice task above. No row left unimplemented.
- Acceptance is observable behavior, not testid presence — directly closes the anti-pattern.
- Types/fields referenced (`line_matches`, `block_index`, `ocr_line_text`, `selectedWords`,
  `resolveModifier`, `toggleWord`) are grounded in real code (see references).
- FastAPI+SPA browser-verification milestone present.

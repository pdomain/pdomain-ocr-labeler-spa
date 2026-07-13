---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-07-13
---

# 06 — Toolbar Action Grid

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#16

The 14-column grid above the matches view, with one row per scope
(page / paragraph / line / word). Plus the Apply Style row and the
Add Word row.

> Cross-refs:
> Legacy implementation —
> `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/word_match_toolbar.py`
> Legacy testid catalogue —
> `pd-ocr-labeler/docs/architecture/ui-action-buttons.md` §4a-4d
> Backend endpoints — [`02-backend.md`](02-backend.md) §5.4–§5.7
> Allowed labels —
> `pdomain_book_tools.ocr.label_normalization.ALLOWED_TEXT_STYLE_LABELS`,
> `ALLOWED_WORD_COMPONENT_LABELS`

---

## 1. Action grid layout

A 14-column grid; row labels in column 1; one row per scope:

```
| Scope | Merge | Refine | E+R | Expand | SplitAfter | SplitSelected | W→L | →Para | GT→OCR | OCR→GT | Validate | Unvalid | Delete |
|-------|-------|--------|-----|--------|------------|---------------|-----|-------|--------|--------|----------|---------|--------|
| Page  |       |   ✔    |  ✔  |   ✔    |            |               |     |       |   ✔    |   ✔    |    ✔     |    ✔    |        |
| Para  |  ✔    |   ✔    |  ✔  |   ✔    |     ✔      |       ✔       |     |       |   ✔    |   ✔    |    ✔     |    ✔    |   ✔    |
| Line  |  ✔    |   ✔    |  ✔  |   ✔    |     ✔      |       ✔       |     |   ✔   |   ✔    |   ✔    |    ✔     |    ✔    |   ✔    |
| Word  |       |   ✔    |  ✔  |   ✔    |            |               |  ✔  |   ✔   |   ✔    |   ✔    |    ✔     |    ✔    |   ✔    |
```

`✔` = the legacy has this button; cells with `–` are absent (button
hidden but DOM-present with `data-testid-stub="true"`).

The toolbar lives inside `TextTabs` above the tab switcher. Each
button has `data-testid="toolbar-{scope}-{action}"`.

### Column abbreviations

| Column | Action |
|---|---|
| Merge | Merge selected (≥2). Lines/Paragraphs only. Words merge in dialog. |
| Refine | Refine bboxes (no expand) |
| E+R | Expand-then-refine bboxes |
| Expand | Expand-only bboxes (`expand_to_content` etc.) |
| SplitAfter | Split parent after this child |
| SplitSelected | Extract selected children to new parent (or split parent into selected/unselected) |
| W→L | Word→Line: extract selected words to new line |
| →Para | Promote selected lines/words to new paragraph |
| GT→OCR | Copy GT into OCR text fields |
| OCR→GT | Copy OCR into GT text fields |
| Validate | Mark validated |
| Unvalid | Clear validation |
| Delete | Delete selected |

### Disabled-state rules (from legacy `update_button_state:742`)

| Cell | Enabled when |
|---|---|
| Page row | Always (operates on the whole page) |
| Paragraph row | At least one paragraph selected |
| Line row | At least one line selected |
| Word row | At least one word selected |
| Merge cell | ≥2 of the scope selected AND callbacks present |
| SplitAfter (line) | ≥1 word in a single line selected |
| SplitSelected (line) | ≥1 word in a single line selected |
| W→L | ≥1 word selected, all in the same line |
| Word→Para | ≥1 word/line selected |
| Validate | ≥1 of scope selected, AND not all already validated |
| Unvalid | ≥1 of scope selected, AND ≥1 already validated |
| Delete | ≥1 selected |
| GT→OCR / OCR→GT (line/paragraph/word) | ≥1 of scope selected |
| GT→OCR / OCR→GT (page) | Always |

The disabled-state computation lives in
`useToolbarButtonStates(selection)` — pure function, fully tested.

---

## 2. Backend mapping

Each cell click POSTs one of:

| Action | Endpoint | Body |
|---|---|---|
| `page-merge` | (none — disabled) | — |
| `page-refine` | `/api/.../refine` | `{scope:"page", mode:"refine"}` (queues job) |
| `page-expand-refine` | `/api/.../refine` | `{scope:"page", mode:"expand_then_refine"}` (queues job) |
| `page-expand` | `/api/.../refine` | `{scope:"page", mode:"expand_only"}` (queues job) |
| `page-gt-to-ocr` | `/api/.../lines/copy-gt-batch` | `{line_indices: ALL, direction:"gt_to_ocr"}` |
| `page-ocr-to-gt` | `/api/.../lines/copy-gt-batch` | (mirror) |
| `page-validate` | `/api/.../words/validate-batch` | `{scope:"page", validated:true}` |
| `page-unvalidate` | (mirror) | |
| `paragraph-merge` | `/api/.../paragraphs/merge` | `{paragraph_indices: selected}` |
| `paragraph-refine` | `/api/.../refine` | `{scope:"paragraph", paragraph_indices, mode:"refine"}` |
| (… all scope-action combinations follow the same pattern) | | |
| `word-merge` | (hidden — done in dialog) | — |
| `word-refine` | `/api/.../refine` | `{scope:"word", word_indices, mode:"refine"}` |
| `word-w-to-l` | `/api/.../lines/{n}/split-with-selected-words` | `{word_indices, mode:"extract_to_new"}` |
| `word-to-para` | `/api/.../paragraphs/group-selected-words` | `{word_indices}` |
| `word-validate` | `/api/.../words/validate-batch` | `{scope:"word", word_indices, validated:true}` |
| `word-delete` | `/api/.../words/delete-batch` | `{word_indices}` |

The full mapping lives in `frontend/src/lib/toolbarMapping.ts`,
keyed by `${scope}-${action}`. Tests assert that every cell in the
grid has an entry.

---

## 3. Apply Style row

Below the action grid, a horizontal row:

```
[Style ▼] [Scope ▼] [Apply Style]   [Component ▼] [Apply Component] [Clear Component]
```

| Element | data-testid | Notes |
|---|---|---|
| Style select | `apply-style-select` | shadcn `<Select />`, options from `ALLOWED_TEXT_STYLE_LABELS` |
| Scope select | `scope-select` | options: `whole`, `part` |
| Apply Style button | `apply-style-button` | POST `/api/.../words/style-batch {style, scope, word_keys}` |
| Component select | `apply-component-select` | options from `ALLOWED_WORD_COMPONENT_LABELS` |
| Apply Component button | `apply-component-button` | POST `/api/.../words/component-batch {component, enabled:true, word_keys}` |
| Clear Component button | `clear-component-button` | POST `/api/.../words/component-batch {component, enabled:false, word_keys}` |

`word_keys` is taken from `useSelectionStore.selectedWords`. If empty,
all three Apply/Clear buttons are disabled.

Style values (verbatim from `ALLOWED_TEXT_STYLE_LABELS`):
`italics`, `small_caps`, `blackletter`, `all_caps`, `bold`,
`underline`, `strikethrough`, `monospace`, `handwritten`.

Component values: `footnote_marker`, `drop_cap`, `subscript`,
`superscript`, `header`, `footer`, `marginalia`, `abandoned`.

Important: the **legacy** routes the first three styles
(`italics`/`small_caps`/`blackletter`) through a legacy 5-bool API.
The SPA backend collapses this into a single `apply_style` API; the
SPA frontend doesn't need to know about the legacy split. ([Q14
Reso](../../OPEN_QUESTIONS.md))

---

## 4. Add Word row

Below the Apply Style row:

```
[Add Word]
```

| Element | data-testid | Notes |
|---|---|---|
| Add Word button | `word-add-button` | Toggle: when pressed, viewport mode = `add-word`. Press again to leave. |

When the user drags on the viewport in add-word mode, the bbox is
sent to `POST /api/.../words/add` with `text=""`. Mode persists for
multi-add until clicked again. ([04-image-viewport.md](04-image-viewport.md) §4.3)

---

## 5. Selection-state syncing

The toolbar's enabled-states derive from `useSelectionStore`. The
store is updated:

- On viewport drag (M4).
- On clicking a paragraph/line/word checkbox.
- On clicking inside a paragraph/line/word bbox.
- After a multi-word mutation reduces the number of words (server
  echoes the new selection set in `PagePayload.selection`).

The store is NOT persisted — opening a fresh tab starts with empty
selection.

---

## 6. Notifications + jobs

Long-running actions (page-scope refine in particular) return `202`
with a `job_id`. The toolbar shows a subtle progress indicator on the
scope row while the job runs.

```
Page row: [bar progress 60%]   when refine is mid-flight
```

Implementation: subscribe to `useJobProgress(jobId)`. While
`status === "running"`, show a slim line under the row; on completion,
toast.success and dismiss.

---

## 7. Hotkeys

When focus is in the matches view, the toolbar listens for:

- `R` — Refine on current scope
- `Shift+R` — Expand-then-refine on current scope
- `D` — Delete selected (with confirm)
- `V` — Validate selected
- `U` — Unvalidate selected
- `M` — Merge selected (when applicable)

These are new ([D-022](../../specs/17-decisions.md)). Full list in
[`12-hotkeys-a11y.md`](12-hotkeys-a11y.md).

---

## 8. Tests

- Unit: `useToolbarButtonStates.test.ts` — exhaustive over selection
  shapes (empty, 1 word, 2 words, mixed lines, etc.).
- Unit: `toolbarMapping.test.ts` — every cell maps to a real endpoint.
- E2E: `test_toolbar_page_actions.py` — port full from legacy.
- E2E: `test_toolbar_paragraph_actions.py` — same.
- E2E: `test_toolbar_line_actions.py` — same.
- E2E: `test_toolbar_word_actions.py` — same.

These four are the most important conformance tests — the legacy
toolbar is the most-used surface and the driver agent's main entry
point.

---

## 9. Open issues

- **`scope_select="part"` semantics.** When the user picks "part"
  scope and applies italics, the legacy applies it to the *first half*
  of the selected text, not the whole word. The SPA preserves this —
  but it's a weird UX. Consider replacing with explicit `part_left` /
  `part_right` options in v2. Out of scope for v1.
- **Disabled-state lag.** The disabled-state recomputes synchronously
  on every selection change. With ~30 buttons × ~50 selection events
  per second during a drag, this could matter. Profile in M6 and
  optimise with `useMemo` on selection-shape signature if needed.

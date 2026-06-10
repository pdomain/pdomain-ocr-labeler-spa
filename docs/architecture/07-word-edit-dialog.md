# 07 — Word Edit Dialog

> **Superseded 2026-06-10**: the word-edit dialog (`WordEditDialog` component and
> associated `WordActionRows`, `WordImageCanvas`, `WordTagRow`, `WordRefineNudgeRows`,
> `useDialogHotkeys`) was replaced by the right-panel `WordDetail` + per-section
> components (`EraseCanvas`, `ReboxCanvas`, `CharFixerSection`, `ErasePixelsSection`,
> `ReboxSection`). See [`26-right-panel-detail.md`](26-right-panel-detail.md) for the
> current design.
>
> **Status**: Superseded — **Last updated**: 2026-06-10 — **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#18

A modal dialog focused on a single word: preview, image-with-marker,
merge/split/delete, crop, refine, fine-tune nudge, drag-erase, tag
chips. The most behaviourally complex single component in the labeler.

> Cross-refs:
> Legacy implementation —
> `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/word_edit_dialog.py`
> Backend endpoints — [`02-backend.md`](02-backend.md) §5.4
> Word-image overlay — [`04-image-viewport.md`](04-image-viewport.md) §4
> Hotkeys — [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md)

---

## 1. Trigger + lifecycle

Triggered by the `edit-word-button-{l}-{w}` button in the matches view
(see [`05-word-matches.md`](05-word-matches.md) §4.row1). The dialog
mounts with `target = {lineIdx, wordIdx}`.

Implementation: shadcn `<Dialog />` (Radix). When closed via the
top-right ✓ ("Apply & Close") it commits any pending erase rects and
nudges. When closed via × it discards.

The dialog **does not auto-close** on apply. A user can apply
multiple changes (style, component, nudge) and close at the end via
✓ to commit, or × to discard. The legacy behaves the same way.

---

## 2. Header

```
┌──────────────────────────────────────────────────┐
│ Edit Line N, Word M                       [✓] [×] │
└──────────────────────────────────────────────────┘
```

| Element | data-testid |
|---|---|
| Title label | `dialog-header-label` |
| Apply & Close (check icon) | `dialog-apply-close-button` |
| Close (× icon) | `dialog-close-button` |

`Apply & Close`: emit any pending nudge / pending erase rects, then close.
`Close`: discard pending changes, close.

---

## 3. Body sections

### 3.1 Preview row (3 columns)

```
┌─────────────────┬─────────────────┬─────────────────┐
│ Previous word   │ Current word    │ Next word       │
│ (read-only img) │ (interactive)   │ (read-only img) │
└─────────────────┴─────────────────┴─────────────────┘
```

| Element | data-testid |
|---|---|
| Previous preview column | `dialog-previous-preview-column` |
| Current preview column | `dialog-current-preview-column` |
| Next preview column | `dialog-next-preview-column` |

Previous/Next are scoped to the same line — wraps at line boundary.
Clicking previous/next switches the dialog target without closing it
(equivalent to closing+reopening on the new word).

### 3.2 Current word section

```
[tag chip slot] [tag chip slot] ...                   [zoom: 1x 2x 5x 10x]
┌───────────────────────────────────────────────────┐
│   [interactive word image with click-marker]       │
│                                                    │
└───────────────────────────────────────────────────┘
   OCR text:    "abandoned"
   Ground truth:[input field      ]
```

| Element | data-testid |
|---|---|
| Tag chip container | `dialog-tag-chips-slot` |
| Zoom toggle | `dialog-current-zoom-toggle` |
| Interactive image | `dialog-current-image` |
| Click marker (overlay) | `dialog-current-marker` |
| OCR text label | `dialog-current-ocr-text` |
| GT input | `dialog-gt-input` |

#### Tag chips
Style chips and component chips for this word. Same colors as the
matches view ([`05-word-matches.md`](05-word-matches.md) §4 row3).
Hovering reveals × to clear; clicking the chip itself opens a popover
to switch between scopes (`whole` / `part`).

#### Zoom toggle
Four options: 1×, 2×, 5×, 10×. Default 2×. Stored in
`usePrefsStore.zoomLevel`. The interactive image scales by this
factor.

#### Interactive image
A `<Stage>` (Konva) containing:

- The word's bbox slice from the page's `original` cached image.
- Layer for overlay markers/rects (`<DialogImageOverlay />`).

Mouse interactions:

- **mouseenter** / **mousemove**: show a *vertical guide line* at the
  cursor x-position (dashed gray).
- **click**: place / replace the persistent click marker (solid blue,
  vertical line through the word).
- **mouseleave**: hide the guide.

When erase mode is active (toggled via Esc-to-marker, see §4.6), the
mouse handlers switch to:

- **mousedown** / **mousemove** / **mouseup**: draw an erase rect
  staged in the dialog state. Multiple erase rects can stack.

The click marker drives crop (§4.4) and split (§4.3) operations —
both use the marker's x-position as the split/crop x-coordinate
(in source pixels).

#### OCR + GT

- `dialog-current-ocr-text`: read-only label showing `word.ocr_text`.
- `dialog-gt-input`: text input pre-filled with `word.ground_truth_text`.
  Hotkey: `Enter` commits via `POST /api/.../words/{l}/{w}/ground-truth`.

### 3.3 Style/Scope/Component row

```
[Style ▼] [Scope ▼] [Component ▼] [Apply Style] [Apply Component] [Clear Component]
```

| Element | data-testid |
|---|---|
| Style select | `dialog-style-select` |
| Scope select | `dialog-scope-select` |
| Component select | `dialog-component-select` |
| Apply Style | `dialog-apply-style-button` |
| Apply Component | `dialog-apply-component-button` |
| Clear Component | `dialog-clear-component-button` |

Style values: same as toolbar Apply Style row (see
[`06-toolbar-actions.md`](06-toolbar-actions.md) §3). Apply targets
**this word only**; the toolbar's row targets the selection.

### 3.4 Merge/Split/Delete row

```
[Merge Prev] [Merge Next] [H] [V] [Delete]
```

| Element | data-testid |
|---|---|
| Merge Prev | `dialog-merge-prev-button` |
| Merge Next | `dialog-merge-next-button` |
| Split H | `dialog-split-h-button` |
| Split V | `dialog-split-v-button` |
| Delete | `dialog-delete-word-button` |

- **Merge Prev**: POST `/api/.../words/{l}/{w}/merge {direction:"left"}`.
- **Merge Next**: POST `/api/.../words/{l}/{w}/merge {direction:"right"}`.
- **H**: split horizontally at the click marker's x-fraction. POST
  `/api/.../words/{l}/{w}/split {direction:"horizontal", x_fraction:F}`.
- **V**: split vertically and reassign to closest line. POST
  `/api/.../words/{l}/{w}/split {direction:"vertical", x_fraction:F}`.
- **Delete**: DELETE `/api/.../words/{l}/{w}`.

Disabled when the prerequisite isn't met (e.g. Merge Prev disabled
when this is the first word in the line).

### 3.5 Crop row

```
[Crop Above] [Crop Below] [Crop Left] [Crop Right]
```

Each uses the click marker's `(x, y)` as the crop coordinate. POST
`/api/.../words/{l}/{w}/crop {side, marker_x, marker_y}`.

### 3.6 Refine row

```
[Refine] [Expand + Refine]
```

- **Refine**: POST `/api/.../words/{l}/{w}/refine-bbox` (synchronous).
  Updates the word's bbox in the response.
- **Expand + Refine**: POST `/api/.../words/{l}/{w}/expand-and-refine-bbox`.

These return updated `WordMatch`; SPA patches the cache. Dialog
re-renders with the new bbox preview.

### 3.7 Nudge grid

A 3×3 grid (8 active cells, centre is empty) for fine-tune bbox
edges:

```
       [↑+]
[←-]  [center]  [→+]
       [↓-]
```

…actually 4 edges × 2 directions = 8 buttons. Layout:

```
        Top edge:   [-]  [+]
Left edge: [-]  [+]      Right edge: [-]  [+]
        Bottom edge:[-]  [+]
```

testids: `dialog-nudge-{edge}-{sign}-button`, where edge ∈
`left|right|top|bottom`, sign ∈ `minus|plus`.

Click count is **accumulated locally** (`pendingNudge: {l, r, t, b}`).
Apply emits a single POST with the totals. Reset zeroes them.

Step size: `bbox_nudge_step_px = 5` (configurable via setting; not
exposed in UI for v1).

Direction semantics (matches legacy):

- `nudge-left-minus` → move left edge inward (shrink left)
- `nudge-left-plus` → move left edge outward (expand left)
- `nudge-right-minus` → move right edge inward (shrink right)
- `nudge-right-plus` → expand right
- `nudge-top-minus` → shrink top (down)
- `nudge-top-plus` → expand top (up)
- `nudge-bottom-minus` → shrink bottom (up)
- `nudge-bottom-plus` → expand bottom (down)

### 3.8 Apply / Reset row

```
[Reset] [Apply] [Apply + Refine]
```

| Element | data-testid |
|---|---|
| Reset | `dialog-reset-button` |
| Apply | `dialog-apply-button` |
| Apply + Refine | `dialog-apply-refine-button` |

- **Reset**: clear pending nudge + erase rects.
- **Apply**: POST `/api/.../words/{l}/{w}/nudge {l, r, t, b, refine_after:false}`,
  AND if any erase rects exist POST one each
  `/api/.../words/{l}/{w}/erase-pixels {bbox}`.
- **Apply + Refine**: same, with `refine_after:true` on the nudge call.

After apply, the dialog re-renders with the updated word state. The
click marker is preserved; pending nudge resets to zero.

---

## 4. Behavioural details

### 4.1 Click marker

A persistent vertical line through the word. Clicking anywhere on the
image places it (or replaces if already placed). Click on the marker
itself removes it (Escape also clears).

The marker's x-position is the source-pixel x-fraction of the bbox:
`marker_x_fraction = (click_x_in_image - bbox.x) / bbox.width`. This
is what `dialog-split-h-button` uses.

### 4.2 Hover guide

A dashed gray vertical line at the current cursor x-position when
hovering. Disappears on mouseleave. Provides visual feedback for where
a click would place the marker.

### 4.3 Drag-erase

Activated via a small `Erase` toggle in the image's chrome (testid
`dialog-erase-toggle`). When on:

- mousedown starts a drag rect.
- mousemove resizes it.
- mouseup commits it to the staged-erase list.
- Each staged rect renders semi-transparent red over the image.
- Click on a staged rect to remove it.

Apply (or Apply+Refine) POSTs each staged rect as
`/api/.../words/{l}/{w}/erase-pixels`.

### 4.4 Crop semantics

Click marker placed; click `Crop Above`. The new bbox = current bbox
clipped above marker_y. Likewise for Below / Left / Right. POST
`/api/.../words/{l}/{w}/crop {side, marker_x, marker_y}`.

### 4.5 Style/Component application

Style+Scope→Apply: POST
`/api/.../words/{l}/{w}/style {style, scope}`. Scope `whole` applies
to the whole word; `part` applies to the half nearest the click
marker (left half if marker is left of bbox center, right half
otherwise) — semantics inherited from legacy.

Component → Apply / Clear: POST
`/api/.../words/{l}/{w}/component {component, enabled}`.

### 4.6 Hotkeys (dialog scope)

| Key | Action |
|---|---|
| `Enter` (in GT input) | Commit GT |
| `Esc` | Close dialog (discard pending) |
| `Shift+Enter` (anywhere) | Apply & Close (commit pending) |
| `Tab` / `Shift+Tab` | Standard form navigation |
| `←` / `→` | Previous/Next word in line |
| `Shift+←` / `Shift+→` | Nudge left edge (← shrinks, → expands) |
| `Shift+↑` / `Shift+↓` | Nudge top edge |
| `Ctrl+←` / `Ctrl+→` | Nudge right edge |
| `Ctrl+↑` / `Ctrl+↓` | Nudge bottom edge |
| `R` | Refine |
| `Shift+R` | Expand + Refine |
| `M` | Apply current Style+Scope |
| `Shift+M` | Apply current Component |
| `Delete` | Delete word (with confirm) |

These are new ([D-022](../../specs/17-decisions.md)).

---

## 5. State management

The dialog has its own local state owned by `useWordEditDialog()` hook:

```ts
{
  pendingNudge: { left: 0, right: 0, top: 0, bottom: 0 },
  pendingEraseRects: BBox[],
  markerX: number | null,         // source-pixel x
  markerY: number | null,         // source-pixel y
  hoverX: number | null,          // for the dashed guide
  ...
}
```

Server state for the word comes from `useQueryClient.getQueryData`
on the `["page", projectId, pageIndex]` cache. The dialog reads
the latest WordMatch from there; mutations patch the cache.

---

## 6. Performance

- Konva Stage in dialog is small (`bbox.width × zoomLevel` × 2).
  Re-renders are cheap.
- The dialog mounts on demand; not part of the main render tree.
- Closing the dialog discards local state + click marker.

---

## 7. Tests

- Unit: `WordEditDialog.test.tsx` — render with target word, every
  testid present.
- Unit: `useNudge.test.ts` — accumulator semantics, reset, apply.
- Unit: `dragErase.test.ts` — staged rect lifecycle.
- E2E: `test_word_edit_dialog.py` — port full from legacy +:
  - Click marker placement.
  - Crop above/below/left/right.
  - H split: marker at midpoint, click H, see two words appear in
    matches view.
  - V split: same.
  - Nudge: click left+, see bbox grow on left edge.
  - Apply+Refine: pending nudge applied + refine; bbox tightens.
  - Apply&Close: committed; dialog gone.
  - Esc / × discards pending.

---

## 8. Open issues

- **Multi-line tag chips.** Words with many active styles (italics +
  small_caps + handwritten + …) wrap chips. Acceptable.
- **Marker placement on edges.** Clicking exactly at bbox boundaries
  produces edge cases (x_fraction 0 or 1). The legacy clamps; the SPA
  follows.
- **Image zoom + crop**. When zoom is 10× and the dialog is narrow,
  the image overflows. CSS `overflow: auto` on the image container
  handles it but loses the ability to nudge from far edges. Match
  legacy: scrollable container, no special UI. Improve in v2.

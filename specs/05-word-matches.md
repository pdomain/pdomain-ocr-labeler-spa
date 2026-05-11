# 05 — Word Matches View (Right Pane)

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#14

The right pane shows OCR-vs-GT comparisons line by line. It's the
densest piece of UI in the labeler and the most performance-sensitive.

> Cross-refs:
> Legacy implementation —
> `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/text_tabs.py`,
> `word_match.py`, `word_match_renderer.py`, `word_match_gt_editing.py`.
> Match-status semantics —
> `pd-ocr-labeler/pd_ocr_labeler/operations/ocr/word_operations.py:classify_match_status`
> Wire shapes — [`01-data-models.md`](01-data-models.md) `LineMatch` /
> `WordMatch`

---

## 1. Layout

```
<TextTabs>                                  (components/TextTabs.tsx)
  <ToolbarActionGrid />                     (see 06-toolbar-actions.md)
  <ApplyStyleRow />
  <AddWordRow />
  <Tabs defaultValue="matches">
    <TabsTrigger value="matches">           data-testid="text-tab-matches"
    <TabsTrigger value="ground-truth">      data-testid="text-tab-ground-truth"
    <TabsTrigger value="ocr">               data-testid="text-tab-ocr"
    <TabsContent value="matches">
      <WordMatchView />                     ← THIS SPEC
    <TabsContent value="ground-truth">
      <PlainTextarea readOnly value={page.page_text_gt} />
    <TabsContent value="ocr">
      <PlainTextarea readOnly value={page.page_text_ocr} />
```

The Matches tab is the default. Plain textarea tabs replace legacy
CodeMirror ([D-008](17-decisions.md)).

---

## 2. Filter toggle

Single segmented control above the line list:

| Option | data-testid | Filter rule |
|---|---|---|
| Unvalidated Lines (default) | `match-filter-unvalidated` | `!line.is_fully_validated` |
| Mismatched Lines | `match-filter-mismatched` | `line.overall_match_status in {"mismatch", "unmatched_ocr", "unmatched_gt"}` |
| All Lines | `match-filter-all` | `true` |

State: `usePrefsStore.lineFilter`. Sent to the server as the
`?line_filter=...` query param so the backend can return only the
filtered subset.

---

## 3. Virtualisation

A page can have up to 200 lines × ~20 words. Render via
`@tanstack/react-virtual`:

```tsx
const virtualizer = useVirtualizer({
  count: filteredLines.length,
  getScrollElement: () => scrollRef.current,
  estimateSize: () => 80,         // typical card height
  overscan: 3,
});
```

Estimated size 80px gets refined per-card via `measureElement`. Only
visible cards mount, plus 3 ahead/behind. **Crucially**, when the
filter changes (Unvalidated → All), only the cards in the new viewport
hydrate — the others are virtualised away.

The legacy `_build_word_match_page_key` SHA1 fingerprint isn't needed
on the SPA: react-query caches by `(projectId, pageIndex, filter)`,
and React reconciliation keys per word-id avoid full rebuilds.

---

## 4. Line card

`<LineCard />` per filtered line. Components:

```
<div data-testid="line-card-{n}" className="...">
  <LineHeader />          ← status colors, line label, paragraph label,
                            count chips, GT→OCR / OCR→GT, validate, delete
  <WordTable />           ← per-word columns
</div>
```

### Line header

Background by `overall_match_status`:

| Status | Tailwind class |
|---|---|
| `exact` | `bg-green-100` |
| `fuzzy` | `bg-yellow-100` |
| `mismatch` | `bg-red-100` |
| `unmatched_ocr` | `bg-gray-100` |
| `unmatched_gt` | `bg-blue-100` |

Header row contents:

```
[  ] Line 5  Paragraph 2  📊 ✓3 ⚠1 ✗2  🔵0 ⚫0   [✓ 5/6]   [GT→OCR] [OCR→GT] [Validate] [Delete]
└┬┘ └─────┘ └──────────┘ └────────────────────┘ └─────────┘ └──────────┘ └────────┘ └──────┘
 │
 └─ paragraph checkbox (only on first line of each paragraph)
```

Icons:

- `📊` chart-bar from `lucide-react`.
- `✓` `check-circle` (green).
- `⚠` `alert-triangle` (yellow).
- `✗` `x-circle` (red).
- `🔵` `circle-dot` (blue).
- `⚫` `circle` (gray).

`Validate` button label flips to `Unvalidate` when
`line.is_fully_validated`. Tooltip: "Validate N words" / "Unvalidate
N words".

`GT→OCR` / `OCR→GT` buttons hidden when `overall_match_status === "exact"`.

### Word table

A `display: grid` with one column per word. Columns auto-fit. Each
column has 5 rows:

```
┌────────────────────┐
│ [ ] [edit] [✓]      │ ← row 1: selection cell
├────────────────────┤
│  word image slice   │ ← row 2: image cell
├────────────────────┤
│ "OCR text"  [it][sc]│ ← row 3: OCR + tag chips
├────────────────────┤
│ [GT input        ]  │ ← row 4: GT input
├────────────────────┤
│  ✓ status icon      │ ← row 5: status cell
└────────────────────┘
```

#### Row 1 — Selection cell

Three controls per word:

- Word checkbox (testid `word-checkbox-{l}-{w}`). Bound to
  `useSelectionStore.selectedWords`.
- Edit button (testid `edit-word-button-{l}-{w}`). `lucide-react Pencil`
  icon. Opens the `<WordEditDialog />`.
- Per-word validate (testid `word-validate-button-{l}-{w}`). Green
  filled-check when validated, gray check otherwise. Toggles via
  optimistic mutation.

#### Row 2 — Image cell

Two variants:

- **Unmatched-GT** word (`match_status === "unmatched_gt"`): show a
  `Type` (lucide) icon in blue (`text-blue-600`). No image.
- **Other**: CSS-clip the page's `original` cached image at the
  word's bbox.

```tsx
<div
  data-testid={`word-image-cell-${l}-${w}`}
  className="overflow-hidden"
  style={{
    width: word.bbox.width * scale,
    height: word.bbox.height * scale,
    backgroundImage: `url(${page.image_url})`,
    backgroundPosition: `-${word.bbox.x * scale}px -${word.bbox.y * scale}px`,
    backgroundSize: `${page.encoded.display_width}px ${page.encoded.display_height}px`,
  }}
/>
```

This lets all words on a page share one cached image — no per-word
image fetches. Same algorithm as legacy
`WordMatchBbox.get_word_image_slice:42`.

#### Row 3 — OCR text + tag chips

```tsx
<div data-testid={`ocr-text-label-${l}-${w}`} className="font-mono">
  {word.ocr_text}
</div>
<div className="flex flex-wrap gap-1">
  {word.text_style_labels.map((s) => <StyleChip key={s} word={word} label={s} />)}
  {word.word_components.map((c) => <ComponentChip key={c} word={word} label={c} />)}
</div>
```

Tooltip on the OCR label: match status, fuzz score, OCR/GT diff.
Implemented with shadcn `<Tooltip />`.

Chip styles per [`04-image-viewport.md`](04-image-viewport.md) §2
(style chips blue family, component chips green family). Each chip has
a hover-revealed × button (testid `word-tag-clear-button-{l}-{w}-{label}`)
that POSTs `style` or `component` with the cleared value.

#### Row 4 — GT input

```tsx
<input
  type="text"
  data-testid={`gt-text-input-${l}-${w}`}
  className="font-mono text-sm w-auto min-w-[40px]"
  value={draft}
  onChange={...}
  onBlur={() => commit(draft)}
  onKeyDown={(e) => {
    if (e.key === "Enter") { e.preventDefault(); commit(draft); }
    else if (e.key === "Tab") {
      e.preventDefault();
      commit(draft);
      focusNeighbour(e.shiftKey ? "prev" : "next");
    }
  }}
  size={Math.max(8, draft.length + 2)}
/>
```

`commit(text)` POSTs `update-ground-truth`. Optimistic via
`useMutation.onMutate` — patches the cached `PagePayload`.

Tab navigation: walks the flat list of GT inputs in reading order
(line by line, then word by word). Implemented with a `useTabNavigation`
hook backed by a refs map keyed by `${l}:${w}`.

#### Row 5 — Status cell

Icon + optional fuzz score:

| Status | Icon | Color class |
|---|---|---|
| exact | `CheckCircle` | `text-green-600` |
| fuzzy | `AlertTriangle` | `text-yellow-600` |
| mismatch | `XCircle` | `text-red-600` |
| unmatched_ocr | `HelpCircle` | `text-gray-500` |
| unmatched_gt | `Info` | `text-blue-600` |

Fuzz score (when not exact) shown as a tiny text below the icon:
`fuzz_score.toFixed(2)`.

---

## 5. Performance details

- **Memoise per-word components** with `React.memo` keyed on
  `word.word_id` (or `${l}:${w}` if id missing) so a single edit
  doesn't re-render all 4000 word cells.
- **Avoid heavy `useEffect`s in `<WordCell />`.** All work happens in
  the parent's `useQuery` hook; `<WordCell />` is presentational.
- **Image cell uses CSS background**, not `<img>`, so changing the
  bbox doesn't trigger a network fetch.
- **Filter changes** are server-side: SPA passes `line_filter` as a
  query param; backend returns only matching `LineMatch`es. This
  halves wire size on the common case.

---

## 6. Mutations

| Action | Endpoint | Returns |
|---|---|---|
| Inline GT edit | `POST /api/.../words/{l}/{w}/ground-truth` | `WordMatch` |
| Toggle word validate | `POST /api/.../words/{l}/{w}/validate` | `WordMatch` |
| Toggle line validate | `POST /api/.../lines/{n}/validate` | `PagePayload` |
| GT→OCR (line) | `POST /api/.../lines/{n}/copy-gt {direction:"gt_to_ocr"}` | `PagePayload` |
| OCR→GT (line) | `POST /api/.../lines/{n}/copy-gt {direction:"ocr_to_gt"}` | `PagePayload` |
| Delete (line) | `POST /api/.../lines/delete-batch {line_indices: [n]}` | `PagePayload` |
| Clear chip | `POST /api/.../words/{l}/{w}/style {style: "x", scope:"clear"}` | `WordMatch` |

Optimistic-update semantics:

- Single-word mutations: patch the WordMatch in the cache directly.
- Multi-word mutations: replace the whole `PagePayload` from the response.

---

## 7. Hotkeys (matches view scope)

In addition to the global keymap (see [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md)),
when focus is in the matches view:

- `Tab` / `Shift+Tab`: navigate between GT inputs in reading order.
- `Enter` (in GT input): commit and stay on this word.
- `Escape` (in GT input): revert to last committed value, blur.

When focus is on a line card (not in a GT input):

- `V`: toggle line validate.
- `Delete`: delete the line (with confirm via shadcn `<AlertDialog />`).
- `O`: copy OCR→GT.
- `G`: copy GT→OCR.
- `J` / `K`: previous/next line card (vim-style — bonus, optional).

---

## 8. ARIA

- Each line card is a `<section role="region" aria-labelledby="line-{n}-heading">`.
- Status icons have `aria-label` describing the status (`"exact match"`,
  etc.) so screen readers announce them.
- The bulk-validate button (in the toolbar) when activated triggers a
  `role="status" aria-live="polite"` announcement: "Validated 5 words".

---

## 9. Tests

- Unit: `LineCard.test.tsx` — given a `LineMatch`, renders header
  with correct background class, count chips, action buttons.
- Unit: `WordCell.test.tsx` — given a `WordMatch` with a tag, renders
  the chip; clicking × calls the right mutation.
- Unit: `WordMatchView.test.tsx` — virtualised list with 200 lines
  renders only ~10 at any time, scroll triggers more.
- E2E (Playwright): `test_word_match.py` — port full from legacy.
- E2E: `test_word_match_inline_edit.py` — Tab/Shift-Tab nav, Enter commits.
- E2E: `test_word_match_filter.py` — Unvalidated → All toggles
  the visible line count.

---

## 10. Open issues

- **Per-row height variability.** Tag chips wrap to multiple lines for
  rare words with many tags. Virtualizer's `measureElement` handles
  it, but the first render flickers. Acceptable for v1; nice-to-have:
  cache measured heights to localStorage.
- **Mobile / narrow viewport.** The grid breaks down below ~600px
  wide. Out of scope for v1 — show a "screen too narrow" banner.

# pd-ocr-labeler-spa: Word Matches View (Right Pane)

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#14

## TL;DR

The right pane shows OCR-vs-GT line comparisons as virtualised `<LineCard>` rows.
Each card has a header (status color, count chips, GT↔OCR copy, validate, delete)
and a word grid (image slice, OCR text + tag chips, GT input, status icon). Filter
toggle (Unvalidated / Mismatched / All) is sent to the server as `?line_filter`.
Virtualised with `@tanstack/react-virtual`; only visible cards mount.

## Context

The legacy `text_tabs.py` / `word_match_renderer.py` renders match cards server-side
into NiceGUI components. The SPA replaces this with a virtualised React list: the server
sends pre-computed `LineMatch[]` with all counters; the client renders cards directly.
Plain textarea tabs (GT / OCR) replace legacy CodeMirror (D-008).

The density (up to 200 lines × 20 words = 4000 cells per page) makes virtualisation
mandatory. `@tanstack/react-virtual` with `measureElement` for variable-height cards
is the chosen approach.

## Constraints

- **Server-side filtering.** `?line_filter=unvalidated|mismatched|all` is sent to
  `GET /api/.../pages/{idx}` — the server returns only the requested subset.
- **Pre-computed counters.** `LineMatch.exact_count`, `fuzzy_count`, etc. are computed
  by the server; the client must not re-derive them.
- **Virtualisation mandatory.** No full-page render; only visible cards plus 3
  overscan cards mount.
- **GT input is the only editable field in the card.** All other fields are read-only.
  GT edit → optimistic local update → debounced POST to
  `PUT /api/.../words/{l}/{w}/ground-truth`.
- **`word_id` is the React key.** Not `(line_index, word_index)`, which can shift on
  split/merge.

## Decision

### Layout

```
<TextTabs>
  <ToolbarActionGrid />   (specs/06-toolbar-actions.md)
  <Tabs default="matches">
    tab "matches"       → <WordMatchView />
    tab "ground-truth"  → <PlainTextarea value={page.page_text_gt} readOnly />
    tab "ocr"           → <PlainTextarea value={page.page_text_ocr} readOnly />
```

### Filter toggle

Segmented control above line list. Options: `Unvalidated Lines` (default),
`Mismatched Lines`, `All Lines`. State in `usePrefsStore.lineFilter`. Sent as
`?line_filter=unvalidated|mismatched|all` query param; invalidates page query on change.

### Virtualisation

`useVirtualizer({ count: filteredLines.length, estimateSize: () => 80, overscan: 3 })`.
`measureElement` refines heights after first render. Scroll container is the
`<WordMatchView>` wrapper div.

### LineCard header

Background by `overall_match_status`: `exact`→green-100, `fuzzy`→yellow-100,
`mismatch`→red-100, `unmatched_ocr`→gray-100, `unmatched_gt`→blue-100.
Count chips: exact ✓, fuzzy ⚠, mismatch ✗, unmatched_ocr 🔵, unmatched_gt ⚫.
Buttons: GT→OCR, OCR→GT (hidden when exact), Validate (flips to Unvalidate), Delete.

### WordCell grid

5-row CSS grid per word. Row 1: checkbox + edit button + validate icon. Row 2: image
slice from `word_id`-derived crop URL. Row 3: OCR text + style/component tag chips.
Row 4: GT `<input>` (Tab/Shift-Tab nav between cells). Row 5: match status icon.
Tag chips: style chips (bg `#e7f0ff`), component chips (bg `#e7f8ee`).

### GT editing

Controlled `<input>` per word. On blur (or Tab to next): if value changed, optimistic
local update + `POST /api/.../words/{l}/{w}/ground-truth` with `{text}`. No debounce —
commit on blur only. On error: revert optimistic update, toast error.

### Line/word hotkeys (scoped to WordMatchView)

`V` — validate line under cursor. `Delete` — delete selected words. `O` — copy OCR→GT
for line. `G` — copy GT→OCR for line. `J/K` — navigate lines. Tab/Shift-Tab — GT inputs.

## Contract / Acceptance

- Playwright: page with 200 lines renders without full-DOM mount; scroll to last line
  mounts that card.
- Playwright: GT edit on word 3/5 → blur → POST fires with correct text.
- Playwright: filter toggle to "Mismatched Lines" triggers new `GET /api/.../pages/{idx}`
  with `?line_filter=mismatched`.
- Vitest: `LineCard` snapshot matches legacy status colors for all 5 match statuses.
- Vitest: Tab key in GT input moves focus to next word's GT input.

## Trade-offs considered

**Server-side vs client-side filter.** Client-side filter would avoid a server round-trip
on toggle. Server-side chosen because the server can return a smaller payload for dense
pages (200 → 30 unvalidated lines), reducing parse time and memory in the browser.

**Debounce vs blur-commit for GT editing.** Debounce causes mid-edit POSTs that can race
with the blur. Blur-commit gives one POST per "done typing" event, simpler error handling,
and matches the legacy behaviour.

**`word_id` as React key vs `(l,w)` tuple.** After split/merge operations the
`(line_index, word_index)` of a word changes; `word_id` is stable. Using `word_id` as key
prevents React from remounting the wrong cell after structural edits.

## Consequences

- Adding a new tab (e.g., a glyph-annotation tab in M9.9) requires an entry in
  `<TextTabs>` and a new `TabsContent` panel.
- Validate/delete actions must invalidate the page query on success so the virtual list
  refetches the updated `LineMatch[]`.

## Open questions

None.

## References

- `specs/05-word-matches.md` — legacy feature doc
- `specs/01-data-models.md` — `LineMatch`, `WordMatch`, `MatchStatus`
- `specs/06-toolbar-actions.md` — toolbar mounted above the tab list
- `specs/13-driver-contract.md` — testids for filter toggle and tab triggers

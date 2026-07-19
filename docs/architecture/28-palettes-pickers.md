---
kind: architecture
status: built
owner: maintainers
created: 2026-05-16
last_verified: 2026-07-13
---

# 28 — Palettes and Pickers

> **Status**: Active (shipped — hi-fi redesign P2.d, P2.e, P4.c)
> **Last updated**: 2026-05-16
> **Components documented**: `StylePalette`, `ComponentPalette`, `UnicodePicker`,
> `useLayerColors`

## 1. Overview

These three components provide the labeler with selection surfaces for tagging
words and inserting special characters. `StylePalette` and `ComponentPalette`
are chip rows that toggle text-style and component labels on a word. `UnicodePicker`
is a browsable glyph inserter that appears inline wherever a GT text field needs
a special character. `useLayerColors` is a supporting utility hook that reads
CSS custom properties for the four OCR layer colors so Konva canvases and
label chips use theme-accurate colors.

## 2. User-facing goals

- I need to mark a word as bold, italic, superscript, etc. with a single chip
  click rather than navigating to a menu or typing a tag string.
- I need to tag structural word components (drop caps, footnote references,
  page numbers) that distinguish word roles beyond text styling.
- I need to insert em-dashes, accented characters, Greek letters, and other
  non-keyboard characters directly into a GT input without leaving the right
  panel or switching to a character map application.
- I need canvas overlays (bbox rectangles, selection highlights) to respect the
  current theme's layer colors rather than being hardcoded.

## 3. Component tree / layout

```
WordDetail
├── StylePalette            data-testid="style-palette"
│   └── ChipPalette (reusable building block)
│       └── Chip (tristate) × N   data-testid="style-chip-{key}"
│
└── ComponentPalette        data-testid="component-palette"
    └── ChipPalette
        └── Chip (tristate) × N   data-testid="component-chip-{key}"

OcrGtCompareRow
└── UnicodePicker (inline, collapsible)   data-testid="unicode-picker"
    ├── Sets row (horizontal scrollable pills)
    ├── Code-point card grid (auto-fill, max 160px tall)
    └── Slash-command input

CharFixerSection
└── UnicodePicker (inline, collapsible, same component)

CharRangesSection
└── ChipPalette (style or component, per range card kind)
```

`useLayerColors` is consumed by `Rail`, `BBoxOverlay`, `ReboxCanvas`,
`CharFixerCanvas`, and `Breadcrumb`.

## 4. Data model

### StylePalette

Props:
```typescript
interface StylePaletteProps {
  activeStyles: string[];         // WordMatch.text_style_labels
  onStyleChange: (styleKey: string, next: TristateValue) => void;
}
```

Supported style keys (in display order):

| key | label |
|---|---|
| `bold` | B |
| `italic` | I |
| `small-caps` | Sc |
| `superscript` | Sup |
| `subscript` | Sub |
| `strikethrough` | Strike |
| `underline` | U |

Each chip value is derived as `activeStyles.includes(key) ? "on" : "off"`.
The `"mixed"` state is never emitted by this component (whole-word styling only).

### ComponentPalette

Props:
```typescript
interface ComponentPaletteProps {
  activeComponents: string[];     // WordMatch.word_components
  onComponentChange: (componentKey: string, next: TristateValue) => void;
}
```

Supported component keys:

| key | label |
|---|---|
| `drop-cap` | Drop Cap |
| `footnote-ref` | Fn Ref |
| `page-num` | Page # |
| `running-head` | Run Hd |
| `abbreviation` | Abbr |
| `proper-noun` | Proper |

Same derivation as StylePalette. `"mixed"` state is skipped for whole-word
component toggles (per `WordDetail`'s `onComponentChange` handler).

### ChipPalette (shared building block)

```typescript
interface ChipPaletteProps {
  items: Array<{ key: string; label: string }>;
  activeKeys: Set<string>;
  "data-testid-prefix": string;
  onChange: (key: string, next: TristateValue) => void;
}
```

Used directly by `CharRangesSection` for per-range style and component chip
palettes, with `data-testid-prefix` set to `char-range-{N}-style-chip` or
`char-range-{N}-component-chip`.

The palette uses `TriStateChip` from `@pdomain/pdomain-ui/primitives`; the SPA
no longer owns a local tri-state chip implementation. `TriStateChip` exposes
its value through `aria-pressed`: `off`
maps to `false`, `on` maps to `true`, and `mixed` maps to `mixed`. It also keeps
the driver-facing `data-tristate` and `data-tristate-value` attributes.

Evidence:

- Code: `frontend/src/components/right-panel/StylePalette.tsx`,
  `frontend/src/components/right-panel/ComponentPalette.tsx`, and
  `frontend/src/components/right-panel/sections/CharRangesSection.tsx` consume
  `@pdomain/pdomain-ui` 0.11.0 as locked in `frontend/pnpm-lock.yaml`
- Tests: `TriStateChip (pdui) — a11y (aria-pressed)`, `TriStateChip (pdui) —
  cycle`, and `TriStateChip (pdui) — data-tristate attrs`
- Commits: `caba90822c9238a55f6bbbc7081a4d35e801089a`, `fcab138`
- Verified: 2026-07-19 against the migration export for GitHub issue #450

### UnicodePicker

Props:
```typescript
interface UnicodePickerProps {
  onInsert: (glyph: string) => void;
}
```

Internal state: `activeSet: SetId` (default `"punctuation"`), `slashValue: string`.

Seven character sets, each as a `CharEntry[]`:

| id | label | description |
|---|---|---|
| `latin` | Latin | Extended Latin + ligatures (À–ÿ, ﬁ, ﬂ, œ, Œ) |
| `greek` | Greek | Full Greek alphabet (α–ω, Α–Ω) |
| `punctuation` | Punctuation | Em/en dash, ellipsis, smart quotes, section/pilcrow, dagger |
| `symbols` | Symbols | Copyright, trademark, arrows, check/cross, card suits |
| `math` | Math | Operators, fractions, set symbols, infinity, integral |
| `currency` | Currency | €, £, ¥, ¢, ₹, ₽, ₩, ₿, $, ¤ |
| `other` | … | Ordinals, Unicode superscripts/subscripts, misc book OCR chars |

Each `CharEntry` has `{ char: string, cp: string }` where `cp` is `"U+XXXX"`.

**Slash-command map**: ~80 named aliases (`emdash`, `alpha`, `Beta`, `pm`,
`euro`, `copy`, `frac12`, etc.) plus any `U+XXXX` codepoint string.

### useLayerColors

```typescript
interface LayerColors {
  block: string;  // CSS hex string, e.g. "#a89074"
  para: string;
  line: string;
  word: string;
}

// Fallbacks used in jsdom / when CSS tokens are unavailable:
const FALLBACKS = { block: "#a89074", para: "#7fb56a", line: "#d088a8", word: "#6e9cdf" };
```

Reads `--layer-block`, `--layer-para`, `--layer-line`, `--layer-word` from
`getComputedStyle(document.documentElement)`. Falls back silently.

Additional exports from the same module:

- `readLayerColors()` — imperative (non-hook) version.
- `hexToRgba(hex, alpha)` — converts a 6-digit hex to `rgba(r,g,b,a)` string.
- `LAYER_FILL_ALPHA = 0.2`, `LAYER_STROKE_ALPHA = 0.65`
- `hexToLayerColorSpec(hexColor)` — returns `{ fill, stroke, strokeWidth }` for
  Konva overlays.
- `readCssToken(prop, fallback)` — generic CSS token reader.
- `readAccentColor()` — reads `--accent`, falls back to `"#d6925a"`.
- `buildSelectionLayerSpec()` — uses `--accent`; `fill` at 18% opacity.
- `buildDragRectLayerSpec()` — uses `--accent`; transparent fill, 2px stroke.

`LayerColorSpec` is also re-exported by `BBoxOverlay.tsx` for backwards
compatibility (the type was originally defined there).

## 5. Interactions and behaviors

### StylePalette / ComponentPalette

- Each `Chip` cycles through `"off"` → `"on"` → `"off"` on successive clicks
  (tristate, but `"mixed"` is only externally assignable, not reached by user
  clicks in this context).
- `onChange(key, next)` fires immediately on each click; `WordDetail` wires this
  to `applyStyle.mutate(...)` or `applyComponent.mutate(...)` which POST to the
  server and invalidate the page cache.
- The `activeStyles` / `activeComponents` arrays come from the server-fetched
  `WordMatch`, so the chip state always reflects the persisted value.

### UnicodePicker

**Set pill row**

- Clicking a pill sets `activeSet`, filtering the card grid to that set's
  characters.
- Default active set on mount: `"punctuation"`.

**Card grid**

- Grid uses `auto-fill` columns of minimum 44 px width, max height 160 px with
  vertical scroll.
- Clicking a card calls `onInsert(char)` immediately and closes nothing — the
  picker stays open so multiple characters can be inserted.
- Each card shows the character in serif 16px and the `U+XXXX` code-point below
  in 8px monospace.

**Slash-command input**

- Accepts typed names like `\emdash`, `\alpha`, `U+2019`.
- Enter key: resolves the input via `resolveSlashCommand(raw)`. If resolved to
  a character, calls `onInsert(resolved)` and clears the input. If not resolved,
  does nothing (no error shown).
- Leading backslash is optional: both `\emdash` and `emdash` resolve.
- `U+XXXX` form: hex codepoint, case-insensitive, 1–6 hex digits.

**Insertion target**

- In `OcrGtCompareRow`: the UnicodePicker's `onInsert` calls
  `handleInsertGlyph(glyph)` which inserts at the GT input's current cursor
  position using `selectionStart` / `selectionEnd`, then restores cursor.
- In `CharFixerSection`: inserts into `draft[lastFocusedIndex]` (replaces the
  entire character cell content).

### useLayerColors

- Called on each render (no subscription); reads once from `getComputedStyle`.
- For live theme-switch reactivity the caller must subscribe to a `matchMedia`
  or `data-theme` attribute mutation and force a re-render. No built-in
  subscription in the current implementation.

## 6. data-testid contract

### StylePalette / ComponentPalette

| testid | element | description |
|---|---|---|
| `style-palette` | div | Style palette outer container |
| `style-chip-bold` | Chip button | Bold toggle |
| `style-chip-italic` | Chip button | Italic toggle |
| `style-chip-small-caps` | Chip button | Small-caps toggle |
| `style-chip-superscript` | Chip button | Superscript toggle |
| `style-chip-subscript` | Chip button | Subscript toggle |
| `style-chip-strikethrough` | Chip button | Strikethrough toggle |
| `style-chip-underline` | Chip button | Underline toggle |
| `component-palette` | div | Component palette outer container |
| `component-chip-drop-cap` | Chip button | Drop Cap toggle |
| `component-chip-footnote-ref` | Chip button | Footnote reference toggle |
| `component-chip-page-num` | Chip button | Page number toggle |
| `component-chip-running-head` | Chip button | Running head toggle |
| `component-chip-abbreviation` | Chip button | Abbreviation toggle |
| `component-chip-proper-noun` | Chip button | Proper noun toggle |

### UnicodePicker

| testid | element | description |
|---|---|---|
| `unicode-picker` | div | Outer container |
| `unicode-set-latin` | button | Latin character set pill |
| `unicode-set-greek` | button | Greek character set pill |
| `unicode-set-punctuation` | button | Punctuation set pill |
| `unicode-set-symbols` | button | Symbols set pill |
| `unicode-set-math` | button | Math set pill |
| `unicode-set-currency` | button | Currency set pill |
| `unicode-set-other` | button | Miscellaneous set pill |
| `unicode-char-{U+XXXX}` | button | Code-point card (one per character) |
| `unicode-slash-input` | input[type=text] | Slash-command text input |

`data-testid` for `unicode-char-*` uses the `U+` prefix and four uppercase hex
digits: e.g. `unicode-char-U+2014` for em-dash.

## 7. Keyboard shortcuts

- `Enter` in `unicode-slash-input`: resolve and insert if the slash command is
  valid; no-op if unresolved.
- No other document-level hotkeys registered by these components.

## 8. Edge cases

- **All styles off**: all chips render in "off" state. No default selection.
- **Unknown style in `activeStyles`**: the chip for that key will not be found
  in `STYLE_ITEMS`, so it will not be rendered (unknown keys are silently dropped
  from display, not errored).
- **UnicodePicker empty set**: no set in `CHAR_SETS` should be empty, but if one
  is, the card grid renders nothing and no error is thrown.
- **Unresolvable slash command**: `resolveSlashCommand` returns `null`; no
  insertion; input text remains unchanged.
- **useLayerColors in jsdom**: `getComputedStyle` returns empty strings for custom
  properties; fallback values are used. Tests should not assert exact hex values
  unless they set the CSS variables explicitly.
- **Mixed state from CharRangesSection**: `ChipPalette` in `CharRangesSection`
  uses `activeKeys.has(key) ? "on" : "off"`. The `"mixed"` state in
  CharRangesSection comes only from the legacy `pendingStyles` map in the pending
  panel — it is never emitted by `ChipPalette` itself.

## 9. Open questions

1. **Style chip "mixed" in word context**: the `TristateValue` type supports
   `"mixed"` to indicate that some (but not all) characters in the word carry a
   style. WordDetail skips `"mixed"` updates (guard `if (next === "mixed")
   return`). When should `"mixed"` appear for a whole-word chip? E.g. when the
   word has both bold and non-bold characters via `CharRanges`. Currently
   `activeStyles` comes from `word.text_style_labels` which is an all-or-nothing
   list — there is no mixed-state representation in the API schema.

2. **UnicodePicker size / scroll**: the card grid has a hard-coded `maxHeight:
   160px`. Whether this is appropriate for all deployment contexts (small laptop
   screens vs. external monitors) has not been validated.

3. **Slash-command coverage**: the SLASH_MAP covers ~80 names. Common OCR book
   characters (e.g. `\pound`, `\asterism`, Old English letters) may be missing.
   A process for extending the map (community-maintained? user-configurable?) is
   not defined.

4. **useLayerColors reactivity**: reading CSS tokens once per render is correct
   for initial load and for most interactions. If the user switches theme (e.g.
   via a settings panel) mid-session, Konva canvases that cache the color values
   will not automatically update. A subscription mechanism (MutationObserver on
   `document.documentElement`'s `data-theme` attribute) would solve this.

5. **ComponentPalette scope**: `ApplyComponentRequest.enabled` toggles
   `component` on or off for the whole word. There is no per-character component
   annotation path at the whole-word level. The relationship between
   `ComponentPalette` at the word level and the `CharRangesSection` "Component"
   kind is not fully specified.

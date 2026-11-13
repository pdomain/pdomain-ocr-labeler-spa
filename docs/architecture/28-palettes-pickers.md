---
kind: architecture
status: built
owner: maintainers
created: 2026-05-16
last_verified: 2026-11-13
---

# 28 — Palettes and Pickers

> **Status**: Active (shipped — hi-fi redesign P2.d, P2.e, P4.c)
> **Last updated**: 2026-05-16
> **Components documented**: `ChipPalette`, `ComponentPalette`, `UnicodePicker`,
> `useLayerColors`

## 1. Overview

These components provide selection surfaces for structural component tagging
and special-character insertion. `ComponentPalette` uses `ChipPalette` to
toggle structural labels on a word. `UnicodePicker`
is a browsable glyph inserter that appears inline wherever a GT text field needs
a special character. `useLayerColors` is a supporting utility hook that reads
CSS custom properties for the four OCR layer colors so Konva canvases and
label chips use theme-accurate colors.

`ChipPalette` is used by `ComponentPalette` only. `TypographySection` renders
its own server-taxonomy buttons. The frontend has no fallback typography
taxonomy.

## 2. User-facing goals

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

TypographySection
└── Native buttons from TypographyHeadResponse.taxonomy.labels
```

`useLayerColors` is consumed by `Rail`, `BBoxOverlay`, `ReboxCanvas`,
`CharFixerCanvas`, and `Breadcrumb`.

## 4. Data model

### ChipPalette

Props:
```typescript
interface ChipPaletteProps {
  items: Array<{ key: string; label: string }>;
  activeKeys: Set<string>;
  "data-testid-prefix": string;
  onChange: (key: string, next: TristateValue) => void;
}
```

Each chip is on when `activeKeys` contains its key. User clicks toggle on/off;
an externally supplied `mixed` transition is normalized to off.

### ComponentPalette

Props:
```typescript
interface ComponentPaletteProps {
  activeComponents: string[];     // WordMatch.word_components
  onComponentChange: (componentKey: string, next: TristateValue) => void;
}
```

The runtime keys come from `useLabelVocabulary().wordComponents`. Known display
overrides are:

| key | label |
|---|---|
| `drop cap` | Drop Cap |
| `drop cap unrecovered` | Drop Cap? |
| `footnote marker` | Fn Mark |
| `subscript` | Sub |
| `superscript` | Sup |

Other server keys display verbatim. Chip test IDs replace spaces with hyphens.

### ChipPalette (shared building block)

```typescript
interface ChipPaletteProps {
  items: Array<{ key: string; label: string }>;
  activeKeys: Set<string>;
  "data-testid-prefix": string;
  onChange: (key: string, next: TristateValue) => void;
}
```

Used by `ComponentPalette` for structural component chips. Typography label
buttons are implemented directly in `TypographySection`.

The palette uses `TriStateChip` from `@pdomain/pdomain-ui/primitives`; the SPA
no longer owns a local tri-state chip implementation. `TriStateChip` exposes
its value through `aria-pressed`: `off`
maps to `false`, `on` maps to `true`, and `mixed` maps to `mixed`. It also keeps
the driver-facing `data-tristate` and `data-tristate-value` attributes.

Evidence:

- Code: `frontend/src/components/right-panel/ChipPalette.tsx` and
  `frontend/src/components/right-panel/ComponentPalette.tsx` consume
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

The hook reads CSS aliases and observes document.documentElement's data-theme attribute.
Its current exported API is defined in the source; helper export examples below are not needed
to consume the hook. Theme changes trigger a token reread.

## 5. Interactions and behaviors

### ComponentPalette

- Each `Chip` cycles through `"off"` → `"on"` → `"off"` on successive clicks
  (tristate, but `"mixed"` is only externally assignable, not reached by user
  clicks in this context).
- `onChange(key, next)` fires immediately; `WordDetail` wires this to the
  structural component mutation and invalidates the page cache.
- Active components come from the server-fetched `WordMatch`.

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

The hook has a live data-theme subscription, so mounted consumers refresh colors on a theme change.

## 6. data-testid contract

### ComponentPalette

| testid | element | description |
|---|---|---|
| `component-palette` | div | Component palette outer container |
| `component-chip-drop-cap` | Chip button | `drop cap` toggle |
| `component-chip-drop-cap-unrecovered` | Chip button | `drop cap unrecovered` toggle |
| `component-chip-footnote-marker` | Chip button | `footnote marker` toggle |
| `component-chip-subscript` | Chip button | `subscript` toggle |
| `component-chip-superscript` | Chip button | `superscript` toggle |

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

- **All components off**: all component chips render in "off" state.
- **UnicodePicker empty set**: no set in `CHAR_SETS` should be empty, but if one
  is, the card grid renders nothing and no error is thrown.
- **Unresolvable slash command**: `resolveSlashCommand` returns `null`; no
  insertion; input text remains unchanged.
- **useLayerColors in jsdom**: `getComputedStyle` returns empty strings for custom
  properties; fallback values are used. Tests should not assert exact hex values
  unless they set the CSS variables explicitly.
- **Mixed component state**: `ChipPalette` normalizes a mixed click transition
  to off. `TypographySection` does not use this component.

## 9. Open questions

UnicodePicker sizing across deployment contexts and a configurable slash-map extension policy have not
been established here. `pound` is already an alias and is not an example of a missing entry.
Theme reactivity is implemented through a data-theme observer. ComponentPalette authors structural
components; TypographySection owns canonical inline typography.

Evidence: `useLayerColors.ts` and its tests, UnicodePicker.tsx and ComponentPalette.tsx.
Verified by source/test inspection on 2026-11-13; no new sizing or extension policy is chosen.

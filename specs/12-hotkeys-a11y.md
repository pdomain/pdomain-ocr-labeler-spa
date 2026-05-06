# 12 — Hotkeys + Accessibility

The complete keymap and accessibility contract.

> Cross-refs:
> Legacy hotkey audit —
> `pd-ocr-labeler/docs/review-notes/2026-05-06-keyboard-shortcuts-coverage.md`
> Implementation library — `react-hotkeys-hook`
> [Q10](../OPEN_QUESTIONS.md) — adopting the wishlist for v1

---

## 1. Hotkey philosophy

- The legacy has only 5 hotkeys (Enter on page input, Enter on GT
  input, Tab/Shift+Tab on GT inputs, Enter on dialog GT, Enter on
  source-folder path input).
- The SPA adopts the gap-analysis wishlist as the v1 keymap. Migrating
  the UI is a one-time chance to fix the keyboard story. The legacy
  hotkeys are preserved.
- Mod key: `Ctrl` on Windows/Linux, `Cmd` on macOS. Implemented via
  `react-hotkeys-hook`'s `Mod+...` syntax.

## 2. Scopes

Keys fire only when their scope is active. Scopes:

- `global` — always active (project nav, save shortcuts).
- `viewport` — left-pane image canvas focused.
- `matches` — right-pane matches view focused.
- `dialog` — word-edit dialog open.
- `source-folder` — source-folder dialog open.
- `gt-input` — focus is in a GT input.

Implementation: each `useHotkey(map, scope)` call registers handlers
with `react-hotkeys-hook`, scoping to the relevant DOM region via
`enabled`-flag refs.

---

## 3. Global keymap

| Key | Action | Scope |
|---|---|---|
| `Mod+S` | Save Page | global |
| `Mod+Shift+S` | Save Project (with confirm) | global |
| `Mod+R` | Reload OCR (with confirm) | global |
| `Mod+Shift+R` | Reload OCR (Edited) (with confirm) | global |
| `Mod+L` | Load Page (with confirm — destructive) | global |
| `Mod+G` | Rematch GT (with confirm — destructive) | global |
| `Mod+E` | Open Export dialog | global |
| `Mod+,` | Open OCR config | global |
| `Mod+O` | Open Source Folder dialog | global |
| `?` | Open hotkey-help modal | global |
| `Esc` | Close any open modal | global |

Confirms via shadcn `<AlertDialog />` for destructive actions.

## 4. Project navigation

| Key | Action | Scope |
|---|---|---|
| `Mod+ArrowLeft` | Prev page | global |
| `Mod+ArrowRight` | Next page | global |
| `Mod+Home` | First page | global |
| `Mod+End` | Last page | global |
| `Mod+J` | Jump to page (focuses page input) | global |
| `Enter` (on page input) | Go to page | global (in input) |

## 5. Viewport scope

| Key | Action |
|---|---|
| `Esc` | Cancel pending mode → select; clear selection |
| `Shift+P` | Toggle paragraph layer |
| `Shift+L` | Toggle line layer |
| `Shift+W` | Toggle word layer |
| `Shift+1` | Selection mode → paragraph |
| `Shift+2` | Selection mode → line |
| `Shift+3` | Selection mode → word |
| `Shift+E` | Toggle Erase mode |
| `Shift+A` | Toggle Add Word mode |
| `+` / `-` | Zoom viewport (future, off by default) |

Drag modifiers (mouse + key combos):
- Plain drag → replace selection
- `Shift+drag` → remove from selection
- `Ctrl+drag` → toggle selection (XOR)

## 6. Matches view scope

| Key | Action | Notes |
|---|---|---|
| `Tab` | Next GT input | follows reading order |
| `Shift+Tab` | Prev GT input | |
| `Enter` (in GT input) | Commit GT, stay | |
| `Esc` (in GT input) | Revert, blur | |
| `J` | Next line card | bonus |
| `K` | Prev line card | bonus |
| `V` | Validate selected | scope from selectionMode |
| `U` | Unvalidate selected | |
| `D` | Delete selected (confirm) | |
| `R` | Refine selected | |
| `Shift+R` | Expand+Refine selected | |
| `M` | Merge selected (when ≥2) | |
| `O` | OCR→GT for selected | |
| `G` | GT→OCR for selected | |

## 7. Word edit dialog scope

| Key | Action |
|---|---|
| `Enter` (in GT input) | Commit GT |
| `Esc` | Close dialog (discard pending) |
| `Shift+Enter` | Apply & Close (commit pending) |
| `Tab` / `Shift+Tab` | Standard form navigation (auto via Radix focus trap) |
| `ArrowLeft` / `ArrowRight` | Switch to prev/next word in line |
| `Shift+ArrowLeft` / `Shift+ArrowRight` | Nudge left edge in/out |
| `Shift+ArrowUp` / `Shift+ArrowDown` | Nudge top edge in/out |
| `Ctrl+ArrowLeft` / `Ctrl+ArrowRight` | Nudge right edge in/out |
| `Ctrl+ArrowUp` / `Ctrl+ArrowDown` | Nudge bottom edge in/out |
| `R` | Refine |
| `Shift+R` | Expand + Refine |
| `M` | Apply current Style+Scope |
| `Shift+M` | Apply current Component |
| `Delete` | Delete word (with confirm) |

## 8. Source folder dialog scope

| Key | Action |
|---|---|
| `Enter` (on path input) | Open typed path |
| `Esc` | Cancel |
| `Mod+Enter` | Apply (use current) |

## 9. Hotkey help modal

`?` opens a modal listing every hotkey grouped by scope. Implemented
with shadcn `<Dialog />`. Scrollable. Pulls the keymap from
`src/lib/hotkeyMap.ts` so it's always in sync.

testid: `hotkey-help-dialog`.

---

## 10. Implementation skeleton

`src/lib/hotkeyMap.ts`:

```ts
export type HotkeyEntry = { combo: string; scope: Scope; description: string; };

export const hotkeyMap: HotkeyEntry[] = [
  // global
  { combo: "mod+s", scope: "global", description: "Save Page" },
  { combo: "mod+shift+s", scope: "global", description: "Save Project" },
  ...
];
```

`src/hooks/useHotkey.ts`:

```ts
export function useHotkey(combo: string, handler: () => void, opts?: { scope?: Scope; preventDefault?: boolean }) {
  useHotkeysHook(combo, (e) => {
    if (opts?.preventDefault !== false) e.preventDefault();
    handler();
  }, { enableOnFormTags: false, ... });
}
```

Form-tag opt-out by default: most shortcuts shouldn't fire while
typing. Per-input opt-in (e.g. `Tab` in GT input) uses
`enableOnFormTags: ['INPUT']`.

---

## 11. Accessibility contract

### 11.1 Focus management

- Every interactive element is focusable via Tab.
- Focus order matches visual order (left-to-right, top-to-bottom).
- Modals trap focus (Radix default).
- Modal close returns focus to the triggering element (Radix default).

### 11.2 ARIA roles + labels

- Every button has either visible text **or** `aria-label`.
  Icon-only buttons (delete, close, sort, edit) MUST have `aria-label`.
- Form controls have an associated `<label>` (visible or `srOnly`)
  OR `aria-label`.
- Dialogs have `role="dialog"` + `aria-modal="true"` (Radix default).
- The matches view container has `role="region"
  aria-label="Word matches"`.
- The image viewport `<Stage>` wrapper has `role="img"
  aria-label="Page image with bounding-box overlays"`.
- Status icons (check_circle, warning, etc.) have `aria-label`
  describing the status ("exact match", "fuzzy match", etc.).

### 11.3 Live regions

- A `role="status" aria-live="polite"` slot in `App.tsx`. The SPA
  writes short narration text on bulk changes (e.g., "Validated 5
  words", "Refined bboxes for line 12").
- A separate `role="alert" aria-live="assertive"` slot reserved for
  errors (used sparingly — most errors flow through toasts which have
  built-in live-region semantics).

### 11.4 Color and contrast

- All text on colored backgrounds passes WCAG AA contrast (4.5:1 for
  body text, 3:1 for large/UI text).
- Status colors are distinguished by **icon shape + text** in addition
  to color. Colorblind users still know which line is exact vs
  mismatch by the icon (`check_circle` vs `x_circle`).

### 11.5 Keyboard-only operation

- The full app is operable without a mouse:
  - Project load: dropdown via Tab, Enter to open, ArrowKeys to
    select.
  - Page navigation: keyboard shortcuts (above).
  - Matches view: Tab through GT inputs, V/U/D shortcuts for actions.
  - Word edit dialog: Tab through controls; nudge via Shift+Arrow;
    Apply/Close via Mod+Enter / Esc.
  - Toolbar: Tab to each button.
- The image viewport's *drag* operations require a mouse. Document
  this: the viewport is a power-user interface for selection; all the
  same operations are available via the toolbar with keyboard
  selection.

### 11.6 Screen reader support

- Test with NVDA (Windows), VoiceOver (macOS), and Orca (Linux)
  manually before each release.
- Every page action and toolbar action announces clearly when
  triggered ("Saving page…", "Page saved").
- No `<canvas>`-only critical UI: the matches view is the canonical
  source of truth for word-level state, and it's plain HTML.

---

## 12. Tests

- Unit: `hotkeyMap.test.ts` — every entry has unique combo within
  scope, descriptions present.
- Unit: `useHotkey.test.tsx` — registers, fires on combo, respects
  `enableOnFormTags`.
- E2E: `test_hotkeys.py` — for each global hotkey, simulate keypress,
  assert action fires.
- E2E: `test_keyboard_only.py` — load project, navigate to page 2,
  validate a word, save — all without using the mouse.
- A11y: `axe-core` runs in Playwright e2e on every key page; fails on
  any WCAG AA violation.

---

## 13. Open issues

- **Mod+S in browsers with native Save shortcut.** Most browsers
  hijack `Mod+S` for "Save Page As…". The SPA preempts via
  `e.preventDefault()`. Verified to work in Chrome / Firefox; Safari
  may complain. Acceptable; the busy overlay shows the SPA's save
  feedback.
- **`?` shortcut conflicts.** Inside a GT input, `?` is just a question
  mark. Outside (focus on a card), it opens help. Spec rule:
  `enableOnFormTags: false` means `?` is suppressed inside inputs.
- **Custom hotkey rebinding.** Out of scope for v1. The keymap is
  static.

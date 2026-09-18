---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-07-13
---

# Open findings

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-13
- **Read when:** triaging known unresolved product or test defects.
- **Search terms:** open bugs, keyboard, reload OCR, hierarchy, XDG data root.

## Keyboard findings

### BUG-KBD-1 — `Mod+,` is advertised but not registered

`HOTKEY_MAP` advertises OCR Config on `mod+,`, but current searches find no
matching `useHotkey` registration. The modal is clickable, so this is a
keyboard-only accessibility gap. Register the shortcut against the existing
OCR-config dialog store and add focused coverage.

### BUG-KBD-4 — ConfirmDialog keyboard behavior needs browser verification

`ConfirmDialog` relies on its focused button and lacks explicit Escape/Enter
bindings. Verify the destructive-action flow in a browser; add scoped bindings
if native focused-button behavior does not cover both keys.

### BUG-KBD-5 — `Mod+J` is advertised but not registered

`HOTKEY_MAP` advertises jump-to-page on `mod+j`, but current searches find no
matching registration. Wire it to the existing page-number control and test the
full keyboard path.

## Persistence and page findings

### BUG-SMOKE-3 — The default data root is not XDG-compatible — Resolved

`Settings.data_root` now defaults to the OS-aware data directory
(`${XDG_DATA_HOME:-~/.local/share}/pdomain-ocr-labeler-spa` on Linux; the
macOS / Windows equivalents in `docs/architecture/01-data-models.md §5`). An
existing pre-XDG install at `~/pdomain-ocr-labeler-spa` keeps being used, and
is announced at startup, when that legacy directory has data and the new
location doesn't yet — nobody's projects go missing on upgrade. The legacy
NiceGUI app's directory (`~/.local/share/pd-ocr-labeler/`) is never
auto-discovered; `PDLABELER_DATA_ROOT` / `--data-root` still override
everything. See `docs/context/decisions.md`.

### BUG-RELOAD-1 — Zero-area unmatched-GT boxes need explicit handling

Reload OCR may legitimately create unmatched-GT placeholders with zero-area
boxes. Confirm `BBoxOverlay` suppresses them and that a page with genuinely no
OCR text produces a clear failure state instead of a misleading complete page.

### ~~BUG-HIER-1~~ — Hierarchy coverage path can render no nodes (retired 2026-09-18)

Retired after checking both halves and finding neither still true. No hierarchy
skip exists: the empty-hierarchy branch became a hard assertion on 2026-07-21,
so an empty tree would now fail loudly rather than skip. And the exercise
fixture was never missing anything; page 1 carries the full page, block, line
and word nesting the tree needs.

What was real was the mechanism. The helper slept a fixed 200 to 300 ms after
expanding a node and then read the count immediately, which can observe zero
before a fetched hierarchy renders. That is fixed: it waits for the node
selector to attach instead. See the 2026-09-18 entry in `decisions.md`.

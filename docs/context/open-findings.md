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

### BUG-SMOKE-3 — The default data root is not XDG-compatible

`src/pdomain_ocr_labeler_spa/settings.py` still defaults to
`~/pdomain-ocr-labeler-spa`, while existing Linux labeler data may live under
`~/.local/share/pd-ocr-labeler/`. Decide and implement a compatibility policy
before claiming automatic discovery of legacy labeled pages.

### BUG-RELOAD-1 — Zero-area unmatched-GT boxes need explicit handling

Reload OCR may legitimately create unmatched-GT placeholders with zero-area
boxes. Confirm `BBoxOverlay` suppresses them and that a page with genuinely no
OCR text produces a clear failure state instead of a misleading complete page.

### BUG-HIER-1 — Hierarchy coverage path can render no nodes

Issue #403 recorded an empty hierarchy during E2E setup, which skipped six
WordDetail section tests. Replace fixed sleeps with an explicit hierarchy-node
wait and verify the exercise fixture contains the required hierarchy fields.

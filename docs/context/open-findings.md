---
kind: context
status: active
owner: maintainers
created: 2026-07-13
last_verified: 2026-09-18
---

# Open findings

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-09-18
- **Read when:** triaging known unresolved product or test defects, or checking
  what an older finding turned out to be.
- **Search terms:** open bugs, keyboard, reload OCR, hierarchy, XDG data root.

**Nothing here is open as of 2026-09-18.** All six findings were closed that
day. Two were real defects and were fixed: a page where OCR found nothing
looked finished, and the data root ignored where each platform puts data. Two
were stale, already answered by work nobody linked back to them. Two were
verified rather than changed, because the behaviour was already correct and
nobody had ever checked. Each entry below says which it was, and the reasoning
lives in `decisions.md` under 2026-09-18.

## Keyboard findings

### ~~BUG-KBD-1~~ — `Mod+,` is advertised but not registered (retired 2026-09-18)

Registered. `App.tsx` binds `mod+,` to the OCR-config dialog, with a comment
recording that the default delimiter parses that combo as two, which is why it
is registered the way it is.

### ~~BUG-KBD-4~~ — ConfirmDialog keyboard behavior needs browser verification (retired 2026-09-18)

Verified in a real browser against the Matches pane's `D` (delete line)
confirm — `tests/e2e/test_confirm_dialog_keyboard.py`. Escape cancels and
Enter confirms, both checked against the server (`line_matches` before and
after), and focus is sound on open, on Tab, and after either close path. No
scoped bindings were added: Radix's AlertDialog already handles both keys
natively. One correction to the finding's own premise — the dialog
default-focuses **Cancel**, not Confirm, on open (a safety default), so
Enter alone right after opening cancels; reaching Confirm needs one Tab
first.

### ~~BUG-KBD-5~~ — `Mod+J` is advertised but not registered (retired 2026-09-18)

Registered. `useGlobalHotkeys.ts` binds `mod+j` to the jump-to-page handler.

## Persistence and page findings

### ~~BUG-SMOKE-3~~ — The default data root is not XDG-compatible (retired 2026-09-18)

`Settings.data_root` now defaults to the OS-aware data directory
(`${XDG_DATA_HOME:-~/.local/share}/pdomain-ocr-labeler-spa` on Linux; the
macOS / Windows equivalents in `docs/architecture/01-data-models.md §5`). An
existing pre-XDG install at `~/pdomain-ocr-labeler-spa` keeps being used, and
is announced at startup, when that legacy directory has data and the new
location doesn't yet — nobody's projects go missing on upgrade. The legacy
NiceGUI app's directory (`~/.local/share/pd-ocr-labeler/`) is never
auto-discovered; `PDLABELER_DATA_ROOT` / `--data-root` still override
everything. See `docs/context/decisions.md`.

### ~~BUG-RELOAD-1~~ — Zero-area boxes and empty OCR pages (retired 2026-09-18)

Both halves answered. Zero-area boxes were already handled one layer below
where this looked: an unmatched ground-truth placeholder carries no word index
and is dropped before it can become an overlay item.

The second half was a real defect and is fixed. A page where OCR ran and found
nothing looked exactly like a finished page, and the review queue agreed with
it, reporting zero outstanding. See the 2026-09-18 entry in `decisions.md`.

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

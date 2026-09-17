---
kind: issue
status: active
owner: maintainers
created: 2026-09-17
last_verified: 2026-09-17
level: I2
---

# A word or line selection jumps to a different item when the page changes

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I2
- **Last verified:** 2026-09-17
- **Resolution:** Open
- **Severity:** Low to medium — a selection silently moves to another word or line; the panel shows
  the item it moved to, so no action lands on something hidden
- **Affected version:** pdomain-ocr-labeler-spa @ 6ed5156, and every earlier version this code has
- **Read when:** a selection changes unexpectedly after moving between pages, or when changing how
  selection is scoped to a page
- **Search terms:** stale selection, page change, selectionStore, lineId, wordId, resolveWord,
  clearSelection, cross-page selection
- **Relates to:** [issues index](README.md)

## Summary

A word, line or paragraph selection is not tied to the page it was made on. Select line 12 on page
40, move to page 41, and the selection is still line 12 — now meaning line 12 of page 41. The right
panel resolves it against whichever page is loaded, so it quietly shows a different line, and
nothing tells the person their selection changed.

## Evidence

- `selectionStore` holds a `SelectionPath` of plain indices (`lineId`, `wordId`, `paraId`) with no
  page index, in `frontend/src/stores/selection-store.ts` and `frontend/src/lib/selection-walk.ts`.
- Nothing clears a word, line or paragraph selection on page change. `ProjectPage.tsx` clears the
  selection on page change only when its level is `region`.
- `LineDetail.tsx` resolves the line with `page.line_matches?.find((l) => l.line_index === lineId)`,
  and `WordDetail.tsx` resolves the word with `resolveWord(page, lineIdx, path.wordId)`. Both use
  the page currently passed in, whatever page the selection was made on.
- `frontend/src/pages/ProjectPage.pageChange.test.tsx` pins that a line selection survives a page
  change. That test exists to keep the region fix below from widening; it documents today's
  behaviour, not a decision that the behaviour is right.

## How this was found

The first region review surface, on the `feature/region-review` branch, had the same defect for
region selections, with a worse consequence: a keyboard accept could be sent to the new page's
route carrying the old page's proposal id. A whole-branch review caught it, and the fix clears a
region selection on page change and checks the selected id is still on the current page before any
keyboard action. The implementer who fixed it checked the older selection levels and found they
share the underlying problem. They were left alone deliberately, because changing when those
selections clear is a behaviour change nobody had decided on.

## Options

1. **Clear every selection on page change**, as the region level now does. Simplest. It would lose
   a person's place if anyone deliberately keeps a line index selected while paging through a book,
   for example to compare line 12 across pages. Check whether anyone works that way first.
2. **Carry the page index in `SelectionPath`**, and treat a selection whose page does not match the
   loaded page as empty. More work, and it keeps the selection intact on returning to its page.

Option 2 is the better long-term shape. Option 1 is a one-line change if nobody relies on the
current behaviour.

# Full Exercise Workflow — pd-ocr-labeler-spa

> **Purpose.** This document is the authoritative end-to-end test plan for the
> pd-ocr-labeler-spa. Every user-facing capability is represented. Each step is
> written in the format usable for both **manual QA sessions** and as a
> **Playwright test specification**.
>
> **Data-testid source of truth:** `docs/architecture/13-driver-contract.md`
> **Spec authority:** `docs/architecture/00-overview.md` through `19-auto-rotation.md`
> and `specs/16–23`.
>
> **Convention.** Steps are numbered `P<phase>.<step>`. A step may reference
> sub-variants lettered `a`, `b`, `c`. "Testid" always means
> `data-testid="<value>"`.

---

## Prerequisites / Setup

Before executing any phase, the following conditions must be satisfied.

### P0.1 — Server running

**Action.** In a terminal: `make dev` (or `make run` for production-style).

**Expected.** Terminal shows `Uvicorn running on http://127.0.0.1:8000`. Vite
dev server starts on `:5173` and proxies `/api` and `/image-cache` to FastAPI.

**Pass criterion.** `GET http://localhost:5173` returns HTTP 200. No errors in
console.

---

### P0.2 — Fixture project on disk

**Action.** Ensure at least one test project directory exists under the
configured `source_projects_root`. The directory must contain:

- At least two `.png` (or `.jpg`) page image files, named sequentially.
- A `pages.json` file mapping image names to ground-truth text (e.g.
  `{"001.png": "First page text...", "002.png": "Second page text..."}`).

**Recommended minimum fixture.** Two pages, three lines each, six words per
line, with a mix of exact/fuzzy/mismatch words. At least one labeled envelope
(`.json` sidecar) already saved for page 1.

**Pass criterion.** The project directory is listed by
`GET /api/projects?source_root=<path>`.

---

### P0.3 — Browser open at root

**Action.** Navigate to `http://localhost:5173` in Chromium.

**Expected.** Either:

- (a) Root page renders with header and project list (if no session state), or
- (b) Browser redirects to `/projects/{id}/pages/pageno/{n}` (last session
  restored from `session_state.json`).

**Testids present.** `project-select`, `load-project-button`,
`source-folder-button`, `ocr-config-trigger-button`.

**Pass criterion.** Page renders without JS errors. `project-select` is
focusable.

---

## Phase 1: Page Load & Navigation

### 1.1 — Load project via dropdown

**Action.** Click the `project-select` dropdown trigger. From the list, choose
the fixture project name. Click `load-project-button`.

**Expected.**

- `project-loading-overlay` (testid) appears with a spinner.
- After load completes, overlay disappears.
- Browser URL changes to `/projects/{id}/pages/pageno/1`.
- The page image renders in the canvas (Konva Stage visible inside
  `image-viewport` testid).
- Right panel shows word-match line cards in the `WordMatchView`.

**Testids.** `project-loading-overlay`, `image-viewport`, `line-card-0`.

**Pass criterion.** URL is canonical form. First line card is visible. No
`notification-negative-*` toasts appeared.

---

### 1.2 — Navigate to next page (button)

**Action.** Click `nav-next-button`.

**Expected.**

- URL changes to `/projects/{id}/pages/pageno/2`.
- Canvas re-renders with the second page image.
- `nav-prev-button` is now enabled.
- `page-name-label` shows the second image filename.

**Pass criterion.** `page-name-label` text matches `image_paths[1]` filename.
Old line cards are gone; new line cards for page 2 appear.

---

### 1.3 — Navigate to previous page (button)

**Action.** From page 2, click `nav-prev-button`.

**Expected.** URL returns to `/projects/{id}/pages/pageno/1`. Page 1 image
restores. `nav-prev-button` becomes disabled (page 1 is first page).

**Pass criterion.** URL is page 1. `nav-prev-button` has `disabled` attribute.

---

### 1.4 — Navigate by page number input

**Action.** Click `nav-page-input`. Clear any existing value. Type `2`. Press
`Enter`.

**Expected.** Equivalent to clicking `nav-next-button`: URL changes to
`/projects/{id}/pages/pageno/2`.

**Testids.** `nav-page-input`, `nav-goto-button`, `nav-page-total-label`.

**Pass criterion.** URL contains `/pageno/2`. `nav-page-total-label` still
shows the correct total page count.

---

### 1.5 — Navigate by page number input: out-of-range

**Action.** Type a page number larger than the total page count into
`nav-page-input`. Press `Enter`.

**Expected.** URL clamps to the last valid page. No crash. A warning toast
may appear.

**Pass criterion.** URL ends with `pageno/<last_valid_page>`. No JS exception.

---

### 1.6 — Hotkey: next/previous page

**Action.** While focus is anywhere on the `ProjectPage` (not inside an input),
press `Ctrl+ArrowRight` (Windows/Linux) or `Cmd+ArrowRight` (macOS).

**Expected.** Page advances by 1 (same as clicking `nav-next-button`). Pressing
`Ctrl+ArrowLeft` goes back.

**Pass criterion.** URL changes to expected page number. Repeating at last page
does not wrap (stays on last page).

---

### 1.7 — Hotkey: first and last page

**Action.** Press `Ctrl+Home`. Then press `Ctrl+End`.

**Expected.** `Ctrl+Home` navigates to page 1; `Ctrl+End` navigates to the
last page.

**Pass criterion.** URL reflects page 1 after `Ctrl+Home`; URL reflects last
page after `Ctrl+End`.

---

### 1.8 — Deep-link to specific page (URL)

**Action.** Navigate directly to
`http://localhost:5173/projects/{id}/pages/pageno/2` by pasting in the address
bar.

**Expected.** App loads project `{id}` and opens page 2 without user clicking
Load. If the project was not in server memory (fresh server restart), a load is
triggered automatically.

**Pass criterion.** Page 2 image visible. `page-name-label` shows the page-2
filename.

---

### 1.9 — Deep-link with legacy URL (redirect)

**Action.** Navigate to `http://localhost:5173/project/{id}/page/2` (legacy
path).

**Expected.** Browser issues 301 redirect to `/projects/{id}/pages/pageno/2`.
App renders correctly.

**Pass criterion.** Final URL is the canonical `/projects/.../pageno/2` form.

---

### 1.10 — Deep-link with unknown project

**Action.** Navigate to `http://localhost:5173/projects/no-such-project/pages/pageno/1`.

**Expected.** App renders "Project not found" message inline inside the chrome.
Header bar is still visible. No JS 404 error route.

**Testids.** Header testids (`project-select`, etc.) are still present.

**Pass criterion.** Page does not blank out. Header interactive. The inline
message indicates the project was not found.

---

### 1.11 — Change source folder

**Action.** Click `source-folder-button`. Dialog opens.

Sub-step a: inspect controls: `source-folder-current-path-label`,
`source-folder-path-input`, `source-folder-home-button`,
`source-folder-up-button`, `source-folder-open-typed-button`,
`source-folder-use-current-button`, `source-folder-cancel-button`,
`source-folder-apply-button`.

Sub-step b: type a valid path into `source-folder-path-input`. Press `Enter`.
Confirm the path label updates.

Sub-step c: click `source-folder-apply-button`. Dialog closes. Project list
refreshes in `project-select` to reflect the new root.

Sub-step d: click `source-folder-cancel-button` without applying. Confirm the
source root did NOT change.

**Pass criterion.** After apply, `GET /api/projects` returns projects from the
new root. After cancel, root is unchanged.

---

### 1.12 — Load a different project via dropdown

**Action.** With a project already loaded, select a different project from
`project-select` and click `load-project-button`.

**Expected.** `project-loading-overlay` appears. After load, URL changes to the
new project's first page. Old project's state is cleared.

**Pass criterion.** URL contains the new `{id}`. `page-name-label` shows the
new project's first image.

---

## Phase 2: Word Inspection

### 2.1 — View line cards in Matches tab

**Action.** Ensure the `text-tab-matches` tab is active (click it if not). Scroll
the word-match view to see line cards.

**Expected.** Each line card (`line-card-{n}`) shows:

- Line header with background color reflecting `overall_match_status`
  (green=exact, yellow=fuzzy, red=mismatch, gray=unmatched_ocr, blue=unmatched_gt).
- Count chips for exact/fuzzy/mismatch/unmatched counts.
- Per-word cells arranged horizontally.

**Pass criterion.** At least one line card visible. Background color matches the
line's match status.

---

### 2.2 — Inspect word image cell

**Action.** Locate a word in the match list. Observe the image cell
(`word-image-cell-{l}-{w}`).

**Expected.** For normal words, the cell shows a CSS-background crop of the
page image at the word's bbox coordinates. The clip is sized to
`bbox.width * scale` by `bbox.height * scale`.

For `unmatched_gt` words, a blue `Type` (lucide) icon appears instead of an
image.

**Pass criterion.** Image cells for OCR words are non-empty and visually show
the word region from the scan. No HTTP request per word (all use the same
`image_url`).

---

### 2.3 — Inspect OCR text and tag chips

**Action.** Find a word with a style label (e.g. `italics`). Inspect
`ocr-text-label-{l}-{w}`.

**Expected.**

- OCR text renders in monospace font.
- Style chip (`word-tag-chip-{l}-{w}-italics`) appears in blue-family color
  (bg `#e7f0ff`, border `#b8ccf3`).
- Component chip (if present) appears in green-family color (bg `#e7f8ee`).
- Hovering a chip reveals a `×` button (`word-tag-clear-button-{l}-{w}-{label}`).

**Testids.** `ocr-text-label-{l}-{w}`, `word-tag-chip-{l}-{w}-{label}`,
`word-tag-clear-button-{l}-{w}-{label}`.

**Pass criterion.** All active style/component labels have visible chips. Chip
colors match the spec palettes.

---

### 2.4 — Inspect word status icon

**Action.** Observe `word-status-icon-{l}-{w}` for words of each match status.

**Expected.**

| Status | Icon | Color |
|---|---|---|
| exact | CheckCircle | green-600 |
| fuzzy | AlertTriangle | yellow-600 |
| mismatch | XCircle | red-600 |
| unmatched_ocr | HelpCircle | gray-500 |
| unmatched_gt | Info | blue-600 |

Fuzzy words also show the fuzz score below the icon (two decimal places).

**Pass criterion.** Each visible status icon matches its expected icon + color.
Fuzz scores are shown for fuzzy/mismatch words.

---

### 2.5 — Hover tooltip on OCR label

**Action.** Hover the cursor over `ocr-text-label-{l}-{w}` for a fuzzy/mismatch
word.

**Expected.** A shadcn Tooltip appears showing the match status, fuzz score,
and OCR/GT diff.

**Pass criterion.** Tooltip is visible and non-empty within 300 ms.

---

### 2.6 — Switch to Ground Truth tab

**Action.** Click `text-tab-ground-truth`.

**Expected.** The word-match view is replaced by a read-only `<textarea>` showing
the full page GT plaintext (`page_text_gt`). Monospace font.

**Pass criterion.** Textarea content is non-empty and matches the expected GT
for this page.

---

### 2.7 — Switch to OCR tab

**Action.** Click `text-tab-ocr`.

**Expected.** Textarea shows the full page OCR plaintext (`page_text_ocr`).

**Pass criterion.** Content is non-empty. Different from GT if the OCR is not
perfect.

---

### 2.8 — Switch back to Matches tab

**Action.** Click `text-tab-matches`.

**Expected.** Word-match list reappears. Selected filter is remembered.

**Pass criterion.** Line cards are visible. Filter toggle state is unchanged
from before switching.

---

### 2.9 — Filter: Unvalidated Lines (default)

**Action.** Confirm `match-filter-unvalidated` is the active option (default).
Observe how many line cards are shown.

**Expected.** Only lines where `is_fully_validated === false` are listed.

**Pass criterion.** Count of visible line cards equals the number of
incompletely-validated lines on this page.

---

### 2.10 — Filter: Mismatched Lines

**Action.** Click `match-filter-mismatched`.

**Expected.** Only lines with `overall_match_status` in
`{mismatch, unmatched_ocr, unmatched_gt}` are shown. The list may be shorter
than the Unvalidated filter.

**Pass criterion.** Switching to All and back to Mismatched produces the same
count as the initial Mismatched view.

---

### 2.11 — Filter: All Lines

**Action.** Click `match-filter-all`.

**Expected.** All lines (including fully validated ones) appear. Count is the
total line count for the page.

**Pass criterion.** Line count equals `page.line_matches.length` (before any
server-side filtering).

---

### 2.12 — Scroll the virtualised list

**Action.** On a page with more than 15 lines, scroll the word-match list to the
bottom and back to the top.

**Expected.** Only ~10 line cards are mounted in the DOM at any time (others
virtualised). Scrolling does not cause jank or layout shifts. New cards mount as
the user scrolls.

**Pass criterion.** `document.querySelectorAll('[data-testid^="line-card-"]').length`
stays ≤ `visible_count + 6` (3 overscan each direction) throughout scroll.

---

### 2.13 — Open Word Edit Dialog via edit button

**Action.** Click `edit-word-button-{l}-{w}` for any word.

**Expected.** `word-edit-dialog` appears. `dialog-header-label` shows "Edit
Line N, Word M". `dialog-gt-input` is focused. The three preview columns
(`dialog-previous-preview-column`, `dialog-current-preview-column`,
`dialog-next-preview-column`) are all present.

**Pass criterion.** Dialog is open. All `dialog-*` testids are visible and
accessible.

---

### 2.14 — Inspect zoom toggle in dialog

**Action.** With the Word Edit Dialog open, locate `dialog-current-zoom-toggle`.
Click 5× zoom.

**Expected.** The interactive word image in `dialog-current-preview-column`
scales to 5× its original bbox size.

**Pass criterion.** Image visually enlarges. Testid `dialog-current-zoom-toggle`
reflects the new selection.

---

### 2.15 — Navigate prev/next word in dialog

**Action.** In the Word Edit Dialog, click `dialog-previous-preview-column` (or
press `ArrowLeft`).

**Expected.** Dialog updates to show the previous word in the same line. Header
label changes. New word's bbox shown.

**Pass criterion.** `dialog-header-label` reports a different word index.
Dialog does not close and reopen — it updates in place.

---

## Phase 3: Validation Flows

### 3.1 — Validate a single word (per-word button)

**Action.** Click `word-validate-button-{l}-{w}` for an unvalidated word.

**Expected.**

- Button changes from gray check to green filled check (optimistic update).
- `POST /api/projects/{id}/pages/{idx}/words/{l}/{w}/validate` fires with
  `{validated: true}`.
- No loading spinner needed (single-word mutation is fast).

**Pass criterion.** Button is visually green after click. No `notification-negative-*`
toast. On page reload, word is still validated.

---

### 3.2 — Toggle word back to unvalidated

**Action.** Click the same `word-validate-button-{l}-{w}` again (now green).

**Expected.** Button reverts to gray. `validated: false` sent.

**Pass criterion.** Button is gray. Word appears in the Unvalidated filter list
again.

---

### 3.3 — Validate entire line (line header button)

**Action.** Click `line-validate-button-{n}` on a line with some unvalidated
words.

**Expected.**

- All `word-validate-button-{n}-*` buttons in that line go green.
- Line header shows `is_fully_validated` state (Validate button label changes
  to "Unvalidate").
- A positive notification may appear.

**Pass criterion.** After the mutation completes, filtering to "Unvalidated" no
longer shows this line.

---

### 3.4 — Unvalidate line

**Action.** Click the same `line-validate-button-{n}` again (now showing
"Unvalidate").

**Expected.** All words in the line return to unvalidated state.

**Pass criterion.** Line reappears in the Unvalidated filter list.

---

### 3.5 — Validate all words on page (toolbar page-validate)

**Action.** Click `toolbar-page-validate`.

**Expected.**

- `POST /api/projects/{id}/pages/{idx}/words/validate-batch` with
  `{scope:"page", validated:true}`.
- Every line card flips to fully validated.
- Switching to "Unvalidated" filter shows an empty list.
- A positive toast: something like "All words validated".

**Pass criterion.** Unvalidated filter shows zero line cards. No
`notification-negative-*` toast.

---

### 3.6 — Unvalidate all words on page (toolbar page-unvalidate)

**Action.** Click `toolbar-page-unvalidate`.

**Expected.** All words return to unvalidated. Unvalidated filter shows all
lines.

**Pass criterion.** Unvalidated filter count equals total line count.

---

### 3.7 — Validate selected words (word-scope toolbar)

**Action.**

1. Check two word checkboxes: `word-checkbox-{l1}-{w1}` and
   `word-checkbox-{l2}-{w2}`.
2. Click `toolbar-word-validate`.

**Expected.** Only those two words are validated. Other words unchanged.

**Pass criterion.** Both targeted `word-validate-button-*` cells are green.
Other buttons remain gray.

---

### 3.8 — Validate selected line (line-scope toolbar)

**Action.**

1. Check `line-checkbox-{n}` for one or two lines.
2. Click `toolbar-line-validate`.

**Expected.** Selected lines are fully validated. Non-selected lines are
unchanged.

**Pass criterion.** Only checked lines show "Unvalidate" in their header button.

---

### 3.9 — Validate by paragraph

**Action.**

1. Check `paragraph-checkbox-{p}` (present on the first line of each
   paragraph).
2. Click `toolbar-paragraph-validate`.

**Expected.** All lines in that paragraph are validated.

**Pass criterion.** Every line in the selected paragraph shows fully-validated
state.

---

### 3.10 — Edit inline GT text

**Action.**

1. Click `gt-text-input-{l}-{w}` for any word.
2. Clear the field and type a new text value.
3. Press `Enter` (or click elsewhere to blur).

**Expected.**

- While typing, the input holds the new value.
- On commit, `POST .../words/{l}/{w}/ground-truth` fires with `{text: newValue}`.
- The word's match status re-evaluates: if the new GT now matches OCR, the
  status changes to `exact` and the status icon updates.

**Pass criterion.** `ocr-text-label-{l}-{w}` and `gt-text-input-{l}-{w}` show
the new value. Status icon reflects the updated match.

---

### 3.11 — Revert inline GT edit with Escape

**Action.**

1. Focus `gt-text-input-{l}-{w}`.
2. Type a new value but do NOT press Enter.
3. Press `Escape`.

**Expected.** Input reverts to the last committed value. No POST fires.

**Pass criterion.** Input text equals the pre-edit value. No network request.

---

### 3.12 — Tab navigation through GT inputs

**Action.**

1. Focus `gt-text-input-0-0` (first word of first line).
2. Press `Tab` repeatedly.

**Expected.** Focus moves to `gt-text-input-0-1`, then `gt-text-input-0-2`, …
then wraps to `gt-text-input-1-0` (first word of next line).

**Pass criterion.** Focus follows reading order (left-to-right within line,
top-to-bottom across lines).

---

### 3.13 — Shift+Tab reverse navigation

**Action.** Press `Shift+Tab` from `gt-text-input-1-0`.

**Expected.** Focus moves to the last word of line 0 (e.g. `gt-text-input-0-5`
if line 0 has 6 words).

**Pass criterion.** Focus follows reverse reading order.

---

### 3.14 — GT→OCR for a line

**Action.** Click `line-gt-to-ocr-button-{n}` on a line where GT differs from
OCR.

**Expected.**

- `POST .../lines/{n}/copy-gt {direction:"gt_to_ocr"}` fires.
- OCR text for each word in the line updates to match the GT text.
- Match status for all words in the line becomes `exact`.

**Pass criterion.** After the mutation, `ocr-text-label-{n}-*` cells show the
GT values. Status icons all show green checkmarks.

---

### 3.15 — OCR→GT for a line

**Action.** Click `line-ocr-to-gt-button-{n}` on a line where OCR differs from
GT.

**Expected.** GT inputs update to match OCR values.

**Pass criterion.** `gt-text-input-{n}-*` fields all show the OCR text.

---

## Phase 4: CharFixer / Char-level Editing

### 4.1 — Open CharFixer section in RightPanel (WordDetail accordion)

**Action.** Click a word on the canvas (or click its edit button), then in
the RightPanel expand the "Char Fixer" accordion item.

**Expected.** `CharFixerSection` expands showing individual character cells for
the selected word's OCR text. Each character is represented by a canvas tile
(`CharFixerCanvas`).

**Pass criterion.** Accordion item expands. Character count matches the word's
`ocr_text.length`.

---

### 4.2 — Apply a character fix (replace character)

**Action.** In the CharFixer canvas, click on a character cell that is incorrect.
Select or type the correct character. Confirm the fix.

**Expected.** The character in that position updates. The change is staged for
apply (or applied immediately, per implementation). The OCR text label reflects
the new character.

**Pass criterion.** After the fix is applied, the character cell shows the new
glyph.

---

### 4.3 — Open CharRanges section

**Action.** Expand the "Char Ranges" accordion item in WordDetail.

**Expected.** `CharRangesSection` shows range controls allowing the user to mark
character-level style spans within the word (start, end, style list).

**Pass criterion.** Section is visible. At minimum one "Add range" affordance is
present.

---

### 4.4 — Add a character range

**Action.** In CharRangesSection, specify a start/end character index and select
a style label. Confirm.

**Expected.**

- The range is added to the list.
- `POST .../words/{l}/{w}/char-ranges` fires with the new range data.

**Pass criterion.** New range row appears in the section. No error toast.

---

### 4.5 — Delete a character range

**Action.** Click the × or delete button on an existing char range row.

**Expected.** Range is removed from the list and the backend is updated.

**Pass criterion.** The deleted row is gone. Word is re-rendered without the
deleted range's style.

---

## Phase 5: Erase Tool

### 5.1 — Enter Erase mode (button)

**Action.** Click `erase-pixels-button` in the image tabs header.

**Expected.** Button shows pressed/active state. Canvas cursor changes (crosshair
or eraser icon). Mode is `erase`.

**Testid.** `erase-pixels-button`.

**Pass criterion.** Button has active visual state. Subsequent drag on canvas
draws a red-fill rectangle (preview: `rgba(255,255,255,0.92)` fill,
`rgba(220,38,38,0.75)` stroke).

---

### 5.2 — Erase a region on the page canvas

**Action.** With erase mode active, click and drag a rectangle over a word on
the page image.

**Expected.**

- During drag: a semi-transparent red rectangle appears.
- On mouseup: `POST .../erase-pixels {bbox: BBox}` fires.
- The page image updates (the erased region is filled white).
- Mode remains `erase` (allows multi-erase).

**Pass criterion.** After the POST succeeds, the canvas shows the whited-out
region. `has_edited_image` in `PagePayload` becomes `true`, enabling
`reload-ocr-edited-button`.

---

### 5.3 — Exit Erase mode (button toggle)

**Action.** Click `erase-pixels-button` again while in erase mode.

**Expected.** Button state returns to normal (not pressed). Canvas cursor returns
to default select cursor. Mode returns to `select`.

**Pass criterion.** `erase-pixels-button` no longer appears active. Dragging on
canvas now does box-selection, not erase.

---

### 5.4 — Enter Erase mode (hotkey)

**Action.** With canvas focused, press `Shift+E`.

**Expected.** Identical to clicking `erase-pixels-button`.

**Pass criterion.** Same as 5.1.

---

### 5.5 — Cancel erase mode (Escape)

**Action.** With erase mode active, press `Escape`.

**Expected.** Mode returns to `select`. Any in-progress drag rect is discarded.

**Pass criterion.** `erase-pixels-button` appears inactive. Mode is `select`.

---

### 5.6 — Erase pixels inside Word Edit Dialog

**Action.**

1. Open Word Edit Dialog for a word.
2. Click `dialog-erase-toggle` (the Erase toggle inside the dialog image area).
3. Drag a rectangle over part of the word image.

**Expected.**

- Erase mode is activated within the dialog.
- Semi-transparent red rectangle overlays the dragged region.
- Multiple drag operations stage multiple erase rects (all visible simultaneously).
- Each staged rect has a remove affordance (click to remove).

**Pass criterion.** Staged rects are visible as overlaid red shapes on the word
image.

---

### 5.7 — Apply staged erase rects

**Action.** After staging at least two erase rects in the dialog, click
`dialog-apply-button`.

**Expected.** All staged rects are posted as separate
`POST .../words/{l}/{w}/erase-pixels` calls. Dialog re-renders with updated
word image (white regions where erase was applied). Staged list clears.

**Pass criterion.** Erase rects are gone from the staging display. Word image
shows the erasures.

---

### 5.8 — Reset staged erase rects

**Action.** With staged erase rects present in the dialog, click
`dialog-reset-button`.

**Expected.** Staged rects are cleared. No POST fires. Word image unchanged.

**Pass criterion.** No red overlays visible on the dialog word image. No network
request.

---

## Phase 6: Word Editor

### 6.1 — Entry point: edit button in word cell

**Action.** Click `edit-word-button-{l}-{w}`.

**Expected.** `word-edit-dialog` opens. All required testids are present
(listed in `13-driver-contract.md` §2.11).

**Pass criterion.** Dialog opens. `dialog-header-label` reads "Edit Line {l+1},
Word {w+1}" (1-based display).

---

### 6.2 — Edit GT text in dialog

**Action.** Clear `dialog-gt-input` and type new text. Press `Enter`.

**Expected.** `POST .../words/{l}/{w}/ground-truth` fires. Match status updates.
Dialog remains open.

**Pass criterion.** No dialog close occurs. `dialog-gt-input` shows committed
value. Status icon in matches view updates.

---

### 6.3 — Apply style in dialog

**Action.**

1. Select a style from `dialog-style-select` (e.g. "italics").
2. Select scope from `dialog-scope-select` ("whole").
3. Click `dialog-apply-style-button`.

**Expected.** `POST .../words/{l}/{w}/style {style:"italics", scope:"whole"}`.
Style chip appears on the word in the matches view.

**Pass criterion.** Style chip `word-tag-chip-{l}-{w}-italics` is visible after
dialog is applied or closed.

---

### 6.4 — Apply component in dialog

**Action.** Select a component from `dialog-component-select` (e.g.
"footnote_marker"). Click `dialog-apply-component-button`.

**Expected.** `POST .../words/{l}/{w}/component {component:"footnote_marker", enabled:true}`.
Component chip appears.

**Pass criterion.** Component chip visible. No error toast.

---

### 6.5 — Clear component in dialog

**Action.** Click `dialog-clear-component-button` while a component is selected.

**Expected.** `POST .../words/{l}/{w}/component {component:"...", enabled:false}`.
Component chip is removed.

**Pass criterion.** Chip gone from the word cell.

---

### 6.6 — Merge word with previous

**Action.** In the Word Edit Dialog for word `(l, w)` where `w > 0`, click
`dialog-merge-prev-button`.

**Expected.** `POST .../words/{l}/{w}/merge {direction:"left"}`. The dialog
updates to reflect the merged word. Previous word disappears from the line.

**Pass criterion.** Word count in line decreases by 1. Dialog shows updated word
with merged text.

---

### 6.7 — Merge word with next

**Action.** Click `dialog-merge-next-button` for a word that is not the last in
its line.

**Expected.** Analogous to 6.6 in the right direction.

**Pass criterion.** Word count in line decreases by 1.

---

### 6.8 — Place click marker

**Action.** Click on the word image in the dialog (inside
`dialog-current-preview-column`).

**Expected.** A solid blue vertical line (click marker) appears at the click
x-position. Clicking again at a different x replaces the marker.

**Pass criterion.** Marker is visible. Clicking at the marker's position removes
it.

---

### 6.9 — Split word horizontally at marker

**Action.**

1. Place the click marker near the center of the word.
2. Click `dialog-split-h-button`.

**Expected.** `POST .../words/{l}/{w}/split {direction:"horizontal", x_fraction:F}`.
The dialog closes (or the word updates) and the matches view shows two words
where there was one.

**Pass criterion.** Line `l` now has one more word than before. Both new words
are visible in the matches view.

---

### 6.10 — Split word vertically at marker

**Action.**

1. Place the click marker near the center.
2. Click `dialog-split-v-button`.

**Expected.** `POST .../words/{l}/{w}/split {direction:"vertical", x_fraction:F}`.
Split reassigns the right portion to the nearest line (may create a new line).

**Pass criterion.** At least one new word appears in the matches view.

---

### 6.11 — Crop operations

**Action.**

1. Place the click marker at a specific position in the word image.
2. Click `dialog-crop-above-button`.

**Expected.** `POST .../words/{l}/{w}/crop {side:"above", marker_x:..., marker_y:...}`.
The word's bbox shrinks from the top edge.

**Pass criterion.** Word image preview in dialog shows a smaller bbox. The bbox
section in `BBoxSection` accordion reflects the new dimensions.

**Variants.** Repeat for `dialog-crop-below-button`, `dialog-crop-left-button`,
`dialog-crop-right-button`.

---

### 6.12 — Refine bbox in dialog

**Action.** Click `dialog-refine-button`.

**Expected.** `POST .../words/{l}/{w}/refine-bbox`. The word's bbox is refined.
Dialog re-renders with updated word image.

**Pass criterion.** BBox in dialog preview changes (may tighten). No error toast.

---

### 6.13 — Expand + Refine in dialog

**Action.** Click `dialog-expand-refine-button`.

**Expected.** `POST .../words/{l}/{w}/expand-and-refine-bbox`. Bbox first
expands then refines. Usually produces a larger, tighter fit.

**Pass criterion.** Bbox changes. No error toast.

---

### 6.14 — Nudge bbox edges (buttons)

**Action.**

1. Click `dialog-nudge-left-plus-button` three times.
2. Observe the pending nudge accumulator.
3. Click `dialog-apply-button`.

**Expected.**

- Each click of `left-plus` increments the left-edge outward by `bbox_nudge_step_px`
  (5px by default), accumulating `{left: 15, right: 0, top: 0, bottom: 0}`.
- Apply fires `POST .../words/{l}/{w}/nudge {left:15, right:0, top:0, bottom:0, refine_after:false}`.
- Dialog re-renders with updated bbox (3 × 5 = 15 px wider on the left).

**Testids.** `dialog-nudge-left-plus-button`, `dialog-nudge-left-minus-button`,
`dialog-nudge-right-plus-button`, `dialog-nudge-right-minus-button`,
`dialog-nudge-top-plus-button`, `dialog-nudge-top-minus-button`,
`dialog-nudge-bottom-plus-button`, `dialog-nudge-bottom-minus-button`.

**Pass criterion.** Bbox changes by expected pixel delta. Accumulator resets to
zero after apply.

---

### 6.15 — Apply + Refine from dialog

**Action.** With a pending nudge accumulated, click `dialog-apply-refine-button`.

**Expected.** `POST .../words/{l}/{w}/nudge {... refine_after:true}`. After
the nudge moves the box, a refine pass tightens it.

**Pass criterion.** Bbox in dialog preview updates. No error toast.

---

### 6.16 — Reset pending changes

**Action.** With a pending nudge and staged erase rects, click
`dialog-reset-button`.

**Expected.** Pending nudge counters return to zero. Staged erase rects are
removed. No POST fires.

**Pass criterion.** No network requests. Dialog state resets.

---

### 6.17 — Apply & Close (commit button)

**Action.** Click `dialog-apply-close-button` (check icon, top-right).

**Expected.** Any pending nudge and staged erase rects are applied (POSTed). Then
the dialog closes.

**Pass criterion.** Dialog is gone. Changes are visible in the matches view.

---

### 6.18 — Discard and close (× button)

**Action.** Make some pending changes in the dialog. Click `dialog-close-button`
(× icon).

**Expected.** Dialog closes without applying pending changes. Word is unchanged.

**Pass criterion.** Dialog is gone. Word bbox and style unchanged from before
opening.

---

### 6.19 — Delete word from dialog

**Action.** Click `dialog-delete-word-button`.

**Expected.** A confirmation dialog appears (shadcn AlertDialog). Confirm it.
`DELETE .../words/{l}/{w}` fires. Dialog closes.

**Pass criterion.** Word is gone from the matches view. Line word count
decreases by 1.

---

### 6.20 — Hotkey navigation inside dialog

**Action.** Press `ArrowLeft` and `ArrowRight` while the dialog is open.

**Expected.** `ArrowLeft` switches to the previous word; `ArrowRight` to the
next word. Dialog header updates.

**Pass criterion.** `dialog-header-label` reflects the new word index.

---

### 6.21 — Hotkey: nudge edges

**Action.** Press `Shift+ArrowLeft` (left edge, shrink), `Shift+ArrowRight`
(left edge, expand), `Shift+ArrowUp` (top edge), `Shift+ArrowDown` (top edge),
`Ctrl+ArrowLeft` (right edge, shrink), `Ctrl+ArrowRight` (right edge, expand),
`Ctrl+ArrowUp` (bottom edge), `Ctrl+ArrowDown` (bottom edge).

**Expected.** Each keypress increments the corresponding nudge accumulator by 1
step (5px).

**Pass criterion.** After 2 `Shift+ArrowLeft` presses, the pending nudge shows
`left: 10` (or equivalent display). After apply, bbox changes by 10px on left
edge.

---

### 6.22 — Hotkey: Apply Style and Component in dialog

**Action.** Press `M` (while dialog is open, not in GT input).

**Expected.** `dialog-apply-style-button` action fires — style from
`dialog-style-select` is applied.

**Action (variant).** Press `Shift+M`.

**Expected.** Component from `dialog-component-select` is applied.

**Pass criterion.** Style/component chip appears in matches view.

---

## Phase 7: Canvas & Overlay Controls

### 7.1 — Toggle paragraph layer visibility

**Action.** Uncheck `layer-paragraphs-checkbox`.

**Expected.** Paragraph bounding-box rectangles disappear from the canvas overlay.
Checking it again restores them.

**Pass criterion.** No paragraph-colored rects visible when unchecked.

---

### 7.2 — Toggle line layer visibility

**Action.** Uncheck `layer-lines-checkbox`.

**Expected.** Line bboxes (pink family) disappear from canvas.

**Pass criterion.** No pink rects visible when unchecked.

---

### 7.3 — Toggle word layer visibility

**Action.** Uncheck `layer-words-checkbox`.

**Expected.** Word bboxes (blue family) disappear from canvas.

**Pass criterion.** No blue word rects visible when unchecked.

---

### 7.4 — Layer visibility hotkeys

**Action.** Focus the canvas (click on it or Tab to it). Press `Shift+P`.

**Expected.** Paragraph layer toggles (same as unchecking `layer-paragraphs-checkbox`).

**Variants.** `Shift+L` (lines), `Shift+W` (words).

**Pass criterion.** Same visual result as unchecking the corresponding checkbox.

---

### 7.5 — Selection mode: Word (default)

**Action.** Confirm `selection-mode-word` radio is active. Click anywhere on the
canvas outside a word bbox.

**Expected.** Selection clears. Toolbar word-scope buttons are disabled.

**Action.** Drag a box over 2–3 word bboxes.

**Expected.** Those words become selected (highlight rects with 3px stroke
appear). Toolbar `toolbar-word-validate` etc. become enabled.

**Pass criterion.** `useSelectionStore.selectedWords.size === N` where N is
the number of words inside the drag rect.

---

### 7.6 — Selection mode: Line

**Action.** Click `selection-mode-line` radio. Drag a box overlapping multiple
line bboxes.

**Expected.** Lines (not individual words) are selected. Toolbar line-scope
buttons are enabled.

**Pass criterion.** Selected lines are highlighted. `toolbar-line-validate` is
enabled.

---

### 7.7 — Selection mode: Paragraph

**Action.** Click `selection-mode-paragraph` radio. Click inside a paragraph
bbox.

**Expected.** That paragraph is selected. Toolbar paragraph-scope buttons are
enabled.

**Pass criterion.** Paragraph checkbox in the corresponding line header shows
checked state. `toolbar-paragraph-validate` is enabled.

---

### 7.8 — Selection modifier: Shift+drag removes from selection

**Action.**

1. Drag to select 5 words.
2. Hold `Shift` and drag a box over 2 of those words.

**Expected.** Those 2 words are removed from the selection (XOR-set difference).
Remaining 3 words stay selected.

**Pass criterion.** Selection count decreases by 2.

---

### 7.9 — Selection modifier: Ctrl+drag toggles

**Action.**

1. Select 3 words.
2. Hold `Ctrl` and drag over those 3 words plus 2 new ones.

**Expected.** The already-selected 3 are toggled out; the 2 new ones are added.
Net: 2 words selected.

**Pass criterion.** Selection count is 2 (the symmetric difference).

---

### 7.10 — Clear selection with Escape

**Action.** With words selected, press `Escape`.

**Expected.** All selections cleared. Canvas drag rect (if any) dismissed. Mode
returns to `select`.

**Pass criterion.** No highlighted words. Toolbar word-scope buttons are
disabled.

---

### 7.11 — Add Word mode (button)

**Action.** Click `word-add-button`.

**Expected.** Button shows pressed/active state. Canvas cursor indicates add mode.

**Action.** Drag a rectangle on the canvas over blank space.

**Expected.** `POST .../words/add {bbox: BBox, text:""}` fires. A new word
appears in the matches view at the nearest line (identified by the backend).
Mode stays `add-word` (allows multi-add).

**Pass criterion.** New word cell appears. Word has empty GT text. Mode is still
`add-word`.

---

### 7.12 — Exit Add Word mode

**Action.** Click `word-add-button` again.

**Expected.** Button returns to inactive state. Mode returns to `select`.

**Variant.** Press `Escape` while in add-word mode.

**Pass criterion.** Button inactive. Dragging canvas does box-selection, not add.

---

### 7.13 — Add Word hotkey

**Action.** With canvas focused, press `Shift+A`.

**Expected.** Add Word mode toggles on (equivalent to clicking `word-add-button`).

**Pass criterion.** Same as 7.11.

---

### 7.14 — Rebox mode (via Word Edit Dialog)

**Action.**

1. Open Word Edit Dialog.
2. Locate the rebox controls in `ReboxSection` accordion.
3. Click the rebox/draw button to enter rebox mode.

**Expected.** Canvas switches to `rebox` mode. Cursor changes. The dialog may
minimize or remain open depending on implementation.

**Action.** Drag a new bounding box on the canvas for this word.

**Expected.** On mouseup, `POST .../words/{l}/{w}/rebox {bbox: BBox}` fires.
Dialog re-renders with the new bbox preview.

**Pass criterion.** Word's bbox updates in both the dialog and the canvas overlay.

---

### 7.15 — Rail: switch target (Block/Para/Line/Word)

**Action.** Click `rail-target-word` (or press hotkey `4`).

**Expected.** Rail target changes to Word. `data-active="true"` on
`rail-target-word`. Hotkeys `1`/`2`/`3`/`4` switch Block/Para/Line/Word.

**Variants.** Click each of `rail-target-block`, `rail-target-para`,
`rail-target-line` and verify `data-active="true"` on the clicked one.

**Pass criterion.** Active cell carries `data-active="true"`. Other cells have
no `data-active` attribute or `data-active="false"`.

---

### 7.16 — Rail: switch mode (View/Refine/Annotate/Erase)

**Action.** Click `rail-mode-region` ("Refine" mode). Verify `data-active="true"`.
Then click `rail-mode-view` to return to View.

**Hotkeys.** `V`/`R`/`A`/`E` switch view/region/annotate/erase respectively.

**Pass criterion.** Active mode card carries `data-active="true"`.

---

### 7.17 — Rail: open Hotkeys overlay

**Action.** Click `rail-hotkeys-button` (keyboard icon, footer of Rail).

**Expected.** Hotkey help modal opens (same as pressing `?`).

**Pass criterion.** Modal is visible. Closes with `Escape`.

---

### 7.18 — Rail: Bulk actions button

**Action.** Click `rail-bulk-button` (list icon, footer of Rail).

**Expected.** Bulk actions panel or drawer opens showing batch operations for the
selected scope.

**Pass criterion.** Bulk actions UI is visible.

---

### 7.19 — Zoom fit and 100%

**Action.** Click `zoom-fit-button`.

**Expected.** Page image scales to fit the viewport width.

**Action.** Click `zoom-100-button`.

**Expected.** Page image renders at 1:1 pixel ratio.

**Pass criterion.** Canvas width visually changes in each case.

---

### 7.20 — Hotkey help modal

**Action.** Press `?` anywhere on the project page (not inside an input).

**Expected.** `hotkey-help-dialog` opens. Displays all hotkeys grouped by scope
(global, viewport, matches, dialog, etc.). Scrollable.

**Pass criterion.** `hotkey-help-dialog` testid is visible. Contains entries for
at least `Mod+S`, `Shift+P`, `Tab`, `V`.

---

## Phase 8: Keyboard Shortcuts

All shortcuts below must work from their respective scopes. For each, the
pass criterion is that the associated action fires without using the mouse.

### 8.1 — Global shortcuts

| Combo | Action | Verification |
|---|---|---|
| `Ctrl+S` | Save Page | `save-page-button` action fires; `page-source-badge` changes to "LABELED" |
| `Ctrl+Shift+S` | Save Project | Confirmation dialog appears; confirm → busy overlay; completes |
| `Ctrl+R` | Reload OCR | Confirmation dialog appears; confirm → busy overlay; completes |
| `Ctrl+Shift+R` | Reload OCR (Edited) | Same; only works if `has_edited_image` is true |
| `Ctrl+L` | Load Page from disk | AlertDialog appears; confirm → page reloads |
| `Ctrl+G` | Rematch GT | AlertDialog appears; confirm → GT re-matched |
| `Ctrl+E` | Open Export dialog | `export-dialog` opens |
| `Ctrl+,` | Open OCR Config | `ocr-config-trigger-button` action fires; modal opens |
| `Ctrl+O` | Open Source Folder dialog | `source-folder-button` action fires |
| `?` | Open hotkey help | `hotkey-help-dialog` opens |
| `Escape` | Close any open modal | Active modal closes |
| `Ctrl+ArrowLeft` | Previous page | URL changes to previous page |
| `Ctrl+ArrowRight` | Next page | URL changes to next page |
| `Ctrl+Home` | First page | URL changes to page 1 |
| `Ctrl+End` | Last page | URL changes to last page |
| `Ctrl+J` | Jump to page input | `nav-page-input` receives focus |

**Pass criterion.** Each key combination triggers its action without mouse
interaction.

---

### 8.2 — Viewport-scope shortcuts (canvas focused)

| Combo | Action | Verification |
|---|---|---|
| `Escape` | Cancel mode / clear selection | Mode returns to select; selection clears |
| `Shift+P` | Toggle paragraph layer | Paragraph rects appear/disappear |
| `Shift+L` | Toggle line layer | Line rects appear/disappear |
| `Shift+W` | Toggle word layer | Word rects appear/disappear |
| `Shift+1` | Selection mode → paragraph | `selection-mode-paragraph` becomes active |
| `Shift+2` | Selection mode → line | `selection-mode-line` becomes active |
| `Shift+3` | Selection mode → word | `selection-mode-word` becomes active |
| `Shift+E` | Toggle Erase mode | `erase-pixels-button` active state toggles |
| `Shift+A` | Toggle Add Word mode | `word-add-button` active state toggles |

**Pass criterion.** Each key combination has the described effect.

---

### 8.3 — Matches-scope shortcuts (word-match list focused)

| Combo | Action | Verification |
|---|---|---|
| `Tab` | Next GT input | Focus moves to next word's GT input |
| `Shift+Tab` | Previous GT input | Focus moves to previous word's GT input |
| `J` | Next line card | Scroll/focus advances to next line card |
| `K` | Previous line card | Scroll/focus advances to previous line card |
| `V` | Validate focused/selected | Selected lines/words are validated |
| `U` | Unvalidate focused/selected | Selected lines/words are unvalidated |
| `D` | Delete selected (with confirm) | AlertDialog appears; confirm deletes |
| `R` | Refine selected | Refine fires for selection |
| `Shift+R` | Expand+Refine selected | Expand+Refine fires |
| `M` | Merge selected (≥2) | Merge fires when applicable |
| `O` | OCR→GT for selected | OCR text copied to GT |
| `G` | GT→OCR for selected | GT text copied to OCR |

**Pass criterion.** Each key combination triggers the correct action.

---

### 8.4 — Word Edit Dialog shortcuts

| Combo | Action | Verification |
|---|---|---|
| `Enter` (in GT input) | Commit GT | Text saved; dialog stays open |
| `Escape` | Discard and close | Dialog closes; no changes applied |
| `Shift+Enter` | Apply & Close | Pending changes applied; dialog closes |
| `ArrowLeft` | Previous word in line | Dialog shows previous word |
| `ArrowRight` | Next word in line | Dialog shows next word |
| `Shift+ArrowLeft` | Nudge left edge | Left accumulator increments |
| `Shift+ArrowRight` | Nudge left edge expands | Left accumulator decrements |
| `Shift+ArrowUp` | Nudge top edge expand | Top accumulator increments |
| `Shift+ArrowDown` | Nudge top edge shrink | Top accumulator decrements |
| `Ctrl+ArrowLeft` | Nudge right edge shrink | Right accumulator changes |
| `Ctrl+ArrowRight` | Nudge right edge expand | Right accumulator changes |
| `Ctrl+ArrowUp` | Nudge bottom edge shrink | Bottom accumulator changes |
| `Ctrl+ArrowDown` | Nudge bottom edge expand | Bottom accumulator changes |
| `R` | Refine | Refine bbox fires |
| `Shift+R` | Expand+Refine | Expand+Refine fires |
| `M` | Apply current Style | Style applied |
| `Shift+M` | Apply current Component | Component applied |
| `Delete` | Delete word (with confirm) | AlertDialog; word deleted |

**Pass criterion.** Each key combination triggers the correct action.

---

### 8.5 — Source Folder Dialog shortcuts

| Combo | Action | Verification |
|---|---|---|
| `Enter` (in path input) | Open typed path | `source-folder-open-typed-button` fires |
| `Ctrl+Enter` (in path input) | Apply | `source-folder-apply-button` fires |
| `Escape` | Cancel | Dialog closes; root unchanged |

**Pass criterion.** Each key combination triggers the correct action.

---

### 8.6 — Keyboard-only full editing session

**Action.** Complete the following sequence using only the keyboard (no mouse):

1. Press `Ctrl+ArrowRight` to advance to page 2.
2. Press `Tab` until focus reaches `gt-text-input-0-0`.
3. Clear the field and type a corrected word. Press `Enter`.
4. Press `Tab` three times to move to `gt-text-input-0-3`.
5. Press `Escape` to revert.
6. Press `V` (with matches list focused) to validate the first line.
7. Press `Ctrl+S` to save.

**Expected.** Each step completes without mouse interaction. Step 6 validates the
line. Step 7 saves and `page-source-badge` shows "LABELED".

**Pass criterion.** All steps complete. Final state: page saved, one line
validated, one word corrected.

---

## Phase 9: Error & Edge Cases

### 9.1 — Empty page (OCR returned no words)

**Action.** Load a page that has no detected words (all OCR results empty, or
a fixture page where OCR returns an empty document).

**Expected.** The matches view shows zero line cards. No JS exception. The
toolbar page-row buttons are still present but most are no-ops.

**Pass criterion.** No crash. `match-filter-all` shows 0 visible cards.

---

### 9.2 — OCR failed (fallback page)

**Action.** Simulate an OCR failure by pointing to an image that makes DocTR
fail, then click `reload-ocr-button`.

**Expected.**

- After the job completes, `page-source-badge` shows "FALLBACK" in red.
- An inline banner appears: "OCR failed for this page. Click Reload OCR to retry."
- The matches view shows an empty or near-empty list.

**Pass criterion.** `page-source-badge` text is "FALLBACK". Banner is visible.
No JS crash.

---

### 9.3 — Network error during mutation

**Action.** Kill the FastAPI server mid-session. Then attempt to validate a word
by clicking `word-validate-button-{l}-{w}`.

**Expected.**

- The optimistic update briefly toggles the button green.
- The POST fails.
- The mutation's `onError` handler fires.
- The optimistic update is rolled back (button returns to gray).
- A `notification-negative-*` toast appears with an error message.

**Pass criterion.** Button returns to its pre-click state. Error toast visible.
No unrecoverable state.

---

### 9.4 — Validate button disabled state

**Action.** In word-selection mode, without any words selected, observe toolbar
word-row buttons.

**Expected.** `toolbar-word-validate`, `toolbar-word-unvalidate`,
`toolbar-word-delete`, `toolbar-word-refine` are all disabled.

**Pass criterion.** All word-scope toolbar buttons have `disabled` attribute
when selection is empty.

---

### 9.5 — Merge disabled when fewer than 2 items selected

**Action.** Select exactly 1 line checkbox. Observe `toolbar-line-merge`.

**Expected.** `toolbar-line-merge` is disabled (merge requires ≥ 2).

**Pass criterion.** Button has `disabled` attribute with 1 line selected.

---

### 9.6 — Missing bbox (unmatched GT word)

**Action.** Find a line with an `unmatched_gt` word (a GT word with no
corresponding OCR word). Observe its image cell.

**Expected.** Image cell shows a blue `Type` icon instead of a cropped image.
Word is displayed with `match_status === "unmatched_gt"`. No attempts to render
a zero-size image. Info icon in status cell.

**Pass criterion.** `word-image-cell-{l}-{w}` contains the Type icon, not a
blank/broken image.

---

### 9.7 — Page index out of range (URL)

**Action.** Navigate to `/projects/{id}/pages/pageno/9999` (beyond total pages).

**Expected.** URL is clamped to the last valid page (backend or frontend clamping).
No 500 error. A toast or inline message may notify the user.

**Pass criterion.** URL ends with a valid page number. Page renders.

---

### 9.8 — Image drift (409 conflict)

**Action.** Simulate the image-drift scenario:

1. Load page N.
2. Outside the SPA, modify the source image file on disk (change its mtime).
3. Attempt to Save Page.

**Expected.**

- Backend returns `409 image_drift`.
- SPA intercepts this in the mutation `onError` handler.
- Page is auto-reloaded (`["page", pid, idx]` is invalidated and refetched).
- Toast: "Page reloaded — image was updated since last load."
- No user confirmation required.

**Pass criterion.** Page reloads without any "Save" error banner. Toast appears.

---

### 9.9 — BusyOverlay blocks interaction during long jobs

**Action.** Trigger Save Project (`Ctrl+Shift+S`, confirm). While the job is
running, attempt to click `nav-next-button`.

**Expected.** `busy-overlay` (testid) is visible, covering the page.
`nav-next-button` click is ignored (overlay absorbs the click).

**Pass criterion.** `busy-overlay` is present and opaque during job. Navigation
does not occur.

---

### 9.10 — Cancel a long-running Save Project job

**Action.** Start Save Project. While `busy-overlay` is visible, click the
Cancel button inside the overlay.

**Expected.**

- `POST /api/projects/{id}/jobs/{job_id}/cancel` fires.
- The job stops iterating pages.
- Busy overlay hides.
- A toast summarizes how many pages were saved before cancellation.

**Pass criterion.** Overlay disappears. Some pages may be saved (partial
success). Toast reports `cancelled_count`.

---

### 9.11 — Narrow viewport (< 600px)

**Action.** Resize the browser window to 400px width.

**Expected.** A "screen too narrow" banner appears (per spec). The word-match
grid does not break the layout in a catastrophic way.

**Pass criterion.** No JS crash. Some degraded-but-readable state is shown.

---

## Phase 10: Data Persistence

### 10.1 — Save Page

**Action.** On a page that has been edited (some words validated, some GT changed),
click `save-page-button`.

**Expected.**

- `POST .../pages/{idx}/save` fires.
- `page-source-badge` changes from "CACHED OCR" / "RAW OCR" to "LABELED" (green).
- Toast: positive ("Page saved" or similar).
- `SaveStatus` indicator below the page name shows "Saved N seconds ago".
- On disk: `<labeled-projects>/<project_id>/<project_id>_<page:03d>.json`
  and `<project_id>_<page:03d>.png` are created.

**Pass criterion.** Badge is green LABELED. Files exist on disk. JSON envelope
has `schema.version` of 2.1 or 2.2.

---

### 10.2 — Verify saved content after page reload

**Action.**

1. Save a page with some validated words (10.1).
2. Click `load-page-button` (AlertDialog → confirm).

**Expected.** Page reloads from the saved file. Previously validated words are
still validated. Previously edited GT inputs still show the edited values.
`page-source-badge` shows "LABELED" (not "CACHED OCR").

**Pass criterion.** Page state matches what was saved. No data loss.

---

### 10.3 — Auto-save to cache after each mutation

**Action.**

1. Make a word edit (change GT text).
2. Do NOT click Save Page.
3. Restart the FastAPI server.
4. Navigate back to the same page.

**Expected.** The page reloads from the **cached lane** envelope
(`<cache>/page-images/<project>_<page:03d>_envelope.json`). The GT edit is
preserved. `page-source-badge` shows "CACHED OCR".

**Pass criterion.** Edited GT text is visible after server restart. Badge shows
CACHED OCR.

---

### 10.4 — Auto-save notification

**Action.** Make a word edit. Observe the notifications area.

**Expected.** An auto-save positive notification may appear (implementation may
filter these to reduce noise). The `SaveStatus` indicator shows "Saved N seconds
ago".

**Pass criterion.** `SaveStatus` text updates within ~2s of the mutation.

---

### 10.5 — Save Project

**Action.** Navigate through 3 pages, make at least one edit on each. Click
`save-project-button`.

**Expected.**

- `POST /api/projects/{id}/save-all` fires.
- `busy-overlay` is visible with progress text ("Saved 1 of 3", etc.).
- On completion: overlay hides. Positive toast with summary ("Saved 3 pages").
- `project.json` on disk has `saved_pages` updated.

**Pass criterion.** All 3 pages have `.json` and `.png` files in
`<labeled-projects>/<id>/`. Toast shows correct count.

---

### 10.6 — Save Project with partial failures

**Action.** Make a page unwritable on disk (e.g. make the output directory
read-only). Attempt Save Project.

**Expected.**

- Job completes but with `failed_count > 0`.
- A `notification-warning-*` toast appears with "View details" action.
- Clicking "View details" shows the list of failed pages with reasons.

**Pass criterion.** Warning toast is present. Failure list is viewable.

---

### 10.7 — Session state persistence (last project / last page)

**Action.**

1. Load a project. Navigate to page 5.
2. Close the browser tab.
3. Open a new tab to `http://localhost:5173`.

**Expected.** App redirects to
`/projects/{id}/pages/pageno/5` (or nearest valid page).
`session_state.json` on disk has `last_project_path` and `last_page_index`
matching the last visited page.

**Pass criterion.** User lands on page 5 of the previously open project.

---

### 10.8 — Export DocTR training data (current page)

**Action.**

1. Validate all words on the current page (10.5 will have done this for some).
2. Click `export-button` (or press `Ctrl+E`).
3. In `export-dialog`, select `export-scope-current`.
4. Ensure `export-style-all-checkbox` is checked.
5. Click `export-button` (the run button inside the dialog).

**Expected.**

- `POST /api/projects/{id}/export` fires with `{scope:"current", ...}`.
- `export-dialog` shows a spinner with "Exporting page N of N".
- On completion: a result row appears in `export-results`:
  "all: 1 page, N words exported".
- On disk: `<data>/doctr-export/<project_id>/all/detection/labels.json` and
  `<data>/doctr-export/<project_id>/all/recognition/labels.json` exist.

**Pass criterion.** Result row visible. Files exist on disk.

---

### 10.9 — Export with style filter

**Action.**

1. Open Export dialog.
2. Select `export-scope-all`.
3. Uncheck `export-style-all-checkbox` and check `export-style-checkbox-italics`.
4. Click export.

**Expected.**

- Export iterates all validated pages.
- Only words with `italics` style are included.
- Output directory: `<data>/doctr-export/<project_id>/italics/...`.
- Result row: "italics: N pages, M words exported".

**Pass criterion.** Style-filtered output files exist. Result row shows "italics".

---

### 10.10 — Cancel export mid-flight

**Action.**

1. Start a multi-page export.
2. While `export-dialog` shows the progress spinner, click the Cancel button.

**Expected.**

- `POST /api/projects/{id}/jobs/{job_id}/cancel` fires.
- Export stops between page iterations.
- Partial output directory is deleted on the server.
- Export dialog returns to idle (Export button re-enabled).
- No result row is appended.

**Pass criterion.** Cancel button was visible and clickable. Export dialog
returns to idle. No partial output directory on disk.

---

### 10.11 — Rematch GT (resets per-word overrides)

**Action.**

1. Edit 3 word GT values inline.
2. Click `rematch-gt-button` (or press `Ctrl+G`).
3. Confirm the AlertDialog.

**Expected.**

- All per-word GT edits are cleared.
- `Page.add_ground_truth` is re-run server-side.
- Page payload refetches.
- Edited GT inputs return to the auto-matched values.

**Pass criterion.** Previously edited GT fields now show auto-matched values,
not the hand-edited values.

---

### 10.12 — Load Page from disk (discard edits)

**Action.**

1. Make several edits to the current page.
2. Click `load-page-button` (or press `Ctrl+L`).
3. Confirm the AlertDialog.

**Expected.**

- `POST .../pages/{idx}/load` fires.
- Page reloads from the labeled lane (or cached lane if no labeled file exists).
- All in-session edits are discarded.
- Toast: "Page reloaded from disk. Unsaved edits discarded."

**Pass criterion.** Edits are gone. Page shows the state from the last explicit
save.

---

### 10.13 — Reload OCR (original image)

**Action.** Click `reload-ocr-button` (or press `Ctrl+R`). Confirm.

**Expected.**

- `POST .../pages/{idx}/reload-ocr {use_edited_image:false}` fires.
- `202 Accepted` + job_id returned.
- `busy-overlay` visible with progress ("Loading detection model...",
  "Running OCR...").
- On completion: page refetches. `page-source-badge` shows "RAW OCR".
- Toast: "OCR complete" (positive).

**Pass criterion.** Badge shows "RAW OCR" or "CACHED OCR" (not LABELED, since it
was re-OCRed). New OCR words are visible.

---

### 10.14 — Reload OCR (edited image)

**Pre-condition.** Erase at least one region on the page (Phase 5.2). Confirm
that `reload-ocr-edited-button` becomes enabled.

**Action.** Click `reload-ocr-edited-button` (or press `Ctrl+Shift+R`).

**Expected.** Same job flow as 10.13, but OCR runs on the edited (white-filled)
image. OCR output should differ from the original in the erased region.

**Pass criterion.** `busy-overlay` visible during job. After completion, words in
the erased region are different (or absent) compared to before erasure.

---

### 10.15 — Manual rotation (CW and CCW)

**Action.**

1. Click `rotate-cw-button`.
2. Confirm the long-job flow (202 + busy overlay).
3. After completion, click `rotate-ccw-button`.
4. After completion, verify page is back to original orientation.

**Expected.**

- Each rotate fires `POST .../rotate {degrees: 90 | -90}`.
- Rotation triggers a Reload OCR pass.
- `rotation-badge` shows the current rotation state (hidden when 0°).

**Pass criterion.** After CW: `rotation-badge` shows "90" or "↻ 90". After CCW
back to 0°: `rotation-badge` is hidden.

---

### 10.16 — OCR config: change model selection

**Action.**

1. Click `ocr-config-trigger-button` (or press `Ctrl+,`).
2. In the OCR Config modal, observe `ocr-detection-model-select` and
   `ocr-recognition-model-select`.
3. Click `ocr-config-cancel-button`.

**Expected.** Modal opens. Both selects show available options. Cancel closes
without changing config.

**Action (variant).** Change a model select and click `ocr-config-apply-button`.

**Expected.** Config is saved to `ocr_config.json`. On next Reload OCR, the
selected model is used.

**Pass criterion.** Modal opens and closes. After apply, re-opening the modal
shows the previously selected option still selected.

---

### 10.17 — OCR config: rescan models

**Action.** In the OCR Config modal, click `ocr-rescan-models-button`.

**Expected.** The server re-scans for local models and HuggingFace options. The
option lists update.

**Pass criterion.** No error toast. The model lists may change if new models are
available.

---

### 10.18 — Toolbar Refine bboxes (page scope, job flow)

**Action.** Click `toolbar-page-refine`.

**Expected.**

- `POST .../refine {scope:"page", mode:"refine"}` fires.
- `202 Accepted` + job_id.
- A progress bar appears on the Page row of the toolbar while the job runs.
- On completion: toast.success. Page query refetched. Bboxes are tightened.

**Pass criterion.** Progress bar visible during job. After completion, bbox
coordinates in the matches view differ from pre-refine values.

---

### 10.19 — Toolbar Expand+Refine (page scope)

**Action.** Click `toolbar-page-expand-refine`.

**Expected.** Same job flow as 10.18 but with `mode:"expand_then_refine"`. Bboxes
first expand, then refine — typically produces slightly larger results than
plain refine.

**Pass criterion.** Job completes without error. Bboxes update.

---

### 10.20 — Toolbar delete (with confirmation)

**Action.**

1. Select two words via checkboxes.
2. Click `toolbar-word-delete`.

**Expected.** A shadcn AlertDialog appears requesting confirmation. Confirm →
`POST .../words/delete-batch {word_indices: [...]}`. Two words disappear from the
matches view.

**Pass criterion.** Exactly 2 words fewer in the line(s). No error toast.

---

### 10.21 — Toolbar merge lines

**Action.**

1. Check at least two line checkboxes (`line-checkbox-{n1}` and
   `line-checkbox-{n2}` for adjacent lines).
2. Click `toolbar-line-merge`.

**Expected.** `POST .../lines/merge {line_indices:[n1,n2]}` fires. The two lines
merge into one. Line count decreases by 1.

**Pass criterion.** Merged line is visible. Individual lines n1 and n2 are gone.

---

### 10.22 — Toolbar split line after word

**Action.**

1. Select a word in the middle of a line (`word-checkbox-{l}-{w}`).
2. Click `toolbar-line-split-after`.

**Expected.** `POST .../lines/{l}/split-after-word {after_word_index:w}` fires.
The line splits: words 0..w stay in line l; words w+1..end move to a new line.

**Pass criterion.** Two lines visible where one was. Word counts sum to the
original.

---

### 10.23 — OCR Config: HF revision pinning

**Action.** In OCR Config modal, type a specific commit hash into
`ocr-hf-revision-input`. Click apply.

**Expected.** `hf_pinned_revision` saved to `ocr_config.json`. Re-opening the
modal shows the pinned revision still in the field.

**Pass criterion.** Pinned revision persists across modal close/reopen.

---

### 10.24 — Notification stream delivers toasts from server

**Action.** Trigger an action that produces a server-side notification (e.g.
Save Page → auto-save notification).

**Expected.** The SSE stream at `/api/notifications/stream` emits a notification
event. The SPA's `useNotificationStream` hook receives it and calls the
appropriate `toast.*` method. The toast appears in the top-right corner.

**Pass criterion.** Toast is visible. Its `data-testid` matches
`notification-{kind}-{id}` where `{kind}` matches the `NotificationKind` emitted
by the backend.

---

## Appendix: Complete data-testid Reference

The following table consolidates all testids referenced in this document. Source
of truth is `docs/architecture/13-driver-contract.md`.

### Header / Project Load

`project-select`, `load-project-button`, `source-folder-button`,
`ocr-config-trigger-button`

### Source Folder Dialog

`source-folder-current-path-label`, `source-folder-path-input`,
`source-folder-home-button`, `source-folder-up-button`,
`source-folder-open-typed-button`, `source-folder-use-current-button`,
`source-folder-cancel-button`, `source-folder-apply-button`

### OCR Config Modal

`ocr-detection-model-select`, `ocr-recognition-model-select`,
`ocr-hf-revision-input`, `ocr-rescan-models-button`,
`ocr-config-cancel-button`, `ocr-config-apply-button`

### Navigation

`nav-prev-button`, `nav-next-button`, `nav-goto-button`,
`nav-page-input`, `nav-page-total-label`

### Page Actions

`reload-ocr-button`, `reload-ocr-edited-button`, `save-page-button`,
`save-project-button`, `load-page-button`, `rematch-gt-button`,
`export-button`, `page-source-badge`, `page-name-label`,
`rotate-ccw-button`, `rotate-cw-button`, `rotate-180-button`, `rotation-badge`

### Image Tabs (left pane)

`layer-paragraphs-checkbox`, `layer-lines-checkbox`, `layer-words-checkbox`,
`selection-mode-paragraph`, `selection-mode-line`, `selection-mode-word`,
`erase-pixels-button`, `mismatches-only-toggle`,
`zoom-fit-button`, `zoom-100-button`, `image-viewport`

### Rail

`rail`, `rail-mode-view`, `rail-mode-region`, `rail-mode-annotate`,
`rail-mode-erase`, `rail-target-block`, `rail-target-para`,
`rail-target-line`, `rail-target-word`, `rail-bulk-button`, `rail-hotkeys-button`

### Text Tabs / Right Pane

`text-tab-matches`, `text-tab-ground-truth`, `text-tab-ocr`,
`match-filter-toggle`, `match-filter-unvalidated`, `match-filter-mismatched`,
`match-filter-all`

### Per-line (n = 0-based line index)

`line-card-{n}`, `paragraph-checkbox-{p}`, `line-checkbox-{n}`,
`line-gt-to-ocr-button-{n}`, `line-ocr-to-gt-button-{n}`,
`line-validate-button-{n}`, `line-delete-button-{n}`

### Per-word (l = line index, w = word index)

`word-checkbox-{l}-{w}`, `edit-word-button-{l}-{w}`,
`word-validate-button-{l}-{w}`, `gt-text-input-{l}-{w}`,
`ocr-text-label-{l}-{w}`, `word-status-icon-{l}-{w}`,
`word-image-cell-{l}-{w}`, `word-tag-chip-{l}-{w}-{label}`,
`word-tag-clear-button-{l}-{w}-{label}`

### Toolbar Action Grid

`toolbar-{scope}-{action}` where scope ∈ `page|paragraph|line|word` and
action ∈ `merge|refine|expand-refine|expand-bboxes|split-after|split-selected|
word-to-line|to-paragraph|gt-to-ocr|ocr-to-gt|validate|unvalidate|delete`

### Apply Style / Word Add Row

`apply-style-select`, `scope-select`, `apply-style-button`,
`apply-component-select`, `apply-component-button`, `clear-component-button`,
`word-add-button`

### Word Edit Dialog

`word-edit-dialog`, `dialog-header-label`, `dialog-apply-close-button`,
`dialog-close-button`, `dialog-previous-preview-column`,
`dialog-current-preview-column`, `dialog-next-preview-column`,
`dialog-tag-chips-slot`, `dialog-current-zoom-toggle`, `dialog-gt-input`,
`dialog-style-select`, `dialog-scope-select`, `dialog-component-select`,
`dialog-apply-style-button`, `dialog-apply-component-button`,
`dialog-clear-component-button`, `dialog-merge-prev-button`,
`dialog-merge-next-button`, `dialog-split-h-button`, `dialog-split-v-button`,
`dialog-delete-word-button`, `dialog-crop-above-button`,
`dialog-crop-below-button`, `dialog-crop-left-button`, `dialog-crop-right-button`,
`dialog-refine-button`, `dialog-expand-refine-button`,
`dialog-nudge-left-minus-button`, `dialog-nudge-left-plus-button`,
`dialog-nudge-right-minus-button`, `dialog-nudge-right-plus-button`,
`dialog-nudge-top-minus-button`, `dialog-nudge-top-plus-button`,
`dialog-nudge-bottom-minus-button`, `dialog-nudge-bottom-plus-button`,
`dialog-reset-button`, `dialog-apply-button`, `dialog-apply-refine-button`

### Export Dialog

`export-dialog`, `export-scope-current`, `export-scope-all`,
`export-style-all-checkbox`, `export-style-checkbox-{key}`,
`export-button`, `export-results`, `export-close-button`

### Overlays / Busy / Notifications

`busy-overlay`, `project-loading-overlay`,
`notification-{kind}-{id}` (kind ∈ `positive|negative|warning|info`),
`hotkey-help-dialog`

# New labeler SPA — Dimension B: OCR Content Actions

> Audit date: 2026-06-05
> Auditor: subagent (Claude Sonnet 4.6)
> Repo: `/workspaces/ocr-container/pdomain-ocr-labeler-spa`
> Dimension B covers every action that reads or mutates OCR content at glyph / word / line / block / paragraph / region level. Navigation chrome (A) and whole-document / project / system ops (C) are excluded here; spillover is noted in §Cross-dimension spillover.

---

## Action inventory

| # | Action name | Screen / context | Trigger | Scope | Handler file : line | One-sentence behavior |
|---|---|---|---|---|---|---|
| 1 | Edit word GT text (inline blur-commit) | Matches pane — WordCell | Blur on `gt-text-input-{l}-{w}` | Word | `WordCell.tsx:94` `useLineMutations.ts:useUpdateWordGt` | On focus-leave, if the value changed, POSTs the new ground-truth string to `/words/{li}/{wi}/gt` and invalidates the page query. |
| 2 | Edit word GT text (dialog input) | WordEditDialog | `dialog-gt-input` change + Enter key | Word | `WordEditDialog.tsx:306-311` → `onGtChange` / `onGtCommit` props | Updates local state on change; Enter calls `onGtCommit`, which the parent wires to the same GT update mutation. |
| 3 | Edit word GT text (WordDetail OCR/GT compare row) | Right panel — WordDetail | `ocr-gt-input` blur or Enter | Word | `OcrGtCompareRow.tsx:41-49` → `onCommitGt` → `useUpdateWordGroundTruth` in `WordDetail.tsx:153` | Blur-commits the current input value to `useUpdateWordGroundTruth`, which POSTs to `/words/{li}/{wi}/gt`. |
| 4 | Edit word GT text (CharFixerSection per-char inputs) | Right panel — WordDetail > Char Fixer accordion | `char-fixer-input-{i}` change (debounced 500 ms) | Word (per-character) | `CharFixerSection.tsx:163-175` `useUpdateWordGroundTruth` | Debounces edits across per-char cells and POSTs the reconstructed joined string to `/words/{li}/{wi}/gt` after 500 ms idle. |
| 5 | Insert Unicode character (CharFixerSection picker) | Right panel — WordDetail > Char Fixer accordion | `char-fixer-open-picker-button` opens `UnicodePicker`; click a glyph | Word (per-character) | `CharFixerSection.tsx:214-227` | Inserts a selected Unicode glyph into the last-focused char-fixer cell and triggers the debounced save. |
| 6 | Insert Unicode character (OcrGtCompareRow picker) | Right panel — WordDetail > OCR/GT compare row | `ocr-gt-omega-btn` opens `UnicodePicker`; click a glyph | Word | `OcrGtCompareRow.tsx:54-68` | Inserts the glyph at the current cursor position in the GT input; does NOT auto-commit — user must blur to save. |
| 7 | Copy OCR → GT (per-word, OCR/GT compare row button) | Right panel — WordDetail | `ocr-gt-copy-btn` | Word | `OcrGtCompareRow.tsx:46-52` | Sets GT input value to the OCR text and immediately calls `onCommitGt` (commits to server if value changed). |
| 8 | Copy OCR → GT (per-line, Matches pane) | Matches pane — LineCard | `line-ocr-to-gt-button-{n}` | Line | `LineCard.tsx:218` → `useCopyLineGt` via `onCopyOcrToGt` prop | POSTs `{direction: "ocr_to_gt"}` to `/lines/{li}/copy-gt` for every word in the line. |
| 9 | Copy GT → OCR (per-line, Matches pane) | Matches pane — LineCard | `line-gt-to-ocr-button-{n}` | Line | `LineCard.tsx:209` → `useCopyLineGt` via `onCopyGtToOcr` prop | POSTs `{direction: "gt_to_ocr"}` to `/lines/{li}/copy-gt` for every word in the line. |
| 10 | Copy OCR → GT (per-line, LineDetail footer) | Right panel — LineDetail > Line tab | `line-copy-ocr-to-gt` | Line | `LineDetail.tsx:351-358` `useCopyLineGt.mutate` | POSTs `{direction: "ocr_to_gt"}` to `/lines/{li}/copy-gt`. |
| 11 | Copy GT → OCR (per-line, LineDetail footer) | Right panel — LineDetail > Line tab | `line-copy-gt-to-ocr` | Line | `LineDetail.tsx:339-346` `useCopyLineGt.mutate` | POSTs `{direction: "gt_to_ocr"}` to `/lines/{li}/copy-gt`. |
| 12 | Copy OCR → GT (paragraph-scope) | Right panel — ParagraphDetail | `para-copy-ocr-to-gt` | Paragraph | `ParagraphDetail.tsx:166-173` `useCopyParagraphGt.mutate` | POSTs to `/paragraphs/{pi}/copy-ocr-to-gt` for all words in the paragraph. |
| 13 | Copy GT → OCR (paragraph-scope) | Right panel — ParagraphDetail | `para-copy-gt-to-ocr` | Paragraph | `ParagraphDetail.tsx:157-164` `useCopyParagraphGt.mutate` | POSTs to `/paragraphs/{pi}/copy-gt-to-ocr` for all words in the paragraph. |
| 14 | Copy OCR → GT (toolbar grid, word/line/para/page scope) | Toolbar action grid | `toolbar-{scope}-ocr-to-gt` | Word / Line / Para / Page | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` in `useToolbarDispatch.ts` | Dispatches the scope-appropriate copy-GT endpoint via the toolbar mapping. |
| 15 | Copy GT → OCR (toolbar grid, word/line/para/page scope) | Toolbar action grid | `toolbar-{scope}-gt-to-ocr` | Word / Line / Para / Page | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches the scope-appropriate copy-GT endpoint via the toolbar mapping. |
| 16 | Validate / Unvalidate line (Matches pane toggle) | Matches pane — LineCard | `line-validate-button-{n}` (toggles label) | Line | `LineCard.tsx:229-231` → `useValidateLine.mutate` | POSTs `validated: !current` to `/words/validate-batch` with `scope: "line"`, toggling all words in the line. |
| 17 | Validate / Unvalidate line (LineDetail validate-all footer) | Right panel — LineDetail > Line tab | `line-detail-validate-all` | Line | `LineDetail.tsx:289` `validateLine.mutate({validated: true})` | POSTs `scope: "line"` to `/words/validate-batch`; button is disabled when line is already fully validated. |
| 18 | Validate word (per-word toggle in Matches pane) | Matches pane — WordCell | `word-validate-button-{l}-{w}` | Word | `WordCell.tsx:169-174` (button present; mutation wiring is a stub — no `onClick` mutation in WordCell; wired in ProjectPage) | Renders a per-word validate button; the actual toggle mutation is expected to be wired from ProjectPage. |
| 19 | Validate word (WordDetail footer) | Right panel — WordDetail | `word-footer-validate` | Word | `WordFooter.tsx:116` `useToggleValidated.mutate` | POSTs `{validated: !current}` to `/words/{li}/{wi}/validated`. |
| 20 | Validate selected words (LineDetail Words tab bulk bar) | Right panel — LineDetail > Words tab | `line-detail-bulk-validate` | Word (multi-select) | `LineDetail.tsx:402-410` `validateWords.mutate({wordPairs, validated: true})` | POSTs checked word pairs with `scope: "word"` to `/words/validate-batch`. |
| 21 | Skip (unvalidate) selected words (LineDetail Words tab bulk bar) | Right panel — LineDetail > Words tab | `line-detail-bulk-skip` | Word (multi-select) | `LineDetail.tsx:414-421` `validateWords.mutate({wordPairs, validated: false})` | POSTs checked word pairs with `scope: "word"` and `validated: false` to `/words/validate-batch`. |
| 22 | Validate paragraph (ParagraphDetail) | Right panel — ParagraphDetail | `para-validate` | Paragraph | `ParagraphDetail.tsx:181-189` `validatePara.mutate({validated: true})` | POSTs `scope: "paragraph"` to `/words/validate-batch`. |
| 23 | Unvalidate paragraph (ParagraphDetail) | Right panel — ParagraphDetail | `para-unvalidate` | Paragraph | `ParagraphDetail.tsx:190-198` `validatePara.mutate({validated: false})` | POSTs `scope: "paragraph"` and `validated: false` to `/words/validate-batch`. |
| 24 | Validate all words on page (BulkWordActions) | Bulk actions panel (Rail bulk button) | `page-validate-all` | Page | `BulkWordActions.tsx:76-82` `validatePage.mutate({validated: true})` | POSTs `scope: "page"` to `/words/validate-batch` to validate every word on the page. |
| 25 | Unvalidate all words on page (BulkWordActions) | Bulk actions panel (Rail bulk button) | `page-unvalidate-all` | Page | `BulkWordActions.tsx:85-92` `validatePage.mutate({validated: false})` | POSTs `scope: "page"` and `validated: false` to `/words/validate-batch`. |
| 26 | Validate / Unvalidate (toolbar grid, word/line/para/page scope) | Toolbar action grid | `toolbar-{scope}-validate` / `toolbar-{scope}-unvalidate` | Word / Line / Para / Page | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches validate-batch for the appropriate scope via the toolbar mapping. |
| 27 | Delete line (Matches pane) | Matches pane — LineCard | `line-delete-button-{n}` | Line | `LineCard.tsx:236-239` → `useDeleteLine.mutate` | POSTs `scope: "line"` to `/delete`, removing the line and all its words from the page. |
| 28 | Delete word (WordDetail footer, with confirm dialog) | Right panel — WordDetail | `word-footer-delete` → ConfirmDialog → confirm | Word | `WordFooter.tsx:166-176` `useDeleteWord.mutate` | Opens a confirmation dialog, then POSTs `scope: "word"` to `/delete` on confirm. |
| 29 | Delete word (WordActionRows in dialog) | WordEditDialog | `dialog-delete-word-button` | Word | `WordActionRows.tsx:172-174` → `onDelete` callback wired in ProjectPage | Calls the `onDelete` prop (async), which the parent wires to `useSplitWord` / delete mutation. |
| 30 | Delete selected words (BulkWordActions multi-select) | Bulk actions panel | `bulk-word-delete` | Word (multi-select) | `BulkWordActions.tsx:109-117` `deleteWords.mutate({wordIndices: selectedWords})` | POSTs selected `(lineIndex, wordIndex)` tuples to `/words/delete-batch`. |
| 31 | Delete paragraph (ParagraphDetail) | Right panel — ParagraphDetail | `para-delete` | Paragraph | `ParagraphDetail.tsx:137-149` `deletePara.mutate({paragraphIndex: paraId})` | POSTs to `/paragraphs/{pi}/delete`. |
| 32 | Delete (toolbar grid, line/para/word scope) | Toolbar action grid | `toolbar-{scope}-delete` | Line / Para / Word | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches the appropriate delete route via the toolbar mapping. |
| 33 | Merge word with previous (WordEditDialog) | WordEditDialog | `dialog-merge-prev-button` | Word | `WordActionRows.tsx:127-131` → `onMerge("prev")` callback wired in ProjectPage to `useMergeWord.mutate({direction:"left"})` | Merges the current word with its left neighbour. |
| 34 | Merge word with next (WordEditDialog) | WordEditDialog | `dialog-merge-next-button` | Word | `WordActionRows.tsx:135-139` → `onMerge("next")` wired to `useMergeWord.mutate({direction:"right"})` | Merges the current word with its right neighbour. |
| 35 | Merge word with prev (StructureSection in WordDetail) | Right panel — WordDetail > Structure accordion | `structure-merge-prev` → ConfirmDialog → confirm | Word | `StructureSection.tsx:192-199` `mergeWord.mutate({direction:"left"})` | Shows a merge-preview on hover; on confirm, POSTs `{direction:"left"}` to `/words/{li}/{wi}/merge`. |
| 36 | Merge word with next (StructureSection in WordDetail) | Right panel — WordDetail > Structure accordion | `structure-merge-next` → ConfirmDialog → confirm | Word | `StructureSection.tsx:200-208` `mergeWord.mutate({direction:"right"})` | Shows a merge-preview on hover; on confirm, POSTs `{direction:"right"}` to `/words/{li}/{wi}/merge`. |
| 37 | Merge lines with previous (LineDetail footer) | Right panel — LineDetail > Line tab | `line-detail-merge-prev` | Line | `LineDetail.tsx:305-312` `mergeLines.mutate({lineIndex, direction:"prev"})` | POSTs `{line_indices:[prev, current]}` to `/lines/merge`. |
| 38 | Merge lines with next (LineDetail footer) | Right panel — LineDetail > Line tab | `line-detail-merge-next` | Line | `LineDetail.tsx:317-322` `mergeLines.mutate({lineIndex, direction:"next"})` | POSTs `{line_indices:[current, next]}` to `/lines/merge`. |
| 39 | Merge lines (toolbar grid, line scope) | Toolbar action grid | `toolbar-line-merge` | Line | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches `/lines/merge` with selected line indices via toolbar mapping. |
| 40 | Merge paragraphs (ParagraphDetail) | Right panel — ParagraphDetail | `para-merge` | Paragraph | `ParagraphDetail.tsx:114-123` `mergeParas.mutate({paragraphIndices:[paraId, paraId+1]})` | POSTs `{paragraph_indices:[paraId, paraId+1]}` to `/paragraphs/merge`. |
| 41 | Merge paragraphs (toolbar grid, para scope) | Toolbar action grid | `toolbar-para-merge` | Paragraph | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches `/paragraphs/merge` with selected paragraph indices. |
| 42 | Split word horizontal (WordEditDialog) | WordEditDialog | `dialog-split-h-button` | Word | `WordActionRows.tsx:145-151` → `onSplit(fraction, "h")` wired to `useSplitWord.mutate` | Splits the word at the click-marker x-fraction (horizontal cut), POSTing to `/words/{li}/{wi}/split`. |
| 43 | Split word vertical (WordEditDialog) | WordEditDialog | `dialog-split-v-button` | Word | `WordActionRows.tsx:153-159` → `onSplit(fraction, "v")` | POSTs `{direction:"vertical"}` to `/words/{li}/{wi}/split` (returns 400 from backend currently). |
| 44 | Split word (StructureSection char-picker) | Right panel — WordDetail > Structure accordion | `glyph-panel-charspan-cell-{i}` click to pick position → `structure-split-button` | Word | `StructureSection.tsx:232-239` `splitWord.mutate({xFraction, direction:"horizontal"})` | User clicks a character to pick the split position; clicking "Split" POSTs the derived x-fraction to `/words/{li}/{wi}/split`. |
| 45 | Split line after word (LineDetail footer) | Right panel — LineDetail > Line tab | `line-split-after-word` | Line | `LineDetail.tsx:364-371` `splitAfterWord.mutate({lineIndex, wordIndex:0})` | POSTs `{word_index:0}` to `/lines/{li}/split-after-word` (splits after the first word). |
| 46 | Split line by words (LineDetail footer) | Right panel — LineDetail > Line tab | `line-split-by-words` | Line | `LineDetail.tsx:374-381` `splitByWords.mutate({wordKeys:[[lineIndex,0]]})` | POSTs `{word_keys:[[li,0]]}` to `/lines/split-by-words` to extract first word into a new line. |
| 47 | Split line after word (toolbar grid, line scope) | Toolbar action grid | `toolbar-line-split-after` | Line | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches `/lines/{li}/split-after-word` with the first selected word index. |
| 48 | Split line by selected words (toolbar grid, line scope) | Toolbar action grid | `toolbar-line-split-selected` | Line | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches `/lines/split-by-words` with the selected word keys. |
| 49 | Split paragraph after line (ParagraphDetail) | Right panel — ParagraphDetail | `para-split-after-line` | Paragraph | `ParagraphDetail.tsx:126-136` `splitAfterLine.mutate({paragraphIndex:paraId, afterLineIndex:0})` | POSTs `{after_line_index:0}` to `/paragraphs/{pi}/split-after-line`. |
| 50 | Split paragraph after line (toolbar grid, para scope) | Toolbar action grid | `toolbar-para-split-after` | Paragraph | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches `/paragraphs/{pi}/split-after-line` via toolbar mapping. |
| 51 | Split paragraph by selected lines (toolbar grid) | Toolbar action grid | `toolbar-para-split-selected` | Paragraph | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches the split-selected route for paragraph scope. |
| 52 | Edit line GT text (LineDetail consolidated GT input) | Right panel — LineDetail > Line tab | `line-detail-gt-input` blur or Enter key | Line | `LineDetail.tsx:159-165` `useSetLineGt.mutate` | On blur (or Enter→blur), if value changed, POSTs `{text}` to `/lines/{li}/set-gt`. |
| 53 | Rebox word — numeric inputs (BBoxSection) | Right panel — WordDetail > Bounding Box accordion | `bbox-input-x/y/w/h` blur | Word (bbox) | `BBoxSection.tsx:100-107` `useReboxWord.mutate` | Each numeric input commits on blur, POSTing the updated `{x,y,width,height}` to `/words/{li}/{wi}/rebox`. |
| 54 | Rebox word — nudge (BBoxSection) | Right panel — WordDetail > Bounding Box accordion | `bbox-nudge-left/right/top/bottom` buttons; step set by `bbox-nudge-step` | Word (bbox) | `BBoxSection.tsx:113-117` `commitBbox(applyNudge(draft, dir, nudgeStep))` | Immediately commits a pixel-offset rebox after each nudge button click. |
| 55 | Rebox word — Refine (BBoxSection) | Right panel — WordDetail > Bounding Box accordion | `bbox-refine-button` | Word (bbox) | `BBoxSection.tsx:278-285` `commitBbox(draft)` | Commits the current draft bbox, triggering the backend refine path. |
| 56 | Rebox word — Expand+Refine (BBoxSection) | Right panel — WordDetail > Bounding Box accordion | `bbox-expand-refine-button` | Word (bbox) | `BBoxSection.tsx:286-302` expands by 4 px each side then `commitBbox` | Expands the bbox 4 px on each side and commits, triggering backend expand+refine. |
| 57 | Rebox word — Crop (BBoxSection) | Right panel — WordDetail > Bounding Box accordion | `bbox-crop-button` | Word (bbox) | `BBoxSection.tsx:306-314` `commitBbox(draft)` | Commits the current draft bbox (backend handles crop semantics). |
| 58 | Rebox word — Reset (BBoxSection) | Right panel — WordDetail > Bounding Box accordion | `bbox-reset-button` | Word (bbox) | `BBoxSection.tsx:108-110` `setDraft({...originalBbox}); commitBbox(originalBbox)` | Resets draft to the server-side original bbox and commits it. |
| 59 | Rebox word — Konva mini-canvas drag (ReboxSection) | Right panel — WordDetail > Rebox accordion | Drag 8-handle `ReboxCanvas` in snap/draw mode | Word (bbox) | `ReboxSection.tsx:82-89` → `rebox-apply` button → `reboxMutation.mutate` | User drags handles or draws a new rect; changes are staged locally; clicking `rebox-apply` POSTs the final bbox to `/rebox`. |
| 60 | Rebox word — tool mode select (ReboxSection) | Right panel — WordDetail > Rebox accordion | `rebox-tool-snap/draw/pan` | Word (bbox) | `ReboxSection.tsx:118-138` `setTool(...)` | Switches the Konva canvas interaction mode; no server call until Apply. |
| 61 | Rebox word — zoom in/out (ReboxSection) | Right panel — WordDetail > Rebox accordion | `rebox-zoom-in` / `rebox-zoom-out` | Word (bbox view) | `ReboxSection.tsx:95-100` | Adjusts the canvas display zoom (1×–5×); no server call. |
| 62 | Rebox word — Reset to original (ReboxSection) | Right panel — WordDetail > Rebox accordion | `rebox-reset` | Word (bbox) | `ReboxSection.tsx:91-93` `setDraft({...word.bbox})` | Discards staged bbox changes (local only; no server call until Apply). |
| 63 | Rebox word — Apply (ReboxSection) | Right panel — WordDetail > Rebox accordion | `rebox-apply` | Word (bbox) | `ReboxSection.tsx:82-89` `reboxMutation.mutate` | POSTs the rounded staged bbox to `/words/{li}/{wi}/rebox`. |
| 64 | Nudge bbox — dialog (WordRefineNudgeRows) | WordEditDialog | `dialog-nudge-{edge}-{minus|plus}` (8 buttons) | Word (bbox) | `WordRefineNudgeRows.tsx:185-250` accumulates `PendingNudge` | Accumulates per-edge pixel deltas locally; displayed in `dialog-nudge-display`. |
| 65 | Apply nudge (no refine) — dialog | WordEditDialog | `dialog-apply-button` | Word (bbox) | `WordRefineNudgeRows.tsx:270-275` → `onApply(pending, false)` wired in ProjectPage | Applies the accumulated edge-pixel nudge via rebox, without a refine pass. |
| 66 | Apply nudge + Refine — dialog | WordEditDialog | `dialog-apply-refine-button` | Word (bbox) | `WordRefineNudgeRows.tsx:276-281` → `onApply(pending, true)` | Applies the accumulated nudge then triggers a refine pass. |
| 67 | Reset pending nudge — dialog | WordEditDialog | `dialog-reset-button` | Word (bbox) | `WordRefineNudgeRows.tsx:133-136` `setPending(zero); onReset?.()` | Clears the local nudge accumulator and fires the parent's `onReset` (which also clears erase rects). |
| 68 | Refine bbox (dialog) | WordEditDialog | `dialog-refine-button` | Word (bbox) | `WordRefineNudgeRows.tsx:162-168` → `onRefine()` wired to refine endpoint | Fires an immediate refine call (snaps to ink boundary). |
| 69 | Expand + Refine bbox (dialog) | WordEditDialog | `dialog-expand-refine-button` | Word (bbox) | `WordRefineNudgeRows.tsx:169-175` → `onExpandRefine()` | Expands the bbox by 4 px then refines. |
| 70 | Refine bboxes — toolbar grid (word/line/para/page scope) | Toolbar action grid | `toolbar-{scope}-refine` | Word / Line / Para / Page | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches the appropriate refine route for the selected scope. |
| 71 | Expand+Refine bboxes — toolbar grid | Toolbar action grid | `toolbar-{scope}-expand-refine` | Word / Line / Para / Page | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches the expand+refine route for the selected scope. |
| 72 | Expand bboxes — toolbar grid | Toolbar action grid | `toolbar-{scope}-expand` | Word / Line / Para / Page | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` | Dispatches the expand-only route for the selected scope. |
| 73 | Crop word — above/below/left/right (dialog) | WordEditDialog | `dialog-crop-above/below/left/right-button` | Word (bbox) | `WordActionRows.tsx:183-210` → `onCrop(direction, padding)` wired in ProjectPage | Fires a crop POST with direction + padding; `dialog-crop-padding-input` slider (0–20 px) controls padding. |
| 74 | Erase pixels — draw op (brush/lasso/rect) on EraseCanvas | Right panel — WordDetail > Erase Pixels accordion | Drag on `erase-canvas` with `erase-tool-brush/lasso/rect`; `erase-brush-size` slider | Word (pixel data) | `ErasePixelsSection.tsx:67-69` `setOps(prev => [...prev, op])` via `EraseCanvas.onOpCommit` | Draws an erase operation (brush stroke, lasso polygon, or rect) on the Konva canvas; op is staged in local list. |
| 75 | Remove a staged erase op | Right panel — WordDetail > Erase Pixels accordion | `erase-op-{N}-remove` | Word (pixel data) | `ErasePixelsSection.tsx:73-76` `setOps(prev.filter(_, i => i !== N))` | Removes one staged erase operation from the list without committing. |
| 76 | Clear all staged erase ops | Right panel — WordDetail > Erase Pixels accordion | `erase-clear` | Word (pixel data) | `ErasePixelsSection.tsx:77-79` `setOps([])` | Clears all staged erase ops (local; no server call). |
| 77 | Apply erase pixels (commit batch to backend) | Right panel — WordDetail > Erase Pixels accordion | `erase-apply` | Word (pixel data) | `ErasePixelsSection.tsx:80-91` → `onApply(ops)` wired to `useErasePixels.mutateAsync` in `WordDetail.tsx:227` | Iterates staged ops, POSTs each as `{bbox, fill_value:255, shape}` to `/words/{li}/{wi}/erase-pixels`, then clears the local list. |
| 78 | Adjust inter-word gap (StructureSection gap-picker slider) | Right panel — WordDetail > Structure accordion | `structure-gap-slider` drag (mouseUp / blur) | Word (bbox of next word) | `StructureSection.tsx:212-227` `adjustGap.mutate({lineIndex, nextWordIndex, nextWordBbox, deltaX})` | On slider release, clamps the delta and rebboxes the next word to widen/narrow the gap. |
| 79 | Apply style label to word (WordDetail StylePalette) | Right panel — WordDetail > Style chips row | `style-chip-{key}` tri-state Chip click | Word (style) | `WordDetail.tsx:163-173` `applyStyle.mutate({style: styleKey, scope:"whole"})` | Toggles a text-style chip (off → on → off); POSTs to `/words/{li}/{wi}/style`. |
| 80 | Apply style label to word (ToolbarActionGrid Apply Style row) | Toolbar action grid below grid | `apply-style-button` | Word / selection | `ToolbarActionGrid.tsx:311-318` → `onApplyStyle(style, scope)` wired in ProjectPage | Reads the `apply-style-select` + `scope-select` selections; fires `applyStyle.mutate` for each selected word. |
| 81 | Clear style label from word (ToolbarActionGrid) | Toolbar action grid | `clear-style-button` | Word / selection | `ToolbarActionGrid.tsx:320-327` → `onClearStyle(style, scope)` wired in ProjectPage | Clears (removes) the selected style from each selected word via `applyStyle` with the "regular" sentinel. |
| 82 | Apply style label to word (WordEditDialog WordTagRow) | WordEditDialog | `dialog-apply-style-button` | Word | `WordTagRow.tsx:100-107` → `onApplyStyle(style, scope)` | Posts selected style + scope to the word style endpoint. |
| 83 | Apply style label to word (CharRangesSection tri-state chip) | Right panel — WordDetail > Char Ranges accordion | `char-ranges-chip-{style}` tristate click | Word (per char-range) | `CharRangesSection.tsx:304-311` `handlePendingChipChange` → staged in pending range | Changes the pending-range style selections locally; persisted only when "Add range" is clicked. |
| 84 | Apply style to char range (CharRangesSection rich card chip palette) | Right panel — WordDetail > Char Ranges accordion | `char-range-{N}-style-chip-*` click | Word (per char-range) | `CharRangesSection.tsx:358-368` → `persistRanges()` `useSetCharRanges.mutate` | Immediately POSTs the full updated char-range list to `/words/{li}/{wi}/char-ranges`. |
| 85 | Set component on char range (CharRangesSection rich card component palette) | Right panel — WordDetail > Char Ranges accordion | `char-range-{N}-component-chip-*` click | Word (per char-range) | `CharRangesSection.tsx:370-381` → `persistRanges()` `useSetCharRanges.mutate` | Immediately POSTs the full updated char-range list to `/words/{li}/{wi}/char-ranges`. |
| 86 | Add char range with pending styles (CharRangesSection) | Right panel — WordDetail > Char Ranges accordion | `char-ranges-add-button` | Word (char ranges) | `CharRangesSection.tsx:308-325` → `persistRanges()` `useSetCharRanges.mutate` | Commits the pending selection (anchor..end) + styles as a new CharRange row, then POSTs the full range list. |
| 87 | Add blank char range (CharRangesSection bottom button) | Right panel — WordDetail > Char Ranges accordion | `char-range-add` | Word (char ranges) | `CharRangesSection.tsx:382-395` → `persistRanges()` | Appends a blank range spanning all chars and immediately POSTs the updated range list. |
| 88 | Delete char range (CharRangesSection) | Right panel — WordDetail > Char Ranges accordion | `char-range-{N}-delete` or `char-ranges-delete-{N}` (compat alias) | Word (char ranges) | `CharRangesSection.tsx:329-333` → `persistRanges()` | Removes the range card and POSTs the pruned range list. |
| 89 | Edit char-range start/end positions (CharRangesSection numeric inputs) | Right panel — WordDetail > Char Ranges accordion | `char-range-{N}-start` / `char-range-{N}-end` change | Word (char ranges) | `CharRangesSection.tsx:346-356` → `persistRanges()` | Clamps start ≤ end, updates local state, and immediately POSTs the full range list. |
| 90 | Switch char-range kind Style ↔ Component (CharRangesSection) | Right panel — WordDetail > Char Ranges accordion | `char-range-{N}-kind-style` / `char-range-{N}-kind-component` | Word (char ranges) | `CharRangesSection.tsx:340-344` → `persistRanges()` | Toggles the kind switcher and immediately POSTs the full range list. |
| 91 | Select char anchor (CharRangesSection char-cell click) | Right panel — WordDetail > Char Ranges accordion | `char-cell-{i}` click | Word (char selection) | `CharRangesSection.tsx:287-302` `setAnchor(i)` / `setEndPos(i)` | First click sets anchor, second click sets end; no server call (pending state only). |
| 92 | Apply per-char bbox changes (CharFixerSection Apply button) | Right panel — WordDetail > Char Fixer accordion | `charfixer-apply` | Word (per-char bboxes) | `CharFixerSection.tsx:276-297` `charBboxesMutation.mutate({charBboxes})` | POSTs the current per-char bbox array to `/words/{li}/{wi}/char-bboxes`; clears dirty flag on success. |
| 93 | Edit per-char bbox coordinates (CharFixerSection detail strip inputs) | Right panel — WordDetail > Char Fixer accordion | `charfixer-detail-x1/y1/x2/y2` number input change | Word (per-char bboxes) | `CharFixerSection.tsx:246-273` `handleCoordChange` `setDirty(true)` | Updates the selected range's bbox coordinates in local state; does NOT auto-submit (Apply required). |
| 94 | Select per-char bbox range (CharFixerCanvas click) | Right panel — WordDetail > Char Fixer accordion | Click a coloured range rect on `charfixer-canvas` | Word (char selection) | `CharFixerSection.tsx:231-233` `handleSelect(index)` | Selects the clicked char-range rectangle; shows its coords in the detail strip. |
| 95 | Drag per-char bbox handle (CharFixerCanvas handles) | Right panel — WordDetail > Char Fixer accordion | Drag `charfixer-range-{N}-handle-{pos}` (8 handles on selected range) | Word (per-char bbox) | `CharFixerSection.tsx:235-243` `handleBboxChange(index, next)` `setDirty(true)` | Updates the dragged char-range bbox in local state; does NOT auto-submit. |
| 96 | Apply component tag to word (WordDetail ComponentPalette) | Right panel — WordDetail > Component chips row | `component-chip-{key}` tristate Chip click | Word (component) | `WordDetail.tsx:174-185` `applyComponent.mutate({component: key, enabled: next==="on"})` | POSTs `{component, enabled}` to `/words/{li}/{wi}/component`. |
| 97 | Apply component tag to word (ToolbarActionGrid) | Toolbar action grid Apply Style row | `apply-component-button` | Word / selection | `ToolbarActionGrid.tsx:330-337` → `onApplyComponent(component)` wired in ProjectPage | POSTs the selected component label with `enabled:true` for each selected word. |
| 98 | Clear component tag from word (ToolbarActionGrid) | Toolbar action grid Apply Style row | `clear-component-button` | Word / selection | `ToolbarActionGrid.tsx:339-346` → `onClearComponent(component)` wired in ProjectPage | POSTs `enabled:false` for the selected component label. |
| 99 | Apply component tag to word (WordEditDialog WordTagRow) | WordEditDialog | `dialog-apply-component-button` | Word | `WordTagRow.tsx:127-133` → `onApplyComponent(component, true)` | POSTs `{component, enabled:true}` to the component endpoint. |
| 100 | Clear component tag from word (WordEditDialog WordTagRow) | WordEditDialog | `dialog-clear-component-button` | Word | `WordTagRow.tsx:134-140` → `onApplyComponent(component, false)` | POSTs `{component, enabled:false}` to the component endpoint. |
| 101 | Apply style to bulk-selected words (BulkWordActions) | Bulk actions panel | `bulk-word-style-select` + `bulk-word-style-apply` | Word (multi-select) | `BulkWordActions.tsx:141-151` iterates `applyStyle.mutate` for each selected word | Fires one `applyStyle` mutation per selected word with `scope:"whole"`. |
| 102 | Apply component to bulk-selected words (BulkWordActions) | Bulk actions panel | `bulk-word-component-select` + `bulk-word-component-apply` | Word (multi-select) | `BulkWordActions.tsx:176-186` iterates `applyComponent.mutate` | Fires one `applyComponent` mutation per selected word with `enabled:true`. |
| 103 | Remove style chip from word (WordCell) | Matches pane — WordCell | `word-tag-clear-button-{l}-{w}-{label}` (× on chip) | Word (style or component) | `WordCell.tsx:211-217` (button present but no `onClick` mutation — wire is a stub) | Renders an × button on each style/component chip; mutation wiring from a parent is expected (currently unconnected). |
| 104 | Set paragraph layout type (BlockDetail) | Right panel — BlockDetail > Layout tab | `block-detail-layout-chip-{id}` card click + `block-detail-layout-save` | Paragraph / Block | `BlockDetail.tsx:683-705` `patchParagraph.mutate({paragraphIndex, layoutType})` | Selects a layout-type glyph card; clicking "Save layout type" PATCHes the paragraph with `layout_type` via `/paragraphs/{pi}`. |
| 105 | Accept model-suggested layout type (BlockDetail) | Right panel — BlockDetail > Layout tab | `block-detail-layout-accept` | Paragraph / Block | `BlockDetail.tsx:707-727` `patchParagraph.mutate` | One-click accepts the model suggestion and immediately PATCHes the paragraph layout type (backend suggestion not yet wired). |
| 106 | Select paragraph scope in Para Layout tab (BlockDetail) | Right panel — BlockDetail > Para layout tab | `block-detail-para-scope-{pi}` button | Block / Para navigation | `BlockDetail.tsx:909-916` `selectPara(pId)` | Dispatches `selectPara` to the selection-store, switching the right panel to that paragraph; no server call. |
| 107 | Add word from drawn bbox | Page canvas | `word-add-button` toggle → drag on canvas to draw bbox | Page | `ProjectPage.tsx:686` `addWord.mutate({bbox: srcBbox})` | Toggle enters add-word mode; the user draws a bbox on the Konva canvas; on mouseUp POSTs `{bbox, line_index:null, text:""}` to `/words/add`. |
| 108 | Word → Line grouping (toolbar grid, word scope) | Toolbar action grid | `toolbar-word-w-to-l` | Word | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` via `word-word-to-line` mapping | Moves the selected word into its nearest matching line via the backend route. |
| 109 | Line → Paragraph grouping (toolbar grid, line scope) | Toolbar action grid | `toolbar-line-to-para` | Line | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` via `line-word-to-para` mapping | Moves the selected line into a paragraph. |
| 110 | Word → Paragraph (toolbar grid, word scope) | Toolbar action grid | `toolbar-word-to-para` | Word | `ToolbarActionGrid.tsx:237` → `useToolbarDispatch` via `word-word-to-para` mapping | Moves the selected word directly into a paragraph. |
| 111 | Set glyph annotation — add ligature mark (GlyphAnnotationPanel) | Glyph panel (popover from word badge / WordEditDialog) | `glyph-panel-add-ligature` button (after selecting kind + optional char span) | Word (glyph / typography) | `GlyphAnnotationPanel.tsx:77-90` `onSetAnnotations({...base, ligatures:[...base.ligatures, newMark]})` | Appends a ligature mark of the chosen kind (ct, st, fi, etc.) + optional char span to the annotations; caller is responsible for persisting. |
| 112 | Remove ligature mark (GlyphAnnotationPanel) | Glyph panel | × button on each rendered ligature row | Word (glyph) | `GlyphAnnotationPanel.tsx:92-96` `handleRemoveLigature(idx)` | Filters the ligature from the array and calls `onSetAnnotations`. |
| 113 | Set ligature kind (GlyphAnnotationPanel) | Glyph panel | `glyph-panel-ligature-kind-select` dropdown | Word (glyph) | `GlyphAnnotationPanel.tsx:155-159` `setNewKind(value)` | Updates the pending new-ligature kind (local state only; no server call until Add is clicked). |
| 114 | Select ligature char span (GlyphAnnotationPanel) | Glyph panel | `glyph-panel-charspan-cell-{i}` click (+ Shift-click to extend) | Word (glyph) | `GlyphAnnotationPanel.tsx:112-125` `handleCharSpanClick` `setSelectedSpan` | Sets the char-span anchor or extends it; local state only. |
| 115 | Toggle long-s position (GlyphAnnotationPanel) | Glyph panel | `glyph-panel-long-s-cell-{i}` click | Word (glyph) | `GlyphAnnotationPanel.tsx:98-110` `handleToggleLongS(charIdx)` `onSetAnnotations` | Toggles a character position in `long_s_positions`; calls `onSetAnnotations` (caller persists). |
| 116 | Toggle swash (GlyphAnnotationPanel) | Glyph panel | `glyph-panel-swash-checkbox` | Word (glyph) | `GlyphAnnotationPanel.tsx:67-75` `handleSwashChange(checked)` `onSetAnnotations` | Sets `swash: checked` on the annotations; calls `onSetAnnotations`. |
| 117 | Mark word reviewed — no marks (GlyphAnnotationPanel) | Glyph panel | `glyph-panel-mark-reviewed-empty` | Word (glyph) | `GlyphAnnotationPanel.tsx:54-62` `onSetAnnotations({ligatures:[], long_s_positions:[], swash:false, source:"human"})` | Sets the annotations to an empty human-reviewed record (visible badge turns blue). |
| 118 | Reset glyph annotations to null (GlyphAnnotationPanel) | Glyph panel | `glyph-panel-reset` | Word (glyph) | `GlyphAnnotationPanel.tsx:63-65` `onSetAnnotations(null)` | Clears all annotations (badge turns amber or disappears). |
| 119 | Accept predicted ligature (GlyphAnnotationPanel) | Glyph panel | `glyph-panel-accept-prediction-{kind}` | Word (glyph) | `GlyphAnnotationPanel.tsx:219-224` `onAcceptPrediction?.()` | Accepts a model prediction by calling the parent-supplied callback. |
| 120 | Reject predicted ligature (GlyphAnnotationPanel) | Glyph panel | `glyph-panel-reject-prediction-{kind}` | Word (glyph) | `GlyphAnnotationPanel.tsx:225-236` `onSetAnnotations(annotations ?? {...})` | Sets annotations to a human-reviewed (but otherwise unchanged) record, overriding the prediction. |
| 121 | Bulk-mark glyphs — choose recipe (BulkGlyphMarkDialog) | Bulk glyph dialog (toolbar entry `bulk-glyph-mark-button`) | `bulk-glyph-recipe-select` | Page (all matching words) | `BulkGlyphMarkDialog.tsx:124-130` `setRecipe(value)` | Selects the auto-mark recipe (ct_substring / st_substring / long_s_typeset_era); local state only. |
| 122 | Bulk-mark glyphs — toggle skip-annotated (BulkGlyphMarkDialog) | Bulk glyph dialog | `bulk-glyph-skip-annotated-checkbox` | Page | `BulkGlyphMarkDialog.tsx:143-148` `setSkipAnnotated` | Toggles whether already-annotated words are skipped; local state only. |
| 123 | Bulk-mark glyphs — toggle accept-predictions (BulkGlyphMarkDialog) | Bulk glyph dialog | `bulk-glyph-accept-predictions-checkbox` | Page | `BulkGlyphMarkDialog.tsx:152-157` `setAcceptPredictions` | Toggles whether matching predictions are confirmed during the bulk mark; local state only. |
| 124 | Bulk-mark glyphs — dry run preview (BulkGlyphMarkDialog) | Bulk glyph dialog | `bulk-glyph-dry-run-button` | Page | `BulkGlyphMarkDialog.tsx:73-82` `callBulkMark(true)` | POSTs to `/glyph-bulk-mark` with `dry_run:true`; displays the count in `bulk-glyph-preview-count`. |
| 125 | Bulk-mark glyphs — apply (BulkGlyphMarkDialog) | Bulk glyph dialog | `bulk-glyph-apply-button` | Page | `BulkGlyphMarkDialog.tsx:86-96` `callBulkMark(false)` | POSTs to `/glyph-bulk-mark` with `dry_run:false` to apply the recipe to all matching words; closes dialog on success. |
| 126 | Filter word-match view — toggle Unvalidated / Mismatched / All | Matches pane | `match-filter-toggle` / `match-filter-unvalidated/mismatched/all` | Page (display filter) | `FilterToggle.tsx` → `useUiPrefs.matchFilter` state update, consumed by `WordMatchView` | Changes the visible filter for the word-match list; no server call. |
| 127 | Navigate to next/previous word within dialog | WordEditDialog | `dialog-prev-button` / `dialog-next-button` (also ← / → keys via dialog hotkeys) | Word (navigation) | `WordEditDialog.tsx:165-170` `onNavigate({lineIndex, wordIndex: wordIndex±1})` | Moves the dialog to the adjacent word within the same line; no server call (view state only). |
| 128 | Open word edit dialog from Matches pane | Matches pane — WordCell | `edit-word-button-{l}-{w}` | Word (context) | `WordCell.tsx:178-185` → `onEditWord(l, w)` wired in ProjectPage to open WordEditDialog | Selects the word in the selection-store and opens the word-edit dialog. |
| 129 | Toggle word selection checkbox (WordCell) | Matches pane — WordCell | `word-checkbox-{l}-{w}` | Word (selection) | `WordCell.tsx:151-155` (checkbox present; selection-store wiring expected from ProjectPage) | Marks the word in the selection store for subsequent bulk operations. |
| 130 | Toggle line selection checkbox (LineCard) | Matches pane — LineCard | `line-checkbox-{n}` | Line (selection) | `LineCard.tsx:196-200` (checkbox present; stub — no onChange handler in LineCard itself) | Checkbox is rendered; wiring to the selection store is expected from a parent. |
| 131 | Toggle paragraph selection checkbox (LineCard) | Matches pane — LineCard (paragraph-first lines) | `paragraph-checkbox-{p}` | Paragraph (selection) | `LineCard.tsx:188-194` (checkbox present; stub) | Checkbox is rendered on the first line of each paragraph; wiring is expected from a parent. |
| 132 | Toggle word check in LineDetail Words tab | Right panel — LineDetail > Words tab | `LineWordsCard` checkbox (`checked` / `onCheckedChange` props) | Word (bulk selection within line) | `LineDetail.tsx:484-487` `onToggleCheck(wm.word_index, checked)` | Adds/removes the word index from the `checkedWords` Set, enabling the bulk bar. |
| 133 | Toggle word display density (LineDetail) | Right panel — LineDetail > Words tab | `line-detail-density-toggle` | Line (view preference) | `LineDetail.tsx:232-237` `toggleDensity()` | Switches the Words tab between card and row view; persists to `useUiPrefs`. |
| 134 | Pending-range style chip toggle (CharRangesSection) | Right panel — WordDetail > Char Ranges accordion | `char-ranges-chip-{style}` tristate Chip | Word (per-char pending selection) | `CharRangesSection.tsx:441-448` `handlePendingChipChange(key, next)` | Cycles the pending chip value off → on → mixed; local state only until "Add range". |
| 135 | View OCR text (read-only) in Text tabs | Right panel / Text tabs — OCR tab | `text-tab-ocr` → `plaintext-editor-ocr` | Page (read-only) | `PlaintextEditor.tsx:29` (read-only textarea) | Displays the assembled `page_text_ocr` string in a read-only monospace textarea; no mutations. |
| 136 | View GT text (read-only) in Text tabs | Right panel / Text tabs — GT tab | `text-tab-ground-truth` → `plaintext-editor-gt` | Page (read-only) | `PlaintextEditor.tsx:29` (read-only textarea) | Displays `page_text_gt` read-only; no mutations. |

---

## User paths

1. **Per-word GT correction (inline, matches pane)**
   - Open the Matches tab (right side).
   - Optionally filter with `match-filter-unvalidated`.
   - Locate a mismatched word; click `gt-text-input-{l}-{w}` and type the correction.
   - Tab or click away → blur-commit fires `useUpdateWordGt` → page invalidates.
   - Click `word-validate-button-{l}-{w}` or `line-validate-button-{n}` to mark clean.

2. **Per-word deep edit via WordDetail right panel**
   - Click `edit-word-button-{l}-{w}` in the Matches pane → opens WordDetail in the right panel.
   - View OCR vs GT in `ocr-gt-compare` row; optionally use `ocr-gt-copy-btn` (OCR→GT) or Ω picker.
   - Edit GT in `ocr-gt-input` → blur-commit.
   - Open Style / Component chip palettes to tag the word.
   - Open Char Ranges accordion → select char span → configure style/component → "Add range".
   - Open Rebox or Bounding Box accordion to adjust the bbox with snap-handles or numeric nudge.
   - Optionally open Erase Pixels; draw strokes; click "Apply erases".
   - Open Char Fixer to edit per-character GT + per-char bboxes; click Apply.
   - Click `word-footer-validate` (V key) to validate; Tab / Skip to advance.

3. **Line-level GT reconciliation**
   - Click a line in the Matches pane or select line mode in the Rail.
   - Right panel shows LineDetail.
   - Set the full-line GT in `line-detail-gt-input` (blur-commits to `/lines/{li}/set-gt`).
   - Use `line-copy-ocr-to-gt` or `line-copy-gt-to-ocr` for bulk copy.
   - Merge with adjacent line via `line-detail-merge-prev/next`.
   - Validate all words with `line-detail-validate-all`.
   - Switch to Words tab; check individual words; use bulk bar to validate/skip selected words.

4. **Word merge / split workflow (WordDetail Structure section)**
   - Select a word → WordDetail → open Structure accordion.
   - Hover `structure-merge-prev/next` to see merge preview text.
   - Click → confirm dialog → merge POSTs to `/words/{li}/{wi}/merge`.
   - For split: click characters in the SplitPicker to choose a split point → click `structure-split-button` → POSTs x-fraction to `/split`.

5. **Bbox refine workflow (WordDetail Rebox section)**
   - Select a word → WordDetail → open Rebox accordion.
   - Choose snap / draw / pan mode.
   - Drag handles or draw a new rect on the Konva mini-canvas.
   - Zoom in/out with `rebox-zoom-in/out`.
   - Click `rebox-apply` → POSTs final bbox to `/rebox`.
   - Or use `rebox-reset` to discard.

6. **Erase pixels workflow**
   - Select a word → WordDetail → open Erase Pixels accordion.
   - Select brush / lasso / rect tool; adjust brush size.
   - Draw strokes on the Konva canvas; each completed stroke is staged in the ops list.
   - Remove individual ops with `erase-op-{N}-remove` or `erase-clear` all.
   - Click `erase-apply` → fires one POST per op to `/words/{li}/{wi}/erase-pixels`.

7. **Per-char GT fix (CharFixerSection)**
   - Select a word → WordDetail → open Char Fixer accordion.
   - Edit individual per-char cells (`char-fixer-input-{i}`); debounce saves after 500 ms idle.
   - Use `char-fixer-open-picker-button` to open UnicodePicker; click a glyph to insert at the focused cell.
   - Click a char-range rect on the CharFixerCanvas to select it; drag its 8 handles or edit x1/y1/x2/y2 in the detail strip.
   - Click `charfixer-apply` → POSTs per-char bboxes to `/words/{li}/{wi}/char-bboxes`.

8. **Char-range style/component annotation workflow**
   - Select a word → WordDetail → open Char Ranges accordion.
   - Click first char cell (`char-cell-{i}`) to set anchor; click second to set end.
   - Toggle style chips in the pending panel; click "Add range" → POSTs to `/char-ranges`.
   - For existing ranges: open rich card; use kind switcher to toggle Style / Component; click chips → each click immediately POSTs the full range list.
   - Edit start/end numeric inputs if needed (each change immediately POSTs).
   - Delete a range with `char-range-{N}-delete`.

9. **Toolbar grid scope-batch operations**
   - Select one or more words / lines / paragraphs via the canvas (Rail target mode + drag-select) or by checking checkboxes.
   - Open the Toolbar grid above the Matches pane.
   - Click the appropriate `toolbar-{scope}-{action}` cell (validate, delete, merge, split-after, copy-gt, refine, etc.).
   - `useToolbarDispatch` resolves the scope + selection indices into the correct API call and fires.

10. **Paragraph structure editing**
    - Select a paragraph in block/para mode via the Rail.
    - Right panel shows ParagraphDetail.
    - Merge with next: `para-merge`; Split after first line: `para-split-after-line`; Delete: `para-delete`.
    - Bulk copy GT: `para-copy-gt-to-ocr` or `para-copy-ocr-to-gt`.
    - Validate all words: `para-validate` / `para-unvalidate`.

11. **Block layout type assignment**
    - Select block mode in the Rail.
    - Right panel shows BlockDetail > Layout tab.
    - Click a layout-type glyph card (`block-detail-layout-chip-{id}`).
    - Preview renders in the Preview pane.
    - Click `block-detail-layout-save` → PATCHes all paragraphs in the block.
    - For per-paragraph layout: use Para Layout tab; click `block-detail-para-scope-{pi}` → selects that paragraph.

12. **Glyph annotation (per-word, GlyphAnnotationPanel)**
    - Open GlyphAnnotationPanel via the word glyph badge or WordEditDialog typography section.
    - Select ligature kind from `glyph-panel-ligature-kind-select`.
    - Optionally select char span with `glyph-panel-charspan-cell-{i}` (shift-click to extend).
    - Click `glyph-panel-add-ligature` → ligature mark appended.
    - Toggle `glyph-panel-long-s-cell-{i}` for long-s positions.
    - Check `glyph-panel-swash-checkbox`.
    - Or click `glyph-panel-mark-reviewed-empty` to mark with no marks.
    - `glyph-panel-reset` clears all annotations.
    - Accept/reject individual predicted marks with `glyph-panel-accept-prediction-{kind}` / `reject-prediction-{kind}`.

13. **Bulk glyph-mark recipe workflow**
    - Click `bulk-glyph-mark-button` in the toolbar.
    - Select recipe in `bulk-glyph-recipe-select`.
    - Toggle `bulk-glyph-skip-annotated-checkbox` and/or `bulk-glyph-accept-predictions-checkbox`.
    - Click `bulk-glyph-dry-run-button` → preview count shown in `bulk-glyph-preview-count`.
    - Click `bulk-glyph-apply-button` → POSTs with `dry_run:false`.

14. **Add word from canvas bbox**
    - Click `word-add-button` (or Shift+A hotkey) to enter add-word mode.
    - Draw a bbox on the Konva canvas.
    - On mouseUp: `useAddWord.mutate({bbox, line_index:null, text:""})` → POST to `/words/add`.
    - Edit the new word's GT inline in the Matches pane.

15. **Bulk word style/component/delete operations**
    - Click `rail-bulk-button` to open the BulkWordActions panel.
    - Click `page-validate-all` / `page-unvalidate-all` for page-scope validation.
    - Check words via `word-checkbox-{l}-{w}` in the Matches pane (selection store).
    - When words selected: choose style from `bulk-word-style-select` → `bulk-word-style-apply`.
    - Or choose component from `bulk-word-component-select` → `bulk-word-component-apply`.
    - Or click `bulk-word-delete` → `deleteWords.mutate({wordIndices})`.

---

## Cross-dimension spillover

The following actions sit on the boundary between dimension B and adjacent dimensions (A: navigation/chrome; C: whole-document/page/system ops):

- **Reload OCR / Reload OCR (Edited)** (`useReloadOcr` / `useReloadOcrEdited`, `PageActions.tsx`) — triggers a full page re-OCR job; this is a page-level operation with OCR content consequences. Classified as dimension C (page/system op) but directly produces new OCR content.
- **Save Page / Save Project** (`useSavePage` / `useSaveProject`) — flushes in-memory OCR edits to disk. Dimension C, but completes the content-editing lifecycle.
- **Load Page** (`useLoadPage`) — discards in-memory OCR edits by reloading from disk. Dimension C; destroys content mutations.
- **Rematch GT** (`useRematchGt`) — re-aligns the ground-truth file to the OCR. Dimension C; affects all match statuses displayed in the word list.
- **Match filter toggle** (`match-filter-unvalidated/mismatched/all`) — changes which lines are visible in the Matches pane. Dimension A (chrome/navigation), but directly affects which content is surfaced for editing.
- **Mismatches-only canvas toggle** (`mismatches-only-toggle`) — dims validated/exact bbox overlays on the canvas. Dimension A, but affects OCR content visibility.
- **Selection-mode radios** (`selection-mode-paragraph/line/word`) — governs what rail clicks select. Dimension A, but a prerequisite for all content mutations that depend on the selection scope.
- **Layer visibility checkboxes** (`layer-paragraphs/lines/words-checkbox`) — toggles Konva overlay layers. Dimension A.
- **Canvas drag-select** (drag rect on `image-viewport`) — creates a bounding-box selection of paragraphs / lines / words; selection only, no mutation. Dimension A/B boundary.
- **Export** (`export-dialog`, `export-button`) — reads the GT content and writes output files. Dimension C.

---

## Coverage self-check

### Source files read (frontend/src)

| File | Status |
|---|---|
| `components/WordEditDialog.tsx` | Read |
| `components/WordMatchView.tsx` | Read |
| `components/LineCard.tsx` | Read |
| `components/WordCell.tsx` | Read |
| `components/WordActionRows.tsx` | Read |
| `components/WordRefineNudgeRows.tsx` | Read |
| `components/WordTagRow.tsx` | Read |
| `components/BulkWordActions.tsx` | Read |
| `components/ToolbarActionGrid.tsx` | Read |
| `components/PlaintextEditor.tsx` | Read |
| `components/BBoxOverlay.tsx` | Read (rendering only; no mutations) |
| `components/right-panel/WordDetail.tsx` | Read |
| `components/right-panel/LineDetail.tsx` | Read |
| `components/right-panel/BlockDetail.tsx` | Read |
| `components/right-panel/ParagraphDetail.tsx` | Read |
| `components/right-panel/OcrGtCompareRow.tsx` | Read |
| `components/right-panel/WordFooter.tsx` | Read |
| `components/right-panel/WordHeader.tsx` | Not read — display-only (pager nav) |
| `components/right-panel/WordImagePreview.tsx` | Not read — display-only |
| `components/right-panel/StylePalette.tsx` | Read (first 60 lines + key exports) |
| `components/right-panel/ComponentPalette.tsx` | Not individually read — mirrors StylePalette; referenced from CharRangesSection |
| `components/right-panel/UnicodePicker.tsx` | Not read — purely presentational glyph picker |
| `components/right-panel/LineWordsCard.tsx` | Not read — card view of word in LineDetail Words tab; no direct mutations |
| `components/right-panel/sections/BBoxSection.tsx` | Read |
| `components/right-panel/sections/ReboxSection.tsx` | Read |
| `components/right-panel/sections/ErasePixelsSection.tsx` | Read |
| `components/right-panel/sections/CharRangesSection.tsx` | Read |
| `components/right-panel/sections/CharFixerSection.tsx` | Read |
| `components/right-panel/sections/StructureSection.tsx` | Read |
| `components/right-panel/sections/ReboxCanvas.tsx` | Not read — Konva canvas primitives; mutations flow through ReboxSection |
| `components/right-panel/sections/EraseCanvas.tsx` | Not read — Konva canvas primitives; mutations flow through ErasePixelsSection |
| `components/right-panel/sections/CharFixerCanvas.tsx` | Not read — Konva canvas primitives; mutations flow through CharFixerSection |
| `components/right-panel/sections/bboxUtils.ts` | Not read — utility (hint string only) |
| `components/glyph/GlyphAnnotationPanel.tsx` | Read |
| `components/glyph/BulkGlyphMarkDialog.tsx` | Read |
| `components/glyph/GlyphChip.tsx` | Not read — display-only chip |
| `hooks/useWordMutations.ts` | Read |
| `hooks/useLineMutations.ts` | Read |
| `hooks/usePageMutations.ts` | Read |
| `hooks/useToolbarDispatch.ts` | Read |
| `hooks/useLabelVocabulary.ts` | Not read — vocabulary fetcher; no mutations |
| `pages/ProjectPage.tsx` | Grepped for wiring; not read in full |
| `docs/architecture/13-driver-contract.md` | Read |

### Known gaps

1. **`word-tag-clear-button-{l}-{w}-{label}` mutation** — the × button on style/component chips in `WordCell` is rendered but has no `onClick` mutation wired in `WordCell.tsx` itself (line 210-216, 228-238). The mutation is expected to be injected via a prop from `ProjectPage`; that wiring was not visible in the grepped output. **Listed as row 103 with a stub note.**

2. **`word-checkbox-{l}-{w}` selection-store wiring** — checkbox is rendered in `WordCell` but `onChange` wiring to `selectionStore` was not found in `WordCell.tsx`; expected in `ProjectPage`. Listed as row 129 with a stub note.

3. **`line-checkbox-{n}` / `paragraph-checkbox-{p}` selection-store wiring** — both checkboxes are rendered in `LineCard` without an `onChange` handler. Listed as rows 130–131 with stub notes.

4. **`ComponentPalette.tsx` chips** — inferred from `WordDetail.tsx` and `CharRangesSection.tsx` usage; not individually audited (mirrors `StylePalette.tsx`).

5. **`useToolbarDispatch` / `toolbarMapping.ts`** — the toolbar mapping file was not individually read. The full set of routes dispatched by the toolbar is inferred from `useToolbarDispatch.ts` and `ToolbarActionGrid.tsx` scope maps.

6. **Glyph annotation persistence** — `GlyphAnnotationPanel.tsx` calls `onSetAnnotations`; the parent (not read in full) is expected to POST the annotation to the backend. The persistence endpoint is not confirmed from the files read.

7. **`LineWordsCard.tsx` and `WordHeader.tsx`** — not read individually; assumed display-only based on names and usage context.

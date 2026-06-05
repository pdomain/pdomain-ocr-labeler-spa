# Legacy pd-ocr-labeler — Dimension B: OCR Content Actions

## Action inventory

| # | Action name (verb phrase incl. scope) | Screen/context | Trigger | Scope | Handler file:line | One-sentence behavior |
|---|---------------------------------------|----------------|---------|-------|-------------------|-----------------------|
| 1 | Edit ground truth text (inline) | Word comparison table, every OCR-backed word column | Text input `gt-text-input` — blur or Enter key | Word | `word_match_gt_editing.py:60–75` | User types directly into the per-word GT input; committing (blur/Enter) persists the change via `edit_word_ground_truth_callback` and refreshes the line card. |
| 2 | Edit ground truth text (dialog) | Word edit dialog, Current column | Text input `dialog-gt-input` — blur or Enter key | Word | `word_edit_dialog.py:1403–1438` | Same GT edit but opened from the per-word edit dialog; commit path is identical. |
| 3 | Tab-navigate between GT inputs | Word comparison table | Tab / Shift+Tab inside `gt-text-input` | Word | `word_match_gt_editing.py:145–173` | Commits current GT edit then moves focus to the adjacent (next/previous) word GT input in reading order. |
| 4 | Copy GT → OCR (page scope) | Toolbar — Page row | Button `page-copy-gt-to-ocr-button` (icon: content_copy, mirrored) | Page | `word_match_actions.py:136–143` | Copies every ground-truth word text to its matched OCR field for all lines on the page. |
| 5 | Copy OCR → GT (page scope) | Toolbar — Page row | Button `page-copy-ocr-to-gt-button` (icon: content_copy) | Page | `word_match_actions.py:145–152` | Copies every OCR word text to its matched GT field for all lines on the page. |
| 6 | Copy GT → OCR (paragraph scope) | Toolbar — Paragraph row | Button `paragraph-copy-gt-to-ocr-button` (icon: content_copy, mirrored) | Paragraph | `word_match_actions.py:158–165` | Copies GT → OCR text for all words in the selected paragraphs. |
| 7 | Copy OCR → GT (paragraph scope) | Toolbar — Paragraph row | Button `paragraph-copy-ocr-to-gt-button` (icon: content_copy) | Paragraph | `word_match_actions.py:167–174` | Copies OCR → GT text for all words in the selected paragraphs. |
| 8 | Copy GT → OCR (line scope, toolbar) | Toolbar — Line row | Button `line-copy-gt-to-ocr-toolbar-button` (icon: content_copy, mirrored) | Line | `word_match_actions.py:180–187` | Copies GT → OCR text for all words in the selected lines via the bulk toolbar. |
| 9 | Copy OCR → GT (line scope, toolbar) | Toolbar — Line row | Button `line-copy-ocr-to-gt-toolbar-button` (icon: content_copy) | Line | `word_match_actions.py:189–196` | Copies OCR → GT text for all words in the selected lines via the bulk toolbar. |
| 10 | Copy GT → OCR (line scope, inline) | Per-line header (non-exact lines only) | Button `line-gt-to-ocr-button` ("GT→OCR") | Line | `word_match_renderer.py:473–485` | Copies GT → OCR text for all words in that specific line via the inline header button. |
| 11 | Copy OCR → GT (line scope, inline) | Per-line header (non-exact lines only) | Button `line-ocr-to-gt-button` ("OCR→GT") | Line | `word_match_renderer.py:487–507` | Copies OCR → GT text for all words in that specific line via the inline header button. |
| 12 | Copy GT → OCR (word scope) | Toolbar — Word row | Button `word-copy-gt-to-ocr-button` (icon: content_copy, mirrored) | Word | `word_match_actions.py:202–209` | Copies GT → OCR text for all selected words (operates at the containing-line granularity). |
| 13 | Copy OCR → GT (word scope, selected) | Toolbar — Word row | Button `word-copy-ocr-to-gt-button` (icon: content_copy) | Word | `word_match_actions.py:211–242` | Copies OCR → GT text for the selected words only (word-level granularity). |
| 14 | Validate all words (page scope) | Toolbar — Page row | Button `page-validate-button` (icon: check_circle) | Page | `word_match_toolbar.py:632–635` | Sets every word on the page to validated. |
| 15 | Unvalidate all words (page scope) | Toolbar — Page row | Button `page-unvalidate-button` (icon: unpublished) | Page | `word_match_toolbar.py:637–640` | Clears validation on every word on the page. |
| 16 | Validate all words (paragraph scope) | Toolbar — Paragraph row | Button `paragraph-validate-button` (icon: check_circle) | Paragraph | `word_match_toolbar.py:642–645` | Sets every word in the selected paragraphs to validated. |
| 17 | Unvalidate all words (paragraph scope) | Toolbar — Paragraph row | Button `paragraph-unvalidate-button` (icon: unpublished) | Paragraph | `word_match_toolbar.py:647–650` | Clears validation on every word in the selected paragraphs. |
| 18 | Validate all words (line scope, toolbar) | Toolbar — Line row | Button `line-validate-toolbar-button` (icon: check_circle) | Line | `word_match_toolbar.py:652–655` | Sets every word in the selected lines to validated. |
| 19 | Unvalidate all words (line scope, toolbar) | Toolbar — Line row | Button `line-unvalidate-toolbar-button` (icon: unpublished) | Line | `word_match_toolbar.py:657–660` | Clears validation on every word in the selected lines. |
| 20 | Validate / unvalidate all words (line scope, inline) | Per-line header | Button `line-validate-button` ("Validate" / "Unvalidate") | Line | `word_match_renderer.py:510–526` | Toggles validated state for all words in that single line; label and color update to reflect current state. |
| 21 | Validate selected words (word scope, toolbar) | Toolbar — Word row | Button `word-validate-toolbar-button` (icon: check_circle) | Word | `word_match_toolbar.py:662–665` | Sets the selected words to validated. |
| 22 | Unvalidate selected words (word scope, toolbar) | Toolbar — Word row | Button `word-unvalidate-toolbar-button` (icon: unpublished) | Word | `word_match_toolbar.py:667–669` | Clears validation on the selected words. |
| 23 | Toggle word validated (per-word button) | Word column — selection cell | Button `word-validate-button` (check icon, green/grey) | Word | `word_match_renderer.py:774–787` | Toggles the validated state of that single word; updates button colour immediately. |
| 24 | Merge selected lines | Toolbar — Line row | Button `line-merge-button` (icon: call_merge) | Line | `word_match_actions.py:248–277` | Merges two or more selected lines into the first selected line. |
| 25 | Delete selected lines (toolbar) | Toolbar — Line row | Button `line-delete-toolbar-button` (icon: delete) | Line | `word_match_actions.py:519–534` | Deletes all selected lines from the current page. |
| 26 | Delete single line (inline) | Per-line header | Button `line-delete-button` (icon: delete) | Line | `word_match_renderer.py:528–539` | Deletes one specific line via the inline header delete button. |
| 27 | Split paragraph after selected line | Toolbar — Line row (also labelled under Paragraph) | Button `paragraph-split-after-line-button` (icon: call_split) | Line/Paragraph | `word_match_actions.py:362–405` | Splits the containing paragraph immediately after the one selected line, creating two paragraphs. |
| 28 | Form new paragraph from selected lines | Toolbar — Line row | Button `line-form-paragraph-button` (icon: subject) | Line/Paragraph | `word_match_actions.py:407–467` | Moves the selected lines into a new paragraph. |
| 29 | Merge selected paragraphs | Toolbar — Paragraph row | Button `paragraph-merge-button` (icon: call_merge) | Paragraph | `word_match_actions.py:279–317` | Merges two or more selected paragraphs into the first. |
| 30 | Delete selected paragraphs | Toolbar — Paragraph row | Button `paragraph-delete-button` (icon: delete) | Paragraph | `word_match_actions.py:319–360` | Deletes all selected paragraphs from the current page. |
| 31 | Merge words (bulk, selected) | Toolbar — Word row | Button `word-merge-button` (icon: call_merge) | Word | `word_match_actions.py:570–614` | Merges two or more contiguous selected words on the same line into one. |
| 32 | Merge word into left neighbor (per-word) | Word edit dialog — Merge/Split section | Button `dialog-merge-prev-button` ("Merge Prev") | Word | `word_edit_dialog.py:1531–1548` | Merges the current word with its left neighbor in the dialog context. |
| 33 | Merge word with right neighbor (per-word) | Word edit dialog — Merge/Split section | Button `dialog-merge-next-button` ("Merge Next") | Word | `word_edit_dialog.py:1549–1567` | Merges the current word with its right neighbor in the dialog context. |
| 34 | Delete selected words (toolbar) | Toolbar — Word row | Button `word-delete-button` (icon: delete) | Word | `word_match_actions.py:536–568` | Deletes all selected words from their lines. |
| 35 | Delete single word (dialog) | Word edit dialog — Merge/Split section | Button `dialog-delete-word-button` (icon: delete) | Word | `word_edit_dialog.py:1619–1631` | Deletes the current word from its line. |
| 36 | Split line after selected word | Toolbar — Line row | Button `line-split-after-word-button` (icon: call_split) | Line | `word_match_actions.py:469–517` | Splits the selected line immediately after the one selected word, creating two lines. |
| 37 | Split line(s) by selection (selected/unselected words) | Toolbar — Line row | Button `line-split-by-selection-button` (icon: vertical_split) | Line | `word_match_actions.py:961–1007` | Splits each affected line into a line of selected words and a line of unselected words. |
| 38 | Form new line from selected words | Toolbar — Word row | Button `word-form-line-button` (icon: short_text) | Word/Line | `word_match_actions.py:916–959` | Moves all selected words into a single newly created line. |
| 39 | Group selected words into new paragraph | Toolbar — Word row | Button `word-form-paragraph-button` (icon: format_paragraph) | Word/Paragraph | `word_match_actions.py:1009–1055` | Moves all selected words into a newly created paragraph (one new line per source line). |
| 40 | Split word horizontally (H-split) | Word edit dialog — Merge/Split section | Button `dialog-split-h-button` ("H" + call_split icon); enabled after clicking split marker on word image | Word | `word_match_actions.py:1299–1365` | Splits the word at the vertical marker line, creating two words from one; requires a click on the word image to set the split position first. |
| 41 | Split word vertically / assign to closest line (V-split) | Word edit dialog — Merge/Split section | Button `dialog-split-v-button` ("V" + call_split icon); enabled after clicking split marker on word image | Word/Line | `word_match_actions.py:1367–1453` | Splits the word at the horizontal marker line and reassigns the resulting pieces to their geometrically closest lines. |
| 42 | Set split position marker on word image | Word edit dialog — word image (interactive) | Click on word interactive image | Word | `word_edit_dialog.py:237–315` | Records the x/y fraction of the click inside the word image as the pending split/crop marker; enables the H-split, V-split, and crop buttons. |
| 43 | Rebox word (start mode) | Word column (inline, per-word button) | Button `word-rebox-button` (or triggered from inline word card action) then draw on Words image | Word | `word_match_bbox.py:467–493` | Enters rebox mode for that word; user then draws a new bounding rectangle on the page image to replace the word's bbox. |
| 44 | Apply reboxed bbox to word | Words image overlay | Draw rectangle on Words image | Word | `word_match_bbox.py:495–548` | Commits the drawn rectangle as the new bbox for the word pending rebox. |
| 45 | Add word (draw new bbox) | Toolbar — Add Word row | Button `word-add-button` ("Add Word") then draw on Words image | Word | `word_match_bbox.py:554–582` | Enters add-word mode; user draws a bbox on the page image, and the new word is inserted into the nearest line. |
| 46 | Fine-tune / nudge word bbox — left edge expand | Word column (fine-tune open) or Word edit dialog | Button `dialog-nudge-left-plus-button` ("X+") | Word | `word_edit_dialog.py:1719–1729` | Accumulates a pending left-edge expansion on the word bbox (delta persists until Apply). |
| 47 | Fine-tune / nudge word bbox — left edge shrink | Word column or dialog | Button `dialog-nudge-left-minus-button` ("X-") | Word | `word_edit_dialog.py:1708–1718` | Accumulates a pending left-edge shrink. |
| 48 | Fine-tune / nudge word bbox — right edge expand | Word column or dialog | Button `dialog-nudge-right-plus-button` ("X+") | Word | `word_edit_dialog.py:1743–1753` | Accumulates a pending right-edge expansion. |
| 49 | Fine-tune / nudge word bbox — right edge shrink | Word column or dialog | Button `dialog-nudge-right-minus-button` ("X-") | Word | `word_edit_dialog.py:1732–1742` | Accumulates a pending right-edge shrink. |
| 50 | Fine-tune / nudge word bbox — top edge expand | Word column or dialog | Button `dialog-nudge-top-plus-button` ("Y+") | Word | `word_edit_dialog.py:1770–1778` | Accumulates a pending top-edge expansion. |
| 51 | Fine-tune / nudge word bbox — top edge shrink | Word column or dialog | Button `dialog-nudge-top-minus-button` ("Y-") | Word | `word_edit_dialog.py:1758–1767` | Accumulates a pending top-edge shrink. |
| 52 | Fine-tune / nudge word bbox — bottom edge expand | Word column or dialog | Button `dialog-nudge-bottom-plus-button` ("Y+") | Word | `word_edit_dialog.py:1793–1803` | Accumulates a pending bottom-edge expansion. |
| 53 | Fine-tune / nudge word bbox — bottom edge shrink | Word column or dialog | Button `dialog-nudge-bottom-minus-button` ("Y-") | Word | `word_edit_dialog.py:1781–1791` | Accumulates a pending bottom-edge shrink. |
| 54 | Reset pending bbox nudges (dialog) | Word edit dialog — Bounding Box section | Button `dialog-reset-nudges-button` ("Reset") | Word | `word_edit_dialog.py:1812–1817` | Discards all accumulated bbox deltas, restoring the preview to the original bbox. |
| 55 | Apply pending bbox nudges (dialog, no refine) | Word edit dialog — Bounding Box section | Button `dialog-apply-nudges-button` ("Apply") | Word | `word_edit_dialog.py:1818–1825` | Commits the accumulated deltas to the word bbox without running refine. |
| 56 | Apply pending bbox nudges + refine (dialog) | Word edit dialog — Bounding Box section | Button `dialog-apply-refine-nudges-button` ("Apply + Refine") | Word | `word_edit_dialog.py:1826–1833` | Commits accumulated deltas and then runs the refine algorithm on the resulting bbox. |
| 57 | Apply and close dialog (auto-apply) | Word edit dialog — header | Button `dialog-apply-close-button` (check icon) | Word | `word_edit_dialog.py:1352–1354` | Applies any pending erase rects and bbox nudges, then closes the dialog. |
| 58 | Crop word bbox above marker | Word edit dialog — Bounding Box section | Button `dialog-crop-above-button` ("Crop Above") | Word | `word_edit_dialog.py:1641–1646` | Stages a top-edge crop to the horizontal split marker position (removes pixels above the marker). |
| 59 | Crop word bbox below marker | Word edit dialog — Bounding Box section | Button `dialog-crop-below-button` ("Crop Below") | Word | `word_edit_dialog.py:1647–1652` | Stages a bottom-edge crop to the horizontal split marker position. |
| 60 | Crop word bbox left of marker | Word edit dialog — Bounding Box section | Button `dialog-crop-left-button` ("Crop Left") | Word | `word_edit_dialog.py:1653–1658` | Stages a left-edge crop to the vertical split marker position. |
| 61 | Crop word bbox right of marker | Word edit dialog — Bounding Box section | Button `dialog-crop-right-button` ("Crop Right") | Word | `word_edit_dialog.py:1659–1664` | Stages a right-edge crop to the vertical split marker position. |
| 62 | Toggle box-erase mode | Word edit dialog — Bounding Box section | Button `dialog-erase-box-button` ("Erase Box" / "Erase Box On") | Word | `word_edit_dialog.py:1666–1673` | Toggles drag-to-erase-rectangle mode on the word image; dragging while active stages a rectangular pixel-erase region. |
| 63 | Drag erase rectangle on word image | Word edit dialog — word image (while erase-box mode is on) | Mouse drag (mousedown → mousemove → mouseup) on interactive image | Word | `word_edit_dialog.py:435–468` | Draws a transient rectangle during drag; on mouseup the region is staged as a pending erase rect for later Apply. |
| 64 | Apply staged erase rects (via Apply/Close) | Word edit dialog | Button `dialog-apply-close-button` or dialog close sequence | Word | `word_edit_dialog.py:636–657` | Commits all staged pixel-erase rectangles to the underlying page image via `erase_pixels_rect_callback`. |
| 65 | Erase pixels to marker (left direction) | Word edit dialog — erase-to-marker buttons (if exposed) | Via `_erase_to_marker("left")` — accessible through the dialog's erase-direction logic | Word | `word_edit_dialog.py:1126–1201` | Immediately erases the pixel strip left of the active marker position from the word's bbox region. |
| 66 | Erase pixels to marker (right direction) | Word edit dialog | `_erase_to_marker("right")` | Word | `word_edit_dialog.py:1126–1201` | Immediately erases the pixel strip right of the marker. |
| 67 | Erase pixels to marker (above direction) | Word edit dialog | `_erase_to_marker("above")` | Word | `word_edit_dialog.py:1126–1201` | Immediately erases the pixel strip above the horizontal marker. |
| 68 | Erase pixels to marker (below direction) | Word edit dialog | `_erase_to_marker("below")` | Word | `word_edit_dialog.py:1126–1201` | Immediately erases the pixel strip below the horizontal marker. |
| 69 | Refine selected word bboxes (toolbar) | Toolbar — Word row | Button `word-refine-bboxes-button` (icon: auto_fix_high) | Word | `word_match_actions.py:620–646` | Runs the bbox-refine algorithm on all selected words. |
| 70 | Expand then refine selected word bboxes (toolbar) | Toolbar — Word row | Button `word-expand-refine-bboxes-button` (icon: zoom_out_map) | Word | `word_match_actions.py:712–744` | Expands word bboxes beyond their original extent, then refines. |
| 71 | Expand selected word bboxes (toolbar) | Toolbar — Word row | Button `word-expand-bboxes-button` (icon: open_in_full) | Word | `word_match_actions.py:746–772` | Applies uniform padding to selected word bboxes without refine. |
| 72 | Refine single word bbox (dialog preview) | Word edit dialog — Bounding Box section | Button `dialog-refine-preview-button` ("Refine") | Word | `word_edit_dialog.py:1676–1685` | Stages the result of running refine on the current word bbox as pending deltas (preview only; not applied until Apply). |
| 73 | Expand + refine single word bbox (dialog preview) | Word edit dialog — Bounding Box section | Button `dialog-expand-refine-preview-button` ("Expand + Refine") | Word | `word_edit_dialog.py:1686–1697` | Stages expand-then-refine deltas as pending (preview only). |
| 74 | Refine single word bbox (inline per-word) | Word column (when fine-tune open, from `_handle_refine_single_word`) | Button in inline fine-tune row | Word | `word_match_actions.py:1061–1105` | Runs refine directly on one specific word bbox (non-dialog path). |
| 75 | Expand then refine single word bbox (inline per-word) | Word column (inline fine-tune) | Button in inline fine-tune row | Word | `word_match_actions.py:1107–1154` | Runs expand-then-refine on one specific word bbox. |
| 76 | Refine selected line bboxes (toolbar) | Toolbar — Line row | Button `line-refine-bboxes-button` (icon: auto_fix_high) | Line | `word_match_actions.py:648–674` | Runs bbox refine on all selected lines. |
| 77 | Expand then refine selected line bboxes (toolbar) | Toolbar — Line row | Button `line-expand-refine-bboxes-button` (icon: zoom_out_map) | Line | `word_match_actions.py:774–806` | Expands then refines selected line bboxes. |
| 78 | Expand selected line bboxes (toolbar) | Toolbar — Line row | Button `line-expand-bboxes-button` (icon: open_in_full) | Line | `word_match_actions.py:808–834` | Applies uniform padding to selected line bboxes. |
| 79 | Refine selected paragraph bboxes (toolbar) | Toolbar — Paragraph row | Button `paragraph-refine-bboxes-button` (icon: auto_fix_high) | Paragraph | `word_match_actions.py:676–706` | Runs bbox refine on all selected paragraphs. |
| 80 | Expand then refine selected paragraph bboxes (toolbar) | Toolbar — Paragraph row | Button `paragraph-expand-refine-bboxes-button` (icon: zoom_out_map) | Paragraph | `word_match_actions.py:836–873` | Expands then refines selected paragraph bboxes. |
| 81 | Expand selected paragraph bboxes (toolbar) | Toolbar — Paragraph row | Button `paragraph-expand-bboxes-button` (icon: open_in_full) | Paragraph | `word_match_actions.py:875–910` | Applies uniform padding to selected paragraph bboxes. |
| 82 | Refine all bboxes on page | Toolbar — Page row | Button `page-refine-bboxes-button` (icon: auto_fix_high) — only shown when callback registered | Page | `word_match_toolbar.py:99–106` | Runs the refine algorithm on every bounding box on the entire page. |
| 83 | Expand then refine all bboxes on page | Toolbar — Page row | Button `page-expand-refine-bboxes-button` (icon: zoom_out_map) — only when callback registered | Page | `word_match_toolbar.py:108–117` | Expands then refines every bbox on the page. |
| 84 | Apply text style to selected words (toolbar) | Toolbar — Apply Style row | Select `apply-style-select` + Button `apply-style-button` ("Apply Style") | Word | `word_match_toolbar.py:510–518` | Applies the selected text style label (e.g. italics, small caps, blackletter, bold, underline, …) to all selected words. |
| 85 | Apply text style scope to selected words (toolbar) | Toolbar — Apply Style row | Select `scope-select` (Whole / Part) — immediate on change | Word | `word_match_toolbar.py:412–424` | Sets the scope attribute (whole / part) on every existing non-regular style of the selected words. |
| 86 | Apply text style to single word (dialog) | Word edit dialog — style/component row | Select `dialog-style-select` + Button `dialog-apply-style-button` ("Apply Style") | Word | `word_edit_dialog.py:1877–1892` | Applies a text style label to the single current word. |
| 87 | Apply text style scope to single word style (dialog) | Word edit dialog — style/component row | Select `dialog-scope-select` (Whole / Part / --) — immediate on change | Word | `word_edit_dialog.py:1469–1480` | Sets or clears the scope on the selected style of the current word. |
| 88 | Apply component to selected words (toolbar) | Toolbar — Apply Component row | Select `apply-component-select` + Button `apply-component-button` ("Apply Component") | Word | `word_match_toolbar.py:526–531` | Enables a word component (footnote marker, drop cap, subscript, superscript) on all selected words. |
| 89 | Clear component from selected words (toolbar) | Toolbar — Apply Component row | Button `clear-component-button` ("Clear Component") | Word | `word_match_toolbar.py:532–536` | Disables the selected component from all selected words. |
| 90 | Apply component to single word (dialog) | Word edit dialog — style/component row | Button `dialog-apply-component-button` ("Apply Component") | Word | `word_edit_dialog.py:1505–1514` | Enables the selected component on the single current word. |
| 91 | Clear component from single word (dialog) | Word edit dialog — style/component row | Button `dialog-clear-component-button` ("Clear Component") | Word | `word_edit_dialog.py:1515–1524` | Disables the selected component on the single current word. |
| 92 | Clear tag (style or component) from word — inline chip | Word comparison table, OCR cell — tag chip close button | Mouse-hover chip → click `word-tag-clear-button` (X icon) | Word | `word_match_renderer.py:956–970` | Removes one style or component tag from the word via the tag chip X button shown on hover. |
| 93 | Clear tag (style or component) from word — dialog chip | Word edit dialog — tag chips row | Mouse-hover chip → click `word-edit-tag-clear-button` (X icon) | Word | `word_edit_dialog.py:801–817` | Same removal but from the open edit dialog's tag chips. |
| 94 | Toggle italic on word (legacy style button) | Word column — legacy `_handle_toggle_word_attribute` | Triggered via `_handle_toggle_word_attribute(…, "italic")` | Word | `word_match_gt_editing.py:291–332` | Toggles the italic style flag on a single word using the legacy `set_word_attributes_callback`. |
| 95 | Toggle small caps on word (legacy) | Word column — legacy style button | `_handle_toggle_word_attribute(…, "small caps")` | Word | `word_match_gt_editing.py:291–332` | Toggles small-caps style flag. |
| 96 | Toggle blackletter on word (legacy) | Word column — legacy style button | `_handle_toggle_word_attribute(…, "blackletter")` | Word | `word_match_gt_editing.py:291–332` | Toggles blackletter style flag. |
| 97 | Toggle footnote marker on word (legacy) | Word column — legacy style button | `_handle_toggle_word_attribute(…, "footnote")` | Word | `word_match_gt_editing.py:291–332` | Toggles footnote-marker flag (sets both left_footnote and right_footnote). |
| 98 | Rematch GT (re-run GT alignment from source text) | Page actions bar | Button `rematch-gt-button` ("Rematch GT") | Page | `page_actions.py:93–100` | Re-runs ground truth matching from the page's source text, replacing any per-word GT edits on the current page. |
| 99 | Crop word bbox to marker (inline, left direction) | Word column inline fine-tune (via `handle_crop_word_to_marker`) | Inline crop button when fine-tune open | Word | `word_match_bbox.py:783–953` | Immediately commits a left-side bbox crop to the marker position (no pending staging). |
| 100 | Crop word bbox to marker (inline, right direction) | Word column inline fine-tune | Inline crop button | Word | `word_match_bbox.py:783–953` | Immediately commits a right-side bbox crop. |
| 101 | Crop word bbox to marker (inline, above direction) | Word column inline fine-tune | Inline crop button | Word | `word_match_bbox.py:783–953` | Immediately commits a top-side bbox crop. |
| 102 | Crop word bbox to marker (inline, below direction) | Word column inline fine-tune | Inline crop button | Word | `word_match_bbox.py:783–953` | Immediately commits a bottom-side bbox crop. |
| 103 | Toggle bbox fine-tune controls (inline) | Word column | Button (toggle open/close inline fine-tune panel) | Word | `word_match_bbox.py:588–614` | Opens or closes the inline fine-tune nudge/crop/refine controls for a single word column. |
| 104 | Filter lines display — All / Unvalidated / Mismatched | Word match view — filter selector | Select control (filter-selector) | Page-level display | `word_match.py:711–718` | Changes the visible line set to All Lines, Unvalidated Lines, or Mismatched Lines. |

## User paths

### 1. Correct a misread OCR word end-to-end

1. Open a page with OCR and ground truth loaded.
2. The word comparison table shows colored line cards. Find a line with a mismatch (red/yellow background).
3. Locate the misread word column. The OCR cell shows the wrong text.
4. Click the GT input field below the word and type the correct text.
5. Press Enter (or click elsewhere / Tab to next word) to commit: `_commit_word_gt_input_change` calls `edit_word_ground_truth_callback`, the line card refreshes.
6. If the correction now matches OCR exactly, the line card turns green. Otherwise use action 12/13 (Copy OCR→GT) for bulk fixes.
7. Click the word's validate button (check icon) or use toolbar Validate (Word scope) to mark the word as confirmed.
8. Click Save Page to persist.

### 2. Split a word that was incorrectly merged by OCR

1. Click the edit button (pencil icon) on the incorrectly merged word to open the word edit dialog.
2. In the dialog, click on the word image at the desired split point — a crosshair marker appears.
3. Click the "H" (horizontal split) button — `_handle_split_word` is called with the stored fraction.
4. Two new word columns appear in the table. Edit GT text for each new word as needed.
5. Validate both words, then Save Page.

### 3. Fix a word bounding box that clips characters

1. Click the edit button (pencil icon) on the word with a bad bbox.
2. In the word edit dialog, use the fine-tune nudge buttons (Left X+, Right X+, Top Y-, Bottom Y+, etc.) to accumulate deltas; the zoomed preview updates live.
3. Optionally click "Refine" or "Expand + Refine" to let the algorithm auto-tighten.
4. Click "Apply" (or "Apply + Refine") to commit the deltas, or "Apply and close" to commit and dismiss.
5. Confirm the updated slice looks correct in the word column, then Save Page.

### 4. Rebox a word whose bbox is completely wrong

1. From the word column, click the rebox button (or the dialog's Rebox action if available).
2. Switch to the Words image tab; the app enters rebox mode and shows a notification.
3. Draw a rectangle around the correct character extent on the page image.
4. The bbox is replaced: `apply_rebox_bbox` fires, the word column re-renders.
5. Validate the word and Save Page.

### 5. Label a word as italic / apply a style

1. Select the word checkbox in the word column (or select multiple words).
2. In the toolbar Apply Style row, choose the style from the `apply-style-select` (e.g. "italics").
3. Click "Apply Style" — all selected words gain the style; tag chips appear in each word's OCR cell.
4. Optionally set scope (Whole / Part) via the `scope-select` dropdown.
5. To remove a style, hover the tag chip in the word column and click the X button, or open the dialog and use Clear Component / clear the tag chip.

### 6. Mark a word as a footnote marker / drop cap

1. Select the target word(s).
2. In the toolbar Apply Component row, choose "Footnote Marker" or "Drop Cap" from `apply-component-select`.
3. Click "Apply Component" — the component tag chip (green) appears on the word.
4. To remove: hover the tag chip → click X, or use "Clear Component".

### 7. Erase spurious ink from a word's pixel region

1. Click the edit button to open the word edit dialog.
2. Click the word image to place a marker (or skip for full-box erase).
3. Click "Erase Box" to enter drag-erase mode; drag a rectangle over the ink to remove.
4. The region is staged (shown as a white overlay); repeat as needed.
5. Click "Apply and close" to commit all staged erase rects to the page image.

### 8. Restructure paragraph/line layout after a bad OCR segmentation

1. Select the checkboxes of the lines that should form a new paragraph.
2. Click "Select lines to form a new paragraph" (`line-form-paragraph-button`) in the Line row.
3. The selected lines move into a new paragraph group.
4. To merge two paragraphs back, select their paragraph checkboxes and click `paragraph-merge-button`.
5. To split a paragraph after a specific line, select exactly one line, then click `paragraph-split-after-line-button`.

### 9. Bulk validate a page of ground truth after review

1. Review all lines and apply any corrections.
2. Click `page-validate-button` (check_circle icon, Page row in toolbar) to mark every word on the page as validated in one step.
3. If a few words were incorrectly validated, select their word checkboxes and click `word-unvalidate-toolbar-button`.
4. Save Page.

### 10. Copy OCR text to ground truth for a full page (batch initialise GT)

1. If the page has no GT text but has OCR output, click `page-copy-ocr-to-gt-button` (toolbar Page row).
2. All OCR words are copied to their GT fields in one operation.
3. Review any mismatches, then correct individual words via GT input or Copy-GT→OCR overrides.

## Cross-dimension spillover

The following items surfaced during dimension B research but belong to other dimensions:

- **Dimension A (Navigation/Chrome)**:
  - Filter selector ("All Lines" / "Unvalidated Lines" / "Mismatched Lines") — item 104 is listed here as it changes display scope for content actions, but the filter control itself is a navigation chrome element.
  - Paragraph expand/collapse toggle (`paragraph-expander-button`, `paragraph-label-button`) — controls structural layout visibility, not content.
  - Page forward/back navigation (`project_navigation_controls.py`) — pure navigation.

- **Dimension C (Whole-document/global)**:
  - Save Page (`save-page-button`) and Save Project (`save-project-button`) in `page_actions.py` — these are persistence operations scoped to the whole page/project, not individual OCR content elements.
  - Reload OCR (`reload-ocr-button`, `reload-ocr-edited-button`) — triggers re-OCR of the whole page, classified as a page/system operation.
  - Export dialog (`export-button`, `ExportDialog`) — whole-page DocTR export operation.
  - Global keyboard shortcut list (documented in `docs/archive/research/2026-05-06-keyboard-shortcuts-coverage.md`).

- **No vocabulary/dictionary panel found** — the legacy labeler does not expose a dedicated "add to vocabulary" or bulk-word-actions panel in its editing UI. The `vocab` field in model-selection config is an OCR recognition vocabulary (pass-through to DocTR), not a user-facing editing dictionary.

## Coverage self-check

### Source files scanned

| File | Relevance |
|------|-----------|
| `pd_ocr_labeler/views/projects/pages/word_match_toolbar.py` | Primary: all toolbar button declarations, validation handlers |
| `pd_ocr_labeler/views/projects/pages/word_match_actions.py` | Primary: all bulk action handlers (copy, merge, delete, split, refine, expand) |
| `pd_ocr_labeler/views/projects/pages/word_edit_dialog.py` | Primary: per-word dialog UI (split, merge, bbox nudge, crop, erase, style/component, GT edit) |
| `pd_ocr_labeler/views/projects/pages/word_operations.py` | Primary: SelectedWordOperationsProcessor (style/scope/component apply/clear logic) |
| `pd_ocr_labeler/views/projects/pages/word_match_gt_editing.py` | Primary: GT text input, legacy style toggle buttons |
| `pd_ocr_labeler/views/projects/pages/word_match_renderer.py` | Primary: per-word column rendering, inline validate button, inline line buttons, tag chips |
| `pd_ocr_labeler/views/projects/pages/word_match_bbox.py` | Primary: rebox, add-word, inline fine-tune nudge/crop, refine helpers |
| `pd_ocr_labeler/views/projects/pages/word_match.py` | Primary: callback wiring, `_clear_word_tag`, `_word_display_tag_items`, filter handler |
| `pd_ocr_labeler/views/projects/pages/page_actions.py` | Partial (Rematch GT is content-adjacent; Save/Reload → dim C) |
| `pd_ocr_labeler/views/projects/pages/content.py` | Read (erase callback wiring, not direct UI) |
| `pd_ocr_labeler/views/projects/pages/text_tabs.py` | Read (TextTabsModel / callback factories; no additional content actions) |
| `pd_ocr_labeler/views/projects/pages/word_match_selection.py` | Read (selection state only; no content mutations) |
| `pd_ocr_labeler/views/projects/pages/page_view.py` | Not read individually; routing only |
| `pd_ocr_labeler/state/page_state.py` | Method signatures scanned for completeness check |
| `pd_ocr_labeler/views/callbacks.py` | Scanned (rematch, reload_ocr callbacks) |
| `tests/browser/test_toolbar_word_actions.py` | Consulted for action names |
| `tests/browser/test_toolbar_line_actions.py` | Consulted |
| `tests/browser/test_toolbar_paragraph_actions.py` | Consulted |
| `tests/browser/test_word_edit_dialog.py` | Consulted |
| `tests/browser/test_word_match_line_actions.py` | Consulted |
| `docs/architecture/ui-action-buttons.md` | Consulted for architectural context |

### Not fully covered / potential gaps

- **Inline fine-tune controls (word column, not dialog)**: The `toggle_bbox_fine_tune` path from `word_match_bbox.py:588` opens an inline nudge/crop/refine panel directly inside the word column. The exact set of buttons rendered in that inline panel was not read in full; the dialog version is fully catalogued (actions 46–103). The crop and nudge callbacks follow the same pattern.
- **`split_paragraphs` (batch by indices)**: `page_state.py` exposes `split_paragraphs(paragraph_indices)` but no toolbar button for this specific signature was found; `split_paragraph_after_line` and `split_paragraph_with_selected_lines` are the two wired forms.
- **Legacy-style toggle buttons rendered in the word column**: `_handle_toggle_word_attribute` (actions 94–97) is implemented but it is unclear from the code whether the four legacy style icon buttons (italic/small-caps/blackletter/footnote) are currently rendered in the word column in the deployed UI or only invoked via the `WordOperationsProcessor` path; both paths are documented.
- **Export dialog**: Not audited for content-level actions (considered a whole-document operation → dim C).

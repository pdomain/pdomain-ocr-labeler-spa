# Legacy → New Parity Gap Matrix

**Legacy:** `pd-ocr-labeler` (NiceGUI) · **New:** `pdomain-ocr-labeler-spa` (FastAPI + React/Vite/TS, **v0.2.0**)
**Audited:** 2026-06-06 · **Method:** per-dimension synthesis of the six inventories in this folder, re-verified against current code.

> Status key — classified by **capability**, not code presence:
> - ✅ **PRESENT & WIRED** — visible, enabled, and performs the stated effect via *some* reachable surface.
> - ⚠️ **PARTIAL / STUBBED** — code path exists but is hidden (`display:none`), unwired, hardcoded, backend-stubbed, or silently no-ops.
> - ❌ **MISSING** — no reachable working path today.
>
> A `data-testid` existing is **not** parity. A wired child button whose parent never passes the mutation callback is ❌, not ✅.

---

## 1. Executive summary

| Dimension | ✅ Present | ⚠️ Partial/stub | ❌ Missing | Notes |
|---|---:|---:|---:|---|
| **A — screens / nav / chrome** | ~20 | 5 | 2 (+1 new-only unreachable) | Shell is solid; gaps are minor chrome + one blocked entry point (#405). |
| **B — OCR content actions** | ~35 | ~12 | ~16 | Two entire editing **surfaces** are dead; most capabilities survive via alternate surfaces. |
| **C — document / project / system** | ~18 | 7 | 5 | Export & save are real; rotate/auto-rotate are known stubs (M9.1/M9.2). |

### The headline finding — why raw counts mislead

The new SPA has **more** actions in code than legacy, yet is **not at full parity**, for one structural reason that recurs across dimension B:

> **Capabilities are implemented, but two whole surfaces that expose them are non-functional.**

1. **`WordEditDialog` is a complete no-op.** `ProjectPage.tsx:1048` mounts the dialog with **none** of its mutation callbacks (`onMerge`, `onSplit`, `onDelete`, `onCrop`, `onRefine`, `onExpandRefine`, `onApplyNudge`, `onApplyStyle`, `onApplyComponent`, `onGtChange`, `onGtCommit`). Every button inside the dialog renders, fires `?? Promise.resolve()`, and silently does nothing. **Verified directly** (ProjectPage.tsx:1048–1063 — only `open/target/lineWords/onNavigate/onApply/onClose` + `wordImageUrl={undefined}`).

2. **The Matches pane is hidden.** `WordMatchView` + `TextTabs` + `PlaintextEditor` live inside `<div style={{display:"none"}} data-testid-stub="canvas-hidden-stubs">` (ProjectPage.tsx:978–988). Per-word validate buttons, line/paragraph checkboxes, tag-chip × buttons, GT inputs, and the match-filter content all exist in the DOM purely to satisfy driver-contract testids — invisible and non-interactive to users.

**The saving grace:** most dimension-B *capabilities* are still reachable through **alternate, working surfaces** — the **WordDetail right panel** (rebox, nudge, refine, erase, merge, delete, char-ranges, char-fixer, style/component chips), the **visible ToolbarActionGrid** (page/para/line/word bulk ops — shipped in v0.2.0), and **inline LineCard/ParagraphDetail** controls. So **capability-parity is high (~80%)** even though **surface-parity is not**: a user *can* do most things, just not from the dialog or the Matches pane the legacy app trained them to use.

### True-parity estimate

- **Capability reachability (can the user accomplish the task by *some* path today?): ~80%.**
- **Surface parity (is it reachable where a legacy user would look?): lower** — two primary editing surfaces are dead.
- **Genuinely missing capabilities (no working path anywhere):** rebox-on-main-canvas, per-word glyph annotation, form-new-line-from-selected-words (backend stub), erase-to-marker (4 directions), Tab-navigation between GT inputs, and the real image rotate / auto-rotate / re-OCR pipeline.

### Top root causes (fix these and most ❌ rows clear)

1. **Unwired dialog callbacks** (one parent, ~11 props) → clears ~9 ❌ rows at once.
2. **Hidden Matches pane** (one `display:none`) → architectural decision needed: restore vs. formally retire.
3. **Two backend stubs** — `/lines/{li}/split-with-selected` (form-new-line) and the rotate/auto-rotate handlers.
4. **Unmounted components** — `GlyphAnnotationPanel`, `QuickSearch` exist but are mounted nowhere.

---

## 2. Missing (❌) — no reachable working path today

### Dimension B — content actions (the bulk of the gaps)

| Legacy capability | Legacy ref | New evidence | Why it matters |
|---|---|---|---|
| WordEditDialog — merge word prev/next | `word_edit_dialog.py:1531` | `WordActionRows.tsx:127`; `onMerge` not passed (ProjectPage.tsx:1048) | Dialog merge dead. Alt: `StructureSection` (WordDetail). |
| WordEditDialog — split word H/V | `word_match_actions.py:1299` | `WordActionRows.tsx:145`; `onSplit` not passed | Dialog split dead. Alt: `StructureSection`. V-split also 400s backend. |
| WordEditDialog — delete word | `word_edit_dialog.py:1619` | `WordActionRows.tsx:167`; `onDelete` not passed | Dialog delete dead. Alt: `WordFooter`. |
| WordEditDialog — crop bbox (4 dir) | `word_edit_dialog.py:1641` | `WordActionRows.tsx:185`; `onCrop` not passed | No alt crop surface in WordDetail. |
| WordEditDialog — apply/clear style | `word_edit_dialog.py:1877` | `WordTagRow.tsx:100`; `onApplyStyle` not passed | Dialog style dead. Alt: ToolbarActionGrid + WordDetail chips. |
| WordEditDialog — apply/clear component | `word_edit_dialog.py:1505` | `WordTagRow.tsx:127`; `onApplyComponent` not passed | Dialog component dead. Alt: toolbar + chips. |
| WordEditDialog — refine / expand+refine / apply-nudge | `word_edit_dialog.py:1676` | `WordRefineNudgeRows.tsx:162`; callbacks not passed | Dialog bbox tuning dead. Alt: `BBoxSection`. |
| WordEditDialog — GT edit (commit) | `word_edit_dialog.py:1403` | `WordEditDialog.tsx:306`; `onGtChange/onGtCommit` not passed | Typing in `dialog-gt-input` has no effect. Alt: WordDetail `ocr-gt-input`. |
| WordEditDialog — pixel erase on dialog image | `word_edit_dialog.py:435` | `wordImageUrl={undefined}` (ProjectPage.tsx:1052) → blank canvas | Dialog erase broken. Alt: `ErasePixelsSection`. |
| Rebox word on **main canvas** (draw mode) | `word_match_bbox.py:467` | `"rebox"` mode + `onRebox` prop exist; **not wired** in ProjectPage's `<PageImageCanvas>` | No draw-to-rebox on page. Alt: WordDetail mini-canvas (per-word only). |
| Per-word **glyph annotation** panel | (new-only target M11) | `GlyphAnnotationPanel.tsx` mounted **nowhere** (only self + test import) | Swash/long-s/ligature per-word review unreachable. Alt: bulk recipe only. |
| Per-word **validate** button in Matches pane | `word_match_renderer.py:774` | `WordCell.tsx:187` wired, but `WordMatchView` hidden + prop chain broken | Alt: `word-footer-validate`, toolbar, BulkWordActions. |
| Tag-chip **×** remove in Matches pane | `word_match_renderer.py:956` | `WordCell.tsx:227`; `onClearTag` not threaded + hidden | Alt: `clear-style/component-button`, WordDetail chips. |
| **Form new line** from selected words (toolbar) | `word_match_actions.py:916` | `/lines/{li}/split-with-selected` is a **backend stub** (`lines_paragraphs.py:1907`, returns empty payload) | Toolbar cell appears to succeed, makes no change. |
| **Erase-to-marker** (left/right/above/below) | `word_edit_dialog.py:1126` | No equivalent; new erase is brush/lasso/rect only | 4 directional erase ops have no surface. |
| **Tab-navigate** between GT inputs (word scope) | `word_match_gt_editing.py:145` | No `onKeyDown` Tab handler; Matches pane hidden anyway | Sequential keyboard GT editing missing. |

### Dimension A — screens / chrome

| Legacy capability | Legacy ref | New evidence | Why it matters |
|---|---|---|---|
| **OCR Config from root / no-project** context | `project_load_controls.py:110` | `ocr-config-trigger-button` only injected when `onProjectRoute` (App.tsx:203); absent on RootPage | Can't configure models before opening a project. **Issue #405 open.** |
| **Resolved project filesystem path** in header | `project_load_controls.py:114` | `source-root-label` shows source *root*, and is `sr-only` on project routes | Lost at-a-glance confirmation of which project dir is open. |
| *(new-only, unreachable)* **QuickSearch** bar | — | `QuickSearch.tsx:23` defined + tested, **mounted nowhere** | Worklist search store is wired but has no QuickSearch entry point (filter chips still work). |

### Dimension C — document / system

| Legacy capability | Legacy ref | New evidence | Why it matters |
|---|---|---|---|
| OCR config **Cancel** (discard w/o applying) | `ocr_config_modal.py:127` | `OCRConfigModal` POSTs on every select `onChange`; no pre-open snapshot | Can't preview model options and back out. |
| Rotate page **180°** button | (SPA spec C-31) | `PageActions.tsx` renders only CW/CCW; 180 testid in comment, no button | Spec'd variant absent (and rotate is stubbed anyway). |
| Generic **job queue / progress panel** UI | (SPA-new) | `GET /api/jobs` backend-only; only ExportDialog shows progress | OCR/refine/rotate progress invisible after click. |
| Source folder **"Use Current"** copy-to-input | `project_load_controls.py:348` | No equivalent button in `SourceFolderDialog` | Minor convenience gap. |
| Source folder **"Open Typed Path"** (browse w/o apply) | `project_load_controls.py:322` | Single `Mod+Enter` apply only | Reorganized; browse-then-confirm split lost. |

---

## 3. Partial / stubbed (⚠️)

### Dimension B

| Capability | New evidence | Nature of the gap |
|---|---|---|
| Line split-after-word | `LineDetail.tsx:381` `wordIndex: 0` hardcoded | Always splits after the *first* word; user can't pick the point. |
| V-split word | `words.py:1080` returns HTTP 400 for `direction="vertical"` | Backend blocks vertical split by design. |
| Refine / expand bboxes (all scopes) | `handlers/refine.py:90` real, but raises if page image absent | Real op; **silently fails when OCR image not loaded** (job reports "complete"). |
| WordEditDialog nudge accumulation | `WordRefineNudgeRows.tsx:185` | Preview/accumulate works; **commit discarded** (callback unwired). |
| Split paragraph after line (right panel) | `ParagraphDetail.tsx` `afterLineIndex: 0` | Always after line 0; no line picker. |
| Line/para checkbox selection (Matches pane) | `LineCard.tsx:188` no `onChange`; hidden | Bulk checkbox select dead. Alt: canvas drag-select + Rail. |
| Match-filter content (Unvalidated/Mismatched/All) | `WordMatchView` correct but inside `display:none` | Toggle visible (TextTabs); filtered content invisible. |
| Word-scope copy-GT (toolbar) | route real, but needs hidden Matches-pane word selection | Reachable only if word checkboxes were visible. |
| Inline fine-tune bbox (per word column) | `BBoxSection` (right panel) only | Functional, reduced discoverability. |

### Dimension A

| Capability | New evidence | Nature |
|---|---|---|
| TextTabs right-pane (Matches/GT/OCR tabs) | `ProjectPage.tsx:978` `display:none` | Deliberate re-map to Drawer/RightPanel; raw GT-vs-OCR side-by-side view lost. |
| Word-match toolbar location | `ToolbarActionGrid` now **visible** (ProjectPage.tsx:908) but relocated above canvas | Inventory's "hidden" claim is **STALE**; reachable, different surface. |
| **Go To** button | `ProjectNavigationControls.tsx:155` `className="sr-only"` | No visible click target; Enter-in-input works. Mouse-only minor regression. |
| Page-navigation spinner | `ProjectLoadingOverlay` cache-dependent | May show nothing on fast cached nav. |
| Session restore | `RootPage.tsx:458` real | Functionally equivalent; works. |

### Dimension C

| Capability | New evidence | Nature |
|---|---|---|
| **Rotate page CW/CCW (manual)** | `handlers/rotate.py:61` `asyncio.sleep(0)`, no image I/O | **Stub** (M9.1). Buttons fire a job that "succeeds" with no effect. |
| **Auto-rotate all pages** | `handlers/auto_rotate_all.py:71` progress only, no detection | **Stub** (M9.2). |
| Save page (labeled lane) | `api/pages.py:767`; no-op 200 when `page_store is None` | Silent no-op in store-less configs (CI risk); real when wired. |
| Save all pages (save-project) | `handlers/save_project.py:191` skips `page_id is None` pages with debug-only log | Partial save, **no user warning** for skipped pages. Route docstring STALE ("stub"). |
| Export history panel | `api/export.py:246` `list_exports` returns `[]` | Past-session exports not listed; current job progress is shown. |
| OCR config trigger on RootPage | absent on root (HeaderBar.tsx:193) | Arguably correct (config needs a project); was always-visible in legacy. |
| QuickSearch `⌘K` focus | `QuickSearch.tsx:34` keycap opens hotkeyHelp, not the field | Misleading shortcut. |

---

## 4. Missing / broken user paths (end-to-end journeys)

1. **Correct a word from the word-edit dialog** — *broken.* The dialog opens but **every** action (merge/split/delete/GT/style/component/crop/refine/nudge) is a no-op. The whole dialog workflow is dead. (Workaround: WordDetail right panel + ToolbarActionGrid.)
2. **Inline-edit words in the Matches pane** — *broken.* The pane is `display:none`; GT inputs, validate buttons, checkboxes, chip-× are invisible.
3. **Rebox a word by drawing on the page** — *broken.* `"rebox"` mode unwired on the main canvas; only per-word mini-canvas works.
4. **Per-word glyph annotation (swash/long-s/ligature)** — *broken.* Panel is dead code; only the page-scope bulk recipe exists.
5. **Form a new line from selected words (toolbar)** — *silently no-ops.* Backend route is a stub returning an empty payload.
6. **Open → rotate → export rotated training data** — *broken.* Rotate is a stub; export emits original-orientation image; rotation badge is cosmetic.
7. **OCR config: explore models then Cancel** — *broken.* Each select POSTs immediately; no discard.
8. **Save all → restart → reload** — *lossy.* Pages whose `page_id` was never registered are silently skipped with a "saved N pages" toast that may undercount.

---

## 5. Present & wired (✅, condensed)

**Dimension A:** SPA shell + routing; RootPage project grid; No-project placeholder; project/page busy overlays (incl. Cancel); nav bar (Prev/Next/input, Enter goto, Mod+Arrow/Home/End); Source Folder dialog; OCR Config modal (project routes); Export dialog (Mod+E); project select + LOAD; HeaderBar + breadcrumb + metrics strip; Toasts; layer toggles; selection-mode radio; URL deep-links; ConfirmDialog.

**Dimension B:** GT text edit (inline blur-commit); copy GT↔OCR at line/para/page; validate/unvalidate at word/line/para/page; delete word/line/para; merge word/line/para (right panel + toolbar); split word-H, split-line-by-words, split-para-after-line (real routes); form-new-**paragraph** from words/lines; rebox via numeric inputs + Konva mini-canvas; refine/expand+refine/expand (image-dependent); apply/clear style + component (right panel chips, toolbar, BulkWordActions); erase pixels (brush/lasso/rect right panel); add-word from drawn bbox; char-range annotation; per-char GT fix; inter-word gap slider; bulk-mark glyph recipe; paragraph layout-type; line-level GT set; rematch-GT.

**Dimension C:** project list + load; source folder browse/navigate/apply; page nav (prev/next/goto/first/last + hotkeys); save page; load page (discard); **export DocTR** (current page + all-validated — handler is real, route docstring STALE); export style/component filters; reload-OCR (orig + preserve-edits); rematch-GT; refine bboxes (page); OCR config (model select / HF rev / rescan); session restore; page validate/copy via toolbar; 72 global hotkeys; zoom/pan; SSE job progress.

---

## 6. New-only additions (no legacy equivalent)

**A:** RootPage card grid + per-project menu; Drawer (Worklist/Hierarchy); RightPanel detail levels; Rail; HotkeyHelpModal; generic ConfirmDialog; OcrFailed/ImageDrift banners; theme chips; metrics strip; `/__perf-test`.
**B:** CharRangesSection; CharFixerSection (+per-char bbox canvas); multi-tool ErasePixelsSection; gap-picker; BlockDetail layout-type; BulkGlyphMarkDialog (recipe + dry-run); BulkWordActions panel; UnicodePicker; GlyphAnnotationPanel *(built, unmounted)*.
**C:** zoom/pan; hotkey help; worklist quick-search store; breadcrumb nav; SSE job progress + cancel; auto-save cache lane; adjacent-page prefetch; export output-mode flags; GT normalization profile; auto-rotate config.

---

## 7. Prioritized slice plan

Ordered by **(user impact ÷ effort)**. Each slice gets a capability-matrix spec with observable-behavior acceptance + a **mandatory Playwright browser-verification milestone** before close. **No implementation until CT picks slices.**

| # | Slice | Dim | Effort | Why first |
|---|---|---|---|---|
| **S1** | **Wire `WordEditDialog` mutation callbacks** | B | **S** | Highest leverage: one parent (`ProjectPage.tsx`), ~11 props; all child handlers + backend routes already exist. Clears ~9 ❌ rows and restores a whole editing surface. Spec drafted: `docs/specs/2026-06-06-word-edit-dialog-wiring.md`. |
| **S2** | **Matches-pane decision: restore or retire** | A/B | S–M | `display:none` is a fork in the road. *Decision needed from CT:* un-hide WordMatchView (restore inline editing + filter + checkboxes + tag-× + Tab-nav) **or** formally retire the surface and delete the driver-only stubs. Don't fix blind. |
| **S3** | **Rebox on main canvas** | B | S | Wire `onRebox` → `useReboxWord` in ProjectPage's `<PageImageCanvas>`; restores draw-to-rebox. |
| **S4** | **`form-new-line-from-selected-words` backend** | B | S | Implement `/lines/{li}/split-with-selected` (currently returns empty stub payload); toolbar cell already routes to it. |
| **S5** | **Save-project skipped-page warning** | C | S | Surface skipped (`page_id is None`) pages in the toast/result instead of silent debug-log; prevents silent data loss. Update STALE "stub" docstrings. |
| **S6** | **Chrome gaps bundle** | A/C | S | Visible Go-To button; resolved-project-path label; OCR-config trigger + Cancel/snapshot semantics (#405); QuickSearch mount + real `⌘K` focus; source-folder "Use Current". |
| **S7** | **Per-word glyph annotation panel** | B | M | Mount `GlyphAnnotationPanel` in WordDetail (or dialog). **Gated on M11 / Q-A7** (`status:blocked`) — sequence after that resolves. |
| **S8** | **Real rotate / auto-rotate + re-OCR** | C | **L** | M9.1/M9.2 stubs → actual image rotation, PageRecord update, re-OCR. Largest; needs `pdomain-book-tools` image ops + job pipeline. |

**Verification harness for every slice:** `tests/e2e/` (`helpers.py`, `fixtures/`, `_seed_event_store` / `_ingest_ocr_result`; run `CI=true`). Acceptance = the action is **visible + enabled + produces the persisted effect**, asserted in a real browser — not a unit test with spies (a prior sweep shipped green while a backend bug made per-word validate silently not persist).

---

## 8. Stale-inventory corrections (for the record)

- **ToolbarActionGrid is visible**, not a hidden stub (shipped v0.2.0). `new-a-screens.md` is stale here.
- **WordEditDialog callbacks are NOT wired in ProjectPage** — `new-b-content.md` implied they were. They are wired internally in the child rows but the parent injects none.
- **Export handler is real** — route docstrings in `api/export.py` and the save-project route still say "stub/immediately completes"; the handlers are implemented. Docstrings should be corrected.
- **`persist_page_to_file` is retired** (`page_state.py` raises `NotImplementedError`); all persistence goes through the event store.

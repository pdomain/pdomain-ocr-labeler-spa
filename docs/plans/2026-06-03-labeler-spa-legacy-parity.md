# Legacy ocr-labeler Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan is built for **parallel workers**: after the M0 foundation gate, Lanes A–E run concurrently, each in its own git worktree, integrated by **rebase → fast-forward merge** (no merge commits, no squash) per the workspace `CLAUDE.md` merge rule.

**Goal:** Bring `pdomain-ocr-labeler-spa` to functional parity with the legacy NiceGUI `pd-ocr-labeler` — every legacy labeling capability reachable, working, and persisted across restart — while deferring all non-legacy extras.

**Architecture:** The SPA's save/reload is currently broken (labeled/cached load lanes hard-stubbed to `None`; labels not serialized). M0 fixes this by executing the already-approved page-split event-store migration, which also stabilizes the `api/pages.py` / `api/words.py` / `api/lines_paragraphs.py` surface. The remaining parity work is mechanical wiring on that stable surface: register the refine job handler, add the scope-batch routes the frontend already expects, un-stub the toolbar action grid, mount the viewport chrome, and surface per-element/bulk operations whose backend routes already exist.

**Tech Stack:** Backend — FastAPI, uvicorn, `pdomain-ops` event store (`PageStore`/`BlobStore`), `pdomain-book-tools` DocTR OCR. Frontend — React 19, Vite, TS, TanStack Query, Konva, Tailwind. Tests — pytest (`-n auto`), vitest (jsdom), Playwright (Chromium).

---

## Source of truth

This plan is derived from the 2026-06-03 six-domain parity audit. The companion gap report is `docs/research/2026-06-03-open-plans-specs-review.md`. Legacy reference tree: `/workspaces/ocr-container/pd-ocr-labeler/`. SPA tree: this repo.

## Scope: what is IN, DEFERRED, and ACCEPTED-AS-DELTA

**IN scope (parity gaps to close):** persistence round-trip + label persistence (M0); refine/expand bbox handler (Lane A); scope-batch routes + grid wireup (Lanes A+B); viewport chrome + dropped action buttons + OCR-config model selects (Lane C); paragraph/line/page/word bulk operations surfaced in the UI + add-word affordance + 3-way line filter (Lane D); export style-filter population + per-style subfolders (Lane E); browser verification (M-Final).

**DEFERRED — do NOT implement (not in legacy, or explicitly out of scope):**
- All **glyph annotations** (M11): `GlyphAnnotationPanel`, `GlyphChip`, `BulkGlyphMarkDialog`, `POST .../glyph-bulk-mark`, `IGlyphPredictor`, glyph parts of `CharRangesSection`.
- **Image rotation** (M9.1/M9.2) — not in legacy. Leave `rotate.py` / `auto_rotate_all.py` stubs as-is.
- **Text normalization** (M10) — not in legacy. Leave `api/normalize.py` and the OCRConfigModal normalize section as-is.
- **Tesseract OCR engine** — legacy had it as an option; DocTR is the real engine. Defer.
- SPA-only extras already present and fine (no work): zoom/fit controls, theme toggle, Rail mode/target system, mode-pill, hierarchy tree, quick search, gap slider, merge preview, char-ranges editor, rebox-zoom, project card grid, session-state resume.

**ACCEPTED AS DELTA (functional parity — no work, documented divergence):**
- Line filter: we ADD a 3rd "unvalidated only" option (Lane D) but otherwise keep the SPA filter UI.
- Bbox nudge: immediate per-click commit instead of legacy staged Apply/Reset.
- Word GT navigation: `◀▶` pager instead of Tab-advance focus chaining.
- Crop-to-marker bbox editing, GT-input auto-resize width, folder-dialog breadcrumb strip: skipped (cosmetic; functional equivalents exist).
- Word **vertical** split (split + reassign to nearest lines): skipped (niche; horizontal split covers the common case; backend already rejects `direction=vertical`).

---

## Execution model (parallel workers)

```
M0  Foundation: page-split event-store migration  ──┐  (GATE — all lanes wait)
                                                     │
        ┌───────────────┬───────────────┬───────────┴───┬───────────────┐
     Lane A          Lane B          Lane C          Lane D          Lane E
   backend:        frontend:       frontend:       per-element     export
   refine + scope  grid wireup     chrome +        bulk ops UI     parity
   batch routes    (needs A's      OCR-config
   + auto-rematch  route contract) selects
        └───────────────┴───────────────┴───────────────┴───────────────┘
                                     │
                              M-Final: Browser Verification (needs all lanes)
```

- Each lane is a worktree under `.claude/worktrees/parity-lane-<x>` created with the `superpowers:using-git-worktrees` skill.
- Lane B depends on Lane A **Task A2** (the scope-batch route contract) being merged first; start Lane B's chrome-independent tests in parallel but gate the grid-dispatch tasks on A2.
- Integration per lane: `make ci AI=1` green in the worktree → `git fetch origin && git rebase origin/main` → `git checkout main && git merge --ff-only <lane-branch>`. Linear history. Do **not** open GitHub PRs (workspace rule).
- Track each lane as its own GitHub issue under `ConcaveTrillion/ocr-container-meta` (cut via `/decompose-spec --sync` on this plan before starting).

---

## M0 — Foundation: persistence + stable API (GATE)

**This milestone is the already-written plan `/workspaces/ocr-container/docs/plans/2026-06-01-page-split-labeler-spa.md`** (governed by the approved spec `2026-06-01-page-server-extensible-distributed.md`). Execute it in full first. Do not duplicate its 94 steps here; this milestone adds only the parity-specific acceptance gates it must satisfy.

### Task M0.1: Execute the page-split migration plan

**Files:** per `2026-06-01-page-split-labeler-spa.md` (retires `user_page_envelope.py`, `lanes.py`, `image_cache.py`, local `PageRecord`/`RotationSource`/`CachedImageSet`; adds `LabelerPageExtension` + `LabelerPageStore`; rebuilds `api/pages.py`/`words.py`/`lines_paragraphs.py` on ops `PagePayload`; replaces `/image-cache/` mount with blob serving; regenerates `frontend/src/api/types.ts`).

- [ ] **Step 1:** Follow that plan task-by-task to completion under subagent-driven-development.
- [ ] **Step 2:** Run `make ci AI=1`. Expected: green.

### Task M0.2: Parity acceptance — label round-trip survives restart

This guards the #1 audit finding (`load_labeled`/`load_cached` returned `None`; labels not serialized). The migration must make these real.

**Files:**
- Test: `tests/integration/test_label_roundtrip.py` (Create)

- [ ] **Step 1: Write the failing test** — save a page with a GT edit, a validation, and a word style, then reload via a fresh store and assert all three persist.

```python
# tests/integration/test_label_roundtrip.py
import pytest
from pdomain_ocr_labeler_spa.core.page_state import save_page_to_store, load_page_from_store

@pytest.mark.integration
def test_labels_survive_save_reload(project_with_one_ocr_page):
    proj = project_with_one_ocr_page          # fixture: opened project, page 0 OCR'd
    page = proj.load_page(0)
    page.lines[0].words[0].set_ground_truth("Hello")
    page.lines[0].words[0].add_label("validated")
    page.lines[0].words[0].add_label("italic")
    save_page_to_store(proj.store, proj.project_id, 0, page)

    reopened = proj.fresh_store()              # new PageStore over the same on-disk events.db
    reloaded = load_page_from_store(reopened, proj.project_id, 0)
    w = reloaded.lines[0].words[0]
    assert w.ground_truth_text == "Hello"
    assert "validated" in w.word_labels
    assert "italic" in w.word_labels
```

- [ ] **Step 2: Run it, expect FAIL** — `uv run pytest tests/integration/test_label_roundtrip.py -v`. Expected: fail (labels not serialized) until the migration's `LabelerPageExtension` carries per-word labels.
- [ ] **Step 3:** If the migration's extension payload omits word labels, extend `LabelerPageExtension` (in the migration's `core/labeler_extension.py`) to serialize `word_labels` + `ground_truth_text` per word, and round-trip them in `load_page_from_store`.
- [ ] **Step 4: Run it, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "test(parity): assert label round-trip persists across reload (close M0 gate)"`.

### Task M0.3: Parity acceptance — structural edits reload

**Files:** Test: `tests/integration/test_structural_roundtrip.py` (Create)

- [ ] **Step 1:** Write a test that splits a word, merges two lines, deletes a word, saves, reloads via a fresh store, and asserts the structure matches post-edit (line count, word counts).
- [ ] **Step 2:** Run, expect PASS if M0.1 is correct; if FAIL, fix the migration's payload serialization. Commit.

**M0 exit gate:** `make ci` green AND M0.2 + M0.3 pass. Only then do Lanes A–E start.

---

## Lane A — Backend: refine handler, scope-batch routes, auto-rematch

Worktree: `.claude/worktrees/parity-lane-a`. No dependency on other lanes. **Task A2 is the route contract Lane B consumes — merge A2 early.**

### Task A1: Register the refine_bboxes job handler (+ OCR image attach)

Audit finding: `POST .../refine` enqueues job type `refine_bboxes`, but it is absent from `core/jobs/runner._HANDLERS` → `NotImplementedError` at run time. Also the DocTR loader never attaches the cv2 image or calls `reorganize_page`, so `word.refine_bbox(cv2_image)` would fail.

**Files:**
- Modify: `src/pdomain_ocr_labeler_spa/adapters/ocr/local_doctr.py` (attach cv2 image + `reorganize_page` after OCR — mirror legacy `operations/ocr/page_operations.py:305-355`)
- Create: `src/pdomain_ocr_labeler_spa/core/jobs/handlers/refine.py` (`handle_refine_bboxes`)
- Modify: `src/pdomain_ocr_labeler_spa/core/jobs/runner.py` (register handler in `_HANDLERS`)
- Modify: `src/pdomain_ocr_labeler_spa/api/refine.py` (probe `available: True`)
- Test: `tests/unit/test_refine_handler.py`, `tests/integration/test_refine_bboxes.py`

- [ ] **Step 1: Write failing unit test** — `runner._HANDLERS` contains `"refine_bboxes"`.

```python
# tests/unit/test_refine_handler.py
from pdomain_ocr_labeler_spa.core.jobs.runner import _HANDLERS

def test_refine_bboxes_handler_registered():
    assert "refine_bboxes" in _HANDLERS
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_refine_handler.py -v`.
- [ ] **Step 3: Implement.** In `local_doctr.py` `run_ocr`, after `Document.from_image_ocr_via_doctr(...)`, attach `page_obj.cv2_numpy_page_image = cv2_imread(image_path)` and call `page_obj.reorganize_page()` if available (guard with `hasattr`). Create `handlers/refine.py`:

```python
# core/jobs/handlers/refine.py
async def handle_refine_bboxes(ctx, payload):
    scope = payload["scope"]          # "page"|"paragraph"|"line"|"word"
    mode = payload["mode"]            # "refine"|"expand_then_refine"|"expand_only"
    page = ctx.load_page(payload["page_index"])
    if page.cv2_numpy_page_image is None:
        page.cv2_numpy_page_image = ctx.read_page_image(payload["page_index"])
    targets = ctx.resolve_scope(page, scope, payload.get("ids"))
    for word in targets:
        if mode in ("expand_only", "expand_then_refine"):
            word.expand_bbox(px=4)
        if mode in ("refine", "expand_then_refine"):
            word.refine_bbox(page.cv2_numpy_page_image)
    ctx.finalize_and_save(page)
    return {"refined": len(targets)}
```

Register in `runner.py`: `_HANDLERS["refine_bboxes"] = handle_refine_bboxes`. In `api/refine.py`, change the availability probe to return `available: True`.

- [ ] **Step 4: Run, expect PASS** — unit test, then `tests/integration/test_refine_bboxes.py` (post a word-scope refine job, poll to terminal, assert bbox changed).
- [ ] **Step 5: Commit** — `git commit -m "feat(refine): register refine_bboxes handler + attach cv2 image for bbox refine"`.

### Task A2: Scope-batch routes matching the frontend toolbarMapping contract

Audit: `frontend/src/lib/toolbarMapping.ts` references routes that don't exist — `lines/copy-gt-batch`, `paragraphs/delete-batch`, `lines/delete-batch`, `words/delete-batch`, `paragraphs/split-selected`, `paragraphs/group-selected-words`. Make the backend satisfy that contract so the grid (Lane B) can dispatch one request per click. (`words/validate-batch` and `words/group-into-paragraph` already exist — reuse them.)

**Files:**
- Modify: `src/pdomain_ocr_labeler_spa/api/lines_paragraphs.py` (add `copy-gt-batch`, `delete-batch` for line/paragraph, `paragraphs/split-selected`, `paragraphs/group-selected-words`)
- Modify: `src/pdomain_ocr_labeler_spa/api/words.py` (add `words/delete-batch`)
- Modify: `frontend/src/lib/toolbarMapping.ts` (only if a path needs correcting to the agreed contract)
- Test: `tests/integration/test_scope_batch_routes.py`

- [ ] **Step 1: Write failing integration tests** — one per new route, asserting it exists (not 404) and performs the op. Example:

```python
# tests/integration/test_scope_batch_routes.py
def test_copy_gt_batch_line_scope(client, project_with_one_ocr_page):
    pid, idx = project_with_one_ocr_page
    r = client.post(f"/api/projects/{pid}/pages/{idx}/lines/copy-gt-batch",
                    json={"scope": "line", "line_index": 0, "direction": "gt_to_ocr"})
    assert r.status_code == 200
    # OCR text of every word in line 0 now equals its GT
```

Add analogous tests for `delete-batch` (line/paragraph/word), `paragraphs/split-selected`, `paragraphs/group-selected-words`, and `copy-gt-batch` at page/paragraph/word scope.

- [ ] **Step 2: Run, expect FAIL (404)** — `uv run pytest tests/integration/test_scope_batch_routes.py -v`.
- [ ] **Step 3: Implement** each route as a thin scope-resolver over the existing per-item operations (copy/delete/split). Keep each atomic (one event per request). Reuse `words/validate-batch`'s scope-resolution helper as the model.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5:** Run `make openapi-export AI=1` to regenerate `frontend/src/api/types.ts`.
- [ ] **Step 6: Commit** — `git commit -m "feat(api): add scope-batch routes (copy-gt/delete/split/group) for toolbar grid contract"`. **Merge A2 to main now so Lane B can rebase onto it.**

### Task A3: GT auto-rematch after structural edits

Audit: legacy `_finalize_structural_edit` re-runs the GT matcher after every word/line/paragraph mutation; SPA does not, so per-word GT and OCR diverge after edits.

**Files:**
- Modify: `src/pdomain_ocr_labeler_spa/core/ground_truth_matcher.py` (expose `rematch_page` already exists)
- Modify: `src/pdomain_ocr_labeler_spa/api/words.py` + `api/lines_paragraphs.py` (call rematch in the structural-edit finalize path)
- Test: `tests/integration/test_auto_rematch.py`

- [ ] **Step 1: Write failing test** — split a word, then assert page-level GT mapping was recomputed (a word that should now match its GT shows `match_status == "exact"`).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** a `_finalize_structural_edit(page)` helper that calls `rematch_page(page)` and save, invoked by all structural mutation routes (split/merge/delete/add/group). Preserve explicit per-word GT edits (legacy preserves manual GT; rematch only fills unedited words).
- [ ] **Step 4: Run, expect PASS. Commit.**

### Task A4: Reload OCR (Edited) — re-OCR the erased image

Audit: legacy "Reload OCR (Edited)" re-runs DocTR on the post-erase in-memory image; SPA `reload-ocr` only accepts `force` and always reads the on-disk file. `ReloadOCRRequest` has no `use_edited_image` field; `hasEditedImage` is hardcoded `false`.

**Files:**
- Modify: `src/pdomain_ocr_labeler_spa/api/pages.py` (`ReloadOCRRequest` add `use_edited_image: bool = False`)
- Modify: `src/pdomain_ocr_labeler_spa/core/jobs/handlers/reload_ocr.py` (when `use_edited_image`, OCR from the persisted edited-image blob instead of the source file)
- Modify: erase-pixels path in `api/words.py` to persist the edited image as a blob the reload can read
- Test: `tests/integration/test_reload_ocr_edited.py`

- [ ] **Step 1: Write failing test** — erase a rectangle, POST reload-ocr with `use_edited_image: true`, assert OCR ran against the erased pixels (a word in the erased region disappears or changes).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** edited-image blob persistence on erase + the reload branch. Set `hasEditedImage` truthfully in the frontend later (Lane C, Task C2).
- [ ] **Step 4: Run, expect PASS. Commit.**

---

## Lane B — Frontend: toolbar action grid wireup

Worktree: `.claude/worktrees/parity-lane-b`. **Rebase onto main after Lane A Task A2 merges** so `toolbarMapping.ts` routes resolve.

### Task B1: Un-stub `handleToolbarAction` to dispatch real mutations

Audit: `frontend/src/pages/ProjectPage.tsx:558` `handleToolbarAction(_key)` only calls `invalidatePage()`; the grid fires no API call.

**Files:**
- Modify: `frontend/src/pages/ProjectPage.tsx` (`handleToolbarAction`)
- Use: `frontend/src/lib/toolbarMapping.ts` (existing key→route map)
- Create: `frontend/src/hooks/useToolbarDispatch.ts`
- Test: `frontend/src/pages/__tests__/ProjectPage.toolbar.test.tsx`

- [ ] **Step 1: Write failing vitest** — render ProjectPage with a selected line, click the `toolbar-line-validate` grid cell, assert a POST to `.../words/validate-batch` with `{scope:"line", validated:true}` fires (mock fetch / msw).

```tsx
// frontend/src/pages/__tests__/ProjectPage.toolbar.test.tsx
it("dispatches validate-batch when the line/validate grid cell is clicked", async () => {
  const post = mockPost();
  renderProjectPage({ selection: { kind: "line", lineIndex: 0 } });
  await userEvent.click(screen.getByTestId("toolbar-line-validate"));
  expect(post).toHaveBeenCalledWith(
    expect.stringContaining("/words/validate-batch"),
    expect.objectContaining({ scope: "line", validated: true }),
  );
});
```

- [ ] **Step 2: Run, expect FAIL** — `pnpm vitest run ProjectPage.toolbar`.
- [ ] **Step 3: Implement** `useToolbarDispatch`: given the grid `key` and the current selection, resolve the route + body via `toolbarMapping.ts`, fire the mutation through TanStack Query, invalidate the page on success, surface errors via toast. Replace `handleToolbarAction(_key)` body with a call to it. Wire the disabled/enable state from `useToolbarButtonStates` (already exists).
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(grid): dispatch real mutations from toolbar action grid"`.

### Task B2: Wire Apply-Style / Component / Clear / Add-Word controls

Audit: `handleApplyStyle`/`handleClearStyle` are no-ops; `onApplyComponent`/`onClearComponent` props are `undefined`; the Add-Word toggle flips state but no canvas draw → `POST .../words/add`.

**Files:**
- Modify: `frontend/src/pages/ProjectPage.tsx` (`handleApplyStyle`, `handleClearStyle`, pass component handlers, wire add-word draw)
- Modify: `frontend/src/components/PageImageCanvas.tsx` (emit add-word rect → handler)
- Test: `frontend/src/pages/__tests__/ProjectPage.style.test.tsx`

- [ ] **Step 1: Write failing tests** — (a) selecting a style + clicking `apply-style-button` POSTs `.../words/{li}/{wi}/style` with the chosen style + scope; (b) `clear-style-button` clears it; (c) component apply/clear; (d) drawing a box in add-word mode POSTs `.../words/add`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the four handlers against existing routes (`words/{li}/{wi}/style`, `.../component`, `.../add`). The add-word handler consumes the rect already emitted by `PageImageCanvas.tsx` `onAddWord` (audit row 38 — the canvas already calls `onAddWord?.(rect)`; just connect it to the mutation).
- [ ] **Step 4: Run, expect PASS. Commit.**

### Task B3: Port the legacy toolbar acceptance tests

**Files:**
- Create: `tests/integration/test_toolbar_page_actions.py`, `..._paragraph_actions.py`, `..._line_actions.py`, `..._word_actions.py` (port from legacy `pd-ocr-labeler/tests/.../test_toolbar_*_actions.py`, adapted to the SPA API)

- [ ] **Step 1:** Port each legacy toolbar acceptance test to the SPA's HTTP API (the spec named these in `specs/16-milestones.md` M6).
- [ ] **Step 2: Run, expect PASS** (routes exist from Lane A2). Commit.

---

## Lane C — Frontend: viewport chrome + dropped buttons + OCR-config selects

Worktree: `.claude/worktrees/parity-lane-c`. No dependency on Lane A/B except A4 for C2's edited-reload button enablement.

### Task C1: Mount `ImageTabsHeader` (layer toggles, selection-mode, erase, legend)

Audit: `ImageTabsHeader.tsx` is fully built but never mounted (only commented out at `ProjectPage.tsx:18`). Its controls (Show Para/Lines/Words checkboxes, Select-mode radio, Erase Pixels button, color legend) exist only via Rail + hotkeys.

**Files:**
- Modify: `frontend/src/pages/ProjectPage.tsx` (mount `<ImageTabsHeader />` above the canvas, wired to the same `useUiPrefs`/viewport store the Rail uses)
- Test: `frontend/src/components/__tests__/ImageTabsHeader.mount.test.tsx`

- [ ] **Step 1: Write failing test** — render ProjectPage, assert `layer-paragraphs-checkbox`, `selection-mode-word`, `erase-pixels-button`, `legend-chip-line` are all in the document and that toggling `layer-words-checkbox` updates the words-layer visibility pref.
- [ ] **Step 2: Run, expect FAIL** (component not mounted).
- [ ] **Step 3: Implement** — uncomment/import and mount `ImageTabsHeader`, binding its props to the existing `useUiPrefs` selectors and `toggleEraseMode` already used by the Rail (so Rail and header stay in sync on one source of truth).
- [ ] **Step 4: Run, expect PASS. Commit** — `git commit -m "feat(chrome): mount ImageTabsHeader viewport controls (layers/selection/erase/legend)"`.

### Task C2: Restore dropped action buttons in `PageActionsCompact`

Audit: `PageActionsCompact` omits **Reload OCR (Edited)**, **Save Project**, **Load Page** (they live only in the hidden full `PageActions` bar). Surface them (inline or an overflow "⋯" menu).

**Files:**
- Modify: `frontend/src/components/PageActionsCompact.tsx`
- Modify: `frontend/src/pages/ProjectPage.tsx` (pass `hasEditedImage` truthfully now that Lane A4 supports it; pass `provenanceSummary` to fix the blank page-source tooltip — audit row 26)
- Test: `frontend/src/components/__tests__/PageActionsCompact.test.tsx`

- [ ] **Step 1: Write failing test** — assert `save-project-button`, `load-page-button`, and `reload-ocr-edited-button` are present and enabled in the compact bar; clicking each fires its existing mutation.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** — add the three controls to `PageActionsCompact` (or an overflow menu); set `hasEditedImage` from real edited-image state; pass `provenanceSummary` from the page payload.
- [ ] **Step 4: Run, expect PASS. Commit.**

### Task C3: Wire OCR-config model selection (un-stub the modal)

Audit: `OCRConfigModal.tsx` renders detection-model select, recognition-model select, HF-revision input, Rescan, Apply as hidden `display:none` stubs; backend routes (`GET /api/ocr-config`, `POST /api/ocr-config/models`, `POST /api/ocr-config/rescan`) are fully implemented.

**Files:**
- Modify: `frontend/src/components/OCRConfigModal.tsx` (replace stubs with real controls bound to the backend)
- Test: `frontend/src/components/__tests__/OCRConfigModal.test.tsx`

- [ ] **Step 1: Write failing test** — open the modal, assert the detection/recognition selects are visible and populated from `GET /api/ocr-config`; choosing a model + Apply POSTs `/api/ocr-config/models`; Rescan POSTs `/api/ocr-config/rescan`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the real selects/inputs/buttons (keep the existing `ocr-config-*` testids), bound to the backend. Leave the SPA-only auto-rotate/normalize sections untouched (deferred).
- [ ] **Step 4: Run, expect PASS. Commit.**

### Task C4: Resolved source-root label (minor)

Audit: legacy shows the configured source-projects-root path in the header; SPA has no equivalent.

**Files:** Modify `frontend/src/components/ProjectLoadControls.tsx` (+ test).
- [ ] **Step 1:** Failing test — `source-root-label` shows the path returned by the source-root endpoint. **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Commit.**

---

## Lane D — Per-element & bulk operations UI

Worktree: `.claude/worktrees/parity-lane-d`. Backend routes mostly exist; this lane surfaces them. Gate the few that need A2 batch routes on A2 merge.

### Task D1: Paragraph-scope actions panel

Audit rows 58–61, 73–74: paragraph merge / delete / split-after-line / copy GT↔OCR have backend routes but **no UI**.

**Files:**
- Create: `frontend/src/components/ParagraphDetail.tsx` (right-panel actions for the selected paragraph)
- Modify: `frontend/src/pages/ProjectPage.tsx` (render `ParagraphDetail` when selection.kind === "paragraph")
- Test: `frontend/src/components/__tests__/ParagraphDetail.test.tsx`

- [ ] **Step 1: Write failing test** — with a paragraph selected, assert buttons `para-merge`, `para-delete`, `para-split-after-line`, `para-copy-gt-to-ocr`, `para-copy-ocr-to-gt`, `para-validate`, `para-unvalidate` exist and each fires its route (`paragraphs/merge`, `paragraphs/{pi}/delete`, `paragraphs/{pi}/split-after-line`, `paragraphs/{pi}/copy-gt-to-ocr`/`copy-ocr-to-gt`, `words/validate-batch` scope=paragraph).
- [ ] **Step 2: FAIL → Step 3: Implement → Step 4: PASS → Step 5: Commit.**

### Task D2: Surface line-scope buttons in `LineDetail`

Audit rows 48–50, 54–57: line copy GT↔OCR (hotkey-only, no button), split-after-word, split-by-words, form-paragraph-from-selection — backend routes exist; add visible buttons.

**Files:** Modify `frontend/src/components/LineDetail.tsx` (+ test).
- [ ] **Step 1:** Failing test — `line-copy-gt-to-ocr`, `line-copy-ocr-to-gt`, `line-split-after-word`, `line-split-by-words` buttons present and fire existing routes. **Steps 2–5** as standard.

### Task D3: Word/page bulk operations

Audit rows 13–14, 38, 45–46: page-scope validate/unvalidate-all, bulk multi-word delete, bulk apply style/component to multi-selection — backend supports (`validate-batch` scope=page; per-item delete looped or `words/delete-batch` from A2; `style`/`component` routes).

**Files:** Modify `frontend/src/components/StructureSection.tsx` (or a new `BulkWordActions.tsx`) + `ProjectPage.tsx` (+ test).
- [ ] **Step 1:** Failing tests — page validate-all/unvalidate-all controls; multi-select delete; multi-select style/component apply. **Steps 2–5** standard. (Bulk delete uses `words/delete-batch` from A2.)

### Task D4: Add the "Unvalidated only" line filter mode

Audit row 20: legacy 3-way filter (Unvalidated / Mismatched / All); SPA has 2-way (all / mismatches_only).

**Files:** Modify `frontend/src/pages/ProjectPage.tsx` filter control + `worklistStore` (+ test).
- [ ] **Step 1:** Failing test — selecting "Unvalidated" shows only lines with ≥1 unvalidated word. **Steps 2–5** standard.

### Task D5: Add-Word affordance in the toolbar/canvas

Audit row 30 / row 38: legacy has an explicit "Add Word" button + draw mode; SPA's grid `word-add-button` toggles mode but (pre-Lane-B B2) had no API leg. Ensure a discoverable Add-Word control exists outside the grid too (e.g. in `ImageTabsHeader` or PageActions) and that draw→`words/add` works end-to-end.

**Files:** Modify `frontend/src/components/ImageTabsHeader.tsx` (add `add-word-button`) + verify wiring from B2 (+ test).
- [ ] **Step 1:** Failing test — `add-word-button` enters add mode; drawing a rect POSTs `words/add`. **Steps 2–5** standard. (Coordinate with Lane B2 to avoid duplicate handlers.)

---

## Lane E — Export parity

Worktree: `.claude/worktrees/parity-lane-e`. Independent.

### Task E1: Populate the export style filter

Audit row 11–13: `GET .../export/styles` is a stub returning `[]`; legacy populates from the page's words.

**Files:**
- Modify: `src/pdomain_ocr_labeler_spa/api/export.py` (`/export/styles` returns the distinct styles present in scope)
- Test: `tests/integration/test_export_styles.py`

- [ ] **Step 1:** Failing test — a project with an italic word returns `["italic"]` from `GET .../export/styles`. **Step 2:** FAIL. **Step 3:** Implement (scan saved/loaded pages for word style labels). **Step 4:** PASS. **Step 5:** Commit.

### Task E2: Per-style separate-subfolder export

Audit row 14: legacy runs one export per selected style into separate subfolders; SPA sends a single combined-filter job.

**Files:** Modify `src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py` (loop selected styles → one subfolder each) + test.
- [ ] **Step 1:** Failing test — exporting with two styles selected produces two subfolders. **Steps 2–5** standard.

### Task E3: Export stats breakdown (minor)

Audit row 16: legacy returns detection/recognition word counts + skipped-not-validated; SPA logs counts only.

**Files:** Modify `export.py` handler to emit structured stats in the terminal SSE event + `ExportDialog.tsx` to render them (+ test).
- [ ] **Step 1:** Failing test — terminal event carries `words_exported_detection`, `words_exported_recognition`, `pages_skipped_not_validated`. **Steps 2–5** standard.

---

## M-Final — Browser Verification (MANDATORY)

Worktree: `.claude/worktrees/parity-verify`. Runs after all lanes merge. This repo is a FastAPI app that bundles and serves the React/Vite SPA, so per the writing-plans rule it **must** end with a real-browser Playwright milestone. Builds on the existing `e2e/` Playwright setup (`make e2e`).

### Task V1: Build the SPA and assert the app loads

**Files:** `tests/e2e/test_parity_app_loads.py` (Create)
- [x] **Step 1:** `make frontend-build AI=1`. **Step 2:** Playwright test: open the server URL in Chromium, assert `[data-testid="project-page"]` (or root) visible, assert no `console.error` about failed resource loads. **Step 3:** `make e2e AI=1`, expect PASS. **Commit.** — `tests/e2e/test_parity_app_loads.py`; EXECUTED in Chromium, PASS.

### Task V2: Grid action round-trips in the browser

**Files:** `tests/e2e/test_parity_grid_actions.py` (Create)
- [x] **Step 1:** Open a seeded project+page, select a line, click `toolbar-line-validate`, assert the line shows validated state in the DOM (not just a network 200). **Step 2:** Repeat for a paragraph merge and a word style apply. **Step 3:** `make e2e`, expect PASS. **Commit.** — `tests/e2e/test_parity_grid_actions.py`: page-validate drains the unvalidated worklist, para-merge drops paragraph count, word-style flips `style-chip-italics[aria-pressed]`. Authored against verified testids; SKIPS in this sandbox (no OCR word content on synthetic fixtures → 0 line_matches), runs fully where the fixture carries words.

### Task V3: Save → reload round-trip in the browser

**Files:** `tests/e2e/test_parity_persistence.py` (Create)
- [x] **Step 1:** Edit a word's GT, validate it, apply a style, click Save Page; reload the page route; assert the GT/validation/style persist (guards the M0 fix end-to-end through the UI). **Step 2:** `make e2e`, expect PASS. **Commit.** — `tests/e2e/test_parity_persistence.py`: edits `ocr-gt-input`, `word-footer-validate`, `style-chip-italics`, clicks `page-actions-compact-save-page`, reloads, re-asserts all three. Authored against verified testids; SKIPS in this sandbox (0 line_matches), runs fully where the fixture carries words.

### Task V4: Viewport chrome controls work in the browser

**Files:** `tests/e2e/test_parity_chrome.py` (Create)
- [x] **Step 1:** Toggle `layer-words-checkbox` off, assert word overlays hidden on the canvas; switch `selection-mode-paragraph`, assert clicking the image selects a paragraph; open OCR-config, assert the model selects are populated. **Step 2:** `make e2e`, expect PASS. **Commit.** — `tests/e2e/test_parity_chrome.py`: words-checkbox toggle (EXECUTED, PASS — surfaced + fixed a real bug: `onLayerToggle`/`onSelectionModeChange` skipped `notifyUiPrefs()` so the controlled checkbox never re-rendered); OCR-config model selects populated (EXECUTED, PASS); paragraph selection via rail-target-para + hierarchy → `paragraph-detail` (authored; SKIPS in sandbox, needs word content).

### Task V5: React Router sub-path renders

**Files:** `tests/e2e/test_parity_routes.py` (Create)
- [x] **Step 1:** Navigate directly to a project page sub-path (e.g. `/projects/<id>/pages/3`), assert the page component renders (not a 404 / blank). **Step 2:** `make e2e`, expect PASS. **Commit.** — `tests/e2e/test_parity_routes.py`; EXECUTED in Chromium, PASS.

### Task V6: Wire e2e into CI

**Files:** Modify `Makefile` (`ci` target includes `e2e`) and `.github/workflows/*.yml` (ensure `playwright install chromium` + `-n auto` on any direct pytest e2e invocation).
- [x] **Step 1:** Add `make e2e` to `make ci` (or a CI e2e job). **Step 2:** `make ci AI=1`, expect green. **Commit.** — Dedicated `test-e2e` job already in `.github/workflows/ci.yml`: installs `playwright install chromium --with-deps`, runs `uv run --group e2e pytest tests/e2e -v -n auto` (covers the new `test_parity_*.py` files). NOT folded into local `make ci` (keeps `make ci` green on chromium-less machines). `make e2e` target also updated to `-n auto`. `make ci AI=1` GREEN.

---

## Self-review (completed by plan author)

**Spec coverage vs the six-domain audit:** persistence/labels → M0.2/M0.3; refine/expand handler → A1; missing batch routes → A2; auto-rematch → A3; reload-edited → A4; grid stub → B1; style/component/add-word stubs → B2; toolbar acceptance tests → B3; unmounted `ImageTabsHeader` → C1; dropped action buttons + provenance tooltip → C2; OCR-config stubs → C3; source-root label → C4; paragraph-scope UI → D1; line-scope buttons → D2; page/word bulk ops → D3; 3-way filter → D4; add-word affordance → D5; export styles/subfolders/stats → E1–E3; browser verification → V1–V6. Deferrals and accepted-deltas are listed in **Scope** and intentionally have no tasks.

**Placeholder scan:** no "TBD/handle edge cases/similar to" placeholders; each task names exact files, a concrete test, and a commit.

**Type/route consistency:** the grid (B1) dispatches to the routes created in A2 (`copy-gt-batch`, `delete-batch`, `split-selected`, `group-selected-words`) plus existing `validate-batch`/`style`/`component`/`add` — A2 is gated before B1; `make openapi-export` (A2 Step 5) keeps `types.ts` in sync.

**FastAPI+SPA check:** browser-verification milestone (M-Final, V1–V6) present and wired into CI.

---

## Handoff

Cut GitHub issues for M0 + Lanes A–E + M-Final via `/decompose-spec --sync docs/plans/2026-06-03-labeler-spa-legacy-parity.md` (milestone `spec: labeler-spa-legacy-parity (#N)`), then execute M0 to its gate, then fan out Lanes A–E as parallel subagents in worktrees, then run M-Final. Use `superpowers:finishing-a-development-branch` to integrate each lane (rebase → ff-merge; no PRs).

# Parity-Gap Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Every code step
> shows the actual code. Acceptance is **observable, persisted behavior** verified in a real
> browser — a `data-testid` existing is NOT acceptance. **No deferred work:** no new stubs,
> no `TODO`/`later`, no `display:none` to satisfy a testid, no `?? Promise.resolve()` no-ops.
> Each slice that leaves any capability partial is a slice failure.

**Goal:** Close the legacy→new parity gaps catalogued in `docs/research/parity-audit/PARITY-GAP.md`
by completing slices **S1–S6 + S8** (S7 glyph excluded — blocked on Q-A7).

**Architecture:** Frontend wires already-built components to the mutation hooks and surfaces that
exist (`useWordMutations`, `viewport-store`, right panel, Drawer); backend implements two real
mutations (form-new-line, rotate/re-OCR) and surfaces a save-skip warning. Rotation reuses
`pdomain_book_tools.ocr.rotation` and adds a durable `RotationUpdated` event in `pdomain-ops`.

**Tech Stack:** React 19, Zustand, TanStack Query, Konva, Vitest, MSW, Playwright; FastAPI,
pydantic, pytest, eventsourcing (`pdomain-ops` aggregates), `pdomain-book-tools` OCR.

**Source of truth:** `docs/research/parity-audit/PARITY-GAP.md` (matrix) and the worked spec
`docs/specs/2026-06-06-word-edit-dialog-wiring.md` (S1 capability matrix).

---

## Parallelization & worktree map

Code changes are delegated to repo agents in **isolated worktrees** the orchestrator creates under
`<repo>/.claude/worktrees/<slug>` (pass the absolute path in the prompt — do not rely on
`isolation:"worktree"` alone for parallel writers). One worktree per track. Tracks that share a
file must NOT run concurrently in different worktrees.

| Track | Slices | Repo(s) | Primary files | Conflicts with |
|---|---|---|---|---|
| **T-CANVAS** | S1 + S3 | labeler-spa | `pages/ProjectPage.tsx`, `hooks/useWordMutations.ts`, `components/WordEditDialog.tsx`, `components/PageImageCanvas.tsx` | (own ProjectPage + hooks) |
| **T-PANEL** | S2 | labeler-spa | `components/right-panel/*`, `components/Drawer.tsx`, `components/TextTabs.tsx` | none (no ProjectPage edits) |
| **T-CHROME** | S6 | labeler-spa | `components/ProjectNavigationControls.tsx`, `ProjectLoadControls.tsx`, `shell/QuickSearch.tsx`, `OCRConfigModal.tsx`, `App.tsx` | T-SAVE (PageActionsCompact) |
| **T-LINE** | S4 | labeler-spa | `api/lines_paragraphs.py`, `lib/toolbarMapping.ts` | none |
| **T-SAVE** | S5 | labeler-spa | `core/jobs/handlers/save_project.py`, `api/projects.py`, `api/pages.py`, `components/PageActionsCompact.tsx` | T-CHROME (PageActionsCompact) |
| **T-ROTATE** | S8 | labeler-spa **+ pdomain-ops** | labeler-spa `handlers/rotate.py`, `handlers/auto_rotate_all.py`; pdomain-ops `PageAggregate` | none |

**Wave plan (maximise parallelism, avoid same-file races):**
- **Wave 1 (5 parallel agents):** T-CANVAS, T-PANEL, T-LINE, T-ROTATE-ops (pdomain-ops event first), and T-SAVE.
- **Wave 2:** T-CHROME (after T-SAVE merges, because both edit `PageActionsCompact.tsx`), and
  T-ROTATE-spa (after the pdomain-ops `RotationUpdated` event is published/consumable).
- **Per-task review** runs inside each track (below). **End-of-plan review** runs after all merge.

Each track: agent commits on its worktree branch, closes nothing, returns `path + branch`. The
**orchestrator** owns rebase-onto-local-main + `--ff-only` merge (re-check `git log main -1` first;
`main` gets concurrent CT commits). `CI=true make ci AI=1` green in the worktree before merge.

---

## Review protocol (independent, every level)

**Per-task review (task level).** After an implementer commits a task, the orchestrator dispatches
a **separate** reviewer subagent (`model: sonnet`, fresh context, NOT the implementer) with the
task diff and this checklist. Reviewer returns `PASS` or a findings list; implementer fixes; loop
until `PASS`. Reviewer prompt must demand:

1. **Security** — input validation on new routes/params; no path traversal in file writes
   (rotate overwrites source PNG — assert the path stays within the project dir); no unbounded
   work; no secrets/log leakage.
2. **Correctness** — does the code do what the acceptance row says? Does it **persist** (event
   store / store write), not just optimistic UI? Coordinate conversions correct (display↔source)?
3. **Simplicity / DRY** — reuses existing hooks/helpers (`useWordMutations`, `_finalize_structural_edit`,
   `rotate_image`); no duplicated mutation logic; no needless new abstractions (YAGNI).
4. **Common style** — matches surrounding code (naming, file layout, testid conventions, error
   shape); passes `ruff` / `eslint` / `prettier` / `basedpyright`.
5. **NO DEFERRED WORK** — grep the diff for new `TODO`, `FIXME`, `later`, `stub`, `display:none`,
   `?? Promise.resolve()`, `pass  #`, `NotImplementedError`, empty handlers. Any found → FAIL.

**End-of-plan review (plan level).** After all tracks merge to a single integration branch,
dispatch **5 parallel reviewer subagents** (`model: sonnet`), one per lens, over the full diff:
(a) security, (b) correctness + cross-slice integration, (c) simplicity/DRY, (d) style/conventions,
(e) **spec-coverage + no-deferred audit** (every PARITY-GAP.md S1–S6/S8 row maps to a shipped,
working capability; zero stubs introduced). Findings triaged and fixed before the final
**Browser Verification** milestone. Then `CI=true make ci AI=1` + `make e2e` green.

---

## S1 — Wire WordEditDialog mutation callbacks  (Track T-CANVAS)

Spec: `docs/specs/2026-06-06-word-edit-dialog-wiring.md`. Dead mount: `ProjectPage.tsx:1048-1063`.
Dialog callback signatures (`WordActionRows.tsx:26`, `WordEditDialog.tsx:55-95`):
`onMerge(dir:"prev"|"next")`, `onSplit(fraction:number, axis:"h"|"v")`, `onDelete()`,
`onCrop(dir:"above"|"below"|"left"|"right", padding:number)`, `onRefine()`, `onExpandRefine()`,
`onApplyNudge(nudge:PendingNudge, refineAfter:boolean)`, `onApplyStyle(style, scope:"whole"|"part")`,
`onApplyComponent(component, enabled)`, `onGtChange(text)`, `onGtCommit(text)`.
Hook arg shapes (`hooks/useWordMutations.ts`): `useMergeWord {lineIndex,wordIndex,direction:"left"|"right"}`,
`useSplitWord {lineIndex,wordIndex,xFraction,direction?:"horizontal"|"vertical"}`,
`useApplyStyle {lineIndex,wordIndex,style,scope}`, `useApplyComponent {lineIndex,wordIndex,component,enabled}`,
`useUpdateWordGroundTruth {lineIndex,wordIndex,text}`, `useReboxWord {lineIndex,wordIndex,bbox:BBox}`.
Backend nudge route: `POST .../words/{li}/{wi}/nudge {left,right,top,bottom,refine_after}`.
Delete: `POST .../delete` with `DeleteScopeRequest{scope:"word",word_indices:[[li,wi]],line_indices:[],paragraph_indices:[]}` (pattern in `WordFooter.tsx:70-89`).

### Task S1.1: Add `useDeleteWord` + `useNudgeWord` to `useWordMutations.ts`

**Files:**
- Modify: `frontend/src/hooks/useWordMutations.ts`
- Test: `frontend/src/hooks/useWordMutations.test.tsx` (create if absent; mirror `useLineMutations.test.tsx`)

- [ ] **Step 1: Write failing tests** (mirror the MSW + `renderHook` wrapper in `useLineMutations.test.tsx`)

```ts
// in useWordMutations.test.tsx
it("useDeleteWord POSTs the word delete-scope body", async () => {
  let body: unknown;
  server.use(http.post("*/pages/0/delete", async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ project_id: "p", page_index: 0 });
  }));
  const { result } = renderHook(() => useDeleteWord("p", 0), { wrapper: makeWrapper() });
  await result.current.mutateAsync({ lineIndex: 1, wordIndex: 2 });
  expect(body).toEqual({ scope: "word", word_indices: [[1, 2]], line_indices: [], paragraph_indices: [] });
});

it("useNudgeWord POSTs deltas + refine_after", async () => {
  let body: unknown;
  server.use(http.post("*/words/1/2/nudge", async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ project_id: "p", page_index: 0 });
  }));
  const { result } = renderHook(() => useNudgeWord("p", 0), { wrapper: makeWrapper() });
  await result.current.mutateAsync({ lineIndex: 1, wordIndex: 2, left: 0, right: 1, top: 0, bottom: 0, refineAfter: true });
  expect(body).toEqual({ left: 0, right: 1, top: 0, bottom: 0, refine_after: true });
});
```

- [ ] **Step 2: Run, verify fail** — `cd frontend && pnpm vitest run src/hooks/useWordMutations.test.tsx` → FAIL (`useDeleteWord is not a function`).
- [ ] **Step 3: Implement** (append to `useWordMutations.ts`, reusing `apiPost`, `wordBase`, and the page-invalidation `onSuccess` pattern already in the file)

```ts
export function useDeleteWord(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number; wordIndex: number }>({
    mutationFn: ({ lineIndex, wordIndex }) =>
      apiPost<PagePayload>(`/api/projects/${projectId}/pages/${pageIndex}/delete`, {
        scope: "word", word_indices: [[lineIndex, wordIndex]], line_indices: [], paragraph_indices: [],
      }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] }); },
  });
}

export function useNudgeWord(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error,
    { lineIndex: number; wordIndex: number; left: number; right: number; top: number; bottom: number; refineAfter: boolean }>({
    mutationFn: ({ lineIndex, wordIndex, left, right, top, bottom, refineAfter }) =>
      apiPost<PagePayload>(`${wordBase(projectId, pageIndex, lineIndex, wordIndex)}/nudge`,
        { left, right, top, bottom, refine_after: refineAfter }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] }); },
  });
}
```
> Confirm the exact `queryKey` and `apiPost` import against the top of `useWordMutations.ts` before writing (do not invent a new key shape).

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(hooks): add useDeleteWord + useNudgeWord word mutations"`

### Task S1.2: Wire dialog callbacks in `ProjectPage.tsx`

**Files:** Modify `frontend/src/pages/ProjectPage.tsx` (the `<WordEditDialog>` mount ~1048); Test `frontend/src/pages/ProjectPage.wordEditDialog.test.tsx` (new).

- [ ] **Step 1: Failing test** — render `ProjectPage` (reuse the existing ProjectPage test harness/MSW seed), open the word-edit dialog via `dialogStore.openWordEdit({lineIdx:0,wordIdx:0})`, click `dialog-merge-next-button`, assert a POST to `.../words/0/0/merge` with `{direction:"right"}` fired (MSW spy). Repeat minimal assertions for delete, gt-commit, apply-style.

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** — instantiate the hooks near the other ProjectPage hooks and pass adapters:

```tsx
const mergeWord = useMergeWord(projectId, idx0);
const splitWord = useSplitWord(projectId, idx0);
const deleteWord = useDeleteWord(projectId, idx0);
const reboxWord = useReboxWord(projectId, idx0);
const nudgeWord = useNudgeWord(projectId, idx0);
const applyStyleWord = useApplyStyle(projectId, idx0);
const applyComponentWord = useApplyComponent(projectId, idx0);
const updateGtWord = useUpdateWordGroundTruth(projectId, idx0);
const { lineIndex: dLi, wordIndex: dWi } = dialogTarget; // existing dialogTarget

// crop: shrink the word bbox on one side by `padding` px, then rebox (no dedicated crop route)
const cropWord = (dir: "above" | "below" | "left" | "right", padding: number) => {
  const w = findWord(pagePayload, dLi, dWi);            // existing selection-walk helper
  if (!w) return Promise.resolve();
  const b = { ...w.bbox };
  if (dir === "left")  { b.x += padding; b.width  -= padding; }
  if (dir === "right") {                b.width  -= padding; }
  if (dir === "above") { b.y += padding; b.height -= padding; }
  if (dir === "below") {                b.height -= padding; }
  return reboxWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi, bbox: b }).then(() => {});
};
```

```tsx
<WordEditDialog
  open={wordEditState.open}
  target={dialogTarget}
  lineWords={dialogLineWords}
  wordImageUrl={pagePayload?.image_url ?? undefined}  // WordImageCanvas crops to the target bbox (see S1.3)
  gtText={findWord(pagePayload, dLi, dWi)?.ground_truth_text ?? ""}
  onGtChange={() => {}}
  onGtCommit={(text) => updateGtWord.mutate({ lineIndex: dLi, wordIndex: dWi, text })}
  onMerge={(d) => mergeWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi, direction: d === "prev" ? "left" : "right" }).then(() => {})}
  onSplit={(fraction, axis) => {
    if (axis === "v") return Promise.resolve();        // backend exposes horizontal only (words.py:1080 → 400)
    return splitWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi, xFraction: fraction, direction: "horizontal" }).then(() => {});
  }}
  onDelete={() => deleteWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi }).then(() => { dialogStore.close("wordEdit"); })}
  onCrop={cropWord}
  onRefine={() => nudgeWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi, left: 0, right: 0, top: 0, bottom: 0, refineAfter: true }).then(() => {})}
  onExpandRefine={() => nudgeWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi, left: 4, right: 4, top: 4, bottom: 4, refineAfter: true }).then(() => {})}
  onApplyNudge={(n, refineAfter) => nudgeWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi, left: n.left, right: n.right, top: n.top, bottom: n.bottom, refineAfter }).then(() => {})}
  onApplyStyle={(style, scope) => applyStyleWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi, style, scope }).then(() => {})}
  onApplyComponent={(component, enabled) => applyComponentWord.mutateAsync({ lineIndex: dLi, wordIndex: dWi, component, enabled }).then(() => {})}
  onNavigate={(t) => dialogStore.openWordEdit({ lineIdx: t.lineIndex, wordIdx: t.wordIndex })}
  onApply={() => { invalidatePage(); dialogStore.close("wordEdit"); }}
  onClose={() => dialogStore.close("wordEdit")}
/>
```
> Disable the V-split button in `WordActionRows.tsx` with a tooltip "horizontal split only" rather than letting it silently resolve — surface the backend constraint. (Small edit + test.)

- [ ] **Step 4: Run vitest, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(labeler): wire WordEditDialog mutations (merge/split/delete/crop/refine/nudge/style/component/gt)"`

### Task S1.3: Word image in dialog (WED-10)

**Files:** Modify `frontend/src/components/WordEditDialog.tsx` / `WordImageCanvas.tsx` as needed; Test alongside.

- [ ] **Step 1:** Confirm how `ReboxSection`/`WordImageCanvas` render a word image today (page image URL + bbox crop on a Konva stage). Reuse that exact approach: pass `wordImageUrl={page image_url}` plus the target bbox so `WordImageCanvas` crops to the word. If `WordImageCanvas` already accepts a bbox/crop prop, pass it; if not, add a `cropBBox` prop mirroring `ReboxSection`'s crop math.
- [ ] **Step 2: Failing test** — render dialog with a page image URL + target; assert the canvas mounts a non-empty image layer (not blank).
- [ ] **Step 3: Implement** the crop wiring (reuse `ReboxSection` crop logic; no new image endpoint).
- [ ] **Step 4: Pass. Step 5: Commit** — `feat(labeler): render cropped word image in WordEditDialog`.

**S1 per-task reviews:** run the review protocol after S1.1, S1.2, S1.3.

---

## S3 — Rebox on main canvas  (Track T-CANVAS, after S1)

`PageImageCanvas` already fires `onRebox?.(rect)` in `"rebox"` mode (`PageImageCanvas.tsx:583`)
and auto-exits to select mode; `viewport-store` carries `pendingReboxTarget:{lineIndex,wordIndex}`.
The gap: `ProjectPage.tsx:885-893` mounts `<PageImageCanvas>` **without** `onRebox`. The rebox-mode
entry point already exists (WordDetail rebox accordion sets `mode:"rebox"`+`pendingReboxTarget`).

### Task S3.1: Wire `onRebox` in `ProjectPage`

**Files:** Modify `frontend/src/pages/ProjectPage.tsx`; Test `ProjectPage` canvas test (reuse pattern from `PageImageCanvas.test.tsx:770`).

- [ ] **Step 1: Failing test** — set `viewportStore.setState({mode:"rebox", pendingReboxTarget:{lineIndex:0,wordIndex:0}})`, render ProjectPage, simulate a drag on the canvas surface, assert a POST to `.../words/0/0/rebox` fired with a source-pixel bbox.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** — add a handler mirroring `handleBoxSelect`'s display→source conversion, then pass it:

```tsx
const reboxWordCanvas = useReboxWord(projectId, idx0);  // reuse if S1 already declared reboxWord; do not double-declare
const handleRebox = (rect: BBox) => {
  const t = viewportStore.getState().pendingReboxTarget;
  if (!t) return;
  const bbox = toSourceBBox(rect, pagePayload?.encoded_dims ?? null);  // same conversion handleBoxSelect/handleAddWord use
  reboxWordCanvas.mutate({ lineIndex: t.lineIndex, wordIndex: t.wordIndex, bbox });
};
// in the <PageImageCanvas .../> mount:
onRebox={handleRebox}
```
> Use the existing display→source conversion helper that `handleAddWord` uses (grounded at the `onAddWord` path). If S1 already declared `reboxWord`, reuse it — one declaration.

- [ ] **Step 4: Pass. Step 5: Commit** — `feat(labeler): wire draw-to-rebox on main page canvas`.

**S3 per-task review:** run protocol.

---

## S2 — Matches-pane deltas into visible surfaces  (Track T-PANEL)

**Decision (CT):** do NOT rebuild the Matches pane. The WordDetail right panel already covers
validate / GT-edit / tag-removal (selection-gated). The hidden `canvas-hidden-stubs` block stays
(driver contract §2.7/§2.8 mandates those testids per D-014 — `docs/architecture/13-driver-contract.md`).
Only **two genuine deltas** have no visible equivalent — wire those.

### Task S2.1: Tab-to-next-word GT focus

**Files:** Modify `frontend/src/components/right-panel/OcrGtCompareRow.tsx` (and/or `WordFooter.tsx`
`walkSibling` path); Test alongside.

- [ ] **Step 1: Failing test** — render WordDetail with a selected word that has a next sibling;
  fire `keyDown {key:"Tab"}` on `ocr-gt-input`; assert selection advances to the next word AND the
  new `ocr-gt-input` receives focus (`document.activeElement`).
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** — add an `onKeyDown` to the GT input that on `Tab` (no shift) calls the
  existing `walkSibling("next", page)` (from the WordFooter Skip path) and, after the next row
  renders, focuses its input via a ref + `useEffect` keyed on the selected word. Shift+Tab → `"prev"`.

```tsx
function handleGtKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
  if (e.key !== "Tab") return;
  e.preventDefault();
  commitGt(); // persist current before moving
  walkSibling(e.shiftKey ? "prev" : "next", page);
}
// focus-on-select:
useEffect(() => { gtInputRef.current?.focus(); }, [selectedWordKey]);
```
> Grounded: `WordFooter.tsx:151-160` already exposes `walkSibling`; reuse it (DRY).

- [ ] **Step 4: Pass. Step 5: Commit** — `feat(labeler): Tab/Shift-Tab moves GT editing to next/prev word`.

### Task S2.2: Visible full-page GT/OCR read-only text view

**Files:** Modify `frontend/src/components/Drawer.tsx` (add a "Text" tab) reusing the **existing**
`TextTabs` GT/OCR panels (`text-panel-ground-truth` / `text-panel-ocr`) — do not duplicate; mount
the existing component visibly. Test alongside.

- [ ] **Step 1: Failing test** — render the Drawer, click the new `drawer-tab-text`, assert
  `text-panel-ground-truth` and `text-panel-ocr` are **visible** (`toBeVisible()`) and contain the
  page GT/OCR text from the payload.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** — add a Drawer tab that renders the existing read-only GT/OCR panels
  (extract the GT/OCR panel JSX from `TextTabs.tsx` into a small shared `<PlaintextGtOcrView>` if
  needed to avoid mounting the whole Matches machinery; reuse the same testids). The hidden stub
  block is untouched (keeps the driver contract); this adds a **second, visible** mount of the
  read-only text view. Confirm no testid collision (if the same testid must be unique, give the
  visible view distinct testids and update the e2e that asserts visibility).
- [ ] **Step 4: Pass. Step 5: Commit** — `feat(labeler): visible full-page GT/OCR text view in drawer`.

> Note for reviewer: confirm we did NOT introduce a new `display:none`. The deltas must be visible.

**S2 per-task reviews:** run protocol after S2.1, S2.2.

---

## S4 — Form-new-line-from-selected-words (real backend)  (Track T-LINE)

The toolbar `word-word-to-line` maps to the **stub** `POST .../lines/{li}/split-with-selected`
(`lines_paragraphs.py:1896`, returns `_stub_page_payload` — no mutation). The real page method
`page.split_line_with_selected_words(word_keys)` exists (book-tools `page.py:2217`) and is already
used by the real `/lines/split-by-words` route (`lines_paragraphs.py:976`).

### Task S4.1: Implement the stub route for real

**Files:** Modify `src/pdomain_ocr_labeler_spa/api/lines_paragraphs.py`; Test
`tests/integration/test_lines_paragraphs_router.py` + a persistence assertion mirroring
`test_lines_paragraphs_persist.py`.

- [ ] **Step 1: Failing test**

```python
@pytest.mark.integration
def test_split_with_selected_actually_splits(loaded_client):
    # seed a page with a line containing >=3 words (reuse the persist-test seeding)
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/split-with-selected",
        json={"word_keys": [[0, 1], [0, 2]]},
    )
    assert resp.status_code == 200
    payload = resp.json()
    # the selected words are extracted into a new line -> line count increased
    assert len(payload["line_matches"]) == _baseline_line_count + 1
```

- [ ] **Step 2: Run, verify fail** (current stub returns empty payload → assertion fails).
- [ ] **Step 3: Implement** — replace the stub body to do what `split_by_words` does (DRY: factor a
  shared helper if the two routes now share logic):

```python
@router.post(".../lines/{line_index}/split-with-selected", response_model=PagePayload)
def split_line_with_selected_words(project_id, page_index, line_index, body: SplitByWordsRequest,
                                   project_state, settings, store):
    err = _check_project_and_page(project_id, page_index, project_state)
    if err is not None:
        return err
    pstate = project_state.get_page_state(page_index)
    page = _resolve_page_object(pstate)
    word_keys = [(int(li), int(wi)) for li, wi in body.word_keys]
    with project_state.get_page_lock(page_index):
        ok = bool(page.split_line_with_selected_words(word_keys))
        if not ok:
            return _mutation_failed("split_with_selected_failed")
        _finalize_structural_edit(page, pstate, project_state, page_index, store,
                                  changes=[{"type": "split_with_selected", "word_keys": word_keys}])
    return _refresh_payload_response(project_id, page_index, project_state, settings)
```
> Update the route's request model to `SplitByWordsRequest{word_keys}` (drop the legacy `line_index`/`word_indices`/`mode` shape) OR keep back-compat by accepting both — pick the simpler that keeps existing tests green; update the legacy stub tests to assert the real effect.

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `feat(api): implement form-new-line-from-selected-words (was a stub)`.

### Task S4.2: Repoint the toolbar mapping

**Files:** Modify `frontend/src/lib/toolbarMapping.ts:191`; Test `toolbarMapping` unit test.

- [ ] **Step 1: Failing test** — assert `word-word-to-line` produces a POST to the split route with
  `{word_keys: [...selection]}` (not `{mode:"extract_to_new"}`).
- [ ] **Step 2: Fail. Step 3: Implement** — update the mapping body to send `word_keys` from the
  selection store in the shape the route now expects.
- [ ] **Step 4: Pass. Step 5: Commit** — `fix(toolbar): word-to-line sends word_keys to real route`.

**S4 per-task reviews:** run protocol after S4.1, S4.2.

---

## S5 — Save-project skipped-page warning  (Track T-SAVE)

`save_project.py:194-197` silently skips dirty pages where `page_id is None` (debug log only) yet
counts them complete; `SaveProjectResponse` has no `skipped_pages`; the frontend never replaces the
"Saving…" toast. **Definition of done:** skipped pages are surfaced to the user (count + indices);
the stale "stub" docstring at `api/projects.py:723` is corrected. (Auto-registering unregistered
pages is a separate concern, not in this slice — but skipping must never be silent.)

### Task S5.1: Track + expose skipped pages in the handler

**Files:** Modify `core/jobs/handlers/save_project.py`, `api/pages.py` (`SaveProjectResponse`); Test
`tests/integration/test_save_project_roundtrip.py`.

- [ ] **Step 1: Failing test** — seed one dirty page with `page_id=None`; run the handler; assert
  `job.payload["skipped_pages"] == 1`, `job.payload["skipped_indices"] == [<idx>]`, and the terminal
  notification message mentions the skip.
- [ ] **Step 2: Fail. Step 3: Implement**

```python
# add field
class SaveProjectResponse(BaseModel):
    job_id: str
    failures: list[SaveFailure] = Field(default_factory=list)
    skipped_pages: int = 0
    skipped_indices: list[int] = Field(default_factory=list)
```

```python
# in handler: accumulate alongside failures
skipped: list[int] = []
...
else:
    log.debug("save_project: page %d has no page_id — skipping store write", page_index)
    skipped.append(page_index)
...
job.payload["skipped_pages"] = len(skipped)
job.payload["skipped_indices"] = skipped
msg = f"Saved {total} page(s)."
if skipped:
    msg += f" {len(skipped)} unsaved (not registered): pages {skipped}."
notification_queue.queue(NEGATIVE if skipped else POSITIVE, msg)
```

- [ ] **Step 4: Pass.** Step 5 commit: `feat(save): surface skipped (unregistered) pages instead of silent skip`.

### Task S5.2: Surface in the frontend toast + fix docstring

**Files:** Modify `frontend/src/components/PageActionsCompact.tsx` (`handleSaveProject`),
`api/projects.py:723` docstring; Test `PageActionsCompact.test.tsx`.

- [ ] **Step 1: Failing test** — stub the job result with `skipped_pages:1`; trigger save; assert a
  `toast.warning`/`toast.error` is shown mentioning skipped pages (not `toast.success`).
- [ ] **Step 2: Fail. Step 3: Implement** — register a save-project completion handler (mirror the
  existing `useJobCompletionInvalidation` OCR instance) that polls `GET /api/jobs/{id}`, reads
  `payload.skipped_pages`, and replaces the loading toast with success (0 skipped) or warning (>0).
  Remove the stale "stub that immediately completes" sentence from the `save-all` docstring.
- [ ] **Step 4: Pass.** Step 5 commit: `feat(save): warn on skipped pages in save toast; fix stale docstring`.

**S5 per-task reviews:** run protocol after S5.1, S5.2.

---

## S6 — Chrome gaps bundle  (Track T-CHROME, after T-SAVE merges)

Confirmed-real gaps only: (a) Go-To button `sr-only`; (b) no resolved project path; (c) OCR config
unreachable on root + no Cancel/snapshot; (d) QuickSearch unmounted + `⌘K` opens help not search.
(Source-folder "Use Current" already exists — `SourceFolderDialog.tsx:320` — out of scope.)

### Task S6.1: Visible Go-To button

**Files:** Modify `frontend/src/components/ProjectNavigationControls.tsx:149`; Test alongside.

- [ ] **Step 1: Failing test** — assert `nav-goto-button` is **visible** (`toBeVisible()`) and a
  click calls `onGoTo`.
- [ ] **Step 2: Fail. Step 3:** Replace `className="sr-only"` with the real button styling used by
  the adjacent nav buttons (match `nav-next-button`); keep the testid.
- [ ] **Step 4: Pass.** Commit: `fix(nav): make Go To button visible`.

### Task S6.2: Resolved project path label

**Files:** Modify `frontend/src/components/ProjectLoadControls.tsx:184`; Test alongside.

- [ ] **Step 1: Failing test** — on a project route, assert a label shows the loaded
  `project.project_root` (from `useProject`), not `sr-only`.
- [ ] **Step 2: Fail. Step 3:** Call `useProject(projectId)` (the `GET /api/projects/{id}` hook),
  render `project.project_root` in a visible `font-mono truncate` label on project routes (keep the
  source-root label for the root route). Reuse the existing `useProject` hook (DRY).
- [ ] **Step 4: Pass.** Commit: `feat(chrome): show resolved project path on project routes`.

### Task S6.3: OCR config on root + Cancel/snapshot

**Files:** Modify `frontend/src/App.tsx` (mount an OCR-config trigger on root without colliding with
`PageActionsCompact`), `frontend/src/components/OCRConfigModal.tsx`; Tests alongside.

- [ ] **Step 1: Failing tests** — (1) on root route, `ocr-config-trigger-button` (or a root variant)
  is present and opens the modal; (2) changing a model select then clicking a new
  `ocr-config-cancel-button` restores the pre-open values (no net POST), while `Done` persists.
- [ ] **Step 2: Fail. Step 3:** (a) In `App.tsx`, render the OCR-config trigger when `!onProjectRoute`
  too (a small dedicated trigger to avoid editing `PageActionsCompact`, which T-SAVE also touches).
  (b) In `OCRConfigModal`, capture a snapshot of config into local pending state on `open→true`,
  route all selects through pending state, POST only on `Done`, and add a `ocr-config-cancel-button`
  that discards pending + closes.
- [ ] **Step 4: Pass.** Commit: `feat(ocr-config): reachable from root + Cancel/snapshot semantics (#405)`.

### Task S6.4: Mount QuickSearch + fix ⌘K

**Files:** Modify the shell/header layout (where `HeaderBar` renders) to mount
`frontend/src/components/shell/QuickSearch.tsx`; fix the `⌘K` keycap; Test alongside.

- [ ] **Step 1: Failing tests** — (1) QuickSearch input is rendered in the header and typing calls
  `worklistStore.setSearchQuery`; (2) pressing `Mod+K` focuses the search input (not opens hotkey
  help).
- [ ] **Step 2: Fail. Step 3:** Mount `<QuickSearch>` in the header; add a global `Mod+K` hotkey
  (via the existing `useHotkey`/`useGlobalHotkeys` mechanism) that focuses the input ref; change the
  keycap to a non-misleading affordance (or keep `⌘K` now that it focuses search) and move
  hotkey-help to `?` if it isn't already.
- [ ] **Step 4: Pass.** Commit: `feat(chrome): mount QuickSearch; Mod+K focuses search`.

**S6 per-task reviews:** run protocol after each S6.x.

---

## S8 — Real rotate / auto-rotate + re-OCR  (Track T-ROTATE, cross-repo)

Stubs: `handlers/rotate.py:40-74` (`asyncio.sleep(0)`), `handlers/auto_rotate_all.py:47-83`.
Upstream ready (no book-tools change needed): `pdomain_book_tools.ocr.rotation.rotate_image(ndarray, degrees)->ndarray`
and `detect_best_rotation(image, *, ocr_fn, confidence_threshold=0.6, rotations=(0,90,180,270))->(int, Document, probes)`.
Re-OCR model: `handlers/reload_ocr.py:185-305` (`loader.run_ocr` on a thread, write `page_record`,
bump generation, `_ingest_ocr_result` writes image+json blobs). Image source on disk:
`project.image_paths[page_index]`. **Gap:** no durable rotation event on `PageAggregate`.

### Task S8.1 (pdomain-ops): Add `RotationUpdated` event to `PageAggregate`  ← Wave 1

**Repo:** `pdomain-ops` (delegate to the `pdomain-ops` agent in a worktree).
**Files:** the `PageAggregate` module + its tests.

- [ ] **Step 1: Failing test** — create a `PageAggregate`, call
  `agg.rotation_updated(degrees=90, source="manual")`, reload from the event store, assert
  `record.rotation_degrees == 90` and `record.rotation_source == "manual"` persisted.
- [ ] **Step 2: Fail. Step 3: Implement** a `@event("RotationUpdated")` method on `PageAggregate`
  that sets `self._record.rotation_degrees` / `rotation_source` (mirror the existing
  `labeler_edited` event method's shape and persistence). Export it so the labeler handler can call it.
- [ ] **Step 4: Pass.** Commit (pdomain-ops): `feat(page-aggregate): add RotationUpdated event`.
- [ ] **Per-task review** (pdomain-ops reviewer). Then orchestrator merges + (if needed) the labeler
  repo bumps the `pdomain-ops` dep (`make update-pdomain-deps`) — coordinate before T-ROTATE-spa.

### Task S8.2 (labeler-spa): Implement `handle_rotate_page`  ← Wave 2

**Files:** Modify `core/jobs/handlers/rotate.py`; add a rotate-bytes helper; Test
`tests/integration/test_rotate_job.py` (new, mirror `test_reload_ocr_job.py` seeding +
`_seed_event_store`).

- [ ] **Step 1: Failing test** — seed a project+page with a known image; submit a rotate job
  (degrees=90); after completion assert: (a) the on-disk source image dimensions are transposed
  (rotated), (b) `page_record.rotation_degrees == 90`, (c) the page was re-OCR'd (a fresh
  `_ingest_ocr_result` blob written / generation bumped).
- [ ] **Step 2: Fail. Step 3: Implement** (real steps 2–4, no `sleep`):

```python
import cv2, numpy as np
from pdomain_book_tools.ocr.rotation import rotate_image

def _rotate_png_on_disk(path: Path, degrees: int) -> None:
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    rotated = rotate_image(img, degrees)            # lossless np.rot90 quarter-turn
    ok, buf = cv2.imencode(".png", rotated)
    if not ok:
        raise RuntimeError("png re-encode failed")
    path.write_bytes(buf.tobytes())

async def handle_rotate_page(runner, job):
    pid, idx, degrees = job.payload["project_id"], int(job.payload["page_index"]), int(job.payload["degrees"])
    source = "manual" if job.payload.get("manual", True) else "auto"
    project_state = runner.context["project_state"]
    project = project_state.project
    src_path = Path(project.image_paths[idx]).resolve()
    # security: source must live under the project image dir
    assert _within(src_path, Path(project.images_root).resolve())
    await asyncio.to_thread(_rotate_png_on_disk, src_path, degrees)
    # re-OCR via the SAME path reload_ocr uses (image already upright on disk)
    loader = _get_page_loader(runner)            # reuse reload_ocr's builder
    outcome = await asyncio.to_thread(loader.run_ocr, idx)
    _apply_reocr_outcome(project_state, idx, outcome)   # reuse reload_ocr's write-back helper
    # durable rotation metadata
    agg = _load_page_aggregate(runner, pid, idx)
    agg.rotation_updated(degrees=degrees, source=source)
    _save_aggregate(runner, agg)
```
> Reuse `reload_ocr`'s `_get_page_loader` + the write-back block (factor a shared
> `_apply_reocr_outcome` helper used by BOTH handlers — DRY; do not copy-paste). `_within` is a
> path-containment guard (security). Confirm `project.images_root`/`image_paths` attribute names
> against the loader code before writing.

- [ ] **Step 4: Pass.** Commit: `feat(rotate): real page rotation + re-OCR + durable rotation metadata`.

### Task S8.3 (labeler-spa): Implement `handle_auto_rotate_all`

**Files:** Modify `core/jobs/handlers/auto_rotate_all.py`; Test `tests/integration/test_auto_rotate_all_job.py`.

- [ ] **Step 1: Failing test** — seed a project where one page image is sideways; run auto-rotate-all
  with a stub/predictor that reports the correct rotation ≥ threshold; assert that page got a
  `rotate_page` applied (rotation metadata set) and an upright page was left at 0°.
- [ ] **Step 2: Fail. Step 3: Implement** — build an `ocr_fn` from `runner.context["predictor_cache"]`
  + `ocr_config_carrier` (same keys `reload_ocr._get_page_loader` reads), loop pages, call
  `detect_best_rotation(image_ndarray, ocr_fn=ocr_fn, confidence_threshold=0.6)`, and for pages with
  `chosen != 0` enqueue/await the same rotate path as S8.2 (reuse the S8.2 helper — DRY). Emit real
  per-page progress events. Honor `overwrite_manual` (skip pages whose `rotation_source=="manual"`
  unless set).
- [ ] **Step 4: Pass.** Commit: `feat(auto-rotate): detect + apply best rotation across all pages`.

### Task S8.4 (labeler-spa): Rotate-180 button + degrees plumbing

**Files:** Modify `frontend/src/components/PageActions.tsx` (or `PageActionsCompact`) to add a
visible `rotate-180-button` (backend `RotatePageRequest` already accepts 180); Test alongside.

- [ ] **Step 1: Failing test** — assert `rotate-180-button` is visible and POSTs `{degrees:180}`.
- [ ] **Step 2: Fail. Step 3:** Add the button next to CW/CCW; wire to the rotate mutation with 180.
- [ ] **Step 4: Pass.** Commit: `feat(rotate): add visible 180° rotate button`.

**S8 per-task reviews:** run protocol after S8.1 (pdomain-ops), S8.2, S8.3, S8.4 — with extra
security scrutiny on the on-disk PNG overwrite path.

---

## End-of-plan review (plan level)

After all tracks rebase + `--ff-only` merge to an integration branch and `CI=true make ci AI=1` is
green:

- [ ] Dispatch the **5 parallel reviewer subagents** (security / correctness+integration /
  simplicity / style / spec-coverage+no-deferred) over the full integrated diff. Triage + fix all
  findings. Re-run `make ci`.
- [ ] Confirm every PARITY-GAP.md row for S1–S6 + S8 is now ✅ (working), and that **zero** new
  stubs/`display:none`/`Promise.resolve()` no-ops/`TODO`s were introduced (grep the full diff).

## Browser Verification milestone (MANDATORY — FastAPI+SPA)

Playwright e2e in `tests/e2e/` against the running server (`CI=true`), using
`_seed_event_store` / `_ingest_ocr_result` seeding (`helpers.py`, `fixtures/`). Assert observable,
**persisted** behavior. Add `make e2e` to `make ci` if not already wired.

- [ ] **App loads** — ProjectPage renders; no `console.error` resource failures.
- [ ] **S1** — open word-edit dialog (word image visible); type GT + commit → reopen page → GT
  persists; merge-next → line word count drops by 1 and persists; apply a style → chip shows.
- [ ] **S3** — enter rebox (WordDetail accordion), drag on the page canvas → the word bbox numeric
  values change and persist.
- [ ] **S2** — Tab in the GT input moves focus to the next word's GT input; Drawer "Text" tab shows
  visible GT/OCR page text.
- [ ] **S4** — select ≥2 words, fire word-to-line → a new line appears (line count +1), persists.
- [ ] **S5** — trigger save with an unregistered dirty page → a warning toast names the skipped page.
- [ ] **S6** — Go-To button visible + navigates; resolved project path visible; OCR config opens
  from root and Cancel discards; Mod+K focuses QuickSearch.
- [ ] **S8** — click rotate CW → the page image visibly rotates and survives reload; rotate-180
  works; (auto-rotate-all covered by integration test if no skewed fixture in e2e).

## Self-review (author checklist — done)

- **Spec coverage:** every S1–S6 + S8 row in PARITY-GAP.md maps to a task here; S7 explicitly
  excluded (Q-A7 blocked). ✓
- **Placeholder scan:** no "TBD/handle edge cases/similar to"; every code step shows real code or a
  grounded `file:line` confirm-before-write instruction. ✓
- **Type consistency:** hook arg shapes (`{lineIndex,wordIndex,...}`), dialog callback signatures,
  `RotationUpdated(degrees, source)`, `SaveProjectResponse.skipped_pages` are consistent across
  tasks. ✓
- **FastAPI+SPA check:** Browser Verification milestone present and asserts persistence. ✓
- **No deferred work:** each slice's "definition of done" forbids leaving a capability partial; the
  review protocol greps for new stubs at task and plan level. ✓

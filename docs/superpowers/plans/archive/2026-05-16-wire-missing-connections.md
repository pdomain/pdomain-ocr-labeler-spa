# Wire Missing UI Connections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire five discovered dead-ends so every visible UI control actually commits data — WorklistRow→selectionStore bridge, WorklistRow checkboxes→BulkActions, LineDetail GT input commit (backend + frontend), Rail mode→canvas sync, and QuickSearch text filtering.

**Architecture:** Each fix is a narrow slice with a clear input→store/API→output path. No new components are created; only missing wiring and one new backend endpoint are added. The frontend changes follow existing TanStack Query + external-store patterns already established in the codebase.

**Tech Stack:** FastAPI (Python), React 19, TanStack Query, Vitest, pytest

---

## Files to Create or Modify

| File | Action |
|------|--------|
| `src/pd_ocr_labeler_spa/api/lines_paragraphs.py` | Add `SetLineGtRequest` model + `POST .../lines/{li}/set-gt` endpoint |
| `tests/test_lines_paragraphs_router.py` | Add tests for the new set-gt endpoint |
| `frontend/src/hooks/useLineMutations.ts` | Add `useSetLineGt` mutation hook |
| `frontend/src/components/right-panel/LineDetail.tsx` | Wire `GTRow` onBlur/Escape/Enter commit via `useSetLineGt` |
| `frontend/src/components/drawer/Worklist.tsx` | WorklistRow onClick→`selectLine()`; add bulk-select checkboxes |
| `frontend/src/components/shell/QuickSearch.tsx` | Remove `readOnly`; wire input→`worklistStore.setSearchQuery` |
| `frontend/src/stores/worklist-store.ts` | Add `searchQuery` field + `setSearchQuery` mutator |
| `frontend/src/components/PageImageCanvas.tsx` | Subscribe to `railStore.mode` and sync to `viewportStore` |
| `frontend/src/hooks/useLineMutations.test.tsx` | Tests for `useSetLineGt` |
| `frontend/src/components/drawer/Worklist.test.tsx` | Tests for checkbox + selectionStore bridge |
| `frontend/src/components/shell/QuickSearch.test.tsx` | Tests for search filtering |

---

## Task 1: WorklistRow → selectionStore bridge + bulk-select checkboxes

**Files:**
- Modify: `frontend/src/components/drawer/Worklist.tsx`
- Modify: `frontend/src/components/drawer/Worklist.test.tsx`

- [ ] **Step 1: Write the failing test — selectionStore bridge**

Add to `frontend/src/components/drawer/Worklist.test.tsx`:

```typescript
import { selectLine, selectionStore, clearSelection } from "../../stores/selection-store";
import { worklistStore } from "../../stores/worklist-store";
import { vi, describe, it, expect, beforeEach } from "vitest";

// Mock selectLine so we can spy on calls without full store setup
vi.mock("../../stores/selection-store", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../stores/selection-store")>();
  return { ...actual, selectLine: vi.fn() };
});

describe("WorklistRow bridge", () => {
  beforeEach(() => {
    worklistStore.reset();
    vi.clearAllMocks();
  });

  it("calls selectLine with line_index on row click", async () => {
    const lineMatches = [
      { line_index: 3, overall_match_status: "exact", ocr_line_text: "hello", ground_truth_line_text: "hello", is_fully_validated: false, validated_word_count: 0, total_word_count: 1, word_matches: [], paragraph_index: 0 },
    ];
    render(<Worklist lineMatches={lineMatches} />);
    await userEvent.click(screen.getByTestId("worklist-row-3"));
    expect(selectLine).toHaveBeenCalledWith(3);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/drawer/Worklist.test.tsx 2>&1 | tail -20
```

Expected: FAIL — `selectLine` not called.

- [ ] **Step 3: Wire WorklistRow onClick to also call selectLine**

In `frontend/src/components/drawer/Worklist.tsx`, add the import at the top:

```typescript
import { selectLine } from "../../stores/selection-store";
```

Find the existing WorklistRow render in the Worklist component (around line 321):
```typescript
onClick={() => worklistStore.setSelectedLineIndex(line.line_index)}
```

Replace with:
```typescript
onClick={() => {
  worklistStore.setSelectedLineIndex(line.line_index);
  selectLine(line.line_index);
}}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/drawer/Worklist.test.tsx 2>&1 | tail -20
```

Expected: PASS

- [ ] **Step 5: Write failing test — checkboxes populate selectedIds**

Add to the same test file:

```typescript
it("checkbox click calls worklistStore.toggle with line_index", async () => {
  const lineMatches = [
    { line_index: 2, overall_match_status: "mismatch", ocr_line_text: "foo", ground_truth_line_text: "bar", is_fully_validated: false, validated_word_count: 0, total_word_count: 1, word_matches: [], paragraph_index: 0 },
  ];
  render(<Worklist lineMatches={lineMatches} />);
  const checkbox = screen.getByTestId("worklist-row-checkbox-2");
  await userEvent.click(checkbox);
  expect(worklistStore.getState().selectedIds).toContain(2);
});

it("checkbox click does not trigger row navigation", async () => {
  const lineMatches = [
    { line_index: 5, overall_match_status: "exact", ocr_line_text: "x", ground_truth_line_text: "x", is_fully_validated: false, validated_word_count: 0, total_word_count: 1, word_matches: [], paragraph_index: 0 },
  ];
  render(<Worklist lineMatches={lineMatches} />);
  await userEvent.click(screen.getByTestId("worklist-row-checkbox-5"));
  expect(selectLine).not.toHaveBeenCalled();
});
```

- [ ] **Step 6: Add checkbox to WorklistRow**

In `frontend/src/components/drawer/Worklist.tsx`, in the `WorklistRow` function, add a checkbox as the first child of the `<button>`, before the 4px color bar:

```typescript
function WorklistRow({ line, isSelected, onClick }: WorklistRowProps) {
  // ... existing vars ...
  const isChecked = /* read from store */ false; // will wire in next step

  return (
    <button
      type="button"
      role="option"
      data-testid={`worklist-row-${line.line_index}`}
      data-selected={isSelected ? "true" : undefined}
      aria-selected={isSelected}
      onClick={onClick}
      className={cn(
        "w-full flex items-stretch text-left text-[11px] transition-colors border-b border-border-1/40",
        isSelected
          ? "bg-bg-raised text-ink-1"
          : "text-ink-2 hover:bg-bg-raised/60 hover:text-ink-1",
      )}
    >
      {/* Bulk-select checkbox */}
      <div className="flex items-center pl-1.5 pr-0.5 flex-shrink-0">
        <input
          type="checkbox"
          data-testid={`worklist-row-checkbox-${line.line_index}`}
          checked={isChecked}
          onChange={() => worklistStore.toggle(line.line_index)}
          onClick={(e) => e.stopPropagation()}
          className="w-3 h-3 cursor-pointer accent-accent"
          aria-label={`Select line ${line.line_index + 1} for bulk action`}
        />
      </div>

      {/* 4px status color bar */}
      <div className={cn("w-1 flex-shrink-0 rounded-sm my-0.5 ml-0.5", barClass)} />

      {/* Row body — unchanged */}
      ...
    </button>
  );
}
```

Because `WorklistRow` receives `isSelected` from the parent `Worklist`, add `isChecked` as a prop too. Update `WorklistRowProps` and the parent:

```typescript
interface WorklistRowProps {
  line: LineMatch;
  isSelected: boolean;
  isChecked: boolean;
  onClick: () => void;
}
```

In the Worklist component, pass `isChecked`:
```typescript
<WorklistRow
  key={line.line_index}
  line={line}
  isSelected={selectedLineIndex === line.line_index}
  isChecked={state.selectedIds.includes(line.line_index)}
  onClick={() => {
    worklistStore.setSelectedLineIndex(line.line_index);
    selectLine(line.line_index);
  }}
/>
```

- [ ] **Step 7: Run tests to verify all pass**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/drawer/Worklist.test.tsx 2>&1 | tail -20
```

Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git -C /workspaces/ocr-container/pd-ocr-labeler-spa add frontend/src/components/drawer/Worklist.tsx frontend/src/components/drawer/Worklist.test.tsx
git -C /workspaces/ocr-container/pd-ocr-labeler-spa commit -m "feat(worklist): bridge row click to selectionStore + add bulk-select checkboxes"
```

---

## Task 2: LineDetail GT — backend endpoint

**Files:**
- Modify: `src/pd_ocr_labeler_spa/api/lines_paragraphs.py`
- Modify: `tests/test_lines_paragraphs_router.py`

- [ ] **Step 1: Write failing backend tests**

Add to `tests/test_lines_paragraphs_router.py`:

```python
def test_set_line_gt_distributes_tokens(seeded_client, project_id, page_idx):
    """POST .../lines/0/set-gt distributes space-split tokens to words."""
    resp = seeded_client.post(
        f"/api/projects/{project_id}/pages/{page_idx}/lines/0/set-gt",
        json={"text": "hello world"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    # The refreshed PagePayload should have updated GT text
    lines = payload.get("line_matches") or []
    if lines:
        line0 = next((l for l in lines if l["line_index"] == 0), None)
        if line0:
            assert line0["ground_truth_line_text"] == "hello world"


def test_set_line_gt_clears_excess_words(seeded_client, project_id, page_idx):
    """Fewer tokens than words → remaining words get empty GT."""
    resp = seeded_client.post(
        f"/api/projects/{project_id}/pages/{page_idx}/lines/0/set-gt",
        json={"text": "only"},
    )
    assert resp.status_code == 200


def test_set_line_gt_rejects_ligatures(seeded_client, project_id, page_idx):
    """GT text containing ligature codepoints → 422."""
    resp = seeded_client.post(
        f"/api/projects/{project_id}/pages/{page_idx}/lines/0/set-gt",
        json={"text": "ﬀoo"},  # U+FB00 ff-ligature
    )
    assert resp.status_code == 422


def test_set_line_gt_404_unknown_line(seeded_client, project_id, page_idx):
    resp = seeded_client.post(
        f"/api/projects/{project_id}/pages/{page_idx}/lines/9999/set-gt",
        json={"text": "x"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && uv run pytest tests/test_lines_paragraphs_router.py -k "set_line_gt" -v 2>&1 | tail -20
```

Expected: FAIL — 404 (endpoint does not exist yet)

- [ ] **Step 3: Add the request model and endpoint to lines_paragraphs.py**

In `src/pd_ocr_labeler_spa/api/lines_paragraphs.py`, add the import of `_GT_FORBIDDEN_CODEPOINTS` to the existing `from .words import ...` block:

```python
from .words import (
    _GT_FORBIDDEN_CODEPOINTS,
    _page_not_loaded,
    _refresh_payload_response,
    _resolve_page_object,
    _write_cached_envelope_best_effort,
)
```

Then add the request model (after the existing `RefineBatchRequest` model, before the error helpers):

```python
class SetLineGtRequest(BaseModel):
    """``POST .../lines/{li}/set-gt`` body.

    Splits ``text`` by whitespace and distributes tokens to the line's
    words left-to-right. Excess tokens are concatenated onto the last
    word with a space separator; words with no corresponding token
    receive empty-string GT. Forbidden codepoints (ligatures, long-s)
    are rejected with 422 — mirror of ``UpdateWordGroundTruthRequest``.
    """

    text: str

    @field_validator("text")
    @classmethod
    def _reject_forbidden_codepoints(cls, v: str) -> str:
        bad = [hex(ord(ch)) for ch in v if ord(ch) in _GT_FORBIDDEN_CODEPOINTS]
        if bad:
            raise ValueError(
                f"GT text contains forbidden codepoints: {', '.join(bad)}. "
                "Normalize ligatures and long-s to ASCII before saving GT."
            )
        return v
```

Add the endpoint after `split_line_after_word_d1` and before the collective line endpoints section:

```python
@router.post(
    "/{project_id}/pages/{page_index}/lines/{line_index}/set-gt",
    response_model=PagePayload,
)
def set_line_gt(
    project_id: str,
    page_index: int,
    line_index: int,
    body: SetLineGtRequest,
    project_state: ProjectState = Depends(get_project_state),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """``POST .../lines/{li}/set-gt`` — set line GT by distributing tokens.

    Splits ``body.text`` on whitespace; assigns each token to the
    corresponding word in the line left-to-right.  Excess tokens
    (more tokens than words) are concatenated with a space onto the
    last word.  Words with no corresponding token receive empty-string GT.

    Use this to commit the LineDetail right-panel GT input on blur.
    """

    def _mutate(_page: Any, line: Any) -> bool:
        words = list(getattr(line, "words", []) or [])
        if not words:
            return True
        tokens = body.text.split()
        for i, word in enumerate(words):
            if i < len(tokens):
                if i == len(words) - 1:
                    # Last word absorbs remaining tokens.
                    word.ground_truth_text = " ".join(tokens[i:])
                else:
                    word.ground_truth_text = tokens[i]
            else:
                word.ground_truth_text = ""
        return True

    return _line_mutation_handler(
        project_id=project_id,
        page_index=page_index,
        line_index=line_index,
        project_state=project_state,
        settings=settings,
        mutate=_mutate,
        mutation_label="set_line_gt",
    )
```

Also add `SetLineGtRequest` to `__all__` at the bottom of the file.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && uv run pytest tests/test_lines_paragraphs_router.py -k "set_line_gt" -v 2>&1 | tail -20
```

Expected: PASS (the seeded tests that need a real page object may be skipped/partial — that is fine; the 404 and 422 tests must pass)

- [ ] **Step 5: Regenerate OpenAPI types**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && make openapi-export AI=1 2>&1 | tail -10
```

Expected: `frontend/src/api/types.ts` updated with `SetLineGtRequest` schema.

- [ ] **Step 6: Commit**

```bash
git -C /workspaces/ocr-container/pd-ocr-labeler-spa add src/pd_ocr_labeler_spa/api/lines_paragraphs.py tests/test_lines_paragraphs_router.py frontend/src/api/types.ts
git -C /workspaces/ocr-container/pd-ocr-labeler-spa commit -m "feat(api): POST lines/{li}/set-gt — distribute line GT text to words"
```

---

## Task 3: LineDetail GT — frontend hook + wire commit

**Files:**
- Modify: `frontend/src/hooks/useLineMutations.ts`
- Modify: `frontend/src/components/right-panel/LineDetail.tsx`
- Modify: `frontend/src/hooks/useLineMutations.test.tsx`

- [ ] **Step 1: Write failing test for useSetLineGt**

Add to `frontend/src/hooks/useLineMutations.test.tsx`:

```typescript
describe("useSetLineGt", () => {
  it("posts to lines/{li}/set-gt with text", async () => {
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/set-gt", async ({ request }) => {
        const body = await request.json() as { text: string };
        return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] }, { status: 200 });
      }),
    );
    const { result } = renderHook(() => useSetLineGt("p1", 0), { wrapper });
    act(() => { result.current.mutate({ lineIndex: 2, text: "hello world" }); });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/hooks/useLineMutations.test.tsx -t "useSetLineGt" 2>&1 | tail -20
```

Expected: FAIL — `useSetLineGt` not defined.

- [ ] **Step 3: Add useSetLineGt to useLineMutations.ts**

Add to `frontend/src/hooks/useLineMutations.ts` after `useMergeLines`:

```typescript
// ─── useSetLineGt ──────────────────────────────────────────────────────────

/**
 * Set line-level ground-truth text by distributing space-split tokens to words.
 *
 * POST /api/projects/{pid}/pages/{idx}/lines/{li}/set-gt
 * Body: { text: string }
 *
 * Call on blur/Enter from LineDetail's GT input.
 */
export function useSetLineGt(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number; text: string }>({
    mutationFn: ({ lineIndex, text }) =>
      apiPost<PagePayload>(
        `${pageBase(projectId, pageIndex)}/lines/${lineIndex}/set-gt`,
        { text },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/hooks/useLineMutations.test.tsx -t "useSetLineGt" 2>&1 | tail -20
```

Expected: PASS

- [ ] **Step 5: Write failing test for GTRow commit**

Add to `frontend/src/components/right-panel/LineDetail.test.tsx` (or create it):

```typescript
it("commits GT text on blur via set-gt endpoint", async () => {
  let capturedText: string | undefined;
  server.use(
    http.post("/api/projects/:pid/pages/:idx/lines/:li/set-gt", async ({ request }) => {
      const body = await request.json() as { text: string };
      capturedText = body.text;
      return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
    }),
  );
  // render LineDetail with a line that has GT text "old text"
  const line = makeLine({ line_index: 0, ground_truth_line_text: "old text" });
  const page = makePage({ line_matches: [line] });
  render(<LineDetail page={page} projectId="p1" pageIndex={0} />, { wrapper });
  // selectLine(0) so LineDetailInner renders
  act(() => selectLine(0));
  const input = await screen.findByTestId("line-detail-gt-input");
  await userEvent.clear(input);
  await userEvent.type(input, "new text");
  fireEvent.blur(input);
  await waitFor(() => expect(capturedText).toBe("new text"));
});

it("reverts GT text on Escape without committing", async () => {
  const line = makeLine({ line_index: 0, ground_truth_line_text: "original" });
  const page = makePage({ line_matches: [line] });
  render(<LineDetail page={page} projectId="p1" pageIndex={0} />, { wrapper });
  act(() => selectLine(0));
  const input = await screen.findByTestId("line-detail-gt-input");
  await userEvent.clear(input);
  await userEvent.type(input, "changed");
  await userEvent.keyboard("{Escape}");
  expect(input).toHaveValue("original");
});
```

- [ ] **Step 6: Run test to verify it fails**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/right-panel/LineDetail.test.tsx 2>&1 | tail -20
```

Expected: FAIL

- [ ] **Step 7: Wire GTRow in LineDetail.tsx**

In `frontend/src/components/right-panel/LineDetail.tsx`:

Add import at top:
```typescript
import { useSetLineGt } from "../../hooks/useLineMutations";
```

Change `GTRowProps` to accept mutation context:
```typescript
interface GTRowProps {
  line: LineMatch;
  projectId: string;
  pageIndex: number;
}
```

Replace the `GTRow` function body:
```typescript
function GTRow({ line, projectId, pageIndex }: GTRowProps) {
  const [gtText, setGtText] = useState(line.ground_truth_line_text ?? "");
  const setLineGt = useSetLineGt(projectId, pageIndex);

  // Keep local state in sync when the line prop updates from a server refresh.
  useEffect(() => {
    setGtText(line.ground_truth_line_text ?? "");
  }, [line.ground_truth_line_text]);

  function commit() {
    const trimmed = gtText.trim();
    const original = (line.ground_truth_line_text ?? "").trim();
    if (trimmed !== original) {
      setLineGt.mutate({ lineIndex: line.line_index, text: trimmed });
    }
  }

  return (
    <div className="px-3 py-2 border-b border-border-1 flex-shrink-0">
      <label className="block text-[10px] text-ink-3 mb-1 uppercase tracking-wide">
        Ground Truth
      </label>
      <input
        type="text"
        data-testid="line-detail-gt-input"
        value={gtText}
        onChange={(e) => setGtText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.currentTarget.blur();
          }
          if (e.key === "Escape") {
            setGtText(line.ground_truth_line_text ?? "");
          }
        }}
        placeholder="Enter ground truth text…"
        className="w-full text-[11px] font-mono bg-bg-surface border border-border-2 rounded px-2 py-1 text-ink-1 focus:outline-none focus:border-accent transition-colors"
        aria-label="Line ground truth text"
      />
      {line.ocr_line_text && (
        <p className="text-[10px] text-ink-3 mt-1 truncate">
          OCR: <span className="font-mono">{line.ocr_line_text}</span>
        </p>
      )}
    </div>
  );
}
```

Add `useEffect` to the imports at the top of the file:
```typescript
import { useSyncExternalStore, useState, useEffect } from "react";
```

Update the `GTRow` call site inside `LineDetailInner` to pass the new props:
```typescript
<GTRow line={line} projectId={projectId} pageIndex={pageIndex} />
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/right-panel/LineDetail.test.tsx 2>&1 | tail -20
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git -C /workspaces/ocr-container/pd-ocr-labeler-spa add frontend/src/hooks/useLineMutations.ts frontend/src/components/right-panel/LineDetail.tsx frontend/src/hooks/useLineMutations.test.tsx frontend/src/components/right-panel/LineDetail.test.tsx
git -C /workspaces/ocr-container/pd-ocr-labeler-spa commit -m "feat(line-detail): wire GT input commit on blur/Enter via set-gt endpoint"
```

---

## Task 4: Rail mode → Canvas interaction mode sync

**Files:**
- Modify: `frontend/src/components/PageImageCanvas.tsx`
- Modify: `frontend/src/stores/viewport-store.ts` (read to confirm exported names)

- [ ] **Step 1: Confirm viewport-store exports**

Read `frontend/src/stores/viewport-store.ts` to confirm that `exitToSelectMode`, `toggleAddWordMode`, `toggleEraseMode`, and `viewportStore` are exported. If names differ, adjust the steps below.

```bash
grep -n "export" /workspaces/ocr-container/pd-ocr-labeler-spa/frontend/src/stores/viewport-store.ts | head -20
```

Expected output should include all four of: `exitToSelectMode`, `toggleAddWordMode`, `toggleEraseMode`, `viewportStore`.

- [ ] **Step 2: Write failing test for rail mode sync**

Add to `frontend/src/components/PageImageCanvas.test.tsx` (or create it):

```typescript
import { railStore } from "../../stores/rail-store";
import { viewportStore } from "../../stores/viewport-store";

describe("rail mode → canvas sync", () => {
  afterEach(() => {
    railStore.reset();
  });

  it("setting rail mode to erase activates viewportStore erase mode", () => {
    render(<PageImageCanvas imageUrl="/img.png" encoded={null} />);
    act(() => railStore.getState().setMode("erase"));
    expect(viewportStore.getState().mode).toBe("erase");
  });

  it("setting rail mode to annotate activates add-word mode", () => {
    render(<PageImageCanvas imageUrl="/img.png" encoded={null} />);
    act(() => railStore.getState().setMode("annotate"));
    expect(viewportStore.getState().mode).toBe("add-word");
  });

  it("setting rail mode to view resets to select mode", () => {
    // First put canvas in erase mode via rail
    render(<PageImageCanvas imageUrl="/img.png" encoded={null} />);
    act(() => railStore.getState().setMode("erase"));
    act(() => railStore.getState().setMode("view"));
    expect(viewportStore.getState().mode).toBe("select");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/PageImageCanvas.test.tsx -t "rail mode" 2>&1 | tail -20
```

Expected: FAIL — viewportStore mode unchanged.

- [ ] **Step 4: Add rail-mode subscription to PageImageCanvas.tsx**

In `frontend/src/components/PageImageCanvas.tsx`, find the existing `railStore.subscribe` useEffect (around line 222):

```typescript
// Subscribe to rail target changes (Slice 13 — target-scoped bbox opacity).
useEffect(() => {
  const unsub = railStore.subscribe(() => setRailTarget(railStore.getState().target));
  return unsub;
}, []);
```

Add a NEW useEffect immediately after it:

```typescript
// Sync rail interaction mode to viewportStore so the canvas responds to
// the rail mode buttons (region/annotate/erase/view).
useEffect(() => {
  const unsub = railStore.subscribe(() => {
    const railMode = railStore.getState().mode;
    const current = viewportStore.getState().mode;
    if (railMode === "erase" && current !== "erase") {
      toggleEraseMode();
    } else if (railMode === "annotate" && current !== "add-word") {
      toggleAddWordMode();
    } else if ((railMode === "view" || railMode === "region") && current !== "select") {
      exitToSelectMode();
    }
  });
  return unsub;
}, []);
```

`toggleEraseMode`, `toggleAddWordMode`, and `exitToSelectMode` are already imported at the top of the file (confirmed in the existing import block at line 66–67).

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/PageImageCanvas.test.tsx -t "rail mode" 2>&1 | tail -20
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git -C /workspaces/ocr-container/pd-ocr-labeler-spa add frontend/src/components/PageImageCanvas.tsx frontend/src/components/PageImageCanvas.test.tsx
git -C /workspaces/ocr-container/pd-ocr-labeler-spa commit -m "feat(canvas): sync rail mode changes to viewport interaction mode"
```

---

## Task 5: QuickSearch text filtering

**Files:**
- Modify: `frontend/src/stores/worklist-store.ts`
- Modify: `frontend/src/components/shell/QuickSearch.tsx`
- Modify: `frontend/src/components/drawer/Worklist.tsx`
- Modify: `frontend/src/components/shell/QuickSearch.test.tsx`

- [ ] **Step 1: Write failing test — worklistStore searchQuery**

Add to `frontend/src/stores/worklist-store.test.ts`:

```typescript
describe("searchQuery", () => {
  beforeEach(() => worklistStore.reset());

  it("starts as empty string", () => {
    expect(worklistStore.getState().searchQuery).toBe("");
  });

  it("setSearchQuery updates the field", () => {
    worklistStore.setSearchQuery("hello");
    expect(worklistStore.getState().searchQuery).toBe("hello");
  });

  it("reset clears searchQuery", () => {
    worklistStore.setSearchQuery("something");
    worklistStore.reset();
    expect(worklistStore.getState().searchQuery).toBe("");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/stores/worklist-store.test.ts -t "searchQuery" 2>&1 | tail -20
```

Expected: FAIL — `searchQuery` undefined, `setSearchQuery` not a function.

- [ ] **Step 3: Add searchQuery to worklist-store.ts**

In `frontend/src/stores/worklist-store.ts`, update `WorklistState`:

```typescript
export interface WorklistState {
  activeFilter: MatchFilter;
  sort: WorklistSort;
  selectedLineIndex: number | null;
  selectedIds: number[];
  /** Text filter applied to OCR/GT line text in the worklist. Empty string = no filter. */
  searchQuery: string;
}
```

Update initial state:

```typescript
let state: WorklistState = {
  activeFilter: "unvalidated",
  sort: "index",
  selectedLineIndex: null,
  selectedIds: [],
  searchQuery: "",
};
```

Add the mutator function inside `createWorklistStore`:

```typescript
function setSearchQuery(query: string) {
  state = { ...state, searchQuery: query };
  notify();
}
```

Add to the `reset` body:

```typescript
function reset() {
  state = {
    activeFilter: "unvalidated",
    sort: "index",
    selectedLineIndex: null,
    selectedIds: [],
    searchQuery: "",
  };
  notify();
}
```

Add `setSearchQuery` to the returned object:

```typescript
return {
  getState: () => state,
  setActiveFilter,
  setSort,
  setSelectedLineIndex,
  setSearchQuery,
  reset,
  selectAll,
  clearBulk,
  toggle,
  subscribe: (cb: Listener) => {
    listeners.add(cb);
    return () => { listeners.delete(cb); },
  },
};
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/stores/worklist-store.test.ts -t "searchQuery" 2>&1 | tail -20
```

Expected: PASS

- [ ] **Step 5: Write failing test — QuickSearch updates worklistStore**

Add to `frontend/src/components/shell/QuickSearch.test.tsx`:

```typescript
import { worklistStore } from "../../stores/worklist-store";

beforeEach(() => worklistStore.reset());

it("typing in the input updates worklistStore.searchQuery", async () => {
  render(<QuickSearch />);
  const input = screen.getByTestId("quick-search-input");
  await userEvent.type(input, "foo");
  expect(worklistStore.getState().searchQuery).toBe("foo");
});

it("pressing Escape clears the query and worklistStore", async () => {
  render(<QuickSearch />);
  const input = screen.getByTestId("quick-search-input");
  await userEvent.type(input, "bar");
  await userEvent.keyboard("{Escape}");
  expect(input).toHaveValue("");
  expect(worklistStore.getState().searchQuery).toBe("");
});

it("input is no longer readOnly", () => {
  render(<QuickSearch />);
  const input = screen.getByTestId("quick-search-input");
  expect(input).not.toHaveAttribute("readOnly");
});
```

- [ ] **Step 6: Run test to verify it fails**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/shell/QuickSearch.test.tsx 2>&1 | tail -20
```

Expected: FAIL — input is readOnly, no store update.

- [ ] **Step 7: Wire QuickSearch.tsx**

Replace the `QuickSearch` component in `frontend/src/components/shell/QuickSearch.tsx`:

```typescript
import { useCallback, useState } from "react";
import { Search } from "lucide-react";
import { dialogStore } from "../../stores/dialog-store";
import { worklistStore } from "../../stores/worklist-store";

export function QuickSearch() {
  const openHotkeyHelp = useCallback(() => {
    dialogStore.open("hotkeyHelp");
  }, []);
  const [query, setQuery] = useState("");

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setQuery(val);
    worklistStore.setSearchQuery(val);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setQuery("");
      worklistStore.setSearchQuery("");
      e.currentTarget.blur();
    }
  }

  return (
    <div
      data-testid="quick-search"
      className="flex items-center gap-1.5 h-7 px-2 rounded border border-border-2 bg-bg-sunk text-ink-3 min-w-[160px] max-w-[240px] w-full cursor-text"
      onClick={(e) => {
        const input = (e.currentTarget as HTMLElement).querySelector("input");
        input?.focus();
      }}
    >
      <Search size={11} aria-hidden="true" className="shrink-0 text-ink-3" />

      <input
        type="text"
        data-testid="quick-search-input"
        value={query}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="Search…"
        aria-label="Quick search"
        className="flex-1 bg-transparent text-[11px] text-ink-2 placeholder:text-ink-3 focus:outline-none cursor-text"
      />

      <button
        type="button"
        data-testid="quick-search-keycap"
        aria-label="Show keyboard shortcuts (⌘K)"
        title="Show keyboard shortcuts"
        onClick={(e) => {
          e.stopPropagation();
          openHotkeyHelp();
        }}
        className="shrink-0 flex items-center gap-0.5 px-1 py-0.5 rounded border border-border-2 bg-bg-raised text-[9px] font-medium text-ink-3 hover:text-ink-1 hover:border-ink-3 transition-colors leading-none"
      >
        <span aria-hidden="true">⌘K</span>
      </button>
    </div>
  );
}
```

- [ ] **Step 8: Run QuickSearch tests to verify they pass**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/shell/QuickSearch.test.tsx 2>&1 | tail -20
```

Expected: PASS

- [ ] **Step 9: Write failing test — Worklist filters by searchQuery**

Add to `frontend/src/components/drawer/Worklist.test.tsx`:

```typescript
it("filters rows by searchQuery in worklistStore", async () => {
  const lineMatches = [
    { line_index: 0, ocr_line_text: "hello world", ground_truth_line_text: "hello world", overall_match_status: "exact", is_fully_validated: false, validated_word_count: 0, total_word_count: 1, word_matches: [], paragraph_index: 0 },
    { line_index: 1, ocr_line_text: "foo bar", ground_truth_line_text: "foo bar", overall_match_status: "exact", is_fully_validated: false, validated_word_count: 0, total_word_count: 1, word_matches: [], paragraph_index: 0 },
  ];
  worklistStore.setActiveFilter("all");
  render(<Worklist lineMatches={lineMatches} />);
  expect(screen.getByTestId("worklist-row-0")).toBeInTheDocument();
  expect(screen.getByTestId("worklist-row-1")).toBeInTheDocument();

  act(() => worklistStore.setSearchQuery("foo"));
  expect(screen.queryByTestId("worklist-row-0")).not.toBeInTheDocument();
  expect(screen.getByTestId("worklist-row-1")).toBeInTheDocument();
});
```

- [ ] **Step 10: Run test to verify it fails**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/drawer/Worklist.test.tsx -t "filters rows by searchQuery" 2>&1 | tail -20
```

Expected: FAIL — both rows visible despite search query.

- [ ] **Step 11: Apply search filter in Worklist.tsx**

In `frontend/src/components/drawer/Worklist.tsx`, add a search filter function before the component:

```typescript
function filterBySearch(lines: LineMatch[], query: string): LineMatch[] {
  const q = query.trim().toLowerCase();
  if (!q) return lines;
  return lines.filter(
    (l) =>
      (l.ocr_line_text ?? "").toLowerCase().includes(q) ||
      (l.ground_truth_line_text ?? "").toLowerCase().includes(q),
  );
}
```

In the `Worklist` component body, add `searchQuery` to the destructured state and apply the filter:

```typescript
const { activeFilter, selectedLineIndex, sort, searchQuery } = state;

// Apply filter, then search, then sort.
const filtered = sortLines(
  filterBySearch(filterLines(lineMatches, activeFilter), searchQuery),
  sort,
);
```

- [ ] **Step 12: Run all Worklist tests to verify they pass**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && npx vitest run frontend/src/components/drawer/Worklist.test.tsx 2>&1 | tail -20
```

Expected: all PASS

- [ ] **Step 13: Commit**

```bash
git -C /workspaces/ocr-container/pd-ocr-labeler-spa add frontend/src/stores/worklist-store.ts frontend/src/components/shell/QuickSearch.tsx frontend/src/components/drawer/Worklist.tsx frontend/src/stores/worklist-store.test.ts frontend/src/components/shell/QuickSearch.test.tsx frontend/src/components/drawer/Worklist.test.tsx
git -C /workspaces/ocr-container/pd-ocr-labeler-spa commit -m "feat(search): wire QuickSearch input to filter worklist by OCR/GT text"
```

---

## Task 6: Full CI green check

**Files:** none

- [ ] **Step 1: Run full backend test suite**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && make test AI=1 2>&1 | tail -20
```

Expected: all PASS

- [ ] **Step 2: Run full frontend test suite**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && make frontend-test AI=1 2>&1 | tail -20
```

Expected: all PASS

- [ ] **Step 3: Run lint**

```bash
cd /workspaces/ocr-container/pd-ocr-labeler-spa && make lint AI=1 2>&1 | tail -20
```

Expected: no errors

---

## Self-Review

**Spec coverage:**
- WorklistRow → selectionStore: spec `docs/specs/2026-05-16-drawer-worklist-design.md` open question — ✅ Task 1
- WorklistRow checkboxes → selectedIds: spec open question re: "no UI affordance" — ✅ Task 1
- LineDetail GT commit: spec `docs/specs/2026-05-16-right-panel-detail-design.md` open question — ✅ Tasks 2 + 3
- Rail mode → canvas: spec `docs/specs/2026-05-16-shell-layout-design.md` open question — ✅ Task 4
- QuickSearch submit: spec `docs/specs/2026-05-16-shell-layout-design.md` open question — ✅ Task 5

**Placeholder scan:** None. All steps contain real code.

**Type consistency:**
- `useSetLineGt` takes `{ lineIndex: number; text: string }` in Task 3 step 3 and the test in step 1 uses same shape ✅
- `worklistStore.setSearchQuery(string)` defined in Task 5 step 3 and used in Tasks 5 step 7, 11 ✅
- `SetLineGtRequest` added to `__all__` in Task 2 step 3 ✅
- `searchQuery` added to both `WorklistState` interface and initial state in Task 5 step 3, destructured in step 11 ✅

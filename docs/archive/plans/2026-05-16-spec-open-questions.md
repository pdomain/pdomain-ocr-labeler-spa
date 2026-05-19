# Spec Open Questions Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (- [ ]) syntax.

**Goal:** Resolve 6 implementable open questions surfaced from the spec audit of
`2026-05-16-drawer-worklist-design.md`, `2026-05-16-right-panel-detail-design.md`, and
`2026-05-16-shell-layout-design.md`. Each task is self-contained and ends with a passing
test suite and a git commit.

**Architecture:** All changes are frontend-only. The backend is unchanged. Stores used:
`selectionStore` (selection-store.ts), `useUiPrefs` (ui-prefs.ts), `worklistStore`
(worklist-store.ts). Mutations used: `useValidateLine` (useLineMutations.ts). Toast
notifications use `toast` from `sonner`.

**Tech Stack:** FastAPI, React 19, Vite, TS, TanStack Query, Vitest

---

## Files to Create or Modify

| File | Action |
|---|---|
| `frontend/src/components/drawer/Hierarchy.tsx` | Modify — replace direct `selectionStore.setState` calls with canonical helpers |
| `frontend/src/components/drawer/Hierarchy.test.tsx` | Modify — add regression tests for helper usage |
| `frontend/src/pages/ProjectPage.tsx` | Modify — add `rightWidth` prop and `tabCounts` prop |
| `frontend/src/components/drawer/BulkActions.tsx` | Modify — add `onError` toast handlers to three mutation handlers |
| `frontend/src/components/drawer/BulkActions.test.tsx` | Modify — add error-toast tests |
| `frontend/src/components/right-panel/LineDetail.tsx` | Modify — wire "Validate selected" to `validateLine.mutate` per checked word |
| `frontend/src/components/shell/Rail.tsx` | Modify — add `onClick` to `rail-bulk-button` |

---

## Task 1: Hierarchy → canonical selectionStore helpers

**Files:**
- `frontend/src/components/drawer/Hierarchy.tsx`
- `frontend/src/components/drawer/Hierarchy.test.tsx`

The `handleSelect` callback in `Hierarchy.tsx` (lines 350–375) calls
`selectionStore.setState(...)` directly, bypassing the canonical action helpers
`selectLine`, `selectPara`, and `selectWord` exported from `selection-store.ts`.
These helpers also set the `level` and `path` fields atomically; the raw setState
calls leave `level` stale.

- [ ] Step 1: Add a failing test to `frontend/src/components/drawer/Hierarchy.test.tsx`.

  Append after the last existing test in the `describe` block:

  ```typescript
  it("selecting a line node uses selectLine helper and sets level=line", async () => {
    const page = makePage();
    render(<Hierarchy page={page} />);
    const user = userEvent.setup();

    // Click the first line node row
    const lineRow = screen.getByTestId("hierarchy-node-line-0");
    await user.click(lineRow);

    const state = selectionStore.getState();
    expect(state.selectedLines).toEqual([0]);
    expect(state.level).toBe("line");
    expect(state.selectedParagraphs).toEqual([]);
    expect(state.selectedWords).toEqual([]);
  });

  it("selecting a word node uses selectWord helper and sets level=word", async () => {
    const page = makePage();
    render(<Hierarchy page={page} />);
    const user = userEvent.setup();

    // Expand the paragraph and line first
    const paraExpander = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraExpander);
    const lineExpander = screen.getByTestId("hierarchy-node-line-0");
    await user.click(lineExpander);

    const wordRow = screen.getByTestId("hierarchy-node-word-0-0");
    await user.click(wordRow);

    const state = selectionStore.getState();
    expect(state.selectedWords).toEqual([[0, 0]]);
    expect(state.level).toBe("word");
    expect(state.selectedLines).toEqual([]);
    expect(state.selectedParagraphs).toEqual([]);
  });

  it("selecting a para node uses selectPara helper and sets level=para", async () => {
    const page = makePage();
    render(<Hierarchy page={page} />);
    const user = userEvent.setup();

    const paraRow = screen.getByTestId("hierarchy-node-para-0");
    await user.click(paraRow);

    const state = selectionStore.getState();
    expect(state.selectedParagraphs).toEqual([0]);
    expect(state.level).toBe("para");
    expect(state.selectedLines).toEqual([]);
    expect(state.selectedWords).toEqual([]);
  });
  ```

  Run `make frontend-test AI=1` and confirm the three new tests fail (they will pass or
  fail depending on whether `level` is currently wired — the point is to verify `level`
  is set correctly by the helpers).

- [ ] Step 2: Edit `frontend/src/components/drawer/Hierarchy.tsx`.

  Change the import at the top of the file. Find:

  ```typescript
  import { selectionStore } from "../../stores/selection-store";
  ```

  Replace with:

  ```typescript
  import {
    selectionStore,
    selectLine,
    selectPara,
    selectWord,
  } from "../../stores/selection-store";
  ```

- [ ] Step 3: In the same file, replace the `handleSelect` function body (lines 350–375):

  **Find (exact):**
  ```typescript
  const handleSelect = useCallback((id: string, node: TreeNode) => {
    setSelectedId(id);
    // Update selection-store
    if (node.kind === "line") {
      selectionStore.setState((s) => ({
        ...s,
        selectedLines: [node.lineIndex],
        selectedParagraphs: [],
        selectedWords: [],
      }));
    } else if (node.kind === "word") {
      selectionStore.setState((s) => ({
        ...s,
        selectedWords: [[node.lineIndex, node.wordIndex]],
        selectedLines: [],
        selectedParagraphs: [],
      }));
    } else if (node.kind === "para" && node.paraIndex !== null) {
      selectionStore.setState((s) => ({
        ...s,
        selectedParagraphs: [node.paraIndex!],
        selectedLines: [],
        selectedWords: [],
      }));
    }
  }, []);
  ```

  **Replace with:**
  ```typescript
  const handleSelect = useCallback((id: string, node: TreeNode) => {
    setSelectedId(id);
    // Use canonical helpers so level/path are set atomically.
    if (node.kind === "line") {
      selectLine(node.lineIndex);
    } else if (node.kind === "word") {
      selectWord(node.lineIndex, node.wordIndex);
    } else if (node.kind === "para" && node.paraIndex !== null) {
      selectPara(node.paraIndex);
    }
  }, []);
  ```

- [ ] Step 4: Run `make frontend-test AI=1` and confirm all three new tests pass and no
  existing Hierarchy tests regress.

- [ ] Step 5: Commit.

  ```
  git add frontend/src/components/drawer/Hierarchy.tsx \
           frontend/src/components/drawer/Hierarchy.test.tsx
  git commit -m "$(cat <<'EOF'
  fix(hierarchy): use canonical selectLine/selectPara/selectWord helpers

  handleSelect was calling selectionStore.setState directly, leaving
  the `level` and `path` fields stale. Replace with the atomic action
  helpers so the right panel and canvas overlay react to the correct
  selection level.

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 2: Right panel width per selection level

**Files:**
- `frontend/src/pages/ProjectPage.tsx`

`StudioShell` accepts a `rightWidth` prop (see `StudioShell.tsx` line 36). Currently
`ProjectPage` renders `<StudioShell ... />` without that prop, so the right panel is
always 520 px (the CSS variable default). The spec calls for 640 px when the selection
level is "line" or "block", and 520 px otherwise.

The `selectionStore` is already imported in `ProjectPage.tsx`. Read the `level` field
via `useSyncExternalStore` (pattern already used in the file for other stores) and pass
`rightWidth` conditionally.

- [ ] Step 1: Locate the existing selectionStore import and subscription in
  `frontend/src/pages/ProjectPage.tsx`. Confirm `selectionStore` is imported (search
  for `selectionStore` in the file). If a `useSyncExternalStore` bridge for the
  selection store is already present, note which snapshot variable holds `level`.

  Run:
  ```
  grep -n "selectionStore\|useSyncExternalStore" frontend/src/pages/ProjectPage.tsx | head -20
  ```

- [ ] Step 2: If no existing snapshot reads `level`, add the following bridge near the
  other store subscriptions at the top of the `ProjectPage` component body (before
  the `return` statement). Find the block that starts with `const uiPrefs =
  useSyncExternalStore(...)` and add after it:

  ```typescript
  const selectionLevel = useSyncExternalStore(
    selectionStore.subscribe,
    () => selectionStore.getState().level,
    () => "none" as const,
  );
  ```

  If `selectionStore` is not yet imported, add it to the existing import from
  `../../stores/selection-store` (or `../stores/selection-store` depending on the
  relative path used in the file).

- [ ] Step 3: Find the `<StudioShell` render in `ProjectPage.tsx` (around line 563).
  It currently reads:

  ```typescript
        <StudioShell
          headerHeight={0}
          header={headerSlot}
          rail={railSlot}
          drawer={drawerSlot}
          canvas={canvasSlot}
          right={rightSlot}
          drawerCollapsed={!drawerOpen}
        />
  ```

  Replace with:

  ```typescript
        <StudioShell
          headerHeight={0}
          header={headerSlot}
          rail={railSlot}
          drawer={drawerSlot}
          canvas={canvasSlot}
          right={rightSlot}
          drawerCollapsed={!drawerOpen}
          rightWidth={selectionLevel === "line" || selectionLevel === "block" ? 640 : 520}
        />
  ```

- [ ] Step 4: Verify TypeScript compiles cleanly:

  ```
  cd frontend && npx tsc --noEmit 2>&1 | head -30
  ```

- [ ] Step 5: Run `make frontend-test AI=1` to confirm no regressions.

- [ ] Step 6: Commit.

  ```
  git add frontend/src/pages/ProjectPage.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): widen right panel to 640px for line/block selection

  StudioShell rightWidth was unset (defaulting to 520px). Pass
  rightWidth=640 when selectionStore.level is "line" or "block" so
  LineDetail and BlockDetail have enough horizontal space.

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 3: Drawer tab counts from ProjectPage

**Files:**
- `frontend/src/pages/ProjectPage.tsx`

`Drawer` accepts a `tabCounts` prop (`Partial<Record<DrawerTab, number>>`). Currently
`ProjectPage` passes only `lineMatches` and `page` to `Drawer`, so no count badge is
shown on tabs (Gap 18 per hifi-gaps-plan).

The count for the "worklist" tab = number of lines where
`overall_match_status !== "exact"` OR where `is_fully_validated === false`, matching the
legacy labeler's "items needing attention" semantics. The "hierarchy" tab shows the total
line count (informational).

`lines` (the `line_matches` array from `pagePayload`) is already in scope in
`ProjectPage`.

- [ ] Step 1: In `frontend/src/pages/ProjectPage.tsx`, find the comment block around
  line 465–467 where `drawerSlot` is constructed:

  ```typescript
  // IS-3: Drawer wired with real Drawer component.
  // lineMatches is already computed above; page is pagePayload.
  const drawerSlot = <Drawer lineMatches={lines} page={pagePayload ?? undefined} />;
  ```

  Replace with:

  ```typescript
  // IS-3: Drawer wired with real Drawer component.
  // lineMatches is already computed above; page is pagePayload.
  // Gap 18: tabCounts — worklist shows lines needing attention, hierarchy shows total.
  const worklistCount = lines.filter(
    (l) => l.overall_match_status !== "exact" || !l.is_fully_validated,
  ).length;
  const drawerTabCounts: Partial<Record<DrawerTab, number>> = {
    worklist: worklistCount,
    hierarchy: lines.length,
  };
  const drawerSlot = (
    <Drawer lineMatches={lines} page={pagePayload ?? undefined} tabCounts={drawerTabCounts} />
  );
  ```

- [ ] Step 2: Confirm `DrawerTab` type is imported. Find the existing `Drawer` import
  line (e.g. `import { Drawer } from ...`). If `DrawerTab` is not already imported,
  update it:

  Find the current import like:
  ```typescript
  import { Drawer } from "../components/shell/Drawer";
  ```

  Replace with (or add `DrawerTab` to it if other items are already imported):
  ```typescript
  import { Drawer } from "../components/shell/Drawer";
  import type { DrawerTab } from "../stores/ui-prefs";
  ```

  (Note: `DrawerTab` is exported from `ui-prefs.ts`. If it is already imported
  from somewhere else, skip this step.)

- [ ] Step 3: Verify TypeScript compiles cleanly:

  ```
  cd frontend && npx tsc --noEmit 2>&1 | head -30
  ```

- [ ] Step 4: Run `make frontend-test AI=1` — confirm no regressions.

- [ ] Step 5: Commit.

  ```
  git add frontend/src/pages/ProjectPage.tsx
  git commit -m "$(cat <<'EOF'
  feat(drawer): pass tabCounts to Drawer from ProjectPage (Gap 18)

  Worklist tab now shows count of lines where overall_match_status
  is not exact or the line is unvalidated. Hierarchy tab shows total
  line count. Both counts update reactively with the page data.

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 4: BulkActions error toasts

**Files:**
- `frontend/src/components/drawer/BulkActions.tsx`
- `frontend/src/components/drawer/BulkActions.test.tsx`

The three async handlers in `BulkActions.tsx` (`handleMarkReviewed`,
`handleRerunMatch`, `handleExport`) currently log errors to `console.error` with a
comment "Surface in production via toast; for now just log." Replace these with actual
`toast.error(e.message)` calls from `sonner` (already a dependency in this repo).

- [ ] Step 1: Add failing tests to `frontend/src/components/drawer/BulkActions.test.tsx`.

  At the top of the file, add to the import block:
  ```typescript
  import { vi, type MockInstance } from "vitest";
  ```
  (merge with existing `vi` import if already present)

  Append the following tests inside the existing `describe` block, after all existing
  tests:

  ```typescript
  describe("error toasts", () => {
    let toastErrorSpy: MockInstance;

    beforeEach(async () => {
      const sonner = await import("sonner");
      toastErrorSpy = vi.spyOn(sonner.toast, "error").mockImplementation(() => "t1");
    });

    it("shows toast.error when mark-reviewed fetch fails", async () => {
      // Pre-select a line
      worklistStore.toggle(2);
      // Force fetch to fail
      vi.spyOn(global, "fetch").mockResolvedValueOnce(
        new Response(JSON.stringify({ message: "Server error" }), { status: 500 }),
      );

      renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("bulk-actions-mark-reviewed"));

      // Wait for async handler
      await vi.waitFor(() => {
        expect(toastErrorSpy).toHaveBeenCalledWith("Server error");
      });
    });

    it("shows toast.error when re-run-match fetch fails", async () => {
      worklistStore.toggle(3);
      vi.spyOn(global, "fetch").mockResolvedValueOnce(
        new Response(JSON.stringify({ message: "OCR unavailable" }), { status: 503 }),
      );

      renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("bulk-actions-rerun-match"));

      await vi.waitFor(() => {
        expect(toastErrorSpy).toHaveBeenCalledWith("OCR unavailable");
      });
    });

    it("shows toast.error when export fetch fails", async () => {
      worklistStore.toggle(4);
      vi.spyOn(global, "fetch").mockResolvedValueOnce(
        new Response(JSON.stringify({ message: "Export failed" }), { status: 500 }),
      );

      renderWithQuery(<BulkActions projectId="p1" pageIndex={0} />);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("bulk-actions-export"));

      await vi.waitFor(() => {
        expect(toastErrorSpy).toHaveBeenCalledWith("Export failed");
      });
    });
  });
  ```

  Run `make frontend-test AI=1` and confirm the three new tests fail (toast.error is
  not yet called).

- [ ] Step 2: Edit `frontend/src/components/drawer/BulkActions.tsx`.

  Add the `toast` import at the top of the file, after the existing imports:

  ```typescript
  import { toast } from "sonner";
  ```

- [ ] Step 3: Replace the three `catch` blocks in the same file.

  **In `handleMarkReviewed`**, find:
  ```typescript
    } catch (e) {
      // Surface in production via toast; for now just log.
      console.error("Mark reviewed failed:", e);
    }
  ```
  Replace with:
  ```typescript
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Mark reviewed failed");
    }
  ```

  **In `handleRerunMatch`**, find:
  ```typescript
    } catch (e) {
      console.error("Re-run match failed:", e);
    }
  ```
  Replace with:
  ```typescript
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Re-run match failed");
    }
  ```

  **In `handleExport`**, find:
  ```typescript
    } catch (e) {
      console.error("Export failed:", e);
    }
  ```
  Replace with:
  ```typescript
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  ```

- [ ] Step 4: Run `make frontend-test AI=1` — confirm all three new toast tests pass
  and no existing BulkActions tests regress.

- [ ] Step 5: Commit.

  ```
  git add frontend/src/components/drawer/BulkActions.tsx \
           frontend/src/components/drawer/BulkActions.test.tsx
  git commit -m "$(cat <<'EOF'
  fix(bulk-actions): surface error toasts instead of console.error

  The three bulk-action handlers (mark-reviewed, re-run-match, export)
  had TODO comments to add toast.error. Wire them up using sonner so
  errors are visible to the user in the UI, not just in the console.

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 5: LineDetail bulk validate wiring

**Files:**
- `frontend/src/components/right-panel/LineDetail.tsx`

The "Validate selected" button in the `line-detail-bulk-bar` section (lines 319–329)
calls only `clearChecked()`. It should call `validateLine.mutate` for each word index
in `checkedWords`. `validateLine` is the `useValidateLine` hook result, already in
scope in `LineDetailInner`. The `validate-batch` endpoint supports `scope: "word"` with
a `word_indices` array of `[lineIndex, wordIndex]` pairs.

There is no skip/invalidate endpoint for individual words at the word level (the
endpoint only accepts `validated: true | false` per the schema). "Skip selected" should
mark words as unvalidated (`validated: false`) using the same `validate-batch` endpoint
with `scope: "word"`.

- [ ] Step 1: Read lines 197–230 of
  `frontend/src/components/right-panel/LineDetail.tsx` to confirm the inner component
  signature and that `validateLine` and `line.line_index` are in scope.

  Run:
  ```
  grep -n "validateLine\|line\.line_index\|checkedWords\|clearChecked" \
    frontend/src/components/right-panel/LineDetail.tsx | head -20
  ```

- [ ] Step 2: Add failing tests. Locate the LineDetail test file:

  ```
  ls frontend/src/components/right-panel/LineDetail.test.tsx 2>/dev/null || echo "no test file"
  ```

  If the file exists, append the following tests. If it does not exist, create it with
  the appropriate imports (mirror the pattern from `BulkActions.test.tsx`).

  The tests to add (append inside the existing describe block, or create a new
  `describe("bulk bar", ...)` block):

  ```typescript
  describe("bulk bar validate/skip wiring", () => {
    it("Validate selected calls validate-batch with validated=true for each checked word", async () => {
      const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
        new Response(JSON.stringify(makePage()), { status: 200 }),
      );
      const page = makePage();
      renderWithQuery(<LineDetail page={page} projectId="p1" pageIndex={0} />);
      const user = userEvent.setup();

      // Check first two word checkboxes
      const checkboxes = screen.getAllByRole("checkbox");
      await user.click(checkboxes[0]);
      await user.click(checkboxes[1]);

      // Click Validate selected
      await user.click(screen.getByTestId("line-detail-bulk-validate"));

      // Expect at least one validate-batch POST with validated=true
      const validateCalls = fetchSpy.mock.calls.filter(
        ([url]) => typeof url === "string" && url.includes("validate-batch"),
      );
      expect(validateCalls.length).toBeGreaterThan(0);
      const body = JSON.parse(validateCalls[0][1]?.body as string) as {
        validated: boolean;
        scope: string;
      };
      expect(body.validated).toBe(true);
      expect(body.scope).toBe("word");
    });

    it("Skip selected calls validate-batch with validated=false for each checked word", async () => {
      const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
        new Response(JSON.stringify(makePage()), { status: 200 }),
      );
      const page = makePage();
      renderWithQuery(<LineDetail page={page} projectId="p1" pageIndex={0} />);
      const user = userEvent.setup();

      const checkboxes = screen.getAllByRole("checkbox");
      await user.click(checkboxes[0]);

      await user.click(screen.getByTestId("line-detail-bulk-skip"));

      const validateCalls = fetchSpy.mock.calls.filter(
        ([url]) => typeof url === "string" && url.includes("validate-batch"),
      );
      expect(validateCalls.length).toBeGreaterThan(0);
      const body = JSON.parse(validateCalls[0][1]?.body as string) as {
        validated: boolean;
        scope: string;
      };
      expect(body.validated).toBe(false);
      expect(body.scope).toBe("word");
    });
  });
  ```

  Run `make frontend-test AI=1` — confirm the two new tests fail.

- [ ] Step 3: Add a helper mutation to `useLineMutations.ts` that validates a batch of
  specific word indices at word scope. Append to
  `frontend/src/hooks/useLineMutations.ts`:

  ```typescript
  // ─── useValidateWords (Task 5 — LineDetail bulk bar) ──────────────────────

  /**
   * Validate or invalidate a set of words identified by [lineIndex, wordIndex] pairs.
   *
   * Uses ``validate-batch`` with ``scope: "word"`` and sends the full list of
   * word index pairs in a single request.
   *
   * Endpoint: ``POST /api/projects/{pid}/pages/{idx}/words/validate-batch``
   */
  export function useValidateWords(projectId: string, pageIndex: number) {
    const qc = useQueryClient();
    return useMutation<
      unknown,
      Error,
      { wordPairs: [number, number][]; validated: boolean }
    >({
      mutationFn: ({ wordPairs, validated }) => {
        const body: ValidateBatchRequest = {
          scope: "word",
          line_indices: [],
          paragraph_indices: [],
          word_indices: wordPairs,
          validated,
        };
        return apiPost<unknown>(`${pageBase(projectId, pageIndex)}/words/validate-batch`, body);
      },
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
      },
    });
  }
  ```

  Note: `ValidateBatchRequest` already includes `validated` in the schema
  (confirm via `grep "Validated\|validated" frontend/src/api/types.ts | head -10`).
  If the generated type does not include `validated`, add it inline as an intersection:
  `body: { ...body_object, validated } as ValidateBatchRequest & { validated: boolean }`.

- [ ] Step 4: Wire `useValidateWords` into `LineDetailInner`.

  In `frontend/src/components/right-panel/LineDetail.tsx`, add the import:

  ```typescript
  import { useValidateLine, useMergeLines, useSetLineGt, useValidateWords } from "../../hooks/useLineMutations";
  ```
  (or add `useValidateWords` to the existing import from that module)

  Inside the `LineDetailInner` function body, after the existing
  `const validateLine = useValidateLine(...)` line, add:

  ```typescript
  const validateWords = useValidateWords(projectId, pageIndex);
  ```

- [ ] Step 5: Replace the "Validate selected" and "Skip selected" `onClick` handlers.

  **Find (Validate selected):**
  ```typescript
                onClick={() => {
                  /* bulk validate selected words */
                  clearChecked();
                }}
  ```
  **Replace with:**
  ```typescript
                onClick={() => {
                  const pairs: [number, number][] = Array.from(checkedWords).map(
                    (wi) => [line.line_index, wi],
                  );
                  validateWords.mutate({ wordPairs: pairs, validated: true });
                  clearChecked();
                }}
  ```

  **Find (Skip selected):**
  ```typescript
                onClick={() => {
                  /* bulk skip selected words */
                  clearChecked();
                }}
  ```
  **Replace with:**
  ```typescript
                onClick={() => {
                  const pairs: [number, number][] = Array.from(checkedWords).map(
                    (wi) => [line.line_index, wi],
                  );
                  validateWords.mutate({ wordPairs: pairs, validated: false });
                  clearChecked();
                }}
  ```

- [ ] Step 6: Run `make frontend-test AI=1` — confirm both new tests pass and no
  existing LineDetail tests regress.

- [ ] Step 7: Commit.

  ```
  git add frontend/src/hooks/useLineMutations.ts \
           frontend/src/components/right-panel/LineDetail.tsx \
           frontend/src/components/right-panel/LineDetail.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(line-detail): wire bulk validate/skip buttons to validate-batch endpoint

  "Validate selected" and "Skip selected" in the bulk bar previously only
  called clearChecked(). Now they call validate-batch scope=word for each
  checked word index, with validated=true and false respectively. Adds
  useValidateWords helper to useLineMutations.

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 6: Rail Bulk button wiring

**Files:**
- `frontend/src/components/shell/Rail.tsx`

The `rail-bulk-button` button (line 244) has no `onClick` handler. It should open the
Drawer to the "worklist" tab. The pattern used by other buttons in the codebase is
`useUiPrefs.setState({ drawerOpen: true, drawerTab: "worklist" })`.

There is no dedicated "bulk mode" toggle in `worklistStore` — the store exposes
`selectedIds` (populated via `toggle`/`selectAll`/`clearBulk`) but has no separate
`isBulkMode` flag. The button therefore only opens the drawer to the worklist tab
(which already surfaces the BulkActions bar when items are selected). A TODO comment
is added for a future "enter bulk mode" feature.

- [ ] Step 1: Add a failing test. Locate the Rail test file:

  ```
  ls frontend/src/components/shell/Rail.test.tsx 2>/dev/null || echo "no test file"
  ```

  If the test file exists, append the following test inside the existing describe block.
  If it does not exist, create it:

  ```typescript
  // Rail.test.tsx — tests for Rail.tsx
  import { describe, it, expect, beforeEach } from "vitest";
  import { render, screen } from "@testing-library/react";
  import userEvent from "@testing-library/user-event";
  import { Rail } from "./Rail";
  import { useUiPrefs } from "../../stores/ui-prefs";

  function renderRail() {
    return render(<Rail />);
  }

  describe("Rail bulk button", () => {
    beforeEach(() => {
      useUiPrefs.setState({ drawerOpen: false, drawerTab: "hierarchy" });
    });

    it("opens the drawer to the worklist tab on click", async () => {
      renderRail();
      const user = userEvent.setup();
      await user.click(screen.getByTestId("rail-bulk-button"));

      const state = useUiPrefs.getState();
      expect(state.drawerOpen).toBe(true);
      expect(state.drawerTab).toBe("worklist");
    });
  });
  ```

  Run `make frontend-test AI=1` — confirm the new test fails.

- [ ] Step 2: In `frontend/src/components/shell/Rail.tsx`, confirm `useUiPrefs` is
  already imported (the file uses it for theme and other state). If not, add:

  ```typescript
  import { useUiPrefs } from "../../stores/ui-prefs";
  ```

- [ ] Step 3: Find the `rail-bulk-button` render in `Rail.tsx` (around line 242–251):

  ```typescript
        <button
          type="button"
          data-testid="rail-bulk-button"
          title="Bulk actions"
          aria-label="Bulk actions"
          className="w-full flex flex-col items-center justify-center gap-0.5 py-1.5 rounded text-[9px] font-medium text-ink-3 hover:text-ink-2 hover:bg-bg-raised/50 transition-colors select-none"
        >
  ```

  Replace with (adding `onClick`):

  ```typescript
        <button
          type="button"
          data-testid="rail-bulk-button"
          title="Bulk actions"
          aria-label="Bulk actions"
          onClick={() => {
            // Open drawer to the worklist tab so the BulkActions bar is visible.
            // TODO: add a dedicated "enter bulk mode" flag to worklistStore when
            //       the multi-select UI needs to be activated programmatically.
            useUiPrefs.setState({ drawerOpen: true, drawerTab: "worklist" });
          }}
          className="w-full flex flex-col items-center justify-center gap-0.5 py-1.5 rounded text-[9px] font-medium text-ink-3 hover:text-ink-2 hover:bg-bg-raised/50 transition-colors select-none"
        >
  ```

- [ ] Step 4: Run `make frontend-test AI=1` — confirm the new Rail test passes and no
  existing Rail tests regress.

- [ ] Step 5: Commit.

  ```
  git add frontend/src/components/shell/Rail.tsx \
           frontend/src/components/shell/Rail.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(rail): wire bulk button to open drawer on worklist tab

  The rail-bulk-button had no onClick handler. Now clicking it sets
  drawerOpen=true and drawerTab="worklist" so the user lands directly
  on the Worklist panel where bulk selection and the BulkActions bar
  are available. A TODO marks the future "enter bulk mode" flag.

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Final verification

After all 6 tasks are committed, run the full frontend test suite and CI:

```
make frontend-test AI=1
make ci AI=1
```

All tests must pass (no new failures). If `make ci AI=1` fails on a non-frontend step
unrelated to these changes, document the failure and do not block the plan on it.

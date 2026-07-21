---
last_verified: 2026-07-21
created: 2026-07-21
owner: maintainers
kind: plan
status: draft
priority: now
repo: pdomain/pdomain-ocr-labeler-spa
related: GH #366 (residual; issue historically closed COMPLETED)
---

# Enable `noUncheckedIndexedAccess` in `tsconfig.test.json`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish residual #366 work by aligning frontend test TypeScript strictness with app
code: set `noUncheckedIndexedAccess: true` in `frontend/tsconfig.test.json` (currently the only
remaining relaxation), fix resulting test-file type errors, and make the flag enforceable so it
does not regress.

**Architecture:** Tests already compile under a dedicated project (`tsconfig.test.json` extends
`tsconfig.app.json`, with its own `include` of `*.test.*`, `__tests__/**`, and `src/test/**`).
App code already uses `noUncheckedIndexedAccess: true`. Other test-config flags already match or
exceed app strictness (`exactOptionalPropertyTypes`, `noPropertyAccessFromIndexSignature`,
`noUnusedLocals` / `noUnusedParameters`). Only `noUncheckedIndexedAccess: false` remains. Flip
that flag, fix diagnostics with the same patterns already used in some tests (e.g.
`calls[0]!.url` in `ProjectPage.test.tsx`), and add an explicit test-project typecheck command so
CI/local gates catch regressions. Prefer **one commit** — blast radius is modest and localized to
test files.

**Tech Stack:** TypeScript 5.9, Vitest 3, Testing Library, existing Vite/pnpm frontend toolchain.

**Prerequisite:** None. Pure frontend type-strictness; no backend or OpenAPI changes.

---

## Background / current state

| Config | `noUncheckedIndexedAccess` | Notes |
|---|---|---|
| `frontend/tsconfig.app.json` | `true` | Production SPA source |
| `frontend/tsconfig.test.json` | **`false`** | Only remaining relaxation vs app |
| `frontend/tsconfig.node.json` | (not set; not relevant) | Vite/config tooling |

Other flags already aligned on the test project:

- `exactOptionalPropertyTypes: true`
- `noPropertyAccessFromIndexSignature: true`
- `noUnusedLocals` / `noUnusedParameters: true`

**Enforcement gap today:**

- `pnpm typecheck` → `tsc --noEmit` uses root `tsconfig.json`, which only project-references
  `tsconfig.app.json` + `tsconfig.node.json`. **Test files are not typechecked by default.**
- `make frontend-test` / `pnpm test` → `vitest run` does **not** enable typecheck mode.
- `vitest.config.ts` only points `test.typecheck.tsconfig` at `./tsconfig.test.json` for when
  typecheck mode is requested; it is not currently part of `make ci`.

So #366 residual work is both (1) flip the flag and fix tests, and (2) optionally but strongly
recommended: wire a gate so the flag cannot silently drift.

---

## Blast-radius estimate (static survey; confirm with tsc)

**Corpus size:** ~90–110 Vitest files under `frontend/src/**/*.{test,spec}.{ts,tsx}` plus
`src/test/**` helpers.

**Likely to need edits:** **~15–25 test files** (not the full suite).

Static patterns that break under `noUncheckedIndexedAccess` (array/tuple/index access becomes
`T | undefined`):

| Pattern | Sample sites | Est. files |
|---|---|---|
| Property access after index: `calls[0].url`, `rects[0].getAttribute`, `ops[0].tool` | `ProjectPage.style.test.tsx`, `ProjectPage.toolbar.test.tsx`, `BBoxOverlay.test.tsx`, `ErasePixelsSection.test.tsx`, `selection-expand.test.ts` (`result.paragraphs[0].id`), `hotkey-bridge.test.ts` (`keyCaps[0].length`) | ~8–12 |
| Nested mock index: `mock.calls[0][1]`, `onRebox.mock.calls[0][0]` | `PageImageCanvas.test.tsx` | ~1–3 |
| Destructure possibly-undefined call: `const [args] = fn.mock.calls[0]` | `OCRConfigModal.test.tsx`, `PageImageCanvas.test.tsx` | ~2–3 |
| Fixture mutation without `!`: `page.line_matches![0].word_matches[0].word_index` | `PageImageCanvas.test.tsx`, `LineDetail.test.tsx` | ~2–3 |
| DOM list element used as definite: `getAllByTestId(...)[0]` then method call / `user.click` | `BBoxOverlay.test.tsx`, `Worklist.test.tsx`, `StructureSection.test.tsx` | ~3–4 |
| Tuple/array helper: `pairs[0][0]`, `body.char_bboxes[0].x`, `word_keys[0][0]` | `BulkWordActions.test.tsx`, `CharFixerSection.test.tsx`, `LineDetail.test.tsx` | ~3–4 |
| Numeric compare on mock order: `invocationCallOrder[0]` | `OcrGtCompareRow.test.tsx` | ~1 |

**Usually fine (no edit needed):**

- Array **literals** in expectations: `.toEqual([0])`, `selected_lines: [0]`.
- `expect(arr[0]).toEqual(...)` / `.toMatchObject(...)` / `.toBe(...)` when the value is only
  passed into `expect` (no property access on the indexed result).
- Already-defended sites: `calls[0]!.url` (`ProjectPage.test.tsx`), `words[0]!` /
  `line_matches![0]!.word_matches[0]!` in several right-panel tests.
- Type-level indexing: `Parameters<typeof X>[0]` (not a runtime value access).
- Casts that erase undefined: `items[0] as HTMLElement` (`Accordion.test.tsx`),
  `mock.calls[0] as [string, RequestInit]` (`ReboxSection.test.tsx`) — assertion is allowed;
  prefer `!` + cast only when needed for clarity.

**Estimate of diagnostic count:** on the order of **~50–100 errors**, concentrated in a few
heavy files (`BBoxOverlay.test.tsx`, `PageImageCanvas.test.tsx`, ProjectPage style/toolbar tests).
Most files will be clean.

Treat the static estimate as a planning bound; **Task 0 ground-truths the list via tsc**.

---

## Sample failing patterns and fix recipes

### Pattern A — Captured request / mock call property access

**Breaks:**

```ts
expect(calls[0].url).toContain("/words/validate-batch");
expect(calls[0].body).toEqual(expect.objectContaining({ scope: "line" }));
```

**Fix (preferred — already used in `ProjectPage.test.tsx`):**

```ts
await waitFor(() => {
  expect(calls.length).toBeGreaterThanOrEqual(1);
});
expect(calls[0]!.url).toContain("/words/validate-batch");
expect(calls[0]!.body).toEqual(expect.objectContaining({ scope: "line" }));
```

Or bind once after a length assertion:

```ts
expect(calls.length).toBeGreaterThanOrEqual(1);
const call = calls[0]!;
expect(call.url).toContain("...");
expect(call.body).toEqual(...);
```

### Pattern B — Nested `vi.fn().mock.calls` indexing

**Breaks:**

```ts
const [rect, modifier] = onBoxSelect.mock.calls[0];
expect(onBoxSelect.mock.calls[0][1]).toBe("remove");
const rect = onRebox.mock.calls[0][0];
```

**Fix:**

```ts
const firstCall = onBoxSelect.mock.calls[0]!;
const [rect, modifier] = firstCall;
// or
expect(onBoxSelect.mock.calls[0]![1]).toBe("remove");
const rect = onRebox.mock.calls[0]![0];
```

### Pattern C — Testing Library `getAllBy*` / `querySelectorAll` element use

**Breaks:**

```ts
const rect = getAllByTestId("konva-rect")[0];
expect(rect.getAttribute("data-fill")).toBe(expectedFill);

await user.click(screen.getAllByTestId("worklist-row-0")[0]);
await user.click(charButtons[2]);
```

**Fix:**

```ts
const rect = getAllByTestId("konva-rect")[0]!;
// or prefer singular query when identity is unique:
await user.click(screen.getByTestId("worklist-row-0"));
```

When multiple matches are intentional, assert length then `!`:

```ts
const rects = getAllByTestId("konva-rect");
expect(rects.length).toBeGreaterThanOrEqual(2);
expect(rects[0]!.getAttribute("data-x")).toBe("0");
expect(rects[1]!.getAttribute("data-x")).toBe("10");
```

### Pattern D — Fixture graph mutation

**Breaks:**

```ts
page.line_matches![0].word_matches[0].word_index = 3;
page.line_matches![0].ground_truth_line_text = "helo world";
```

(`!` only asserts `line_matches` is non-null; `[0]` is still `T | undefined`.)

**Fix:**

```ts
page.line_matches![0]!.word_matches[0]!.word_index = 3;
// or
const line = page.line_matches![0]!;
line.word_matches[0]!.word_index = 3;
```

Mirror existing good style in `WordDetail.test.tsx` /
`selection-expand.test.ts` (`line.word_matches[0]!.word_index = 3`).

### Pattern E — Body field after parse

**Breaks:**

```ts
const bbox0 = body.char_bboxes[0];
expect(typeof bbox0.x).toBe("number");
expect(body!.word_keys[0][0]).toBe(3);
```

**Fix:**

```ts
const bbox0 = body.char_bboxes[0]!;
expect(typeof bbox0.x).toBe("number");
expect(body!.word_keys[0]![0]).toBe(3);
```

### Pattern F — Tuple argument helpers

**Breaks:**

```ts
path: { lineId: pairs[0][0], wordId: pairs[0] },
```

**Fix:**

```ts
const first = pairs[0]!;
path: { lineId: first[0], wordId: first },
```

### Pattern G — Prefer expect-only when no property access is needed

If the test only needs equality of the whole element, leave it as:

```ts
expect(result.words[0]).toEqual({ id: "0-0", bbox: ... });
expect(capturedBodies[0]).toMatchObject({ path: "/data/projects" });
```

Only add `!` when TypeScript errors (property access, destructuring, or a callee that rejects
`undefined`).

### Anti-patterns to avoid

- Do **not** disable the flag per-file or re-introduce `noUncheckedIndexedAccess: false`.
- Do **not** blanket-cast entire mocks to `any`.
- Prefer `!` after a length/presence assertion over deep optional chaining that weakens the
  assertion (`calls[0]?.url` would hide a missing call).
- Do not change production (`tsconfig.app.json`) behavior; scope is test project only.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `frontend/tsconfig.test.json` | Modify | Set `noUncheckedIndexedAccess: true` (or remove override to inherit `true` from app); drop redundant flags only if intentionally simplifying |
| Test files with diagnostics (est. 15–25 under `frontend/src/**`) | Modify | Apply Pattern A–F fixes |
| `frontend/package.json` | Modify | Add `typecheck:test` script: `tsc -p tsconfig.test.json --noEmit` |
| `Makefile` (`lint` and/or `frontend-test` / new target) | Modify (recommended) | Invoke test typecheck so `make ci` enforces the flag |
| `frontend/src/toolchain.test.tsx` or a tiny config unit test | Optional | Assert test tsconfig keeps `noUncheckedIndexedAccess: true` (pdomain-ui has a similar contract test) |
| `AGENTS.md` open-work bullet for #366 | Modify | Remove residual backlog line once done |
| `docs/process/lint-deviations.md` | Modify only if any suppression remains | Should end with **no** test-tsconfig relaxation for this flag |

---

## Approach decision: one commit vs batch

**Recommendation: one commit (batch fix).**

Reasons:

1. Single flag flip; no intermediate product state of value.
2. Estimated ≤25 files / ≤100 diagnostics — one focused PR.
3. Partial enablement is not really possible per-file without `// @ts-nocheck` or splitting
   tsconfigs (worse than the residual).
4. Existing in-repo pattern (`calls[0]!`) already documents the fix style.

Do **not** multi-PR by directory unless Task 0 shows >>100 files or multi-hour churn.

---

## Task 0 — Baseline: measure failures before changing the flag

**Files:** none (read-only measurement)

- [ ] **Step 1: Confirm current flag is false**

```bash
cd /workspaces/pdomain/pdomain-ocr-labeler-spa
rg -n 'noUncheckedIndexedAccess' frontend/tsconfig.test.json frontend/tsconfig.app.json
```

Expected: app `true`, test `false`.

- [ ] **Step 2: Baseline typecheck of the test project (should be clean today)**

```bash
cd frontend
pnpm exec tsc -p tsconfig.test.json --noEmit
```

Expected: exit 0 (current relaxation). If this already fails, fix pre-existing test type errors
before flipping the flag — they are out of scope of #366 residual but block measurement.

- [ ] **Step 3: Dry-run failure inventory (temporary local edit, do not commit yet)**

Edit `frontend/tsconfig.test.json` to `"noUncheckedIndexedAccess": true`, then:

```bash
cd frontend
pnpm exec tsc -p tsconfig.test.json --noEmit 2>&1 | tee /tmp/tsconfig-test-strict.log
# summary helpers
rg -o 'frontend/src/[^(]+\.test\.tsx?' /tmp/tsconfig-test-strict.log | sort -u | wc -l
rg -o 'frontend/src/[^(]+\.test\.tsx?' /tmp/tsconfig-test-strict.log | sort -u
rg -c 'error TS' /tmp/tsconfig-test-strict.log || true
```

Record: unique file count, error count, top error codes (`TS2532` object possibly undefined is
the main one).

- [ ] **Step 4: Revert the temporary flip if not immediately continuing**

Keep the working tree intentional; either proceed to Task 1 in the same session or restore
`false` until ready.

---

## Task 1 — Flip the flag

**Files:**
- Modify: `frontend/tsconfig.test.json`

- [ ] **Step 1: Enable the flag**

Preferred minimal change:

```json
"noUncheckedIndexedAccess": true
```

Optional cleanup (same commit if low-risk): remove compilerOptions that merely restate app
defaults and keep only test-specific `types` + `include`. Do **not** weaken any other flag.

- [ ] **Step 2: Confirm tsc now reports the expected errors**

```bash
cd frontend
pnpm exec tsc -p tsconfig.test.json --noEmit 2>&1 | head -80
```

Expected: non-zero exit; errors concentrated in the surveyed files.

---

## Task 2 — Fix test diagnostics (batch)

**Files:** all files listed by Task 0 inventory (expected subset of):

High-likelihood:

- `frontend/src/pages/__tests__/ProjectPage.style.test.tsx`
- `frontend/src/pages/__tests__/ProjectPage.toolbar.test.tsx`
- `frontend/src/components/BBoxOverlay.test.tsx`
- `frontend/src/components/PageImageCanvas.test.tsx`
- `frontend/src/components/OCRConfigModal.test.tsx`
- `frontend/src/components/right-panel/LineDetail.test.tsx`
- `frontend/src/components/right-panel/sections/ErasePixelsSection.test.tsx`
- `frontend/src/components/right-panel/sections/CharFixerSection.test.tsx`
- `frontend/src/components/right-panel/sections/StructureSection.test.tsx`
- `frontend/src/components/right-panel/OcrGtCompareRow.test.tsx`
- `frontend/src/components/BulkWordActions.test.tsx`
- `frontend/src/components/drawer/Worklist.test.tsx`
- `frontend/src/lib/selection-expand.test.ts`
- `frontend/src/lib/hotkey-bridge.test.ts`
- `frontend/src/hooks/useNotificationStream.test.tsx`

- [ ] **Step 1: Fix by file, re-running tsc after each cluster**

```bash
cd frontend
pnpm exec tsc -p tsconfig.test.json --noEmit 2>&1 | rg 'error TS' | head -40
```

Apply Patterns A–F. Prefer:

1. `!` after an existing length/`toHaveBeenCalled` assertion.
2. Singular `getBy*` when a unique testid exists.
3. Local `const first = arr[0]!` when used multiple times.

- [ ] **Step 2: Full clean typecheck**

```bash
cd frontend
pnpm exec tsc -p tsconfig.test.json --noEmit
```

Expected: exit 0.

- [ ] **Step 3: Runtime tests still pass**

```bash
cd /workspaces/pdomain/pdomain-ocr-labeler-spa
make frontend-test AI=1
```

Expected: Vitest green. Type-only edits should not change runtime behavior.

---

## Task 3 — Enforce so the residual cannot regress

**Files:**
- Modify: `frontend/package.json`
- Modify: `Makefile` (recommended)
- Optional: small contract test for the tsconfig flag

- [ ] **Step 1: Add package script**

In `frontend/package.json`:

```json
"typecheck:test": "tsc -p tsconfig.test.json --noEmit"
```

Verify:

```bash
cd frontend && pnpm run typecheck:test
```

- [ ] **Step 2: Wire into Makefile / CI path**

Recommended options (pick one, keep it simple):

**Option A (minimal):** extend the existing frontend branch of `make lint` after app
`typecheck`:

```make
$(call _npm,run typecheck); \
$(call _npm,run typecheck:test); \
```

**Option B:** new `frontend-typecheck` target invoked from `ci` alongside `frontend-test`.

Do **not** rely on `vitest --typecheck` alone unless verified — project already documents
Vitest/Vite version friction; raw `tsc -p tsconfig.test.json` is the reliable gate.

- [ ] **Step 3 (optional contract test):** follow pdomain-ui’s
  `tests/tsconfig.contract.test.ts` style — read `tsconfig.test.json` and assert
  `compilerOptions.noUncheckedIndexedAccess === true` (or absent with app parent true). Only add
  if cheap; the Makefile gate is the real protection.

- [ ] **Step 4: Clear backlog pointer**

Remove or update the AGENTS.md open-work line:

> `#366 tighten tsconfig.test.json relaxations (status:backlog)`

---

## Task 4 — Full gate + commit

- [ ] **Step 1: CI**

```bash
cd /workspaces/pdomain/pdomain-ocr-labeler-spa
make ci AI=1
```

Expected: all targets pass, including the new test typecheck if wired into `lint`/`ci`.

- [ ] **Step 2: Single commit**

Suggested message:

```text
fix(frontend): enable noUncheckedIndexedAccess in tsconfig.test.json

Finish residual #366: align test TS project with app strictness, fix
indexed-access diagnostics in Vitest files, and typecheck the test
project in the frontend gate so the flag cannot regress.
```

Do **not** push unless explicitly asked.

---

## Acceptance criteria

1. `frontend/tsconfig.test.json` has `noUncheckedIndexedAccess: true` (or inherits `true` with
   no overriding `false`).
2. `pnpm exec tsc -p tsconfig.test.json --noEmit` exits 0.
3. `make frontend-test AI=1` exits 0.
4. A durable gate runs the test-project typecheck (`pnpm run typecheck:test` via Makefile/`make ci`).
5. No new lint suppressions or per-file `@ts-nocheck` for this flag.
6. AGENTS.md no longer lists #366 residual as open work.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Underestimated file count | Task 0 inventory first; if >40 files, still one PR but budget more time; do not re-disable the flag |
| `exactOptionalPropertyTypes` interactions surface only after fixes | Fix those too if they appear; do not flip EOPT off |
| Vitest typecheck mode flaky with Vite 6 | Prefer `tsc -p tsconfig.test.json`; treat vitest typecheck as optional |
| Over-use of `!` hides empty arrays | Keep length / `toHaveBeenCalled` assertions immediately above `!` |
| Helpers under `src/test/**` also typechecked | Include them in the fix pass; they are in `tsconfig.test.json` include |

---

## Out of scope

- Changing `tsconfig.app.json` (already strict).
- Enabling other experimental TS flags.
- Runtime test refactors unrelated to type errors.
- Glyph M11 or other backlog items.

---

## Implementation order (summary)

1. Measure with temporary flag flip + `tsc -p tsconfig.test.json`.
2. Commit-ready flip to `true`.
3. Batch-fix ~15–25 test files using Patterns A–F.
4. Add `typecheck:test` + Makefile/CI wire-up.
5. `make frontend-test` + `make ci`, one commit, update AGENTS.md.

**Effort estimate:** small (≈0.5–1.5 engineer-hours) if Task 0 confirms ≤25 files; still one PR if
somewhat higher.

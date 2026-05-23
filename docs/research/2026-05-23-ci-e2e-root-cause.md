# CI E2E Root Cause Analysis — pd-ocr-labeler-spa

**Date:** 2026-05-23
**CI run:** 26314941850 (commit `ccb14b5` — "fix(ci): replace npm ci with pnpm/action-setup")
**Symptom:** 80/85 Playwright e2e tests fail; `#root` is hidden; React never mounts.
**Prior research:** `docs/research/2026-05-22-ci-red-diagnosis.md` (branch `research/ci-red-diagnosis`)
**In-flight fix attempt:** branch `fix/ci-react-dedupe-and-pnpm-guard` (commit `ae0f789`)

---

## (a) Actual Runtime Error Message

```
Cannot read properties of undefined (reading 'ReactCurrentBatchConfig')
```

Captured via Playwright `page.on("pageerror", ...)` in `test_diag_temp.py` and confirmed in
the 2026-05-22 research doc. This is the canonical JavaScript exception for a **dual React
instance** — two separate `react` module objects are loaded in the same page, each with its own
internal dispatcher state, so one instance's hooks cannot find the other's dispatcher.

The error originates in `react-dom` when it tries to access
`ReactCurrentBatchConfig` from the wrong React instance. React silently fails to render;
`#root` stays present in the DOM but retains zero dimensions (Playwright reports it as hidden).

---

## (b) Precise Root Cause

**Commit that introduced the regression:** `f8e20dc` ("Merge wip/bump-pd-ui-alpha1: bump
@concavetrillion/pd-ui to 0.1.0-alpha.1"), landed before `ccb14b5`.

**Mechanism — two-layer dual-instance problem:**

### Layer 1: react / react-dom dual instance (primary)

`@concavetrillion/pd-ui@0.1.0-alpha.1` declares:

```json
"peerDependencies": { "react": "^18.0.0", "react-dom": "^18.0.0" }
```

pnpm 11 resolves peer dependencies inside a package-scoped symlink tree. Even though both the
labeler-spa and pd-ui ultimately resolve to the same physical files (`react@19.2.6`), Vite
follows symlinks individually to build its module graph. It de-duplicates by resolved path,
not by inode. pnpm creates these two resolution paths:

- `frontend/node_modules/react` → `react@19.2.6` (labeler-spa scope)
- `frontend/node_modules/.pnpm/@concavetrillion+pd-ui@0.1.0-alpha.1.../node_modules/react`
  → also `react@19.2.6` (pd-ui scope)

Vite treats these as **two distinct modules** and bundles both. React's hook dispatcher
(`ReactCurrentBatchConfig`) lives inside one instance; calls from the other instance crash.

`frontend/vite.config.ts` on `main` (commit `ccb14b5`) has **no `resolve.dedupe`**:

```ts
resolve: {
  alias: { "@": path.resolve(__dirname, "./src") },
  // NO dedupe — both react paths are bundled separately
},
```

### Layer 2: react-konva dual instance (secondary, same mechanism)

`@concavetrillion/pd-ui@0.1.0-alpha.1` also declares `react-konva: "^18.0.0"` as a
**direct dependency** (not a peer dep). pnpm installs `react-konva@18.2.16` inside pd-ui's
scope while the labeler-spa uses `react-konva@19.2.4` at top level.

```
frontend/node_modules/.pnpm/
  react-konva@18.2.16_...  ← pd-ui scope (react-reconciler@~0.29)
  react-konva@19.2.4_...   ← labeler-spa scope (react-reconciler@~0.33)
```

`react-konva@18.2.16` depends on `react-reconciler@~0.29.0`; `react-konva@19.2.4` depends on
`react-reconciler@~0.33.0`. **Two separate react-reconciler instances** are present in
the bundle. This is a second source of the `ReactCurrentBatchConfig` crash independently of
the react/react-dom issue.

Confirmed by `ls node_modules/.pnpm/ | grep react-reconciler`:
```
react-reconciler@0.29.2_react@19.2.6
react-reconciler@0.33.0_react@19.2.6
```

Both versions are present. Without dedupe on `react-konva`, both enter the Vite bundle.

### Why vitest passes but Playwright fails

Vitest (jsdom) uses a different module resolution path — it does not go through Vite/Rollup
chunking for test execution. jsdom never encounters the dual-instance issue at runtime.
The `test-frontend` CI job (vitest) passes; only `test-e2e` (Playwright against a
production bundle) sees the crash.

### Why the ci-fix committed change (`ae0f789`) did not fully resolve the issue

Commit `ae0f789` on branch `fix/ci-react-dedupe-and-pnpm-guard` added:

```ts
dedupe: ["react", "react-dom"],
```

This fixes **Layer 1** (react/react-dom) but does **not** fix **Layer 2** (react-konva dual
instance). The uncommitted working-tree change in that worktree's `frontend/vite.config.ts`
goes further:

```ts
dedupe: ["react", "react-dom", "react-konva"],
```

That extended list is what is actually needed. The committed fix is a partial fix; it may
move the crash from `ReactCurrentBatchConfig` to a different reconciler error, but it does
not make all 80+ e2e tests pass.

---

## (c) Minimal Reproduction

```bash
# In pd-ocr-labeler-spa/frontend/
pnpm install --frozen-lockfile
pnpm run build
# → dist/ produced; vite reports "1926 modules transformed"

# In pd-ocr-labeler-spa/
cp -r frontend/dist/. src/pd_ocr_labeler_spa/static/
uv run pd-ocr-labeler-ui --port 19999 &

# Playwright probe (one-liner):
uv run --group e2e python - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://localhost:19999/")
    page.wait_for_timeout(5000)
    print("Page errors:", errors)
    root = page.locator("#root")
    print("Root box:", root.bounding_box())
    browser.close()
EOF
# Output: Page errors: ["Cannot read properties of undefined (reading 'ReactCurrentBatchConfig')"]
#         Root box: None  (or zero-size box)
```

---

## (d) Recommended Fix

### Fix A — `frontend/vite.config.ts` (URGENT, gates all 80+ e2e tests)

**File:** `frontend/vite.config.ts`
**Lines:** the `resolve:` block (currently lines 35–39 on `main`)

```diff
   resolve: {
     alias: {
       "@": path.resolve(__dirname, "./src"),
     },
+    // Force single instances of all React-ecosystem packages when pnpm symlink
+    // scoping creates multiple paths for the same package.
+    //
+    // react/react-dom: @concavetrillion/pd-ui resolves from its own pnpm scope.
+    // react-konva: pd-ui brings react-konva@18 as a direct dep; labeler-spa uses
+    //   react-konva@19. Both get distinct react-reconciler instances (0.29 vs 0.33),
+    //   each with conflicting internal state. Forcing dedupe resolves all to the
+    //   top-level versions.
+    dedupe: ["react", "react-dom", "react-konva"],
   },
```

The ci-fix worktree's uncommitted working-tree state already contains the full version of this
fix (with `react-konva` in the list). The committed `ae0f789` state has only `["react",
"react-dom"]` and is a partial fix.

### Fix B — `tests/integration/test_docker_build.py` (LOW — docker CI only)

The `test-backend` CI job lacks pnpm, so `make docker-build` fails with "no pnpm available".

```python
# Add alongside the existing _have_docker() helper:
def _have_pnpm() -> bool:
    """Check if pnpm is available (needed for make docker-build → frontend-build)."""
    import shutil
    return shutil.which("pnpm") is not None

# Add to TestDockerBuild class:
@pytest.mark.skipif(not _have_pnpm(), reason="pnpm not on PATH")
class TestDockerBuild:
    ...
```

Alternative: add `pnpm/action-setup@v4` to the `test-backend` CI job in `.github/workflows/ci.yml`.

### Fix C — `pd-ui/package.json` peer deps (HOUSEKEEPING, cross-repo)

`@concavetrillion/pd-ui` declares:

- `peerDependencies: { "react": "^18.0.0", "react-dom": "^18.0.0" }` — should be `"^19.0.0"`
- `dependencies: { "react-konva": "^18.0.0" }` — should be a **peerDependency** at `"^19.0.0"`
  (so the consuming app controls the version, eliminating the dual-instance problem at source)

This is a `pd-ui` repo change requiring a new release. Emit as a cross-repo recommendation.

### Sequencing

1. **Fix A first** — single-line change, unblocks all 80+ e2e tests.
2. **Fix B** — cleans up 4 docker test failures in `test-backend`.
3. **Fix C** — long-term structural fix in pd-ui (separate PR/release).

---

## (e) Second-Order Issues

1. **`dedupe` is a Vite-level workaround, not a root-cause fix.** The root cause is that
   pd-ui ships `react-konva` as a direct `dependencies` entry rather than a `peerDependency`.
   Any consuming app that uses a different react-konva major will have this problem. Fix C
   addresses this structurally.

2. **pd-ui peer dep range mismatch** (`^18` vs actual `^19`) means pnpm may install extra
   copies of react/react-dom for other pd-ui consumers in the future. Fix C also covers this.

3. **`resolve.dedupe` is not inherited by vitest.** The `vitest.config.ts` is a sibling
   file (by design — to avoid Vite 6 / vitest 2.x type collision). If vitest ever starts
   running in a browser mode or doing SSR-style rendering, it would need the same dedupe.
   Not urgent for jsdom mode.

4. **The `env.js` classic-script ordering** (noted in the 2026-05-22 doc) is correct and
   not a contributor to the failure. `window.__ENV__` is populated before React reads it.

5. **CI artifact pipeline is sound.** The `test-frontend` → artifact upload → `test-e2e`
   download chain works correctly. The bundle produced by `pnpm run build` is byte-for-byte
   the broken bundle (dual-instance Vite output). There is no stale-artifact or
   asset-path-mismatch issue.

---

## (f) Worktree Disposition

### `ci-diagnosis` (branch `research/ci-red-diagnosis`, commit `948abf2`)

**Status:** Fully superseded by this document. The 2026-05-22 research doc in that worktree
is complete, accurate, and correctly identified H1 (dual React) as the root cause. This RCA
extends it by identifying the Layer 2 react-konva issue and explaining why `ae0f789` is only
a partial fix.

**Recommendation: Abandon.** The research doc has been incorporated here. Delete the
worktree: `git worktree remove .claude/worktrees/ci-diagnosis`. The branch can be deleted
or left as a historical reference (`git branch -d research/ci-red-diagnosis`).

### `ci-fix` (branch `fix/ci-react-dedupe-and-pnpm-guard`, commit `ae0f789`)

**Status:** Contains the right direction but is incomplete.

- Committed (`ae0f789`): `dedupe: ["react", "react-dom"]` — fixes Layer 1, not Layer 2.
- Uncommitted working tree: `dedupe: ["react", "react-dom", "react-konva"]` — the correct
  full fix for both layers.

The uncommitted working tree also has 4 `test_diag*_temp.py` files that were diagnostic
scaffolding only — they should not be committed.

**Recommendation: Salvage the working-tree vite.config.ts change, discard the diag tests,
then commit and push.** The workflow is:

```bash
cd .claude/worktrees/ci-fix
# 1. Stage only vite.config.ts (discard the 4 diag temp files):
git add frontend/vite.config.ts
git commit -m "fix(frontend): extend resolve.dedupe to include react-konva"
# 2. Push the branch and open a PR.
```

OR: cherry-pick / squash-merge the full fix onto a fresh branch off main, since the
`ae0f789` commit is already in `ci-fix`'s history. Either approach is fine.

---

## Appendix — Environment

| Item | Value |
|------|-------|
| Branch with regression | `main` @ `ccb14b5` |
| Regression introduced | `f8e20dc` (pd-ui bump to 0.1.0-alpha.1) |
| React version | `19.2.6` |
| pd-ui version | `0.1.0-alpha.1` |
| react-konva (top-level) | `19.2.4` |
| react-konva (pd-ui scope) | `18.2.16` |
| react-reconciler (dual) | `0.29.2` + `0.33.0` |
| pnpm | `11.1.3` |
| Vite | `6.4.2` |
| Playwright | `1.x` (chromium) |
| Python | `3.13.13` |

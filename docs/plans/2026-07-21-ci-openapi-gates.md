---
last_verified: 2026-07-21
created: 2026-07-21
owner: maintainers
kind: plan
status: draft
priority: now
repo: pdomain/pdomain-ocr-labeler-spa
---

# CI OpenAPI Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GitHub Actions CI enforce the two blocking local-only gates from `make ci` (all-files pre-commit + frontend Knip), and fix the OpenAPI drift job so it only diffs the committed TypeScript artifact instead of the gitignored intermediate schema file.

**Architecture:** Keep the existing multi-job workflow (parallel lint / tests / e2e / wheel / openapi-drift). Do **not** collapse into a single `make ci` job (that would lose SPA artifact sharing and job parallelism). Add one new `pre-commit` job, add one Knip step on the existing `test-frontend` job, and tighten the `openapi-drift` git-diff path list. Treat `frontend/openapi.json` as a generated intermediate forever; `frontend/src/api/types.ts` remains the sole committed OpenAPI contract artifact.

**Tech Stack:** GitHub Actions (`.github/workflows/ci.yml`), Make (`pre-commit-check`, `frontend-knip`, `openapi-export`), `uv` + `pre-commit`, pnpm + knip, `openapi-typescript`.

**Global Constraints:**

- Prefer Make targets (`make pre-commit-check`, `make frontend-knip`, `make openapi-export`) over raw tool invocations in CI steps.
- Do not track `frontend/openapi.json` (already in `.gitignore`; Makefile writes it as intermediate input to `openapi-typescript`).
- Do not implement Auth/S3/Postgres/managed-adapter work (D-042).
- Do not push without explicit say-so. Run `make ci AI=1` before committing.
- Specs / architecture docs that disagree with intentional gitignore behavior are wrong — update the docs as part of this plan.
- Keep scope to CI equivalence (#430) + OpenAPI drift fix (#433). Residual gaps noted below are out of scope unless they fall out for free.

---

## Already done (docs-only; no implementation work)

These issue records are `status:implemented` and need GitHub-issue closure / ledger hygiene only — **do not re-implement**:

| Local issue record | GH issue | Evidence summary |
|---|---|---|
| `docs/issues/2026-05-22-gh-437-openapi-schema-quality.md` | #437 | Conformance tests in `tests/conformance/test_response_models.py` and `tests/unit/api/test_route_conformance.py` (commits `bd3d173`, `e4838a1`, `8a80ce5`, `7faaa7b`) |
| `docs/issues/2026-05-23-gh-460-resolver-narrowing.md` | #460 | Nominal `isinstance` + guarded structural `.lines` fallback; decision in `docs/context/decisions.md` (commit `b66fc19`) |

When shipping this plan's PR, close #437 and #460 with the evidence above if they are still open on GitHub. No code changes for them.

---

## Problem statement (active work)

### #430 — CI ≠ `make ci` for two gates

Canonical local contract (`Makefile`):

```make
ci: setup frontend-install pre-commit-check typecheck openapi-export \
    frontend-build lint test behavior-coverage frontend-format-check \
    frontend-lint frontend-test frontend-knip
```

Current `.github/workflows/ci.yml` jobs cover lint, backend tests, frontend test+build, e2e (non-blocking), wheel assert, and openapi-drift — but **omit**:

1. `pre-commit-check` (`uv run pre-commit run --all-files`)
2. `frontend-knip` (`pnpm exec knip` via Make)

A PR can pass remote CI while failing the documented local gate (or vice versa).

### #433 — OpenAPI drift diffs a gitignored file

`openapi-drift` currently does:

```bash
git diff --exit-code frontend/src/api/types.ts frontend/openapi.json
```

But `.gitignore` has `frontend/openapi.json`. Git never tracks that path, so the second operand is a no-op. Only `types.ts` drift is real.

### Recommendation for #433 (chosen)

**Stop diffing `frontend/openapi.json`. Keep it gitignored. Diff only `frontend/src/api/types.ts`.**

Reasons:

1. `.gitignore` already declares the schema intermediate non-canonical.
2. `make openapi-export` writes `frontend/openapi.json` solely as input to `openapi-typescript`, then regenerates committed `frontend/src/api/types.ts`.
3. The SPA imports `types.ts`, not the raw schema file.
4. `docs/architecture/01-data-models.md` §6 and `docs/architecture/14-testing.md` §7 already describe the gate as `types.ts`-centric.
5. Tracking the schema would duplicate the contract, create two drift surfaces, and fight the Makefile/gitignore convention for no consumer benefit.
6. Sibling `pdomain-prep-for-pgdp` also gitignores `frontend/openapi.json`.

Do **not** start tracking `openapi.json` under this plan.

---

## Current vs desired gate matrix

| `make ci` step | GH CI today | After this plan |
|---|---|---|
| `setup` / `frontend-install` | Per-job install | unchanged |
| `pre-commit-check` | **missing** | new `pre-commit` job |
| `typecheck` | via `make lint` (+ pre-commit will also run basedpyright) | covered |
| `openapi-export` + drift | `openapi-drift` (broken openapi.json operand) | fixed to `types.ts` only |
| `frontend-build` | `test-frontend` | unchanged |
| `lint` | `lint` job | unchanged |
| `test` | `test-backend` | unchanged |
| `behavior-coverage` | missing | **out of scope** (residual) |
| `frontend-format-check` | missing as named job | covered by new pre-commit (`frontend-prettier`) |
| `frontend-lint` | via `make lint` | unchanged |
| `frontend-test` | `test-frontend` | unchanged |
| `frontend-knip` | **missing** | step on `test-frontend` |

Acceptable overlap: the new `pre-commit` job re-runs some lint/format/typecheck hooks already present in `lint`. That is intentional — pre-commit also enforces trailing whitespace, gitleaks, markdownlint, uv-lock-check, etc., which `make lint` does not.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `.github/workflows/ci.yml` | Modify | Add `pre-commit` job; add Knip step; fix openapi-drift diff |
| `docs/architecture/15-deployment-dev.md` | Modify | Drift gate shows `types.ts` only; note intermediate schema |
| `docs/architecture/module-map.md` | Modify | Correct “openapi.json checked into repo” |
| `docs/architecture/14-testing.md` | Modify | Document `pre-commit` + knip in CI job list |
| `docs/issues/2026-05-22-gh-430-ci-equivalence.md` | Modify (after ship) | `status:implemented` + resolution evidence |
| `docs/issues/2026-05-22-gh-433-openapi-drift.md` | Modify (after ship) | `status:implemented` + resolution evidence |
| `docs/issues/README.md` | Modify (after ship) | Move #430/#433 to resolved; note GH closes |

No Makefile changes required — targets already exist and are correct.

---

## Task 1 — Fix OpenAPI drift gate (#433)

**Files:**
- Modify: `.github/workflows/ci.yml` (job `openapi-drift`)
- Modify: `docs/architecture/15-deployment-dev.md` §4.4
- Modify: `docs/architecture/module-map.md` (Generated and build artefacts table)

- [ ] **Step 1: Change the drift diff to the committed artifact only**

In `.github/workflows/ci.yml`, replace the openapi-drift fail step (currently ~lines 181–220) so the comment and command match:

```yaml
# ---------------------------------------------------------------------------
# 6. openapi-drift — fail if committed types.ts differs after re-export
# ---------------------------------------------------------------------------
  openapi-drift:
    name: openapi-drift
    runs-on: ubuntu-latest
    needs: [test-frontend]
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0  # v6.0.2
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990  # v8.1.0
        with:
          version: "0.11.28"
          enable-cache: true
      - uses: actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e  # v6.4.0
        with:
          node-version: "24"
      - name: Enable pnpm via corepack
        run: corepack enable && corepack prepare pnpm@11.3.0 --activate
      - name: Install backend deps
        run: uv sync --group dev
      - name: Install frontend deps
        run: cd frontend && pnpm install --frozen-lockfile
      - name: Download pre-built SPA
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8.0.1
        with:
          name: frontend-dist-${{ github.run_id }}
          path: frontend/dist/
      - name: Copy bundle to static/
        run: |
          mkdir -p src/pdomain_ocr_labeler_spa/static
          rm -rf src/pdomain_ocr_labeler_spa/static/*
          cp -r frontend/dist/. src/pdomain_ocr_labeler_spa/static/
      - name: Re-export OpenAPI schema and regenerate types.ts
        run: make openapi-export
      - name: Fail if types.ts differs from committed version
        run: |
          # frontend/openapi.json is gitignored intermediate input to
          # openapi-typescript; only the committed types.ts is the gate.
          git diff --exit-code frontend/src/api/types.ts || {
            echo "::error::OpenAPI types are out of sync. Run 'make openapi-export' locally and commit frontend/src/api/types.ts."
            git diff frontend/src/api/types.ts
            exit 1
          }
```

Keep the existing action pin SHAs, SPA download, and `make openapi-export` invocation — only the comment + fail-step path list change for this task. Do not remove the SPA copy unless you separately verify `build_app().openapi()` works with empty `static/`; that is optional cleanup, not required.

- [ ] **Step 2: Correct deployment docs**

In `docs/architecture/15-deployment-dev.md` §4.4, replace the CI gate snippet that lists both files:

```yaml
- run: make openapi-export
- run: git diff --exit-code frontend/src/api/types.ts
```

Add one sentence: `frontend/openapi.json` is a gitignored intermediate; only `frontend/src/api/types.ts` is committed and drift-checked.

- [ ] **Step 3: Correct module-map artefact table**

In `docs/architecture/module-map.md`, change the `frontend/openapi.json` row notes from “OpenAPI schema checked into repo” to:

> Intermediate schema written by `make openapi-export` for `openapi-typescript`; gitignored. Canonical committed artifact is `frontend/src/api/types.ts`.

- [ ] **Step 4: Local verification of the gate logic**

```bash
# From a clean tree with types already in sync:
make openapi-export AI=1
git diff --exit-code frontend/src/api/types.ts
# Expected: exit 0, no output

# Confirm openapi.json is ignored:
git check-ignore -v frontend/openapi.json
# Expected: .gitignore match line for frontend/openapi.json

# Confirm a types.ts edit would fail the gate:
# (do not commit) touch a no-op change then restore
python -c "from pathlib import Path; p=Path('frontend/src/api/types.ts'); t=p.read_text(); p.write_text(t+'// drift-test\n')"
git diff --exit-code frontend/src/api/types.ts; echo "exit=$?"
# Expected: non-zero exit
git checkout -- frontend/src/api/types.ts
```

- [ ] **Step 5: Commit this task alone or with Task 2–3 (implementer choice)**

Message suggestion: `fix(ci): drift-check types.ts only; openapi.json stays intermediate (#433)`

---

## Task 2 — Add all-files pre-commit job (#430 part 1)

**Files:**
- Modify: `.github/workflows/ci.yml` (new job)

- [ ] **Step 1: Insert a new top-level job `pre-commit`**

Place it after `lint` (or at the end before/after openapi-drift — order among independent jobs does not matter). No `needs:` — run in parallel with `lint` / `test-backend` / `test-frontend`.

```yaml
# ---------------------------------------------------------------------------
# pre-commit — full-repo hooks (mirrors make pre-commit-check / make ci)
# ---------------------------------------------------------------------------
  pre-commit:
    name: pre-commit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0  # v6.0.2
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990  # v8.1.0
        with:
          version: "0.11.28"
          enable-cache: true
      - uses: actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e  # v6.4.0
        with:
          node-version: "24"
      - name: Enable pnpm via corepack
        run: corepack enable && corepack prepare pnpm@11.3.0 --activate
      - name: Install backend deps
        run: uv sync --group dev
      - name: Install frontend deps
        run: cd frontend && pnpm install --frozen-lockfile
      - name: Run pre-commit on all files
        run: make pre-commit-check
```

Notes for implementers:

- Use the same action pin SHAs as sibling jobs in this file.
- Both backend and frontend installs are required: local hooks include `basedpyright`, `uv-lock-check`, `frontend-tsc`, `frontend-eslint`, and `frontend-prettier`.
- `make pre-commit-check` expands to `uv run pre-commit run --all-files` (see Makefile). Prefer the Make target.
- Do **not** run `pre-commit install` in CI; only the all-files run is needed.
- Commit-msg-only hooks (gitlint) are not exercised by `--all-files`; that is fine and matches local `make pre-commit-check`.

- [ ] **Step 2: Local dry-run of the same command CI will run**

```bash
make setup AI=1          # if pre-commit / deps missing
make frontend-install AI=1
make pre-commit-check AI=1
```

Expected: `✅ pre-commit-check passed` (or clean hook output ending with all Passed). Fix any legitimate pre-commit failures in the same PR if the tree is dirty relative to hooks; do not weaken hooks.

- [ ] **Step 3: Confirm YAML still parses**

```bash
# Optional if python-yaml available; otherwise rely on GH Actions UI
python -c "import pathlib; p=pathlib.Path('.github/workflows/ci.yml'); print(p.stat().st_size, 'bytes ok')"
```

---

## Task 3 — Add frontend Knip gate (#430 part 2)

**Files:**
- Modify: `.github/workflows/ci.yml` (job `test-frontend`)

- [ ] **Step 1: Add Knip after frontend install / before or after vitest**

In job `test-frontend`, after `Install frontend deps` (and preferably after vitest so unit failures surface first; either order is acceptable), add:

```yaml
      - name: Run knip dead-code scan
        run: make frontend-knip
```

Preferred full `test-frontend` step order after this change:

1. checkout
2. setup-node
3. corepack / pnpm
4. `cd frontend && pnpm install --frozen-lockfile`
5. vitest (`pnpm test`)
6. **`make frontend-knip`** ← new
7. `pnpm run build`
8. copy to `static/`
9. upload-artifact

`make frontend-knip` requires `frontend/node_modules/.bin/knip` (already a devDependency) and exits 1 if missing — same contract as local CI.

Do **not** add a separate knip-only job unless install time becomes a problem; piggybacking on `test-frontend` avoids a third full frontend install.

- [ ] **Step 2: Local verification**

```bash
make frontend-install AI=1
make frontend-knip AI=1
```

Expected: knip completes with exit 0. If knip reports dead code/exports, fix those findings in this PR (they are already part of the local `make ci` contract and would block contributors today).

- [ ] **Step 3: Commit**

Message suggestion: `fix(ci): run pre-commit --all-files and knip on GitHub Actions (#430)`

(If Task 1 is in the same PR, a combined message is fine: `fix(ci): align GH Actions with make ci pre-commit/knip; fix openapi drift (#430, #433)`.)

---

## Task 4 — Document CI job list parity

**Files:**
- Modify: `docs/architecture/14-testing.md` §7

- [ ] **Step 1: Update the Continuous integration sketch**

Replace or extend the job list under §7 so it reflects the real workflow file, including:

```yaml
jobs:
  lint:
    - make lint
  pre-commit:
    - make pre-commit-check
  test-backend:
    - make test
  test-frontend:
    - pnpm test
    - make frontend-knip
    - pnpm run build
  test-e2e:
    - Playwright (continue-on-error for now)
  build-wheel:
    - uv build --wheel + static/index.html assert
  openapi-drift:
    - make openapi-export
    - git diff --exit-code frontend/src/api/types.ts
```

Add one prose line: GitHub CI deliberately mirrors the blocking gates of `make ci` as discrete jobs; `frontend/openapi.json` remains gitignored and is not a drift target.

- [ ] **Step 2: Sanity-check docs already correct**

Confirm `docs/architecture/01-data-models.md` §6 still says types.ts is committed and is the drift target — no change required if already accurate.

---

## Task 5 — Close the loop on issue records (after green CI)

**Files:**
- Modify: `docs/issues/2026-05-22-gh-430-ci-equivalence.md`
- Modify: `docs/issues/2026-05-22-gh-433-openapi-drift.md`
- Modify: `docs/issues/README.md`
- Optional GH: close issues #430, #433, #437, #460 on `pdomain/pdomain-ocr-labeler-spa`

- [ ] **Step 1: Mark #430 / #433 implemented**

For each of the two active issue docs:

- Frontmatter + Agent Index: `status: implemented`
- Resolution: Implemented via this plan’s PR; cite the commit SHA and the workflow jobs/steps.
- Next steps: close the corresponding GitHub issue.

- [ ] **Step 2: Update `docs/issues/README.md`**

Move #430 and #433 under resolved / annotate as implemented. Leave #437 / #460 as implemented-with-GH-closure-pending until closed.

- [ ] **Step 3: Close GitHub issues (when user OK / after merge)**

```bash
gh issue close 430 --repo pdomain/pdomain-ocr-labeler-spa \
  --comment "Fixed: pre-commit job + frontend-knip step now run in .github/workflows/ci.yml. See docs/plans/2026-07-21-ci-openapi-gates.md."
gh issue close 433 --repo pdomain/pdomain-ocr-labeler-spa \
  --comment "Fixed: openapi-drift diffs only frontend/src/api/types.ts; openapi.json remains gitignored intermediate."
gh issue close 437 --repo pdomain/pdomain-ocr-labeler-spa \
  --comment "Already implemented: tests/conformance/test_response_models.py + tests/unit/api/test_route_conformance.py."
gh issue close 460 --repo pdomain/pdomain-ocr-labeler-spa \
  --comment "Already implemented: Page|None nominal+structural narrowing (b66fc19); docs/context/decisions.md."
```

Do not close issues until the workflow change is merged (or the PR is the closing reference).

---

## Task 6 — Full verification gate

- [ ] **Step 1: Focused local equivalents of new CI paths**

```bash
make pre-commit-check AI=1
make frontend-knip AI=1
make openapi-export AI=1
git diff --exit-code frontend/src/api/types.ts
```

- [ ] **Step 2: Full local CI**

```bash
make ci AI=1
```

Expected: `✅ ci passed`.

- [ ] **Step 3: After PR open, confirm required checks**

On the PR, verify these jobs appear and pass:

- `lint`
- `pre-commit` ← new
- `test-backend`
- `test-frontend` (includes knip step) ← modified
- `openapi-drift` (types.ts only) ← modified
- `build-wheel`
- `test-e2e` (may be non-blocking via `continue-on-error: true`)

If branch protection lists required checks by name, add `pre-commit` to the required set when merging (repo admin). Without that, the job runs but is not merge-blocking — still ship the job; note the protection update in the PR body.

- [ ] **Step 4: Commit if not already committed; do not push unless asked**

---

## Residual gaps (explicitly out of scope)

1. **`behavior-coverage`** is in `make ci` but still absent from GitHub CI. Track separately if desired; not part of #430 defects-to-fix list.
2. **Collapsing to single-job `make ci`** (prep-for-pgdp style) would guarantee equivalence but destroy parallel jobs and SPA artifact handoff. Rejected for this plan.
3. **Deduping** pre-commit vs `make lint` overlap is a future optimization, not a correctness fix.
4. **e2e `continue-on-error: true`** remains; unrelated.

---

## Acceptance criteria

- [ ] `.github/workflows/ci.yml` runs `make pre-commit-check` in a dedicated job.
- [ ] `.github/workflows/ci.yml` runs `make frontend-knip` on the frontend test path.
- [ ] `openapi-drift` fails only when `frontend/src/api/types.ts` drifts; it does not claim to gate `frontend/openapi.json`.
- [ ] `.gitignore` still lists `frontend/openapi.json`.
- [ ] Architecture docs no longer claim the schema file is a committed drift target.
- [ ] `make ci AI=1` is green locally.
- [ ] Issue docs #430 and #433 marked implemented after ship; #437 and #460 noted as already done (GH close when open).

---

## Effort estimate

**S — small.** Approximately **1–2 hours** for an agent familiar with the repo: workflow YAML edits, short doc fixes, local `make pre-commit-check` / `make frontend-knip` / `make ci` verification. Risk is low; primary failure mode is pre-existing knip or pre-commit findings that already block local `make ci` and must be fixed rather than skipped.

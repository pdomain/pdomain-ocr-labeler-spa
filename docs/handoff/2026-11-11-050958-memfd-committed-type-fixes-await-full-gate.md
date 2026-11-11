---
kind: handoff
status: "active"
created: "2026-11-11"
created_at: "2026-11-11T05:09:58Z"
owner: "CT"
branch: "feature/memfd-tsconfig-state"
scope: "memfd-tsconfig-state"
worktree: "/mnt/work/projects/pdomain/pdomain-ocr-labeler-spa/.worktrees/memfd-tsconfig-state"
base_commit: "a09b50e6d1c38d1af8ffd3c22581f3511dd625cc"
supersedes: "2026-11-11-032240-memfd-fix-written-frontend-gate-unconfirmed.md"
handoff_reason: "stopping"
host: "claude-code"
---

# memfd fix committed, test type fixes wait for the full gate

## Goal

Fix the memfd bundle loading failure, finish test TypeScript strictness, and correct the stale P3 and F2 text in
current-state.

## Done

- The memfd fix is committed as `a09b50e6`. `make ci AI=1` passed first with real exit status 0: 2273 backend tests
  passed with 2 skipped, and 164 frontend files with 2290 tests passed.
- The 3.13.14 comparison ran. On 3.13.14 all 21 issue tests fail with `UnsupportedRuntimeError` or `503
  unsupported_runtime`, and none with `AttributeError`. On 3.13.18 all 21 pass. The refusal is the intended result,
  because those tests need memfd. The 5 new tests, 11 cases with parametrization, pass on both builds.
- All 270 test type errors are fixed with no suppressions. That count excludes the two invalid `include` globs, which
  are also fixed.
- `noUncheckedIndexedAccess` is on in `frontend/tsconfig.test.json`. `make lint` now runs `pnpm run typecheck:test`.
- `@types/node` is a direct dev dependency at the already-locked 26.5.1.
- `docs/context/current-state.md` is corrected. The memfd issue and the strictness plan are retired, with tombstones
  in `docs/context/decisions.md` and every inbound link updated.

## Not done

- Everything after `a09b50e6` is uncommitted: 56 test files, `Makefile`, three frontend config files, and the docs.
  The repo requires a passing `make ci` before each commit.
- The second `make ci AI=1` did not finish. Claude Code stopped it because the machine was critically low on memory
  while other sessions ran gates, and its notice said not to restart it unasked. It reached 99% of the backend tests
  with no failures shown before `make` was terminated. No exit status exists, so this is not a gate pass.
- Both new tombstones in `docs/context/decisions.md` still say `Removal commit: (fill after commit)`.

## Failed approaches

- Importing CSS with `?raw` in the style tests does not work. With `css: false`, Vitest returns it empty, and tests
  asserting that text is absent would pass on nothing. The style tests keep reading from disk.
- `pnpm add --offline` fails on missing registry metadata. The online add changed only three lockfile lines.

## Decisions

- Needs an owner decision: an agent chose to require memfd sealing with no fallback carrier, and batch jobs fail
  instead of skipping pages. The issue had left this open. It is recorded in the tombstone and has not been reviewed.
- Needs an owner decision: `pnpm typecheck` runs `tsc --noEmit` on a root config with `files: []`, so it checks no
  source files. The pre-commit hook runs `tsc -b --noEmit`, which does. This was outside the plan and is unchanged.
- The cause of the difference between the Python builds is not established. `sysconfig` reports `HAVE_MEMFD_CREATE`
  as 0 on both.
- Input element types in tests use type arguments such as `getByTestId<HTMLInputElement>`. Matchers such as
  `toHaveValue` would have changed runtime behavior, which the plan put out of scope.

## State

Focused checks passed on the code changes before the docs edits: test-project `tsc` exit 0, eslint exit 0, knip exit
0, and Vitest 164 files with 2290 tests. Only docs changed after that. `docgraph check --strict` passed with no
blocking issues. A TypeScript reviewer found nothing to fix in the hand edits. Nothing was pushed, merged, tagged,
released or deployed, and all work ran on CPU with the GPU hidden. The 3.13.14 environment is 6.5 GB at
`.worktrees/py31314` inside this worktree, ignored by Git, and can be deleted. Gate output is in
`/mnt/work/pdt/labeler/gate/`.

## Pointers

- `docs/context/decisions.md`
- `docs/context/current-state.md`
- `docs/architecture/09-persistence.md`
- `docs/architecture/14-testing.md`
- `frontend/tsconfig.test.json`

## Resume steps

1. When memory allows, set `TMPDIR=/mnt/work/pdt/labeler` and `CUDA_VISIBLE_DEVICES=`, run `make ci AI=1`, and record
   its real exit status.
2. Commit `frontend/` and `Makefile` as the strictness fix.
3. Commit the docs, including the deletions of the issue and the plan.
4. Fill both `Removal commit` lines with the docs commit hash, rerun the gate, and commit that.
5. Ask the owner about the two decisions above.

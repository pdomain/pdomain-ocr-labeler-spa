---
kind: handoff
status: "active"
created: "2026-11-11"
created_at: "2026-11-11T06:01:38Z"
owner: "CT"
branch: "feature/memfd-tsconfig-state"
scope: "memfd-tsconfig-state"
worktree: "/mnt/work/projects/pdomain/pdomain-ocr-labeler-spa/.worktrees/memfd-tsconfig-state"
base_commit: "e11332316e70b3e59c236ca20b4e617449b197de"
supersedes: "2026-11-11-050958-memfd-committed-type-fixes-await-full-gate.md"
handoff_reason: "stopping"
host: "claude-code"
---

# memfd fix and test type work are committed, and the full gate passes

## Goal

Fix the memfd bundle loading failure, finish test TypeScript strictness, and correct the stale P3 and F2 text in
current-state.

## Done

- All planned work is committed on `feature/memfd-tsconfig-state`. Nothing was pushed or merged.
- `9181753e` holds the test type fixes, the gate wiring and the `tests/unit/test_frontend_config.py` update.
- `f6f2e3de` retires the memfd issue and the strictness plan and updates current-state.
- `e1133231` fills both `Removal commit` lines in `docs/context/decisions.md` with `f6f2e3de`.
- No test type errors remain. `make lint` runs the test-project `tsc`, and it passed inside the gate. The test files
  changed by these commits contain no `ts-ignore`, `ts-expect-error` or `eslint-disable` comments.
- `make ci AI=1` exited 0 on the content of `e1133231`: 2273 backend tests passed with 2 skipped, and 164 frontend
  files with 2290 tests passed. The status came from `make` itself, with no pipe.

## Not done

- The branch is not merged to master. That needs the owner's say-so.
- The two owner decisions below are open.

## Failed approaches

- The first gate of this session exited 2 with one failure. `test_tsconfig_test_exists_and_includes_test_files` still
  required the `include` globs `src/**/__tests__/**` and `src/test/**`. TypeScript rejects both with TS5010, so the
  test now requires `src/**/__tests__/**/*` and `src/test/**/*`. The `exclude` list in `frontend/tsconfig.app.json`
  keeps the trailing `**`, which is valid there.
- `git commit` fails with `pre-commit not found` unless `.venv/bin` is on `PATH`. Git's post-checkout hook needs it
  when `pre-commit` restores stashed changes. Add `.venv/bin` to `PATH` and leave the hooks on.

## Decisions

- Needs an owner decision: an agent chose to require memfd sealing with no fallback carrier, and batch jobs fail
  instead of skipping pages. The issue had left this open. It is recorded in the tombstone and has not been reviewed.
- Needs an owner decision: `pnpm typecheck` runs `tsc --noEmit` on a root config with `files: []`, so it checks no
  source files. The pre-commit hook runs `tsc -b --noEmit`, which does. This was outside the plan and is unchanged.
- The cause of the difference between the Python builds is not established. `sysconfig` reports `HAVE_MEMFD_CREATE`
  as 0 on both.

## State

The working tree was clean at `e1133231`. All work ran on CPU with the GPU hidden. Gate output is in
`/mnt/work/pdt/labeler2/gate/`. `tests/unit/test_frontend_config.py:37` has one older basedpyright error, a bare
`dict` return type. The project's typecheck covers only `src/`, so the gate does not report it, and it was left alone.
The 3.13.14 environment is 6.5 GB at `.worktrees/py31314` inside this worktree, ignored by Git, and can be deleted.

## Pointers

- `docs/context/decisions.md`
- `docs/context/current-state.md`
- `frontend/tsconfig.test.json`
- `tests/unit/test_frontend_config.py`

## Resume steps

1. Get the owner's answer on the two decisions above.
2. Merge `feature/memfd-tsconfig-state` when the owner approves it.
3. Delete `.worktrees/py31314` once the 3.13.14 comparison is no longer needed.

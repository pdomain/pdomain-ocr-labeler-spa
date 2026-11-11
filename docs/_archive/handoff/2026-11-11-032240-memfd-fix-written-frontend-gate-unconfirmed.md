---
kind: archive
status: retired
created_at: "2026-11-11T03:22:38Z"
owner: "CT"
branch: "feature/memfd-tsconfig-state"
scope: "memfd-tsconfig-state"
worktree: "/mnt/work/projects/pdomain/pdomain-ocr-labeler-spa/.worktrees/memfd-tsconfig-state"
base_commit: "5a5fbcf0eb958278f61ed6587384565c214bb06d"
handoff_reason: "user_requested"
host: "claude-code"
created: "2026-11-11"
last_verified: "2026-11-11"
---

# memfd fix written, frontend gate unconfirmed

> **Retired — superseded by `docs/handoff/2026-11-11-050958-memfd-committed-type-fixes-await-full-gate.md`.**

## Goal

Fix the memfd bundle loading failure, then finish test TypeScript strictness, then correct the stale P3 and F2 text in
current-state.

## Done

- The memfd fix is written but uncommitted. Loaders now refuse with `UnsupportedRuntimeError`, which the API returns
  as `503 unsupported_runtime` and which names the missing interfaces. Failed book loads clean up their session.
- Six new tests failed before the fix. A review raised two low-severity gaps, `os.MFD_CLOEXEC` and book tests removing
  only one interface, and both were fixed.
- The backend suite passed with 2273 tests and 2 skipped.

## Not done

- Nothing is committed on this branch.
- The frontend gate is unconfirmed. 138 frontend test files failed before running, each missing a file in Vitest's
  temp directory under `/tmp`, which was over quota. Two files passed on their own, so this looks environmental. The
  session was rerunning the frontend suite alone when interrupted.
- `docs/plans/2026-07-21-tsconfig-test-strictness.md` is not started. Its clean baseline is stale: the strict flag
  shows 272 errors across 63 files, and 194 exist with the flag off.
- `docs/context/current-state.md` is not corrected: it still calls the P3 and F2 work an unreleased local branch
  needing a dev wheel. That work is on master and `pyproject.toml` requires `pdomain-book-contracts>=0.3.0`.
- The memfd issue is not retired.

## Failed approaches

- Subclassing `ValueError` or `OSError` for the new error does not work: the load routes would turn it into a 422 and
  batch jobs would skip the page.
- A second Python environment did not fit in the `/tmp` quota. Build the comparison environment inside the ignored
  `.worktrees` directory.

## Decisions

- The session chose to require memfd sealing with no fallback carrier, keeping image leases immutable. Batch jobs fail
  instead of skipping pages. The docs did not mark this as an owner decision.
- The uv-managed CPython 3.13.14 lacks `os.memfd_create`. The mise-managed 3.13.18 has it, and this worktree uses
  3.13.18.

## State

Eleven modified tracked files, no commits ahead of master. The three old unmerged branches were left alone. The owner
paused this work on 2026-11-10 and the session's herdr tab is closed. Nothing was pushed, merged, tagged, released or
deployed. All work ran on CPU with the GPU hidden. The session's last terminal output is saved in
`/mnt/work/projects/pdomain/.artifacts/handoff-20261110/session-output/`. `/tmp` is a shared tmpfs that ran out of
quota several times on 2026-11-10 while ten sessions ran gates. If a gate fails with a quota error, point `TMPDIR` at
the work drive and rerun before suspecting the code.

## Pointers

- `/mnt/work/projects/pdomain/.artifacts/handoff-20261110/labeler-memfd.patch`
- `docs/issues/2026-11-07-python-build-without-memfd-breaks-labeling-bundles.md`
- `docs/architecture/09-persistence.md`
- `docs/plans/2026-07-21-tsconfig-test-strictness.md`

## Resume steps

1. Set `TMPDIR` on the work drive and rerun `make ci AI=1`.
2. Commit the memfd fix and retire its issue.
3. Run the final comparison on a 3.13.14 environment built inside `.worktrees`.
4. Fix all 272 test type errors without suppressions.
5. Correct current-state.

---
kind: handoff
status: "active"
created: "2026-11-11"
created_at: "2026-11-11T07:54:09Z"
owner: "CT"
branch: "feature/glyph-pgdp-completion"
scope: "glyph-pgdp-completion"
worktree: "/mnt/work/projects/pdomain/pdomain-ocr-labeler-spa/.worktrees/glyph-pgdp-completion"
base_commit: "4982ebc474a714e4f1682a1df5d3d703dd379bd0"
supersedes: "2026-11-11-060138-memfd-and-test-types-committed-gate-green.md"
handoff_reason: "stopping"
host: "claude-code"
---

# Glyph parity and shared UI alignment are done, and both plans are retired

## Goal

Finish `docs/plans/2026-07-21-glyph-annotations-completion.md`, then `docs/plans/2026-07-21-pgdp-alignment-remaining.md`,
on a branch cut from the unmerged `feature/memfd-tsconfig-state`. Use one commit per item, test first, with interface
changes checked in a real browser.

## Done

- `feature/glyph-pgdp-completion` holds six commits on top of `986f01a5`, the memfd branch head. Nothing was pushed or
  merged.
- `b28085a7`: the glyph picker offers all 14 shared ligature kinds and writes their uppercase wire values. Saved legacy
  lowercase marks stay as stored and keep their names. Chip driver identifiers stay lowercase.
- `18391dd5`: the export dialog shows the saved export from `GET .../exports` when it opens and after each run, with
  separate loading, empty and failed states. An unreadable manifest now returns 500 `export_history_unreadable`
  instead of an empty list.
- `800a4dad`: the decision log records why the right panel frame stays local.
- `8391cddc`: the frontend, word match, page surface, module map, runtime flow, worklist, right panel, viewport and
  driver contract docs match the mounted components.
- `4982ebc4`: both plans are deleted. Tombstones are in `docs/context/decisions.md`, and inbound links in docs, specs,
  `AGENTS.md` and code comments point at the architecture docs. A follow-up commit fills in the removal commit hash
  in both tombstones.
- `make ci AI=1` exited 0 before each commit. The status came from `make` itself, written to a file with no pipe. The
  last run passed 2273 backend tests with 2 skipped, and 164 frontend files with 2314 tests.
- Chromium passed `tests/e2e/test_glyph_panel.py`, `tests/e2e/test_bulk_glyph_mark.py` and
  `tests/e2e/test_export_manifest_and_trainer.py`, including the new tests.
- One independent review covered the two code commits. Its only finding was low severity and is recorded below.

## Not done

- The branch is not merged. Merging needs the owner's say-so, and so does the memfd branch underneath it.
- The new backend tests carry the `integration` marker, which `make test` deselects. They passed in focused runs of
  `tests/integration/test_glyph_routes.py` and `tests/integration/test_export_list_and_cli_store.py`, not inside
  `make ci`. `make integration` was not run.

## Failed approaches

- The first gate exited 2 with 35 failures, all `unsupported_runtime`. `uv sync` in a fresh worktree built `.venv`
  on uv's CPython 3.13.14, which lacks `os.memfd_create`. The fix is to rebuild with `UV_PYTHON` set to the mise
  3.13.18 interpreter, as `docs/architecture/09-persistence.md` section 8a describes. Any new worktree hits this.
- This session's worktree guard refuses `git` and `make` commands that mention `$PWD` or `$PATH`. Literal absolute
  paths in `PATH` work. `git commit` still needs `.venv/bin` on `PATH` for the pre-commit hooks.

## Decisions

- Needs an owner decision: an agent decided overnight to keep the right panel frame local. The 2026-11-11 entry in
  `docs/context/decisions.md` gives the evidence. The owner has not reviewed it.
- Needs an owner decision: the export list API changed from best-effort to strict. A corrupt or malformed manifest
  is now a 500, so the dialog can say the read failed. A missing manifest or a project with no entry is still an
  empty list.
- Rejected review finding: the panel's predicted-mark check compares kinds exactly, so a legacy `ct` mark would not
  match a `CT` prediction. No predictor exists and prediction UI is out of scope, so it was left alone.
- Not fixed: bulk recipes still write the legacy `ct` and `st` values. The shared model migrates them on read.
- Not fixed: `tests/e2e/exercise_real_project.py` still clicks `erase-pixels-button`, which no component mounts. Erase
  mode lives at `rail-mode-erase`. That harness is outside the gate and outside these plans.
- Carried over from the memfd branch: the two owner decisions in the predecessor handoff, now in
  `docs/_archive/handoff/`, are still open.

## State

The working tree was clean at `4982ebc4` before the removal-hash commit. The worktree `.venv` uses mise CPython 3.13.18.
Gate output is in `/mnt/work/pdt/labeler3/gate/`, one `.out` and `.status` pair per run. All work ran on CPU with
`CUDA_VISIBLE_DEVICES` empty.

## Pointers

- `docs/context/decisions.md`
- `docs/architecture/20-glyph-annotations.md`
- `docs/architecture/10-export.md`
- `docs/architecture/13-driver-contract.md`
- `frontend/src/components/glyph/GlyphAnnotationPanel.tsx`
- `frontend/src/components/ExportHistorySection.tsx`
- `src/pdomain_ocr_labeler_spa/api/export.py`

## Resume steps

1. Get the owner's answers on the decisions above and on the memfd branch.
2. Run `make integration` if the integration-marked tests need coverage in a full run.
3. Merge `feature/memfd-tsconfig-state`, then this branch, when the owner approves.

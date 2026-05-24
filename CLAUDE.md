# CLAUDE — pd-ocr-labeler-spa

FastAPI + React/Vite/TS replacement for the NiceGUI `pd-ocr-labeler`. Spec-driven,
milestone-by-milestone implementation (M0…M9). Architecture: `docs/architecture/00-overview.md`.

## Commands

| target | does |
|---|---|
| `make setup AI=1` | `uv sync` + pre-commit hooks + hatch-vcs version refresh |
| `make frontend-install AI=1` | `pnpm install --frozen-lockfile` inside `frontend/` |
| `make test AI=1` | pytest — unit + integration, excludes `e2e/` |
| `make frontend-test AI=1` | vitest (jsdom) |
| `make e2e AI=1` | Playwright E2E (requires `playwright install chromium`) |
| `make lint AI=1` / `make format AI=1` | ruff (format runs `--fix` too) |
| `make pre-commit-check AI=1` | all pre-commit hooks on every tracked file |
| `make dev` | uvicorn --reload, points at Vite dev server on :5173 |
| `make frontend-dev` | Vite HMR dev server on :5173 |
| `make frontend-build AI=1` | builds SPA into `src/pd_ocr_labeler_spa/static/` |
| `make openapi-export AI=1` | exports `/openapi.json` → regenerates `frontend/src/api/types.ts` |
| `make build AI=1` | builds the wheel (requires populated `static/`) |
| `make run` | builds SPA if missing, then `pd-ocr-labeler-ui` (production-style) |
| `make ci AI=1` | setup + test + frontend-test + build |
| `make docker-build` | builds the production Docker image |
| `make local-setup` | clone any missing sibling pd-* repos |
| `make local-dev` | switch to local-dev mode (pd-book-tools editable + pd-ui linked + marker) |
| `make local-check` | print local-dev mode + per-sibling resolution |
| `make local-upgrade-deps` | upgrade deps then restore editables (local-mode only) |
| `make local-run` | run the SPA against local-dev workspace (local-mode only) |
| `make update-pd-deps` | bump pd-* sibling deps to registry latest; leaves diff for review |

See [workspace `docs/process/local-dev.md`](../docs/process/local-dev.md) for the canonical local-dev pattern (spec #362).

`AI=1` captures verbose output to `.ci-ai.log`; stdout shows `✅` on pass or
filtered failure sections on error. Remove `AI=1` only if you need full verbose
output for debugging.

## Rules

- Always run `make ci AI=1` before committing.
- Make targets first; fall back to `uv run …` (or `npm`, `vitest`) only when no target exists.
- Never `python -m pytest`. Always `uv run pytest` or `make test`.
  Bare `python`/`python3`/`.venv/bin/python` miss the venv.
- Backend: FastAPI + uvicorn. Frontend: React 19 + Vite + TS + TanStack Query + Tailwind + Konva.
- `data-testid` contract governs Playwright driver integration — see `docs/architecture/13-driver-contract.md`.
- Modeled structurally on `../pd-prep-for-pgdp/` — consult it for scaffolding patterns.
- `pd-book-tools` pinned in `pyproject.toml`; do not reach into its internals.
- Specs are the source of truth. Code that disagrees with a spec is wrong — change the spec first.
- Open questions live in `OPEN_QUESTIONS.md`; do not resolve them unilaterally.
- After FastAPI model changes: run `make openapi-export` to keep TS types in sync.
- `make build` will refuse without a populated `static/` — run `make frontend-build` first.
- Archive closed bugs/questions on close: cut from `docs/archive/research/BUGS_FOUND.md` / `OPEN_QUESTIONS.md`
  into `docs/archive/research/BUGS_RESOLVED.md` / `docs/archive/research/QUESTIONS_RESOLVED.md` in the same commit.
- Auth/S3/Postgres/managed-adapter axes are deferred (D-042) — do not implement without user OK.

## Current milestone

**Cut-over complete as of 2026-05-21.** M0–M10, M9.5, hi-fi FO-1–FO-9,
and all 8 CU milestones (complete-labeler-spa plan) are shipped.
M9.1 (manual rotate) and M9.2 (auto-rotate-all) ship the job/SSE
plumbing only — the actual image rotation, re-OCR, and PageRecord
update are stubbed. See `docs/archive/research/BUGS_FOUND.md`.
Milestone history lives in GitHub milestones and `specs/16-milestones.md`.

**Path to usable** — see `docs/archive/plans/plan-to-usable.md` (archived,
cut-over complete). All rows checked; legacy pd-ocr-labeler superseded.

**Open work:**

- M9.5 keyboard audit (#286, `status:backlog`): browser walk TODOs
  pending CT; hotkeys + audit doc already shipped.
- M11 glyph annotations (#267–#270, `status:blocked`): needs Q-A7
  resolution before implementation.
- #366 tighten tsconfig.test.json relaxations (`status:backlog`).
- #404 lint-deviations.md documentation (`kind:chore`).
- #405 OCR-config modal trigger missing after HeaderBar deprecation
  (`status:blocked`).

Per-slice history is preserved in git log and GitHub closed milestones.

## Specs

Active specs live in `specs/` (milestones, ADR log, glyph-annotations).
Implemented specs are under `docs/architecture/` (`00-overview.md` through
`28-palettes-pickers.md`, minus 16/17/20 which remain active in `specs/`).
All are canonical source of truth. Milestone acceptance gates:
`specs/16-milestones.md`.

## Sibling repos

- `../pd-book-tools/` — upstream dependency.
- `../pd-prep-for-pgdp/` — structural reference (FastAPI + React single-wheel pattern).
- `../pd-ocr-labeler/` — legacy NiceGUI UI being replaced; parity tracked via GitHub issues (`label:hifi:P1..P5`).

## GH issues

Cross-cut work tasks are tracked as GH issues in
**`ConcaveTrillion/ocr-container-meta`** (not in this repo's own tracker).
Plans under `docs/plans/` in the workspace root are synced there
via `/decompose-spec --sync`. Milestone naming: `spec: <plan-basename> (#N)`.

When shipping a plan task:

- Before starting: `gh issue view <N> --repo ConcaveTrillion/ocr-container-meta`
- After completing: `gh issue close <N> --repo ConcaveTrillion/ocr-container-meta`
- List open tasks:
  `gh issue list --repo ConcaveTrillion/ocr-container-meta --milestone "spec: <name> (#N)" --state open`

## docs/ folder

This repo follows the workspace docs/ template — see [`docs/README.md`](docs/README.md). Active
folders: `architecture/`, `decisions/`, `plans/`, `process/`, `research/`,
`runbooks/`, `specs/`, `templates/`, `usage/`, plus parallel `archive/`
subfolders.

**Superpowers redirect.** When a superpowers skill (e.g. `brainstorming`,
`writing-plans`) instructs you to save to `docs/superpowers/specs/<file>.md`
or `docs/superpowers/plans/<file>.md`, save to `docs/specs/<file>.md` or
`docs/plans/<file>.md` instead. There is no `docs/superpowers/` subdirectory
in this repo.

<!-- workspace-process:start -->

## Before coding

These steps are workspace defaults for any coding task. **User-level settings
override them** — a user's own `~/.claude/CLAUDE.md`, `settings.json`, or a
direct instruction in the conversation takes precedence and may waive or
change any step below.

### Working principles

- **Use skills.** Invoke the relevant superpowers skill before starting —
  process skills first (`brainstorming`, `systematic-debugging`,
  `writing-plans`, `test-driven-development`), then implementation skills.
  If a skill applies, using it is not optional.
- **Delegate by default.** Dispatch subagents for non-trivial work: per-repo
  agents for repo changes, `Explore` for code searches. This keeps large tool
  output out of the parent context.
- **Parallelize.** Run independent tasks as concurrent subagents — multiple
  agent calls in a single message. Set `model: sonnet` on implementers and
  reviewers.

### Steps

1. **Check the working tree.** `git status --short`. Surface or resolve stray
   uncommitted work before starting — don't build on it.
2. **Read repo guidance.** This repo's `CLAUDE.md` and `CONVENTIONS.md` for
   repo-specific rules.
3. **Consult `docs/` for authoritative context** (whichever folders exist):
   `plans/` (the work plan), `specs/` (design specs — follow any `Spec:`
   pointer from the issue), `research/` (prior investigations), `decisions/`
   (ADRs / constraints), `architecture/` (shipped design).
4. **Check live issue status.** `gh issue view <N> --repo <owner/repo>` —
   confirm it isn't already closed; note its milestone.
5. **Check for in-flight work.** Open PRs and existing branches touching the
   same area, to avoid colliding with work-in-progress.
6. **Consult agent memory.** `.claude/agent-memory/<repo>/feedback_*.md` for
   corrections not yet promoted to `CONVENTIONS.md`.
7. **Locate code with `Explore` first.** Use an `Explore` subagent to find
   relevant files before broad `Read`/grep.
8. **Isolate in a worktree.** Never work directly in the interactive checkout
   at `/workspaces/ocr-container/<repo>/`. Use the `using-git-worktrees` skill
   to set up an isolated worktree. When delegating to a full-power
   implementation agent, pass `isolation: "worktree"` on the `Agent` call
   (skip for `-docs` agents and the `driver` agent). When an agent returns a
   worktree path + branch, use the `finishing-a-development-branch` skill to
   decide how to integrate.
9. **TDD.** Write the failing test first where the plan calls for it.
10. **Verify before committing.** Focused verification plus `make ci`.
11. **Commit locally; do not push** without explicit say-so.

<!-- workspace-process:end -->

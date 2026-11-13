---
kind: process
status: active
owner: maintainers
created: 2026-05-09
last_verified: 2026-11-12
---

# AGENTS — pdomain-ocr-labeler-spa

FastAPI + React/Vite/TS replacement for the NiceGUI `pd-ocr-labeler`. Spec-driven,
milestone-by-milestone implementation (M0…M9). Architecture: `docs/architecture/00-overview.md`.

## Commands

| target | does |
|---|---|
| `AI=1 just setup` | `uv sync --locked --group dev` + pre-commit hooks + hatch-vcs version refresh |
| `AI=1 just frontend-install` | `pnpm install --frozen-lockfile` inside `frontend/` |
| `AI=1 just test` | pytest — excludes `e2e/`, slow, and integration markers |
| `AI=1 just frontend-test` | vitest (jsdom) |
| `AI=1 just e2e` | Playwright E2E (requires `playwright install chromium`) |
| `AI=1 just lint` / `AI=1 just format` | ruff (lint fixes; format only formats) |
| `AI=1 just pre-commit-check` | all pre-commit hooks on every tracked file |
| `just dev` | uvicorn --reload, points at Vite dev server on :5173 |
| `just frontend-dev` | Vite HMR dev server on :5173 |
| `AI=1 just frontend-build` | builds SPA into `src/pdomain_ocr_labeler_spa/static/` |
| `AI=1 just openapi-export` | exports `/openapi.json` → regenerates `frontend/src/api/types.ts` |
| `AI=1 just build` | exports OpenAPI, builds the SPA, then builds sdist and wheel |
| `just run` | builds SPA if missing or stale, then `pdomain-ocr-labeler-ui` (production-style) |
| `AI=1 just ci` | locked setup + Python/frontend checks + tests + behavior coverage + build + strict docgraph |
| `just docker-build` | builds the production Docker image |
| `just local-setup` | clone any missing sibling pd-* repos |
| `just local-dev` | switch to local-dev mode (pdomain-book-tools editable + pdomain-ui linked + marker) |
| `just local-check` | print local-dev mode + per-sibling resolution |
| `just local-upgrade-deps` | upgrade deps then restore editables (local-mode only) |
| `just local-setup-py` | re-apply editable Python siblings after any `uv sync` (idempotent) |
| `just local-frontend-install` | `pnpm install` + restore `pnpm link` overlays for npm siblings |
| `just local-frontend-build` | Vite build via local-link-preserving path (depends on `local-frontend-install`) |
| `just local-run` | run SPA against local-dev workspace — re-applies Python editables + rebuilds SPA via local path (does NOT call `just run`; avoids registry `pnpm install --frozen-lockfile` that would discard `pnpm link`) |
| `just update-pdomain-deps` | bump pd-* sibling deps to registry latest; leaves diff for review |

See the workspace `docs/process/local-dev.md` for the canonical local-dev pattern (spec #362).

`AI=1` captures verbose output to `.ci-ai.log`; stdout shows one `PASS: <recipe>` line on pass or
filtered failure sections on error. Remove `AI=1` only if you need full verbose
output for debugging.

## Rules

- Always run `AI=1 just ci` before committing.
- Just recipes first; fall back to `uv run …` (or `pnpm`, `vitest`) only when no target exists.
- Never `python -m pytest`. Always `uv run pytest` or `just test`.
  Bare `python`/`python3`/`.venv/bin/python` miss the venv.
- Backend: FastAPI + uvicorn. Frontend: React 19 + Vite + TS + TanStack Query + Tailwind + Konva.
- `data-testid` contract governs Playwright driver integration — see `docs/architecture/13-driver-contract.md`.
- Modeled structurally on `../pdomain-prep-for-pgdp/` — consult it for scaffolding patterns.
- `pdomain-book-tools` pinned in `pyproject.toml`; do not reach into its internals.
- Shipped behavior lives in `docs/architecture/`. If code and an architecture doc disagree, change the architecture doc
  to match the code, with evidence. Unfinished design stays in `docs/specs/`. The roadmap is `docs/context/intent-map.md`.
- Open questions live in `OPEN_QUESTIONS.md`; do not resolve them unilaterally.
- After FastAPI model changes: run `just openapi-export` to keep TS types in sync.
- `just build` builds the SPA before the sdist and wheel; the wheel hook rejects a missing bundle.
- Track open bugs in the issue tracker and open design questions in
  `OPEN_QUESTIONS.md`. Record durable outcomes in `docs/context/decisions.md`.
- Auth/S3/Postgres/managed-adapter axes are deferred (D-042) — do not implement without user OK.

## Current milestone

**Cut-over complete as of 2026-05-21.** M0–M10, M9.5, hi-fi FO-1–FO-9,
and all 8 CU milestones (complete-labeler-spa plan) are shipped.
M9.1 (manual rotate) and M9.2 (auto-rotate-all) now rotate images, rerun OCR,
persist rotation metadata, and protect manual overrides.
Milestone history lives in GitHub milestones and `specs/16-milestones.md`.

**Path to usable** — cut-over is complete; the retired execution plan remains
available in Git history. The legacy `pd-ocr-labeler` is superseded.

**Open work:**

The roadmap is [`docs/context/intent-map.md`](docs/context/intent-map.md).
Shipped ownership is [`docs/architecture/30-repository-boundaries.md`](docs/architecture/30-repository-boundaries.md).
Operational status is [`docs/context/current-state.md`](docs/context/current-state.md).

`docs/issues/` has no open reports. The memfd refusal, the 18 deep-review
reports under `docs/issues/2026-07-21-*`, and every report filed on 2026-09-18
are resolved. Their tombstones are in `docs/context/decisions.md`. The July
deep-review plan is retired.

Summary of what closed 2026-09-18 (full reasoning in
`docs/context/decisions.md`):

- Wave 0 data integrity, Wave 1 export loop, Wave 2 M11 glyph, Wave 3 job
  SSE/canvas-erase/image-drift, and Wave 4 CI gates (#430/#433, moot — the
  GitHub workflows they named were deleted 2026-09-13) are all closed.
- M11 glyph annotations: the manual review path is shipped — a person can
  select a word, mark ligatures/long-s/swash or mark it reviewed with no
  marks, and the mark survives save and reload; bulk apply persists and
  refreshes. No predictor exists and none will be built (decided
  2026-09-18) — the accept-prediction button never fires. Browser coverage:
  `tests/e2e/test_glyph_panel.py` and `tests/e2e/test_bulk_glyph_mark.py`.
  Glyph chips select the word and open the panel on click, same as the
  pencil button.
- Open findings (`docs/context/open-findings.md`): keyboard entries
  (BUG-KBD-1/4/5) are closed; all six findings, including platform data roots, empty OCR, and hierarchy waits, are
  closed.
- Test-project `noUncheckedIndexedAccess` is on as of 2026-11-11.
- Export history, the local right-panel frame, and the driver docs landed on
  2026-11-11. Browser coverage of driver-contract section 2.11 drives the
  mounted right-panel editor. A shared workbench layout was decided against.

Per-slice history is preserved in git log and GitHub closed milestones.

## Specs

Shipped design lives in `docs/architecture/` (`00-overview.md` through
`31-typography-review.md`). `specs/16-milestones.md` is acceptance history.
`specs/17-decisions.md` is the ADR log. Glyph annotations live in
`docs/architecture/20-glyph-annotations.md`. The roadmap is
`docs/context/intent-map.md`.

## Sibling repos

Ownership and the current pins are in
[`docs/architecture/30-repository-boundaries.md`](docs/architecture/30-repository-boundaries.md).

- `../pdomain-book-tools/` — OCR runtime. Do not reach into its internals.
- `../pdomain-prep-for-pgdp/` — structural reference. Do not port its pipeline.
- `../pd-ocr-labeler/` — legacy NiceGUI UI. This SPA supersedes it.

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
folders: `architecture/`, `context/`, `decisions/`, `plans/`, `process/`,
`runbooks/`, `specs/`, `templates/`, and `usage/`. Retired material remains in
Git history and is summarized in `docs/context/decisions.md`.

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
- **Write clearly.** Follow `docs/process/writing-style.md` for direct user
  updates, handoffs, final summaries, docs, reports, issue text, PR text, and
  user-facing copy. Keep agent communication short, clear, and easy to scan.
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
10. **Verify before committing.** Focused verification plus `just ci`.
11. **Commit locally; do not push** without explicit say-so.

<!-- workspace-process:end -->

<!-- >>> repo-setup:repo-facts sha256:26a7d0ab12f9283c98d2ea9203876643555227d638387a97fe5fd8019501f609 -->
## Repository facts

- This repository builds the `pdomain-ocr-labeler-spa` FastAPI service and its React, Vite, and TypeScript frontend.
- Backend source lives under `src/pdomain_ocr_labeler_spa/`. Frontend source lives under `frontend/`.
- Governed documentation lives under `docs/` and `specs/`.
  [`DOCGRAPH.md`](DOCGRAPH.md) owns its lifecycle and indexing rules.
- Codex-specific startup context lives in [`CODEX.md`](CODEX.md).
- The default branch is `master`.
<!-- <<< repo-setup:repo-facts -->

<!-- >>> repo-setup:commands-and-gates sha256:bda452dcbd848059bdff621959f6f80ac5a9fa5e54fd8448fa8f84ad95ebafb1 -->
## Commands and gates

- Run backend tests with `just test` or a focused `uv run pytest ...` command.
- Run the repository lint gate with `just lint`.
- Run focused Python checks through `uv run ruff check`, `uv run ruff format`, and `uv run basedpyright`.
- Run the full repository gate with `AI=1 just ci` before committing.
<!-- <<< repo-setup:commands-and-gates -->

<!-- >>> repo-setup:writing-and-review sha256:be7f6da1ca37f92092fe1f540c5f90a319ac246169076519250033482ca47424 -->
## Writing and review

- Route new durable reader-facing documents through the `write-readably` skill.
- Route edits of existing prose through the `edit-for-readability` skill.
- Apply adversarial review through the policy owned by the consuming skill or plugin.
- Apply the `writing-python` skill and its mandatory gate when writing or changing Python.
<!-- <<< repo-setup:writing-and-review -->

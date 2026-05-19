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
- Archive closed bugs/questions on close: cut from `docs/BUGS_FOUND.md` / `OPEN_QUESTIONS.md`
  into `docs/archive/BUGS_RESOLVED.md` / `docs/archive/QUESTIONS_RESOLVED.md` in the same commit.
- Auth/S3/Postgres/managed-adapter axes are deferred (D-042) — do not implement without user OK.

## Current milestone

M0–M10, M9.5, and hi-fi follow-ons FO-1–FO-9 are all ✅ done.
M9.1 (manual rotate) and M9.2 (auto-rotate-all) ship the job/SSE
plumbing only — the actual image rotation, re-OCR, and PageRecord
update are stubbed. See `docs/BUGS_FOUND.md`.
Milestone history lives in GitHub milestones and `specs/16-milestones.md`;
parity tracking moved to GitHub issues (`label:hifi:P1..P5`).

**Path to usable** — see `docs/plan-to-usable.md` for the gap analysis
between today's tree and "CT opens the SPA, loads a real scanned-book
project, edits OCR, saves, replacing the legacy NiceGUI labeler
end-to-end."

**Open work:**

- **Hi-fi completion (P1–P5)** — primary active workstream. 29 slices
  filed as #336–#364 (`label:hifi:P1..P5`); plan lives at
  `docs/plans/hifi-gaps-plan.md`. Closes the 61 visual-fidelity gaps
  between Slices 0–27 (shipped) and the original hi-fi design; this is
  the cut-over gate for retiring the legacy NiceGUI labeler.
- M9.5 keyboard audit (#286, `status:backlog`): browser walk TODOs
  pending CT; hotkeys + audit doc already shipped.
- M11 glyph annotations (#267–#270, `status:blocked`): needs Q-A7
  resolution before implementation.
- Path-to-usable: `docs/plan-to-usable.md` — only the smoke-run row
  and legacy-README banner are still pending.

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

# CLAUDE — pd-ocr-labeler-spa

FastAPI + React/Vite/TS replacement for the NiceGUI `pd-ocr-labeler`. Spec-driven,
milestone-by-milestone implementation (M0…M9). Architecture: `specs/00-overview.md`.

## Commands

| target | does |
|---|---|
| `make setup` | `uv sync` + pre-commit hooks + hatch-vcs version refresh |
| `make frontend-install` | `npm install` inside `frontend/` |
| `make test` | pytest — unit + integration, excludes `e2e/` |
| `make frontend-test` | vitest (jsdom) |
| `make e2e` | Playwright E2E (requires `playwright install chromium`) |
| `make lint` / `make format` | ruff (format runs `--fix` too) |
| `make pre-commit-check` | all pre-commit hooks on every tracked file |
| `make dev` | uvicorn --reload, points at Vite dev server on :5173 |
| `make frontend-dev` | Vite HMR dev server on :5173 |
| `make frontend-build` | builds SPA into `src/pd_ocr_labeler_spa/static/` |
| `make openapi-export` | exports `/openapi.json` → regenerates `frontend/src/api/types.ts` |
| `make build` | builds the wheel (requires populated `static/`) |
| `make run` | builds SPA if missing, then `pd-ocr-labeler-ui` (production-style) |
| `make ci` | setup + test + frontend-test + build |
| `make docker-build` | builds the production Docker image |

## Rules

- Make targets first; fall back to `uv run …` (or `npm`, `vitest`) only when no target exists.
- Never `python -m pytest`. Always `uv run pytest` or `make test`.
  Bare `python`/`python3`/`.venv/bin/python` miss the venv.
- Backend: FastAPI + uvicorn. Frontend: React 19 + Vite + TS + TanStack Query + Tailwind + Konva.
- `data-testid` contract governs Playwright driver integration — see `specs/13-driver-contract.md`.
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

M0 (repo scaffold) and M1 (settings/adapters/AppState) are both ~97% in progress; M1.h frontend
components (`HeaderBar`, `EmptyProjectState`, `RootPage`) and two medium bugs (B-51, B-58) remain.
See `docs/ROADMAP.md` for per-slice details.

## Specs

Full spec set: `specs/00-overview.md` through `specs/20-*.md`. Canonical source of truth.
Milestone acceptance gates: `specs/16-milestones.md`.

## Sibling repos

- `../pd-book-tools/` — upstream dependency.
- `../pd-prep-for-pgdp/` — structural reference (FastAPI + React single-wheel pattern).
- `../pd-ocr-labeler/` — legacy NiceGUI UI being replaced; parity tracked in `docs/PARITY_STATUS.md`.

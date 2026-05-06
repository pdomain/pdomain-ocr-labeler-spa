# Roadmap — implementation tracker

The authoritative milestone definitions live in
[`../specs/16-milestones.md`](../specs/16-milestones.md). This file
tracks implementation status — what's shipped, what's next. Update on
every iteration.

## Status by milestone

| Milestone | Status | Notes |
|---|---|---|
| **M0** Repo scaffold | 🟡 in progress | Iter 1 backend skeleton + tests; iter 2 frontend scaffold (files only); iter 3 (2026-05-06) `mise.toml` + Makefile + Makefile parse smoke tests; iter 4 (2026-05-06) `.pre-commit-config.yaml` mirroring pd-prep-for-pgdp + 5 YAML-shape smoke tests. Frontend `npm install` still blocked on Q-A8 (no node/npm/mise on PATH). Dockerfile / install scripts / DEVELOPMENT.md pending. |
| M1 Settings + adapters + AppState | ⬜ not started | Pre-conditions: M0. |
| M2 Project discovery + load | ⬜ not started | Pre-conditions: M0, M1. |
| M3 OCR config modal + first-page OCR | ⬜ not started | |
| M4 Image viewport + overlays + drag selection | ⬜ not started | |
| M5 Word matches view (right pane) | ⬜ not started | |
| M6 Toolbar action grid + style/component apply + add-word | ⬜ not started | |
| M7 Word edit dialog + word-image canvas + bbox edit | ⬜ not started | |
| M8 Save / Load page + Save Project + Rematch GT + driver compat | ⬜ not started | |
| M9 Export + cleanup + cut-over | ⬜ not started | |
| M9.1 Manual rotation buttons | ⬜ blocked | Pre: M9. |
| M9.2 Auto-rotation pass | ⬜ blocked | Pre: M9.1 + pd-book-tools `rotation` module. |
| M9.5 Full keyboard-driven editing audit | ⬜ blocked | Pre: M9. |
| M10 Text normalization | ⬜ blocked | Pre: pd-book-tools `text.normalize`. |
| M11 Glyph-level annotations | ⬜ blocked | Pre: M9 + pd-book-tools/pd-ocr-trainer upstreams + Q-A5/A6/A7. |

## M0 sub-tasks

- [x] **Iter 1.** Backend skeleton: `pyproject.toml`, `__init__`,
  `settings.py`, `bootstrap.py`, `__main__.py`, `api/healthz.py`,
  `api/env_js.py`, `static/.gitkeep`, `build_hooks/spa_check.py`,
  unit tests for `/healthz`, `/env.js`, settings, `build_app`.
- [x] **Iter 2.** Frontend scaffold (files only): `frontend/`
  package.json, tsconfig.{,app,node}.json, vite.config.ts,
  vitest.config.ts, index.html, src/{main,App}.tsx, App smoke test
  (`getByTestId("app-shell")`). React 19 + Vite 6 + Vitest 2;
  mirrors pgdp-prep layout. **Not yet `npm install`-ed** — the
  devcontainer lacks Node; tracked as Q-A8 in OPEN_QUESTIONS.md, to
  be verified when `mise.toml` lands.
- [x] **Iter 3.** `mise.toml` (Node 24 / Python 3.13) + Makefile
  mirroring pd-prep-for-pgdp targets (`setup`, `test`,
  `frontend-install`, `frontend-build`, `frontend-test`,
  `frontend-dev`, `openapi-export`, `build`, `ci`, plus mise
  helpers). Added `tests/unit/test_makefile.py` (parse + dry-run
  smoke). Q-A8 still open: devcontainer has no node/npm/mise; see
  iter-3 update note in `OPEN_QUESTIONS.md`.
- [x] **Iter 4.** `.pre-commit-config.yaml` mirroring
  pd-prep-for-pgdp (pre-commit-update; trailing-whitespace,
  end-of-file-fixer, check-yaml, check-json; ruff-check ×2 +
  ruff-format). Added `tests/unit/test_pre_commit_config.py` (5
  tests: YAML parse, repos shape, expected hook IDs per repo, every
  repo pins a `rev`). Drive-by reformat of
  `tests/unit/test_makefile.py` so the new check-format would pass.
- [ ] **Iter 5 (next).** Code-review checkpoint per loop directive.
- [ ] Tailwind v3.4 + shadcn/ui wiring (`tailwind.config.ts`,
  `postcss.config.js`, `src/index.css`, `components.json`).
  Deferred from iter 2 to keep the smoke scaffold minimal.
- [ ] `Dockerfile` (two-stage Node → Python wheel).
- [ ] `install.sh` / `install.ps1` (uv tool installer).
- [ ] `.github/workflows/release.yml` (CI gate including SPA-bundle
  presence check).
- [ ] `DEVELOPMENT.md`.
- [ ] M0 acceptance gate: `make ci` green, `make build` produces a
  wheel that contains `pd_ocr_labeler_spa/static/index.html`,
  `pd-ocr-labeler-ui --no-browser --port 8080` answers `/healthz`,
  `make openapi-export` regenerates `frontend/src/api/types.ts`.

## Iteration index (this repo)

See `/workspaces/ocr-container/docs/LOOP_STATE.md` for the full per-
iteration log driven by the dev /loop.

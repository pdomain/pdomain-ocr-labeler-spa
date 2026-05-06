# Roadmap — implementation tracker

The authoritative milestone definitions live in
[`../specs/16-milestones.md`](../specs/16-milestones.md). This file
tracks implementation status — what's shipped, what's next. Update on
every iteration.

## Status by milestone

| Milestone | Status | Notes |
|---|---|---|
| **M0** Repo scaffold | 🟡 in progress | Iter 1 backend skeleton + tests; iter 2 frontend scaffold (files only); iter 3 (2026-05-06) `mise.toml` + Makefile + Makefile parse smoke tests; iter 4 (2026-05-06) `.pre-commit-config.yaml` mirroring pd-prep-for-pgdp + 5 YAML-shape smoke tests; iter 5 (2026-05-06) **code-review checkpoint** → 9 findings filed in `BUGS_FOUND.md` (1 high, 3 medium, 4 low, 1 nit; B-10 was a non-finding sanity check); iter 6 (2026-05-06) fixed B-02 (vite proxy → :8080) + B-03 (drop CORS `allow_credentials`) with regression tests; iter 7 (2026-05-06) fixed B-01 (gate `/env.js` install on `mode != "api_only"` + parametrised test across modes) and B-09 (retagged `v0.0` → `v0.0.0` at same commit `2f01b17`). Iter 8 should resume scaffolding (Tailwind + shadcn / Dockerfile / install scripts) or pick from remaining bugs (B-04..B-08). Frontend `npm install` still blocked on Q-A8. Dockerfile / install scripts / DEVELOPMENT.md pending. |
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
- [x] **Iter 5 (2026-05-06).** Code-review checkpoint per loop
  directive. 9 findings filed in `BUGS_FOUND.md`. Highest concerns:
  B-02 (vite proxy → :8765 not :8080, blocks dev frontend loop),
  B-03 (CORS `allow_credentials=True` + wildcard origin invalid),
  B-01 (`/env.js` mounted unconditionally despite spec §2.12
  api_only gate; test cements wrong shape). Suggested iter-6 jump-
  ahead fixes: B-02, B-03, B-01, B-09 (re-tag `v0.0.0`).
- [x] **Iter 6 (2026-05-06).** Fixed B-02 (vite dev proxy
  `localhost:8765` → `localhost:8080`, three keys) and B-03 (dropped
  `allow_credentials=True` from CORSMiddleware to match pgdp-prep +
  CORS spec). Added `tests/unit/test_vite_config.py` (3 tests: file
  exists, all 3 proxy keys hit :8080, no stale 8765 literal) and
  `tests/unit/test_cors_middleware.py` (2 tests: wildcard+credentials
  combo refused, kwargs match pgdp-prep shape). Test count: 21 → 26.
- [x] **Iter 7 (2026-05-06).** Fixed B-01 (gate `/env.js` install on
  `settings.mode != "api_only"` per spec §2 step 12) + B-09 (retag
  `v0.0` → `v0.0.0` at same commit `2f01b17` so hatch-vcs version
  derivation is canonical PEP-440). Test count: 26 → 30 (added
  `tests/unit/test_env_js.py` with 4 parametrised tests across
  modes; relocated and tightened the prior `/env.js` shape assertion
  out of `test_healthz.py`; added `api_only`-omits-/env.js
  regression to `test_app_factory.py`). Wheel filename now
  `pd_ocr_labeler_spa-0.0.1.dev6+g6b6835b13.d20260506`. Local-only
  retag, no push.
- [ ] **Iter 8 (next).** Resume scaffolding — Tailwind v3.4 + shadcn,
  or pick from remaining bugs (B-04 settings mutation, B-05 eslint
  script without eslint, B-06 openapi:gen path drift, B-07 unused
  `_build_env(settings)` arg, B-08 tsconfig-includes-tests). B-05 +
  B-08 are closest to "block M1 frontend work."
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

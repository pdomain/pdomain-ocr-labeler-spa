# Roadmap — implementation tracker

The authoritative milestone definitions live in
[`../specs/16-milestones.md`](../specs/16-milestones.md). This file
tracks implementation status — what's shipped, what's next. Update on
every iteration.

## Status by milestone

| Milestone | Status | Notes |
|---|---|---|
| **M0** Repo scaffold | 🟡 in progress | Iter 1 backend skeleton + tests; iter 2 frontend scaffold (files only); iter 3 `mise.toml` + Makefile + Makefile parse smoke tests; iter 4 `.pre-commit-config.yaml` mirroring pd-prep-for-pgdp + YAML-shape smoke tests; iter 5 **code-review checkpoint** → 9 findings filed in `BUGS_FOUND.md`; iter 6 fixed B-02 + B-03; iter 7 fixed B-01 + B-09; iter 8 fixed B-05 + B-06 + B-08; iter 9 (2026-05-06) fixed B-04 (Settings now `frozen=True` + `Settings(**overrides)` in `__main__`) + B-07 (`_build_env()` no-arg) and added `docs/DEVELOPMENT.md` with shape-pin tests. **All iter-5 findings now closed.** Iter 10 is the next code-review checkpoint (reviews iters 6-9). Frontend `npm install` still blocked on Q-A8. Dockerfile / install scripts / Tailwind+shadcn / release workflow still pending for M0 acceptance gate. |
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
- [x] **Iter 8 (2026-05-06).** Bundled fix for the three frontend
  config low bugs: B-05 (dropped dangling `lint` script — restoring
  it requires landing eslint + a real config in the same change,
  filed Q-A9), B-06 (package.json `openapi:gen` now reads
  frontend-local `openapi.json` matching Makefile + spec), B-08
  (split test type-checking into `tsconfig.test.json`; production
  `tsc -b` now excludes `*.{test,spec}.{ts,tsx}`, `__tests__/**`,
  `src/test/**`; vitest config wires `typecheck.tsconfig` →
  `./tsconfig.test.json`). Added `tests/unit/test_frontend_config.py`
  (5 tests: B-05 conditional invariant, B-06 cross-file path check,
  B-08 app-excludes / test-includes / vitest-wiring). Test count:
  30 → 35. ruff lint+format clean. Remaining BUGS_FOUND.md items:
  B-04 (low) + B-07 (nit).
- [x] **Iter 9 (2026-05-06).** Fixed B-04 (built `overrides` dict
  from CLI flags + `Settings(**overrides)` once; enabled
  `frozen=True` in `SettingsConfigDict`; added runtime + AST-level
  regression tests) and B-07 (dropped unused `settings` param from
  `_build_env`; pinned the no-arg signature). Added
  `docs/DEVELOPMENT.md` (prereqs, first-time setup, dev loop, build,
  CI mirror) with `tests/unit/test_development_doc.py` (4 tests:
  exists, every `make <foo>` reference resolves, Node/Python pins
  match `mise.toml`, Astral uv installer mentioned). Test count:
  35 → 42. ruff lint+format clean. **No remaining iter-5 findings.**
- [ ] **Iter 10 (next).** Code-review checkpoint per /loop cadence
  (reviews iters 6-9). File new findings into `BUGS_FOUND.md`. Do
  not fix in the same iter.
- [ ] Tailwind v3.4 + shadcn/ui wiring (`tailwind.config.ts`,
  `postcss.config.js`, `src/index.css`, `components.json`).
  Deferred from iter 2 to keep the smoke scaffold minimal.
- [ ] `Dockerfile` (two-stage Node → Python wheel).
- [ ] `install.sh` / `install.ps1` (uv tool installer).
- [ ] `.github/workflows/release.yml` (CI gate including SPA-bundle
  presence check).
- [ ] M0 acceptance gate: `make ci` green, `make build` produces a
  wheel that contains `pd_ocr_labeler_spa/static/index.html`,
  `pd-ocr-labeler-ui --no-browser --port 8080` answers `/healthz`,
  `make openapi-export` regenerates `frontend/src/api/types.ts`.

## Iteration index (this repo)

See `/workspaces/ocr-container/docs/LOOP_STATE.md` for the full per-
iteration log driven by the dev /loop.

# Roadmap — implementation tracker

The authoritative milestone definitions live in
[`../specs/16-milestones.md`](../specs/16-milestones.md). This file
tracks implementation status — what's shipped, what's next. Update on
every iteration.

## Status by milestone

| Milestone | Status | Notes |
|---|---|---|
| **M0** Repo scaffold | 🟡 in progress | Iter 1 backend skeleton + tests; iter 2 frontend scaffold (files only); iter 3 `mise.toml` + Makefile + Makefile parse smoke tests; iter 4 `.pre-commit-config.yaml` mirroring pd-prep-for-pgdp + YAML-shape smoke tests; iter 5 **code-review checkpoint** → 9 findings filed in `BUGS_FOUND.md`; iter 6 fixed B-02 + B-03; iter 7 fixed B-01 + B-09; iter 8 fixed B-05 + B-06 + B-08; iter 9 fixed B-04 (Settings now `frozen=True` + `Settings(**overrides)` in `__main__`) + B-07 (`_build_env()` no-arg) and added `docs/DEVELOPMENT.md` with shape-pin tests; iter 10 **code-review checkpoint** → 5 new findings (B-11..B-15: 2 low, 3 nit; no blockers); iter 11 fixed B-12 + B-13 + B-14 + B-15; iter 12 fixed B-11 (post-commit pre-commit hook auto-runs `make refresh-version` so `__version__` stays current); iter 13 wired Tailwind v3.4 (`tailwind.config.js`, `postcss.config.js`, `src/index.css` with three `@tailwind` directives, `main.tsx` imports it, devDependencies pin v3.x/v8.x/v10.x); iter 14 added `Dockerfile` (three named stages: `spa`/`wheel`/`runtime`, Node 24 + Python 3.13 matching `mise.toml`, `COPY --from=spa` lands SPA at `src/pd_ocr_labeler_spa/static/` for `build_hooks/spa_check.py`, runtime `EXPOSE 8080` + `pd-ocr-labeler-ui --host 0.0.0.0 --no-browser`) + `.dockerignore`; iter 15 **code-review checkpoint** → 7 new findings (B-16..B-22: 1 high, 2 medium, 2 low, 2 nit). Top concern: B-16 (Dockerfile `ENV PD_LABELER_HOST/PORT` doesn't match `Settings` `PDLABELER_*` prefix — env-name underscore mismatch). iter 16 fixed B-16 (dropped dead `ENV PD_LABELER_*` lines from `Dockerfile`; new test sources the prefix from `Settings.model_config["env_prefix"]` at runtime so any future drift fails loudly) + B-17 (added `post-rewrite` + `post-checkout` pre-commit hook stages, all converging on new `scripts/refresh_version_git_hook.sh` so amend/rebase/cherry-pick no longer leave `__version__` stale) + B-22 (paired doc-honesty annotation on B-11). iter 17 fixed B-20 (Dockerfile runtime stage now installs from a frozen `uv export` requirements.txt with `--no-deps` wheel install, so transitive deps come from `uv.lock` instead of fresh PyPI resolution) + B-21 (runtime apt-get install/purge git+ca-certificates inside a single RUN so the final image carries no git binary) and corrected the iter-12 backlog-zero annotation to reference subsequent iter-15 findings. iter 18 added `make docker-build` / `docker-run` / `docker-shell` targets (mirrors pd-prep-for-pgdp shape; `docker-build` depends on `frontend-build`; `docker-run` maps `$(DOCKER_PORT):8080`) plus `tests/unit/test_makefile_docker.py` (10 tests: dry-run parse for each target, help-output coverage, default tag pin, three-way Settings/Dockerfile-EXPOSE/Makefile-`-p` port alignment, .PHONY coverage). Frontend `npm install` still blocked on Q-A8. Install scripts / shadcn / release workflow still pending for M0 acceptance gate. |
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
- [x] **Iter 10 (2026-05-06).** Code-review checkpoint (reviews iters
  6-9). 5 findings filed (`BUGS_FOUND.md` B-11..B-15): 0 blocker, 0
  high, 0 medium, 2 low (B-11 stale `__version__` after intermediate
  commits; B-12 DEVELOPMENT.md describes a dev loop that's only
  partly real in M0), 3 nit (B-13 AST scan misses
  AugAssign/AnnAssign; B-14 `_build_env` no-arg pin will trip M2's
  correct fix; B-15 CORS conditional test). All four iter-6-9 fixes
  correctly fixed their bugs without shifting failure modes. No
  blocker for moving forward.
- [x] **Iter 11 (2026-05-06).** Fixed B-12 (DEVELOPMENT.md split into
  "What you'll see in M0" + "What's coming in M1+"; new regression
  test pins the M0 callout naming `/healthz`, `/env.js`, and either
  `404` or `M1`), B-13 (AST walker now visits `AugAssign` /
  `AnnAssign` targets; self-test added covering all three forms),
  B-14 (test reframed: if `_build_env` has a `settings` param the
  body must reference it; M0 no-arg and M2 with-real-consumer both
  pass; only the misleading "takes-and-ignores" shape fails), and
  B-15 (CORS test asserts `allow_credentials is False`
  unconditionally — partial-regression diagnostics now point at the
  credentials bit directly). Test count: 42 → 44. ruff clean. Sole
  remaining iter-10 finding: **B-11** (stale `__version__`) —
  deferred to iter 12.
- [x] **Iter 12 (2026-05-06).** Fixed B-11 (last open iter-10
  finding). Approach: post-commit pre-commit hook calling
  `make refresh-version` plus `default_install_hook_types:
  [pre-commit, post-commit]` so the existing `pre-commit install` in
  `make setup` wires both. Three regression tests added: two in
  `tests/unit/test_pre_commit_config.py` (default-install-hook-types
  + local-repo refresh-version hook shape) and a new
  `tests/unit/test_version.py` module (runtime check that
  `__version__ == importlib.metadata.version("pd-ocr-labeler-spa")`
  + AST guard that `__init__.py` only ever assigns `__version__`
  from `version()` calls or a literal inside an
  `except PackageNotFoundError:` block). Test count: 44 → 48. ruff
  clean. **No iter-10 review findings remain.** Iter 13 should resume
  scaffolding — Tailwind v3.4 wiring is the recommended next chunk
  (small, well-bounded: tailwind.config.js, postcss.config.js,
  src/index.css with `@tailwind` directives, file existence + grep
  tests). Iter 15 is the next code-review checkpoint.
- [x] **Iter 13.** Tailwind v3.4 wiring: `frontend/tailwind.config.js`
  (ESM, `content: ["./index.html", "./src/**/*.{ts,tsx}"]`),
  `frontend/postcss.config.js` (tailwindcss + autoprefixer),
  `frontend/src/index.css` (three `@tailwind` directives + body
  font-family rule), `frontend/src/main.tsx` imports `./index.css`,
  `package.json` devDependencies pinned `tailwindcss@^3.4.0` /
  `postcss@^8.4.0` / `autoprefixer@^10.4.0`. Six new pytest shape
  pins in `tests/unit/test_tailwind_config.py`. shadcn/ui generators
  (`components.json` + the `ui/` primitives) deferred to a later sub-
  task — they need npm available to run `pnpm dlx shadcn-ui init`.
- [x] **Iter 14.** `Dockerfile` (two-stage Node → Python wheel) +
  `.dockerignore`. Three named stages (`spa` / `wheel` / `runtime`)
  pinned in tests so `docker build --target` consumers don't break
  when stages are renamed. `spa` uses `node:24-bookworm-slim` matching
  `mise.toml`; `wheel` and `runtime` use `python:3.13-slim-bookworm`.
  `wheel` stage uses Astral's `uv` from `ghcr.io/astral-sh/uv:latest`,
  static-pins the version via `ARG VERSION` + `sed` (mirroring
  `pd-prep-for-pgdp`) since the build context excludes `.git/`. The
  `COPY --from=spa` lands the SPA at `src/pd_ocr_labeler_spa/static/`
  — exactly where `build_hooks/spa_check.py` looks for `index.html`.
  Runtime `ENTRYPOINT` invokes `pd-ocr-labeler-ui --host 0.0.0.0
  --no-browser`; `EXPOSE 8080` matches Settings default.
  `.dockerignore` excludes `.git/`, `__pycache__/`, `.venv/`,
  `frontend/node_modules/`, `frontend/dist/`,
  `src/pd_ocr_labeler_spa/static/`, `tests/`, `specs/`, `docs/`. Nine
  new pytest shape pins in `tests/unit/test_dockerfile.py` covering
  existence, stage names, base-image major versions tracked from
  `mise.toml`, the spa→wheel handoff path, `uv build` invocation,
  the entrypoint name (read live from `pyproject.toml`), `EXPOSE
  8080`, and the host-bind invariant (0.0.0.0). Docker not available
  in the devcontainer so no `docker build` exec — text-grep style.
- [ ] shadcn/ui scaffold (`components.json`, generated `ui/`
  primitives). Blocked on Q-A8 (Node not present in devcontainer).
- [ ] Makefile `docker-build` / `docker-run` targets wiring the new
  Dockerfile (specs/15 §6).
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

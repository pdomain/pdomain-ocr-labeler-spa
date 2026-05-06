# Roadmap — implementation tracker

The authoritative milestone definitions live in
[`../specs/16-milestones.md`](../specs/16-milestones.md). This file
tracks implementation status — what's shipped, what's next. Update on
every iteration.

## Status by milestone

| Milestone | Status | Notes |
|---|---|---|
| **M1** Settings + adapters + AppState | 🟡 in progress — ~40% (entered iter 33) | iter 37 closed B-44 + B-45 + B-46 + B-48 + B-49 (batched 5-bug closeout): **B-44** (medium) — `FilesystemStorage.{put_bytes,delete,list_keys}` now dispatch their sync FS calls (`mkdir(parents=True)`, `exists()`/`unlink()`, `rglob` walk) through `anyio.to_thread.run_sync(...)` so async methods no longer block the event loop. Pinned by new AST-scan test that walks `filesystem.py` and flags any bare sync `Path.{exists,unlink,mkdir,rglob,is_file,relative_to}()` call lexically inside `async def` (correctly excluding `await` expressions and nested `def`/`lambda` bodies passed to the threadpool). **B-45** (low) — path-traversal guard now raises `ValueError` up-front when `key.startswith("/")` (was silently re-rooting under `self._root`); docstring rewritten; new `test_filesystem_storage_absolute_key_rejected` exercises every `IStorage` async method on `/etc/passwd` and asserts no re-rooted side-effect dir appears. **B-46** (low) — dropped `(IOCREngine)` base from `LocalDoctrOCR`/`ModalOCR`/`SharedContainerOCR` (structural-only conformance policy now matches storage/auth + pgdp-prep); `adapters/__init__.py` grew a "Conformance policy" section spelling out the rule; new `test_ocr_impls_conform_structurally_not_by_inheritance` pins `IOCREngine not in __mro__` AND `isinstance(impl(), IOCREngine)` still passes via `@runtime_checkable`. **B-48** (nit) — caplog filter cleanup is now identity-based (`removeFilter(rid_filter)` instead of `filters[-1]`). **B-49** (nit) — `test_request_id_var_default_is_empty_string` now uses a fresh `contextvars.Context()` to read the *declared* default rather than circularly setting then asserting `""`. 171 → 174 pytest (+3 net new shape pins). ruff lint+format clean. **Open BUGS_FOUND items: 0** (iter-35 review backlog cleared going into iter 38). Iter 38 picks M1.c — `error_handler` middleware (spec §8) — for code-progress; iter 40 = next code-review checkpoint. iter 36 closed B-42 + B-43 + B-47: **B-43** — `RequestIdMiddleware.dispatch` now emits the spec §9 per-route audit log (`request_start` info on entry with `path`+`method`; `request_end` info on exit with `path`+`method`+`status`+`duration_ms`). Both lines emitted inside the request-id ContextVar scope so `RequestIdFilter` tags them with `rid=`. `time.monotonic()` for duration measurement; `status_code` defaults to 500 if `call_next` raises. **B-42** — `IAuth.verify` reverted to spec signature `creds: HTTPAuthorizationCredentials | None` (was `credentials: str | None`); `NoneAuth` mirrors. New `test_iauth_verify_signature_matches_spec` uses `typing.get_type_hints` to resolve PEP-563 string annotations and pin parameter name + type + return — future drift fails loudly. **B-47** — autouse `_reset_managed_handlers` fixture lifted into new `tests/unit/core/conftest.py` so it applies session-wide; duplicate dropped from `test_logging_config.py`. Test count 167 → 171 (+4: 3 audit-log + 1 signature drift-pin). ruff lint+format clean. Open BUGS_FOUND items: B-44, B-45, B-46, B-48, B-49 (5 remaining: 1 medium, 2 low, 2 nit). Iter 37 should pick **B-44** (medium — sync FS calls under `async def`; ~6-line fix wrapping with `anyio.to_thread.run_sync`). iter 33 (`2bb956d`): adapter Protocols + impls landed (`adapters/{storage,auth,ocr}/{base,…}` + `core/exceptions.py::NotImplementedYet`). `IStorage` Protocol fixed by `specs/02-backend.md §7`; `FilesystemStorage` round-trip + path-traversal guard tested (rejects `..`-escape and absolute-path keys). `IAuth` + `UserContext(user_id, display_name)` + `NoneAuth.verify` returning `("local", "Local User")` for any input (D-005). `IOCREngine` + `LocalDoctrOCR` (raises bare `NotImplementedError` until M3 wires it) + `ModalOCR`/`SharedContainerOCR` (raise spec-named `NotImplementedYet` per D-018). `core/exceptions.NotImplementedYet` subclasses `NotImplementedError`. 15 new pytest tests across `test_adapters_{storage,auth,ocr}.py` (136 → 151). No frontend dependency, no Q-A8 blocker. iter 34 (`b70ec57`): **M1.b** — `RequestIdMiddleware` (`api/middleware/request_id.py`) + structured logging (`core/logging_config.py`) as verbatim ports from pgdp-prep per spec §9. `request_id_var: ContextVar[str]` (empty-string default) + `RequestIdFilter` injects `record.request_id` + `JsonFormatter` (stable `{ts, level, logger, msg, request_id}` schema, extras folded, `exc_info`→string `exc`). Plain formatter line shape `[rid=%(request_id)s]` so `grep 'rid='` works without parsing JSON. `configure_logging(log_format)` is idempotent — managed handler tagged `_pdlabeler_managed=True` so `--reload` doesn't stack handlers AND caplog/uvicorn handlers aren't accidentally evicted. Bootstrap now calls `configure_logging` first (spec §2 step 1) and adds `RequestIdMiddleware` LAST so Starlette's `user_middleware` places it OUTERMOST (spec §12: index 0 = RequestId; CORS inside it). 16 new pytest tests across `tests/unit/core/test_request_id.py` (7) and `tests/unit/core/test_logging_config.py` (9) — including the spec-named acceptance assertions `test_request_id_echoed`, `test_request_id_generated_when_absent`, plain-formatter contains `rid=abc`. 151 → 167. Remaining M1 sub-tasks: `error_handler` middleware, `core/app_state` skeleton, `api/dependencies`, full `bootstrap.build_app` wiring (steps 2-6 + 9-12 per spec §2), `core/persistence/{paths,session_state}`, `__main__` CLI flag wiring, frontend `HeaderBar`/`EmptyProjectState`/`RootPage` (Q-A8-gated). iter 35 **code-review checkpoint** (iters 31-34) → 8 new findings (B-42..B-49: 0 blocker, 0 high, 3 medium, 3 low, 2 nit). Top concerns: **B-43 (medium)** — spec §9's audit-log enhancement (`request_start`/`request_end` info logs naming path/method/status/duration_ms; explicitly "closes pgdp-prep gap" per spec) was *quietly skipped* on iter-34's "verbatim port from pgdp-prep per spec §9" commit, not in remaining-M1-sub-tasks list, gap is invisible. **B-42 (medium)** — `IAuth.verify` parameter type drifted from spec's `creds: HTTPAuthorizationCredentials \| None` to impl's `credentials: str \| None` without a spec-edit-first decision. **B-44 (medium)** — `FilesystemStorage.delete`/`list_keys`/`put_bytes` parent-mkdir use sync FS calls under `async def` (defeats async; `put_bytes` comment admits the shortcut). Plus B-45 (low, path-traversal docstring vs impl mismatch on absolute keys), B-46 (low, OCR impls subclass Protocol while auth/storage don't), B-47 (low, missing autouse cleanup in `test_request_id.py`), B-48/B-49 (nits). **M1 progress: ~35%** — M1.a + M1.b done; ~6 chunks remain. Iter 36 should pick **B-43 first** (spec gap, ~10 lines), then **B-42** (signature drift, decision required) — pairs with B-47. Alternatively pivot to M1.c (error_handler middleware, spec §8) for code-progress over backlog cleanup. Iter 40 = next code-review checkpoint. |
| **M0** Repo scaffold | 🟡 in progress (acceptance gate blocked on Q-A8 + Q-A9) | Iter 1 backend skeleton + tests; iter 2 frontend scaffold (files only); iter 3 `mise.toml` + Makefile + Makefile parse smoke tests; iter 4 `.pre-commit-config.yaml` mirroring pd-prep-for-pgdp + YAML-shape smoke tests; iter 5 **code-review checkpoint** → 9 findings filed in `BUGS_FOUND.md`; iter 6 fixed B-02 + B-03; iter 7 fixed B-01 + B-09; iter 8 fixed B-05 + B-06 + B-08; iter 9 fixed B-04 (Settings now `frozen=True` + `Settings(**overrides)` in `__main__`) + B-07 (`_build_env()` no-arg) and added `docs/DEVELOPMENT.md` with shape-pin tests; iter 10 **code-review checkpoint** → 5 new findings (B-11..B-15: 2 low, 3 nit; no blockers); iter 11 fixed B-12 + B-13 + B-14 + B-15; iter 12 fixed B-11 (post-commit pre-commit hook auto-runs `make refresh-version` so `__version__` stays current); iter 13 wired Tailwind v3.4 (`tailwind.config.js`, `postcss.config.js`, `src/index.css` with three `@tailwind` directives, `main.tsx` imports it, devDependencies pin v3.x/v8.x/v10.x); iter 14 added `Dockerfile` (three named stages: `spa`/`wheel`/`runtime`, Node 24 + Python 3.13 matching `mise.toml`, `COPY --from=spa` lands SPA at `src/pd_ocr_labeler_spa/static/` for `build_hooks/spa_check.py`, runtime `EXPOSE 8080` + `pd-ocr-labeler-ui --host 0.0.0.0 --no-browser`) + `.dockerignore`; iter 15 **code-review checkpoint** → 7 new findings (B-16..B-22: 1 high, 2 medium, 2 low, 2 nit). Top concern: B-16 (Dockerfile `ENV PD_LABELER_HOST/PORT` doesn't match `Settings` `PDLABELER_*` prefix — env-name underscore mismatch). iter 16 fixed B-16 (dropped dead `ENV PD_LABELER_*` lines from `Dockerfile`; new test sources the prefix from `Settings.model_config["env_prefix"]` at runtime so any future drift fails loudly) + B-17 (added `post-rewrite` + `post-checkout` pre-commit hook stages, all converging on new `scripts/refresh_version_git_hook.sh` so amend/rebase/cherry-pick no longer leave `__version__` stale) + B-22 (paired doc-honesty annotation on B-11). iter 17 fixed B-20 (Dockerfile runtime stage now installs from a frozen `uv export` requirements.txt with `--no-deps` wheel install, so transitive deps come from `uv.lock` instead of fresh PyPI resolution) + B-21 (runtime apt-get install/purge git+ca-certificates inside a single RUN so the final image carries no git binary) and corrected the iter-12 backlog-zero annotation to reference subsequent iter-15 findings. iter 18 added `make docker-build` / `docker-run` / `docker-shell` targets (mirrors pd-prep-for-pgdp shape; `docker-build` depends on `frontend-build`; `docker-run` maps `$(DOCKER_PORT):8080`) plus `tests/unit/test_makefile_docker.py` (10 tests: dry-run parse for each target, help-output coverage, default tag pin, three-way Settings/Dockerfile-EXPOSE/Makefile-`-p` port alignment, .PHONY coverage). iter 19 added `install.sh` (POSIX bash, mirrors pd-prep-for-pgdp installer pattern: `uv tool install` against the wheel attached to the latest GitHub Release; no Node/npm required at install time; ~75 lines) plus `tests/unit/test_install_sh.py` (10 tests: existence + executable bit, bash shebang + `set -euo pipefail`, Python pin sourced from `mise.toml`, entrypoint name sourced from `pyproject.toml [project.scripts]`, repo slug sourced from `[project.urls].Homepage`, `bash -n` syntax check, `uv tool install` peer-mirror pin, ~80-line size budget). iter 20 **code-review checkpoint** → 5 new findings (B-23..B-27: 0 blocker, 0 high, 1 medium, 2 low, 2 nit). Top concern: B-23 (no `uv lock --check` gate anywhere — B-20 made docker-build the only place lockfile drift surfaces). iter 21 fixed B-23 (added `uv-lock-check` pre-commit hook in the `local` repo block running `uv lock --check` with `language: system` + `files: ^(pyproject\.toml|uv\.lock)$`; new `tests/unit/test_uv_lock_check.py` with 2 tests pinning hook shape + asserting current lockfile passes `uv lock --check` as a subprocess) + B-26 (flipped M0 sub-task checkboxes for iter-18 docker-* and iter-19 install.sh, split out a new `install.ps1` pending bullet). iter 22 fixed B-24 (added `_docker` Makefile macro analogous to `_npm` so docker-* targets emit a friendly diagnostic with install pointers when docker isn't on PATH; all three recipes dispatch via `$(call _docker,…)`) + B-25 (added a real `python3 -c "import sys; ..."` preflight check to `install.sh` so the script behaviourally inspects the system Python — was previously comment-only; new `test_install_sh_runs_python_version_preflight` pins the behavioural invariant) + B-27 (switched `install.sh` from `/repos/X/tags` to `/repos/X/releases/latest` — single call, robust to pre-1.0 retag history; new `test_install_sh_uses_releases_latest_endpoint` pins both the new endpoint and forbids the bare `/tags` regression). Frontend `npm install` still blocked on Q-A8. `install.ps1` (Windows) and `release.yml` (GitHub Actions) still pending for M0 acceptance gate; shadcn primitives still gated on Q-A8. iter 23 (`d2bab21`): added `install.ps1` (PS 5.1+ compatible mirror of install.sh) + 9 shape pins. iter 24 (`8a848c8`): added `.github/workflows/release.yml` (publish wheel + sdist on `v*` tag push, 12 shape pins; PyPI deferred per Q-A10). iter 25 **code-review checkpoint** → 9 new findings (B-28..B-36: 0 blocker, 1 high, 1 medium, 2 low, 5 nit). Top concern: **B-28** — `release.yml` runs `npm ci` against an absent `frontend/package-lock.json` (M0-load-bearing; coupled with B-19); release pipeline can't run end-to-end on first tag push. Second: **B-29** — `tags: ["v*"]` is too permissive (matches `vfeature-test` etc.). **M0 acceptance gate not yet declarable complete:** clauses still blocked on Q-A8 (frontend toolchain — no npm/Node available, blocks `make frontend-build`/`frontend-install`/`frontend-test` runtime verification AND the package-lock.json generation that B-28 needs), Q-A9 (eslint config + `lint` script restoration), and B-28 (release pipeline). Iter 26 picks B-28 first; an M0-close iteration needs Node availability resolved first. iter 26 fixed **B-28 + B-19 (paired)**: both `release.yml` "Build SPA bundle" step and `Dockerfile` `spa` stage rewritten to a two-pass install — `if [ ! -f package-lock.json ]; then npm install --package-lock-only; fi && npm ci` — so the first tag push and the docker build both succeed regardless of whether a real `frontend/package-lock.json` is committed (Q-A8 still blocking that). Once a real lockfile lands, the bootstrap branch is a no-op and `npm ci` stays the source of truth. Three new regression tests: `test_uses_two_pass_install_with_lockfile_fallback` (release workflow), `test_spa_stage_uses_npm_ci_with_lockfile_fallback` (Dockerfile), `test_dockerfile_and_release_workflow_agree_on_npm_install_logic` (cross-file alignment guard so future tightenings can't drift the two stages back into the iter-25 inconsistency). Existing `test_uses_npm_ci_not_npm_install` loosened to allow the bootstrap form while still forbidding bare `npm install`. M0 release-pipeline blocker removed; remaining M0 blockers are Q-A8 (Node unavailability) + Q-A9 (eslint config). iter 27 (`c6eabad`): fixed B-29 (PEP-440 tag globs) + B-30 (concurrency block) + B-31 (npm + uv caching) + B-35 (tightened `uv tool install` test) + B-36 (release.yml comment re-word). iter 28: fixed B-32 + B-33 + B-34. **B-32:** `Test-Command` rewritten as `return $null -ne (Get-Command -Name $Name -ErrorAction SilentlyContinue)` — explicit Boolean, no array-on-success-path coercion. **B-33:** Python preflight now invokes `& python --version 2>&1` and matches `^Python \d+\.\d+\.\d+$` via `-notmatch` so the Microsoft Store stub redirector is detected and surfaces a clear "install real Python from python.org / `winget install Python.Python.3.13`" message. **B-34:** dropped `python-version` from `astral-sh/setup-uv@v4`'s `with:` block — `uv build` provisions its own PEP 517 build-isolated Python, so the setup-uv pin was redundant (~5s wasted CI per run). Renamed `test_python_version_matches_mise` → `test_python_pin_in_release_workflow` and loosened to accept comment-mention so the `mise.toml` Python pin still drift-checks against this workflow. New tests: `test_test_command_returns_explicit_boolean`, `test_install_ps1_detects_ms_store_stub_python`, `test_setup_uv_does_not_set_python_version`. install.ps1 size budget bumped 120→140 lines (B-33 stub-detection branch). 130/130 pytest passing. Open BUGS_FOUND items remaining: only **B-18** (Tailwind glob fragility, low). iter 29: closed **B-18** (rewrote the Tailwind shape-pin test to parse the `content: [...]` array and assert it CONTAINS the canonical `./src/**` scan, tolerant to additive shadcn/ui evolution; brace-expansion entries with extra extensions accepted as long as `ts`/`tsx` are in the set) and added **`docs/M0-acceptance.md`** (single-page sign-off doc — eight criterion clauses straight from `specs/16-milestones.md` §M0, current status row-by-row, Q-A8/Q-A9 remaining-blockers section, and the six-step ritual that flips M0 from "in progress" to "done"). New `tests/unit/test_m0_acceptance.py` (6 shape pins: file exists, `## Status` section, Q-A8/Q-A9 named, every spec-mandated `make` token referenced, sign-off ritual section, spec+ROADMAP citations). Test count: 130 → 136. **All open BUGS_FOUND items closed going into iter 30.** iter 30 **code-review checkpoint** (iters 26–29) → 5 new findings (B-37..B-41: 0 blocker, **1 high**, 0 medium, 2 low, 2 nit). Top concern: **B-37 (high)** — `actions/setup-node@v4` `cache: "npm"` + missing `frontend/package-lock.json` will hard-fail the workflow at the Setup Node.js step BEFORE the iter-26 two-pass install gets a chance to bootstrap the lockfile, silently re-opening B-28. Other findings: B-38 (low, `--include=dev` asymmetry between Dockerfile and release.yml — "byte-aligned" framing overstates parity), B-39 (nit, `test_python_pin_in_release_workflow` accepts any `3.13` substring after iter-28 loosening — pinned to a comment, not a real workflow pin), B-40 (nit, install.ps1 MS Store stub regex `^Python \d+\.\d+\.\d+$` rejects pre-release Python like `3.14.0a1` and mislabels it as a stub), B-41 (low, cross-file `--package-lock-only` pin is planned-obsolete; future Q-A8-unblock iter must remove from BOTH files AND the test, no in-test breadcrumb). 136/136 pytest still green; ruff + pre-commit clean. **M0 status (re-assessed):** still NOT declarable complete — three blockers: Q-A8 (frontend toolchain, gates 4/8 acceptance criteria), Q-A9 (ESLint config, gates 1/8), and B-37 (release pipeline cannot run end-to-end due to setup-node hard-failing on missing lockfile). Iter 31 should pick **B-37 first** (one-line fix: drop `cache: "npm"` until Q-A8 lands the lockfile), bundled with B-38 (`--include=dev` symmetry). iter 31 fixed **B-37 + B-38 (paired)**: dropped `cache: "npm"` + `cache-dependency-path` from `actions/setup-node@v4` (with inline comment + Q-A8 breadcrumb), and added `--include=dev` to BOTH npm invocations in `release.yml`'s Build SPA bundle step so Dockerfile/workflow are flag-set-symmetric. Replaced `test_setup_node_enables_npm_cache` with `test_setup_node_npm_cache_disabled_until_lockfile_lands` (YAML-walk forbidding both `cache:` and `cache-dependency-path:` keys until Q-A8 lands); tightened `test_dockerfile_and_release_workflow_agree_on_npm_install_logic` to assert `--include=dev` symmetry on every `--package-lock-only` and `npm ci` line in both files (non-comment only, so a future comment-only mention can't satisfy the symmetry alone). 136/136 pytest still green; ruff lint+format clean. **M0 release pipeline blocker B-37 closed**; remaining M0 blockers are Q-A8 (frontend toolchain, gates 4/8 acceptance criteria) + Q-A9 (ESLint config, gates 1/8). Open BUGS_FOUND items: **B-39** (nit, `test_python_pin_in_release_workflow` `3.13` substring is now coupled to a comment) + **B-40** (nit, install.ps1 MS Store stub regex rejects pre-release Python like `3.14.0a1`) + **B-41** (low, cross-file `--package-lock-only` pin is planned-obsolete; future Q-A8-unblock iter must remove from BOTH files AND the test). Iter 32 will batch B-39 + B-40 + B-41. iter 32 fixed **B-39 + B-40 + B-41 (batched)**: **B-39:** test renamed `test_python_pin_in_release_workflow` → `test_python_pin_in_release_workflow_matches_mise_if_set` and reshaped from prose-coupling ("must mention `3.13` somewhere") to a meaningful drift check (any step's `with: { python-version: ... }` value must equal `_mise_pin("python")`; today no key exists, so the assertion is a no-op until a future setup-python step re-introduces a pin). **B-40:** install.ps1 MS Store stub regex loosened from `^Python \d+\.\d+\.\d+$` to `^Python \d+\.\d+(\.\d+)?` (anchor on major.minor, optional patch, allow any trailing characters), so `Python 3.14.0a1`, `Python 3.14.0rc2`, and `Python 3.13.0+` (pyenv-built) all match while the stub's "Python was not found" reparse-output is still detected; diagnostic message reworded to lead with what was checked rather than asserting "this is the Store stub" up front. **B-41:** added explicit PLANNED-OBSOLESCENCE breadcrumb docstrings to BOTH `test_uses_two_pass_install_with_lockfile_fallback` (release workflow) and `test_dockerfile_and_release_workflow_agree_on_npm_install_logic` (cross-file Dockerfile/release alignment), naming Q-A8 as the unblock trigger and enumerating the four-place cleanup that must land in a single commit (drop bootstrap from release.yml + Dockerfile, drop the workflow-side assertion, drop the cross-file `--package-lock-only` clauses). 136/136 pytest still green; ruff lint+format clean; install.ps1 at 139 lines (under 140 budget). **Open BUGS_FOUND items: 0** (entire iter-30 review backlog closed). Iter 33 should resume scaffolding — natural next chunks are M1 entry specs, shadcn-init prep that doesn't require Node, or a `CHANGELOG.md`. Iter 35 = next code-review checkpoint. |
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
- [x] Makefile `docker-build` / `docker-run` targets wiring the new
  Dockerfile (specs/15 §6). Iter 18 (`b1ac8d5`): added
  `docker-build` / `docker-run` / `docker-shell`; `docker-build`
  depends on `frontend-build`; host port via `DOCKER_PORT`,
  container port pinned to 8080 (matches Settings + Dockerfile
  EXPOSE). 10 new tests in `tests/unit/test_makefile_docker.py`.
- [x] `install.sh` (uv tool installer). Iter 19 (`f540c62`): mirrors
  pd-prep-for-pgdp's installer pattern (auto-installs uv if missing
  → resolves latest tag via GitHub API → `uv tool install
  --reinstall <wheel>`). 75 lines + 10 shape pins in
  `tests/unit/test_install_sh.py`.
- [x] `install.ps1` (Windows uv tool installer). Iter 23: mirrors
  `install.sh` shape in PowerShell idiom (`$ErrorActionPreference =
  'Stop'`, `Test-Command` helper, uv-bootstrap via
  `https://astral.sh/uv/install.ps1`, `python -c` preflight,
  `/releases/latest` endpoint with B-27 parity, `uv tool install
  --reinstall <wheel>`). PowerShell 5.1+ compatible (the version
  shipped with Windows 10/11). No CUDA/GPU branch (matches
  `install.sh`; pd-ocr-labeler-spa has no GPU extras). 9 shape pins
  in `tests/unit/test_install_ps1.py`.
- [x] `.github/workflows/release.yml` (publish wheel + sdist on
  `v*` tag push). Iter 24: single `release` job on `ubuntu-latest`;
  `actions/checkout@v4` with `fetch-depth: 0` (hatch-vcs needs the
  full history + tag); Node 24 + Python 3.13 pinned to match
  `mise.toml`; `cd frontend && npm ci && npm run build` produces
  the SPA bundle; `uv build` produces wheel + sdist; in-workflow
  `python -m zipfile -l` check verifies the wheel contains
  `pd_ocr_labeler_spa/static/index.html` before publish (defence
  in depth alongside `build_hooks/spa_check.py`); both assets
  attached to the GitHub Release via `softprops/action-gh-release@v2`
  with `fail_on_unmatched_files: true`. PyPI publishing
  intentionally NOT wired (Q-A10) — no `PYPI_TOKEN` /
  `secrets.PYPI*` references; the in-workflow comment names OIDC
  trusted-publishing as the only acceptable future path. 12 shape
  pins in `tests/unit/test_release_workflow.py` (existence, valid
  YAML, `v*` tag trigger, `fetch-depth: 0`, `@v<N>` major-pin for
  every `uses:` ref, Node + Python pins sourced from `mise.toml`,
  `npm ci` not `npm install`, `uv build`, publish-or-upload step
  exists, wheel attached to Release, no `PYPI_TOKEN`/`TWINE_*`/
  `secrets.PYPI*` regressions).
- [ ] M0 acceptance gate: `make ci` green, `make build` produces a
  wheel that contains `pd_ocr_labeler_spa/static/index.html`,
  `pd-ocr-labeler-ui --no-browser --port 8080` answers `/healthz`,
  `make openapi-export` regenerates `frontend/src/api/types.ts`.

## Iteration index (this repo)

See `/workspaces/ocr-container/docs/LOOP_STATE.md` for the full per-
iteration log driven by the dev /loop.

# BUGS_FOUND — code-review checkpoint, iter 5 (2026-05-06)

Review scope: commits `2f01b17` (iter 1), `4cb9f31` (iter 1b/ROADMAP),
`d96b6c6` (iter 2 frontend scaffold), `3bfd560` (iter 3 mise+Make),
`c849d0e` (iter 4 pre-commit). Reviewer ran `uv run pytest` (21/21
green), `uv run ruff check` (clean), `uv run ruff format --check`
(clean), `uv build --wheel` (correctly fails at the spa_check hook,
hook works as designed), and confirmed `pd-ocr-labeler-ui --version`
returns `0.0` from the `v0.0` tag.

Findings filed below. **Do not fix this iteration** — iter 6+ picks
from the list. Severity legend: blocker > high > medium > low > nit.

---

## B-01 — `/env.js` is mounted unconditionally; spec §2 step 12 gates it on `mode != "api_only"`
- **Status:** ✅ **Fixed in iter 7 (2026-05-06)** — `install_env_js`
  call is now wrapped in `if settings.mode != "api_only":` in
  `src/pd_ocr_labeler_spa/bootstrap.py`. Test fixture for the prior
  cement-the-wrong-shape assertion was relocated:
  `tests/unit/test_env_js.py` parametrises across modes (route present
  + spec-shape check in `normal`; route absent in `api_only`, both
  via 404 and via app.router.routes inspection). The
  `test_app_factory.py` purity test now uses `mode="normal"` and adds
  a separate `api_only`-omits-/env.js assertion. LOOP_STATE iter-7
  row records the sha.
- **Severity:** medium
- **Where:** `src/pd_ocr_labeler_spa/bootstrap.py:69-70`; spec
  `specs/02-backend.md:99-100`; reinforced by the divergent test
  `tests/unit/test_healthz.py:36-46` which asserts /env.js works
  under the `api_only` fixture (so the test cements the wrong shape).
- **Issue:** `install_env_js(app)` runs in `build_app` regardless of
  `settings.mode`. Spec §2 says step 12 (which installs /env.js,
  /image-cache static mount, and the SPA fallback) is skipped in
  `api_only` mode. The current test fixture pins `mode="api_only"`
  yet the test expects `GET /env.js` to return 200 — so the test
  is also out of contract.
- **Why it matters:** `api_only` exists so headless / OpenAPI-export
  / pure-API integration tests don't pull in SPA-only routes. If the
  /env.js gate is wrong now, M1's mount of `/image-cache` and the
  SPA fallback will likely follow the same pattern and the
  `api_only` mode silently does nothing. It also means `make
  openapi-export` (which builds an app via `build_app()`) emits
  /env.js in the OpenAPI surface inadvertently — currently masked
  by `include_in_schema=False`, but the contract is still wrong.
- **Suggested fix:** Gate the `install_env_js(app)` call on
  `settings.mode != "api_only"`; flip the `test_env_js_…` test to
  the `normal`-mode client (or split fixtures); add a regression test
  asserting `/env.js` is **not** registered in `api_only` mode.

## B-02 — Vite dev proxy targets port 8765, but backend default is 8080
- **Status:** ✅ **Fixed in iter 6 (2026-05-06)** — see
  `frontend/vite.config.ts` (all three proxy keys now → `:8080`) and
  `tests/unit/test_vite_config.py` (3 regression tests). LOOP_STATE
  iter-6 row records the sha.
- **Severity:** high
- **Where:** `frontend/vite.config.ts:17-19` (`/api`, `/image-cache`,
  `/env.js` all → `http://localhost:8765`).
- **Issue:** Three different specs and the Makefile agree the FastAPI
  default port is `8080`:
    - `specs/02-backend.md:118` (`port: int = 8080`)
    - `specs/02-backend.md:559` ("Vite-dev (5173 → 8080)")
    - `specs/15-deployment-dev.md:108` ("vite dev server on :5173 with
      proxy to :8080")
    - `Makefile:167-168` `dev:` target runs
      `pd-ocr-labeler-ui --reload --frontend-dev http://localhost:5173`
      using the default `8080` port.
  But `vite.config.ts` hard-codes `8765`. `make frontend-dev` running
  alongside `make dev` will not proxy — every `/api/*`, `/image-cache/*`
  and `/env.js` request from the SPA falls through to a closed port,
  manifesting as `ECONNREFUSED` in the browser.
- **Why it matters:** This is the only path that lets the dev /loop
  (or a human) iterate on frontend without rebuilding the wheel each
  time. M1+ frontend work is hard-blocked the moment we have a real
  API call.
- **Suggested fix:** Change all three proxies to
  `http://localhost:8080`. (Optionally, read the port from a
  `VITE_BACKEND_PORT` env var with a default of 8080 — but a literal
  matches the Makefile and spec.)

## B-03 — CORS config sets `allow_credentials=True` together with `allow_origins=["*"]`
- **Status:** ✅ **Fixed in iter 6 (2026-05-06)** — `allow_credentials`
  removed from `CORSMiddleware` kwargs in
  `src/pd_ocr_labeler_spa/bootstrap.py`; matches pgdp-prep + spec
  §step-7. Regression test in `tests/unit/test_cors_middleware.py` (2
  tests: wildcard+credentials combo refused; kwargs shape pinned).
  LOOP_STATE iter-6 row records the sha.
- **Severity:** medium
- **Where:** `src/pd_ocr_labeler_spa/bootstrap.py:57-63`.
- **Issue:** Per the CORS spec (and how Starlette/FastAPI implement
  it) `allow_origins=["*"]` and `allow_credentials=True` are mutually
  exclusive — modern browsers reject the combo. pgdp-prep, the
  declared model, sets only `allow_origins`/`allow_methods`/`allow_headers`
  (see `pd-prep-for-pgdp/src/pd_prep_for_pgdp/bootstrap.py:216-219`).
  Spec `specs/02-backend.md:557` lists only the three wildcards — no
  `allow_credentials`.
- **Why it matters:** Cookie/credentialed cross-origin requests will
  not work in the browser; Starlette currently echoes the origin back
  but does so in a way that confuses some proxies. Drift from the
  modeled-on shape will silently bite once auth lands (M1+).
- **Suggested fix:** Remove `allow_credentials=True` from the
  `add_middleware(CORSMiddleware, ...)` call to match the spec and
  pgdp-prep.

## B-04 — `__main__.py` mutates `settings.frontend_dev_url` after construction; spec §3 forbids it
- **Status:** ✅ **Fixed in iter 9 (2026-05-06)** — `__main__.py` now
  builds an `overrides` dict from CLI args (`frontend_dev_url`, `host`,
  `port`) and passes it to `Settings(**overrides)` once. Enabled
  `frozen=True` in `SettingsConfigDict` so any future regression to
  `settings.<field> = …` raises `ValidationError("frozen")` at the
  call-site. Two regression tests in `tests/unit/test_settings.py`:
  (1) runtime check that `frontend_dev_url`/`host`/`port` are frozen;
  (2) AST-level scan of `__main__.py` rejecting any `settings.<attr>
  = …` assignment, so the static guard survives if a future M2 change
  has to disable `frozen` to thread an api-key reload signal.
- **Severity:** low
- **Where:** `src/pd_ocr_labeler_spa/__main__.py:55-60`.
- **Issue:** Spec §3 (`specs/02-backend.md:148-149`) states "override
  after construction is forbidden." The code mutates the field anyway
  with a self-aware comment ("M0 still mutates here…"). The comment
  promises an M1 fix. Filing now so iter 6/M1 doesn't lose track.
- **Why it matters:** Tomorrow's contributor reads `settings.py`,
  decides to add `frozen=True` to `model_config`, and the M0 CLI
  breaks at startup. The sooner we wire `Settings(**overrides)` the
  sooner this dies.
- **Suggested fix:** Build settings overrides as a dict from CLI
  args (`overrides["frontend_dev_url"] = args.frontend_dev` if set)
  and pass into `Settings(**overrides)` once.

## B-05 — `frontend/package.json` declares `npm run lint` but eslint is not installed
- **Status:** ✅ **Fixed in iter 8 (2026-05-06)** — dropped the
  dangling `lint` script from `frontend/package.json`. Re-introducing
  it requires landing eslint + a real `eslint.config.{js,ts}` in
  the same change (deferred under Q-A9 in `OPEN_QUESTIONS.md`).
  Regression test in
  `tests/unit/test_frontend_config.py::test_package_json_does_not_declare_unrunnable_eslint_script`
  pins the invariant: if `lint` exists, eslint must be in
  `devDependencies` simultaneously.
- **Severity:** low
- **Where:** `frontend/package.json:10` (`"lint": "eslint . --ext
  .ts,.tsx"`).
- **Issue:** `eslint` is absent from `devDependencies`. Running
  `npm run lint` (or any contributor / future CI step that calls it)
  errors out with "command not found." `eslint.config.ts` is also
  listed in `specs/16-milestones.md:51` as an M0 file but hasn't
  landed yet — consistent with ROADMAP "Tailwind v3.4 + shadcn/ui
  wiring (deferred from iter 2)" but the dangling script is a trap.
- **Why it matters:** Trips up anyone exploring the package locally;
  also masks the real M0 acceptance gate ("ESLint and ruff pass clean"
  per `specs/16-milestones.md:85`).
- **Suggested fix:** Either drop the `lint` script until eslint
  actually lands, or land eslint + a minimal `eslint.config.js` in
  the same iteration. Track under the existing ROADMAP "ESLint
  config" sub-task.

## B-06 — `frontend/package.json` `openapi:gen` script reads `../openapi.json`; Makefile writes `frontend/openapi.json`
- **Status:** ✅ **Fixed in iter 8 (2026-05-06)** — package.json
  `openapi:gen` now reads `openapi.json` (frontend-local), matching
  the Makefile's `cd frontend && … openapi-typescript openapi.json
  -o src/api/types.ts` invocation and `specs/01-data-models.md:712-713`
  + `specs/15-deployment-dev.md:127`. Regression test in
  `tests/unit/test_frontend_config.py::test_openapi_gen_path_is_consistent_across_makefile_and_package_json`
  cross-checks all three sources (Makefile, package.json, spec).
- **Severity:** low
- **Where:** `frontend/package.json:13` vs `Makefile:135-144`.
- **Issue:** `package.json` has
  `"openapi:gen": "openapi-typescript ../openapi.json -o
  src/api/types.ts"` (relative-from-`frontend/`, i.e. repo root).
  The Makefile writes the schema to `frontend/openapi.json` and
  invokes `openapi-typescript openapi.json -o src/api/types.ts`
  (relative to `frontend/`). Two source-of-truth paths for the same
  artifact. Whichever a contributor runs first determines whether
  the other path exists.
- **Why it matters:** `make openapi-export` works today; `npm run
  openapi:gen` would fail unless the user hand-creates a copy at
  the repo root. The two should agree.
- **Suggested fix:** Change the package.json script to
  `openapi-typescript openapi.json -o src/api/types.ts` (matching
  Makefile), or drop the script and rely solely on `make
  openapi-export`.

## B-07 — `_build_env(settings)` ignores its `settings` argument
- **Status:** ✅ **Fixed in iter 9 (2026-05-06)** — dropped the unused
  `settings: Settings` parameter from `_build_env()` (and the now-
  unused `Settings` import) per the principle that an M0 surface
  should be honest about what it actually depends on. M2 (auth seam)
  will reintroduce a `settings` parameter alongside the first real
  consumer (e.g. wiring `settings.api_key` into `API_TOKEN`).
  Regression test in
  `tests/unit/test_env_js.py::test_build_env_helper_signature_has_no_unused_settings_param`
  pins the new shape: zero parameters until M2 lands a consumer.
  Also `del request` inside the route handler so the unused argument
  signal stays consistent.
- **Severity:** nit
- **Where:** `src/pd_ocr_labeler_spa/api/env_js.py:23-29`.
- **Issue:** Helper takes `settings: Settings` but never reads from
  it — the body is a literal `{API_BASE: "", API_TOKEN: None}`. The
  pgdp-prep counterpart wires `settings.api_key` into `API_TOKEN`.
  M0 auth is fixed at "none" so the inert helper is correct *now*,
  but the unused parameter is a smell that confuses static analysis
  (ruff `ARG` not currently enabled — would flag if it were).
- **Why it matters:** M2's auth seam will need to thread real
  values through here; today's no-op signature is a misleading
  promise.
- **Suggested fix:** Either underscore the unused param
  (`def _build_env(_settings: Settings)`) with a comment that M2
  reactivates it, or drop the parameter entirely and reintroduce it
  when first consumer arrives.

## B-08 — `tsconfig.app.json` includes `src/**` so test files are type-checked by `tsc -b` during `npm run build`
- **Status:** ✅ **Fixed in iter 8 (2026-05-06)** — added explicit
  `exclude` patterns for `*.test.{ts,tsx}`, `*.spec.{ts,tsx}`,
  `src/**/__tests__/**` and `src/test/**` to `tsconfig.app.json`,
  and split test type-checking into a new `tsconfig.test.json` that
  extends the app config and re-`include`s the same patterns
  (plus `vitest/globals` + `@testing-library/jest-dom` types).
  `vitest.config.ts` now wires `typecheck.tsconfig` →
  `./tsconfig.test.json`. Production build (`tsc -b` via root
  `tsconfig.json` references) sees app sources only — no vitest
  globals leak into the prod surface. Regression tests in
  `tests/unit/test_frontend_config.py` (3 tests covering app
  excludes, test tsconfig include shape, and vitest wiring).
- **Severity:** low
- **Where:** `frontend/tsconfig.app.json:22` (`"include": ["src"]`)
  combined with `frontend/package.json:8` (`"build": "tsc -b && vite
  build"`).
- **Issue:** `App.test.tsx` lives under `src/` and is included by
  the production tsconfig. With `noUnusedLocals`, `noUnusedParameters`
  and `verbatimModuleSyntax` strictness, any test file that brings
  in vitest globals via type-side-effect (`@testing-library/jest-dom`)
  will compile under `tsc -b` only because `setup.ts` is also
  included. As tests grow this surface is brittle (e.g. a typed
  `vi.mock` returning `unknown` will fail strict checks on prod
  build).
- **Why it matters:** The first non-trivial Vitest test added in M1
  may break `make frontend-build` and therefore `make build`.
- **Suggested fix:** Either exclude `src/**/*.{test,spec}.{ts,tsx}`
  and `src/test/**` from `tsconfig.app.json`, or split into
  `tsconfig.test.json` (referenced from the root tsconfig). Mirror
  whatever pgdp-prep does in this regard.

## B-09 — `v0.0` tag yields a non-canonical PEP-440 version
- **Status:** ✅ **Fixed in iter 7 (2026-05-06)** — `git tag -d v0.0`
  + `git tag v0.0.0 2f01b17`. Same target commit, so hatch-vcs
  derivation is stable for that point in history. After
  `uv sync --reinstall-package pd-ocr-labeler-spa` the wheel filename
  resolves to `pd_ocr_labeler_spa-0.0.1.dev6+g6b6835b13.d20260506`
  (verified via `uv build --wheel`). No push performed; pure local
  retag. LOOP_STATE iter-7 row records the sha.
- **Severity:** nit
- **Where:** repo `git tag v0.0` (commit `2f01b17`); confirmed by
  `uv run pd-ocr-labeler-ui --version` → `0.0`.
- **Issue:** Peer pd-* repos start at `v0.1` (`pd-prep-for-pgdp`)
  or use full SemVer `v0.10.0` (`pd-book-tools`). `0.0` parses fine
  via `packaging.version.Version("0.0")` and hatch-vcs accepts it,
  but it's sub-canonical (no patch component) and could break
  consumers that grep on a SemVer regex. README/docs do not
  reference a published version yet, so impact is bounded.
- **Why it matters:** First publish (M0 acceptance gate) wants a
  legitimate-looking version. Easy to fix now; embarrassing later.
- **Suggested fix:** Re-tag at `v0.0.0` (or jump to `v0.1.0`,
  matching pgdp-prep's "pre-1.0 increments are minor" convention).
  Add `git tag -d v0.0 && git tag v0.0.0 <sha>` instructions to
  ROADMAP iter-6 task list. **No git rewrite is needed; just retag.**

## B-10 — Iter 4 commit message says "21 passed" but ROADMAP iter 4 entry was earlier; cosmetic drift
- **Severity:** nit
- **Where:** commit `c849d0e` body claims "Tests: ... pre-commit smoke
  YAML-shape" added "5 tests"; current count is 21 (12 baseline + 4
  Makefile + 5 pre-commit = 21). The iter-3 commit log claimed "16
  passed" which checks out (12 + 4). All numbers reconcile — this
  is **not** a bug, recorded as a sanity cross-check.
- **Issue:** None — disregard.
- **Why it matters:** Establishes that test counts in commit
  messages so far have been accurate; trust the counts going forward.
- **Suggested fix:** N/A.

---

## What was checked and did NOT yield a finding

- `build_hooks/spa_check.py`: tested by attempting `uv build --wheel`
  with no SPA bundle — fails loudly with the right message. Editable
  install path (skipped) is exercised in `make refresh-version`.
- `Settings(extra="ignore")` correctly accepts unknown
  `PDLABELER_*` env (test_settings_ignores_extra_env). Spec §3
  doesn't pin `extra`; ignore is a sensible default for forward-compat
  with M1 fields.
- `/healthz` excluded from OpenAPI schema — verified.
- `app.state.settings` stash + factory purity — verified by tests
  and re-read.
- `__main__.py` `--no-browser` honors `args.reload` (skips browser
  open under reload mode) — sensible.
- Pre-commit YAML matches pgdp-prep hook list verbatim
  (trailing-whitespace, end-of-file-fixer, check-yaml, check-json,
  ruff-check ×2, ruff-format, pre-commit-update). All revs pinned.
- pyproject.toml's `pd-book-tools` git pin (`v0.9.0`) matches
  pgdp-prep's pin — confirmed cross-repo dep alignment.
- OPEN_QUESTIONS Q-A1..Q-A4 still open and unaffected by shipped
  code (none of the rotation / normalization / 301 paths exist
  yet). Q-A8 is current — devcontainer toolchain unchanged.
- No secrets in `/env.js`, no auth (M0 by design — flagged
  intentionally as M2 concern in `specs/02-backend.md` §3, not a
  finding).

---

## Recommended iter 6 ordering

1. ~~**B-02** (vite proxy port)~~ — ✅ fixed in iter 6.
2. ~~**B-03** (CORS allow_credentials)~~ — ✅ fixed in iter 6.
3. ~~**B-01** (env.js api_only gate + test)~~ — ✅ fixed in iter 7.
4. ~~**B-09** (re-tag `v0.0.0`)~~ — ✅ fixed in iter 7.
5. ~~**B-05** + **B-06** + **B-08** (frontend config trio)~~ — ✅
   fixed in iter 8.
6. ~~**B-04** (settings mutation, `frozen=True`) + **B-07**
   (`_build_env` unused arg)~~ — ✅ fixed in iter 9.

**All findings from the iter-5 review are now addressed.** Iter 10 is
the next code-review checkpoint per /loop cadence (review iters 6-9);
new findings filed there.

---

# Iter-10 code-review checkpoint (2026-05-06)

Review scope: commits `6b6835b` (iter 6: B-02 + B-03), `a1b087c` (iter 7:
B-01 + B-09), `201edb3` (iter 8: B-05 + B-06 + B-08), `7e593cc` (iter 9:
B-04 + B-07 + DEVELOPMENT.md). Reviewer ran `uv run pytest` (42/42
green), `uv run ruff check` (clean), and `python -c "from
pd_ocr_labeler_spa.bootstrap import build_app; build_app()"` (no
error). Verified `git tag -l` shows only `v0.0.0` (B-09 cleanup).

All four fixes hit their targeted bug. Tests added are mostly
behavior-or-AST style rather than dumb file-presence (improvement on
iter-5). Findings below are quibbles — no blockers, no high.

## B-11 — `__version__` is stale: reports `dev6+g6b6835b13` while HEAD is `7e593cc` (iter-9, 9 commits past `v0.0.0`)
- **Status:** ✅ **Fixed in iter 12 (2026-05-06)** — added a post-commit
  hook to `.pre-commit-config.yaml` (`local` repo, `id: refresh-version`,
  `stages: [post-commit]`) that runs `make refresh-version` after every
  commit, plus `default_install_hook_types: [pre-commit, post-commit]`
  so the single `pre-commit install` call already in `make setup`
  installs both hook types. `__init__.py` already used the dynamic
  `importlib.metadata.version` resolution path; the new post-commit
  hook is what keeps that metadata fresh between commits. Three new
  regression tests:
  `test_pre_commit_config.py::test_default_install_hook_types_includes_post_commit`,
  `test_pre_commit_config.py::test_local_refresh_version_post_commit_hook_present`,
  and `test_version.py` (full module: pins both the runtime invariant
  `__version__ == importlib.metadata.version("pd-ocr-labeler-spa")` and
  the static AST invariant that `__init__.py` only ever assigns
  `__version__` from a `version()` call or a literal inside an
  `except PackageNotFoundError:` block — preventing any future drift
  back to a hard-coded string).
- **Severity:** low
- **Where:** runtime — `python -c "import pd_ocr_labeler_spa; print(pd_ocr_labeler_spa.__version__)"` returns `0.0.1.dev6+g6b6835b13.d20260506` even though `git rev-list --count v0.0.0..HEAD` is 9 and HEAD is `7e593cc`.
- **Issue:** `hatch-vcs` writes `_version.py` at install time. Iter 7 ran `uv sync --reinstall-package` after retagging, which froze the version at iter 6's commit. Subsequent iters 8 + 9 didn't refresh, so the in-tree version is now off by 3 commits. This is exactly what `make refresh-version` exists to undo, but no iteration that lands new commits is wired to call it.
- **Why it matters:** Anyone running `pd-ocr-labeler-ui --version` from the working tree gets a misleading answer (the iter-7 commit message asserted this version too — a forensic record now drifted). The on-disk wheel artefact (if rebuilt) would be correct because `make build` re-derives. But local devs running `uv run` see stale data.
- **Suggested fix:** Make `make refresh-version` part of the post-commit pre-commit hook, or have `make setup` always re-run it. Alternatively, document that `pd_ocr_labeler_spa.__version__` is install-time-frozen and steer callers to `subprocess.run(["git", "describe"])` or `importlib.metadata.version` after a fresh sync. (Either way: not a correctness bug, just a developer-ergonomics gotcha.)

## B-12 — DEVELOPMENT.md describes a dev loop that doesn't exist in M0
- **Status:** ✅ **Fixed in iter 11 (2026-05-06)** — split the
  dev-server section into "What you'll see in M0" (names `/healthz` +
  `/env.js`, flags `GET /` as 404, points at Q-A8 for the Vite-side
  block, recommends pytest+curl as the practical M0 loop) and "What's
  coming in M1+" (preserves the two-process loop for when it lands).
  Added regression test
  `tests/unit/test_development_doc.py::test_development_doc_is_honest_about_m0_limits`
  that pins the M0 callout: requires the doc to name `/healthz`,
  `/env.js`, and either `404` or `M1` so future drift is caught by
  CI rather than by a confused contributor.
- **Severity:** low
- **Where:** `docs/DEVELOPMENT.md:44-60` ("Running the dev server" section).
- **Issue:** The doc says `make dev` "proxies unknown asset paths to a Vite dev server at http://localhost:5173" and instructs the reader to "Open http://localhost:5173 in a browser. Vite serves the SPA, the proxy forwards API calls to FastAPI". Both halves are false in M0:
  - `make dev` runs `uv run pd-ocr-labeler-ui --reload --frontend-dev http://localhost:5173`. The `--frontend-dev` flag only sets `settings.frontend_dev_url`, which currently has **no consumer** in `bootstrap.py`. The FastAPI side does not proxy anything; `GET /` returns 404 (verified via TestClient).
  - On the Vite side, the proxy *does* work for `/api`, `/env.js`, `/image-cache` (B-02 fix), but there is no SPA bundle to serve from `/` either, so visiting `:5173/` shows the React boilerplate from the iter-2 scaffold rather than anything the FastAPI side knows about.
- **Why it matters:** A new contributor following the doc verbatim will see a 404 / blank page and not know whether they're holding it wrong. Also, the test `test_development_doc_references_only_existing_make_targets` is a target-existence check, not a behavior check — it does **not** catch this drift.
- **Suggested fix:** Add a "M0 status" note next to the dev-server section spelling out that `/` is 404 in M0, or strip the dev-server section down to just "the working flows in M0 are `make test`, `make frontend-test`, and `uv run pd-ocr-labeler-ui --no-browser`" until M1 lands the SPA mount + frontend-dev proxy.

## B-13 — `test_settings_is_frozen_post_construction` only catches `ast.Assign`, not `AugAssign` / `AnnAssign`
- **Status:** ✅ **Fixed in iter 11 (2026-05-06)** — extended the AST
  walker in `tests/unit/test_settings.py::test_main_does_not_mutate_settings_post_construction`
  to handle `ast.AugAssign.target` and `ast.AnnAssign.target` with
  the same `Attribute(value=Name("settings"))` shape. Added
  `test_ast_scanner_catches_all_three_assignment_forms` as a self-test
  feeding all three mutation shapes through the same walker logic so
  future regressions in coverage are caught.
- **Severity:** nit
- **Where:** `tests/unit/test_settings.py:99-127` (`test_main_does_not_mutate_settings_post_construction`).
- **Issue:** The AST walker matches `ast.Assign` only. A regression like `settings.port += 1` (`ast.AugAssign`) or `settings.port: int = 9090` (`ast.AnnAssign`) would silently pass the static check. The runtime `frozen=True` *would* still catch both, so this is belt-and-suspenders only — the suspenders are slightly loose.
- **Why it matters:** Trivial — `frozen=True` is the real gate. Filing only because the comment claims the AST scan is the safety net "if a future M2 change has to disable frozen", and that net has holes for the augmented forms.
- **Suggested fix:** Extend the walker to also visit `ast.AugAssign.target` and `ast.AnnAssign.target` with the same `Attribute(value=Name("settings"))` shape. One-line addition.

## B-14 — `_build_env_helper_signature_has_no_unused_settings_param` is a hostile gate against the M2 fix
- **Status:** ✅ **Fixed in iter 11 (2026-05-06)** — renamed test to
  `test_build_env_does_not_take_an_unused_settings_param` and
  reframed the invariant. New shape: if the signature has no
  `settings` parameter, the test trivially passes; if it has one,
  the function body must reference `settings` somewhere (parsed via
  AST). M0 (no param) passes, M2 (param + real consumer) passes,
  only the misleading "takes settings, ignores settings" shape
  fails. M2 author no longer has a tripwire to step over.
- **Severity:** nit
- **Where:** `tests/unit/test_env_js.py:104-124`.
- **Issue:** The test asserts `_build_env` takes zero parameters. Comment says "until M2 reintroduces a settings consumer" — but when M2 lands the **correct** fix (`_build_env(settings)` with a real consumer reading `settings.api_key`), this test fails and the M2 author has to remember it exists and update it. There's no production-code mechanism that flags it; it's just a tripwire in `tests/`.
- **Why it matters:** Future-tax. Iter 6-9 cleanup is meant to reduce drift, but this test inverts the polarity — it pins absence of a parameter that the spec says will return. Mild risk of confusing the M2 implementer.
- **Suggested fix:** Either drop the test (frozen-via-spec is enough) or rewrite it to assert the **correct** invariant: "`_build_env`'s body never references `settings` while its signature includes it" (parses the function source via `ast` and flags the misleading-signature smell, which generalises to other functions). The latter test would naturally retire when M2 adds a real consumer.

## B-15 — `test_cors_middleware_does_not_combine_wildcard_with_credentials` is conditional and would silently pass on a partial regression
- **Status:** ✅ **Fixed in iter 11 (2026-05-06)** — renamed to
  `test_cors_middleware_does_not_enable_credentials` and dropped the
  `if allow_origins == ["*"]` gate. The assertion now fires
  unconditionally: `kwargs.get("allow_credentials", False) is False`.
  A future change that narrows origins AND re-enables credentials
  now fails this test specifically (clear diagnostic) rather than
  the kwargs-shape pin (misleading "we changed origins" diagnostic).
- **Severity:** nit
- **Where:** `tests/unit/test_cors_middleware.py:35-46`.
- **Issue:** The first CORS test uses `if kwargs.get("allow_origins") == ["*"] or "*" in (...): assert not allow_credentials`. If a future change set `allow_origins=["http://localhost:5173"]` and *also* re-added `allow_credentials=True`, this test silently passes (the conditional gate misses) — and the reader of the kwargs-shape pin (test 2) would also pass because test 2 *expects* `["*"]` and would fail loudly... but that failure mode looks like "we changed origins" rather than "we re-introduced credentials". Diagnostics for the credentials regression specifically are weakened.
- **Why it matters:** Only matters if the CORS surface evolves (M2+). Today both tests work as a pair.
- **Suggested fix:** Drop the conditional in test 1 — assert `kwargs.get("allow_credentials", False) is False` unconditionally. The "wildcard+credentials" framing in the test name is descriptive of the *original* bug; the invariant we actually want is "credentials stays off until auth lands." (Or add a third test with that name.)

## Non-findings (checked, no bug)

- **`Settings(frozen=True)` interaction with future lifespan / DI / tests.** Conftest fixtures use constructor kwargs only (no `monkeypatch.setattr(settings, …)`); spec lifespan reads `app.state.settings` and constructs adapters, no settings mutation. M2's auth-key reload (if it materialises) is the only realistic place where frozen could become a constraint — flag for that milestone but no current bug.
- **CORS spec wording.** `specs/02-backend.md §step-7` matches the new kwargs shape (no `allow_credentials`). pgdp-prep parity confirmed.
- **`v0.0.0` tag location.** Sits on `2f01b17` (iter 1 backend skeleton), the natural anchor. `git rev-list --count v0.0.0..HEAD` returns 9 (matches iter count). hatch-vcs version-derive uses this correctly when `_version.py` is regenerated (see B-11 about staleness).
- **`make dev` running both backend and frontend.** It does NOT run both — it runs only the backend, with `--frontend-dev` flagging the dev URL. The doc says "two-process setup" so the contributor is expected to run `make frontend-dev` in a second terminal. That part of the doc is accurate. (Different from B-12 which is about the proxy not actually working in M0.)
- **`tsconfig.app.json` exclude vs vitest typecheck.** vitest config wires `typecheck.tsconfig: ./tsconfig.test.json`; tsconfig.test.json extends app config and re-includes test files. Production `tsc -b` (via root tsconfig.json references) honours the `exclude` patterns in app config. Confirmed correct.
- **`openapi:gen` script ergonomics.** The script reads `frontend/openapi.json` which is `.gitignore`'d and only written by `make openapi-export`. Running `npm run openapi:gen` standalone fails — but that mirrors pgdp-prep's working setup. Accept by parity.

## Summary

5 findings: 0 blocker, 0 high, 0 medium, **2 low** (B-11 stale `__version__`, B-12 DEVELOPMENT.md drifts from M0 reality), **3 nit** (B-13 AST coverage, B-14 hostile M2 gate, B-15 conditional CORS test). All four fixes (B-01 through B-09) actually fixed their bugs without shifting failure modes. Top concern: **B-12** (doc drift visible to first-time contributors). Iter 11 should pick **B-12 first** (docs accuracy is cheap and load-bearing), and either B-11 or resume scaffolding (Tailwind / Dockerfile / install scripts) — both are reasonable.

---

## Iter 11 disposition (2026-05-06)

- ~~**B-12** (DEVELOPMENT.md M0 honesty)~~ — ✅ fixed (doc split into
  M0 / M1+ sections; new regression test pins the M0 callout).
- ~~**B-13** (AST scanner AugAssign/AnnAssign coverage)~~ — ✅ fixed
  (walker extended; self-test added).
- ~~**B-14** (`_build_env` hostile M2 gate)~~ — ✅ fixed (test
  reframed to "if param exists, body must read it").
- ~~**B-15** (CORS conditional)~~ — ✅ fixed (gate dropped; assertion
  unconditional).
- **B-11** (stale `__version__`) — deferred to iter 12. Lowest-risk
  fix is a Makefile tweak adding `make refresh-version` to a
  post-commit hook or to `make setup` itself. Defer to iter 12.

Test count after iter 11: **44** (was 42 — +1 test for B-12 doc
honesty, +1 for B-13 self-test). All ruff gates clean.

---

## Iter 12 disposition (2026-05-06)

- ~~**B-11** (stale `__version__`)~~ — ✅ fixed. Wired
  `make refresh-version` into the post-commit pre-commit hook (new
  `local` repo entry in `.pre-commit-config.yaml`) and added
  `default_install_hook_types: [pre-commit, post-commit]` so a single
  `pre-commit install` (already part of `make setup`) installs both
  hook types. `__init__.py` was already on the dynamic
  `importlib.metadata.version` resolution path; the install-time
  freeze is now refreshed automatically per commit. Three new
  regression tests across `test_pre_commit_config.py` (post-commit
  hook + default-install-hook-types pins) and a new `test_version.py`
  (runtime + AST guards on dynamic resolution).

**Iter-10 review backlog: zero remaining.** All B-11..B-15 closed.

Test count after iter 12: **48** (was 44 — +2 in pre-commit-config,
+2 in new test_version module). All ruff gates clean.

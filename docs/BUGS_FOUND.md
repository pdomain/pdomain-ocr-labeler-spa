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
- **Status:** ✅ **Fixed in iter 12 (2026-05-06) — extended in iter 16 (2026-05-06) to cover rewrite/checkout (see B-17).** Added a post-commit
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

**Iter-10 review backlog: zero remaining as of iter 12** (B-11..B-15 closed).
Subsequent iter-15 code-review checkpoint filed B-16..B-22; see below
for status of those.

Test count after iter 12: **48** (was 44 — +2 in pre-commit-config,
+2 in new test_version module). All ruff gates clean.

---

# Code-review checkpoint, iter 15 (2026-05-06)

Review scope: commits `d7e133d` (iter 11 — B-12/13/14/15 fixes),
`e83bda1` (iter 12 — B-11 post-commit hook), `97f5c89` (iter 13 —
Tailwind v3.4 wiring), `ebf792f` (iter 14 — Dockerfile +
.dockerignore). Reviewer ran `uv run pytest tests/unit -q` (66/66
green), `uv run ruff check` (clean), `uv run python -c "from
pd_ocr_labeler_spa.bootstrap import build_app; build_app()"` (clean
factory boot, routes are `/healthz`, `/env.js`, plus FastAPI's
auto-mounted `/openapi.json` + `/docs` + `/redoc`).

7 findings. Severity legend: blocker > high > medium > low > nit.

## B-16 — Dockerfile sets `ENV PD_LABELER_HOST/PORT` but `Settings` reads `PDLABELER_*` (no underscore)
- **Status:** ✅ **Fixed in iter 16 (2026-05-06)** — dropped the dead
  `ENV PD_LABELER_HOST/PORT` block from the Dockerfile entirely
  (suggestion (b) — argv `--host 0.0.0.0` already binds the host;
  users override the port via `-e PDLABELER_PORT=…`). New regression
  test `test_dockerfile_env_lines_use_settings_prefix` reads
  `Settings.model_config["env_prefix"]` at runtime and walks every
  `ENV PD…=…` line in the Dockerfile — any token starting with `PD`
  that doesn't match the live prefix fails the test. The pre-existing
  `test_runtime_binds_host_to_all_interfaces` was tightened to
  source-of-truth the prefix from Settings as well, so the env-var
  branch can never re-cement a wrong spelling.
- **Severity:** high
- **Where:** `Dockerfile:91` (`ENV PD_LABELER_HOST=0.0.0.0 PD_LABELER_PORT=8080`); cross-check `src/pd_ocr_labeler_spa/settings.py:29` (`env_prefix="PDLABELER_"`).
- **Issue:** The runtime stage exports `PD_LABELER_HOST` and `PD_LABELER_PORT`, but `Settings` declares `env_prefix="PDLABELER_"` (no underscore between `PD` and `LABELER`). Pydantic-settings ignores the `PD_LABELER_*` envs; the bind-host fallback is the in-image `--host 0.0.0.0` argv (which works for `host` but `port` is silently uncovered by env). `tests/unit/test_settings.py:30` and `specs/02-backend.md §3` both use `PDLABELER_*`. The Dockerfile shape pin in `tests/unit/test_dockerfile.py:212-217` actually requires `PD_LABELER_HOST` (with the wrong underscore), so the test cements the wrong contract — both layers drifted together.
- **Why it matters:** A user running `docker run -e PDLABELER_PORT=9000 …` (the documented spelling) would have no effect; `docker run -e PD_LABELER_PORT=9000 …` (current Dockerfile spelling) also has no effect because Settings ignores it. The image happens to boot correctly because `--host 0.0.0.0` is also passed positionally in `ENTRYPOINT`, but the `ENV` lines are dead code, and the test asserts the dead spelling. Anyone copying this for M1 storage/auth env vars (`PDLABELER_DATA_ROOT`, etc.) will hit the same trap and be confused by the mismatch.
- **Suggested fix:** Either (a) replace `PD_LABELER_*` with `PDLABELER_*` in the Dockerfile and update the regex in `tests/unit/test_dockerfile.py::test_runtime_binds_host_to_all_interfaces`, OR (b) drop the `ENV` lines entirely and rely solely on the `--host 0.0.0.0 --no-browser` argv in `ENTRYPOINT` (cleanest — env is then unambiguously a user-override surface). Going with (b) avoids encoding an env-name in two more places. Also tighten the test to assert the `PDLABELER_` (no underscore) prefix is the only one referenced anywhere in the Dockerfile, mirroring the prefix that `Settings` actually reads.

## B-17 — Post-commit `make refresh-version` hook silently no-ops on `git rebase` / `git cherry-pick` / `git commit --amend`
- **Status:** ✅ **Fixed in iter 16 (2026-05-06)** — chose suggestion
  (a). New `scripts/refresh_version_git_hook.sh` centralises the
  refresh body (`make refresh-version`, fail-soft on missing toolchain,
  cd to repo root irrespective of cwd, accept-and-ignore the
  stage-specific args git/pre-commit pass). `.pre-commit-config.yaml`
  now wires three local hooks all pointing at that script:
  `refresh-version-post-commit`, `refresh-version-post-rewrite`
  (covers `git commit --amend` + `git rebase`), and
  `refresh-version-post-checkout` (covers `git switch`/`git checkout`
  + `git cherry-pick` when it lands HEAD on a different sha).
  `default_install_hook_types` extended to `[pre-commit, post-commit,
  post-rewrite, post-checkout]` so a single `pre-commit install`
  wires every stage. Four regression tests in
  `tests/unit/test_pre_commit_config.py`: hook stages declared,
  script exists + is executable + invokes `make refresh-version`,
  every refresh hook covers exactly one of the three required stages,
  every refresh hook shares the same single script entry (prevents
  the "three copies of `make refresh-version`" anti-pattern). Also
  rewords B-22 (paired finding): see annotation below B-11's
  Status line.
- **Severity:** medium
- **Where:** `.pre-commit-config.yaml:38-49` (`stages: [post-commit]`).
- **Issue:** pre-commit's `post-commit` stage fires on `git commit` only. `git rebase`, `git cherry-pick`, `git commit --amend`, and many merge flows skip post-commit hooks (this is git's behaviour, not pre-commit's bug). After any of those, the editable install retains the **pre-rebase** version; `__version__` then drifts back to the symptom B-11 was supposed to eliminate, with no signal that the auto-refresh stopped working.
- **Why it matters:** Iter-12's commit message frames B-11 as *closed*. It isn't — the hook closes the most common drift path (vanilla `git commit`) but the author switching branches with `git rebase` or amending the most recent commit will still drift. Severity is medium not high because (a) `__version__` is only an informational string, not a behaviour gate; (b) `make setup` / `make refresh-version` always make it correct again, so the failure is recoverable; (c) the new `tests/unit/test_version.py::test_version_matches_installed_metadata` would *fail* CI if `make ci` ran post-rebase without a fresh install — so CI catches it, just not the local dev shell. Still: the iter-12 commit message claims "iter-10 review backlog now zero" which is technically true (B-11 is partially closed) but masks that the underlying drift class still exists.
- **Suggested fix:** One of: (a) add `post-rewrite` and `post-checkout` to `default_install_hook_types` and the `refresh-version` hook's `stages` (covers rebase, amend, cherry-pick, branch switch); (b) demote the hook to a no-op safety net and drive the actual freshness invariant via the existing CI test (`test_version_matches_installed_metadata`) — that test does the right job already; (c) document the gap in `docs/DEVELOPMENT.md` so contributors know to run `make refresh-version` after a rebase. (a) is most thorough; (b) acknowledges the test is the real guard. Either way, update the iter-12 entry in `LOOP_STATE.md` so future readers don't see B-11 as a fully solved problem.

## B-18 — Tailwind shape-pin test asserts content globs as a literal substring (forward-incompatible with shadcn/ui in M1)
- **Status:** ✅ **Fixed in iter 29 (2026-05-06)** — replaced
  `test_tailwind_config_exists_and_targets_src_globs` (substring/OR
  check) with `test_tailwind_config_content_array_includes_canonical_src_glob`,
  which parses the `content: [...]` array out of `tailwind.config.js`
  via regex, extracts the string-literal entries, and asserts the
  parsed list CONTAINS at least one entry that scans `./src/**` for
  both `.ts` and `.tsx` (tolerating brace-expansion forms with extra
  extensions like `{js,ts,jsx,tsx,mdx}`). Future shadcn/ui init that
  *adds* entries (e.g. `./components/**/*.{ts,tsx}`,
  `./app/**/*.{ts,tsx}`) is now accepted; only a regression that
  *removes* the project's own `./src/**` scan will fail. Inline
  comment in `tailwind.config.js` updated to document the
  contains-not-equals contract for future readers. `tailwind.config.js`
  itself unchanged (the existing single-glob form remains the
  minimal correct form; we don't proactively add `./components/**`
  because shadcn/ui init writes that entry itself when it lands).
- **Severity:** low
- **Where:** `frontend/tailwind.config.js:10-13` (`content: ["./index.html", "./src/**/*.{ts,tsx}"]`); pinning test in `tests/unit/test_tailwind_config.py`.
- **Issue:** The glob `./src/**/*.{ts,tsx}` *does* recurse, so any future `src/components/ui/**.tsx` file is technically scanned. **However**, shadcn/ui's `init` writes a `tailwind.config.js` whose content array explicitly lists `./components/**/*.{ts,tsx}`, `./app/**/*.{ts,tsx}`, `./pages/**/*.{ts,tsx}`, and `./src/**/*.{ts,tsx}` — and the `components.json` `cli.tailwind.config` field points at a config the CLI parses. When iter N runs `npx shadcn@latest init` (currently blocked on Q-A8), the CLI may either (a) detect the existing config and merge cleanly, or (b) overwrite the file with its own template. If the test pins a literal substring of the content array, a shadcn overwrite that *expands* the globs would fail the test and force the iter author to manually patch the test rather than accept the more inclusive globs.
- **Why it matters:** Mild future-tax. The wider concern is the test pattern: pinning a literal substring of a glob list is fragile in the face of additive evolution. Today's globs are sufficient (single-source-tree React app), but the test is set up to fight shadcn rather than accept it.
- **Suggested fix:** Loosen the content-globs assertion to require `"./src/**/*.{ts,tsx}"` is present *as one entry* (superset check), rather than as the full content of the array. The `^3.4.0` major pin is correct (v4 is a breaking-change rewrite); no action there.

## B-19 — `Dockerfile` `wheel` stage uses `npm install` (not `npm ci`) and tolerates missing `package-lock.json`
- **Status:** ✅ **Fixed in iter 26 (2026-05-06)** — paired with B-28.
  The Dockerfile `spa` stage now runs a two-pass install
  byte-aligned with the corresponding step in
  `.github/workflows/release.yml`: when `package-lock.json` is absent
  (Q-A8 — Node not yet in devcontainer, no hand-curated lockfile),
  `npm install --package-lock-only --include=dev` generates the lock
  in-place; then `npm ci --include=dev` runs as the canonical
  CI-safe install that fails fast on drift and never mutates the
  lock. Once a real lockfile is committed (Q-A8 unblock), the first
  pass becomes a no-op and `npm ci` stays the source of truth. New
  regression tests in `test_dockerfile.py`:
  `test_spa_stage_uses_npm_ci_with_lockfile_fallback` (pins both
  `npm ci` and the bootstrap form, forbids bare `npm install` outside
  the bootstrap) and `test_dockerfile_and_release_workflow_agree_on_npm_install_logic`
  (cross-file alignment — both files must carry both tokens, so a
  future tighten on one without the other fails the test rather than
  silently re-creating the iter-25 inconsistency).
- **Severity:** medium
- **Where:** `Dockerfile:17-18` (`COPY frontend/package.json frontend/package-lock.json* ./` + `RUN npm install --include=dev`).
- **Issue:** Two reproducibility holes stacked:
  1. `frontend/package-lock.json` doesn't exist in the repo (`ls frontend/package-lock.json` → ENOENT). The `*` glob in the COPY makes the file optional — the build still succeeds — but every container build resolves dependency versions live from npm, so two `docker build`s a week apart can ship different React/Vite/Tailwind patch versions.
  2. Even when a lockfile *does* land (Q-A8 / iter-2 frontend scaffold milestone), the Dockerfile uses `npm install` (which mutates the lockfile) rather than `npm ci` (which fails fast on lockfile drift). For an immutable-image build the `ci` form is the right one.
- **Why it matters:** The iter-14 commit message says "Versions track mise.toml so dev and image share a toolchain" but only the *Node* version is shared — the *npm dependency tree* is not. Reproducible image builds are part of the M0 acceptance gate per `specs/15-deployment-dev.md` (mirrors pgdp-prep).
- **Suggested fix:** Land the lockfile when `make frontend-install` first runs (Q-A8 unblock), then change `Dockerfile:18` to `RUN npm ci --include=dev` and drop the `*` glob from the COPY (so a missing lockfile becomes a hard error rather than silent fallthrough). Add a `tests/unit/test_dockerfile.py` shape pin for `npm ci` once that lands.

## B-20 — `Dockerfile` doesn't use `uv.lock` for reproducible Python deps; `pip install <wheel>` re-resolves
- **Status:** ✅ **Fixed in iter 17 (2026-05-06)** — chose suggestion
  (b) (the architecturally honest path). The wheel stage now runs
  `uv export --frozen --no-emit-project --no-dev --no-hashes -o
  /dist/requirements.txt` after building the wheel, so the locked
  transitive tree travels alongside the wheel. The runtime stage
  COPYs both `/dist/*.whl` and `/dist/requirements.txt`, then installs
  in two passes inside a single RUN: (1) `pip install -r
  /tmp/requirements.txt` (every transitive dep is `==`-pinned or
  git-sha-pinned, so pip cannot drift), then (2) `pip install
  --no-deps /tmp/*.whl` (the wheel itself, declared deps already
  satisfied). `--frozen` makes `uv export` fail loudly on a stale
  lockfile rather than silently re-resolving. Two new regression tests
  in `test_dockerfile.py`: `test_wheel_stage_exports_frozen_requirements_for_runtime`
  pins `uv export` + `--frozen`; `test_runtime_install_uses_frozen_requirements_with_no_deps_wheel`
  pins both `pip install -r …requirements.txt` and `pip install
  --no-deps …*.whl` in the runtime slice (slicing from the third FROM
  so the wheel-stage `uv export` can't satisfy a runtime assertion).
- **Severity:** low
- **Where:** `Dockerfile:48-67` (wheel stage) + `Dockerfile:88` (runtime `pip install /tmp/*.whl`). Note `pyproject.toml` declares `pd-book-tools = { git = ..., tag = "v0.9.0" }` and the repo carries a `uv.lock` (545 KB).
- **Issue:** The wheel stage runs `uv build --wheel` which produces a wheel with the runtime dependency *requirements* baked in (matching `pyproject.toml`), but the *resolution* is deferred to `pip install /tmp/*.whl` in the runtime stage. `pip install` doesn't read `uv.lock` — it resolves freshly against PyPI + the git source. The `uv.lock` in the repo is therefore decorative for the docker path; reproducibility depends solely on the git tag pin (`v0.9.0` for pd-book-tools) and PyPI's behaviour for the rest.
- **Why it matters:** Lower severity than B-19 because the wheel does have a tagged git source for the only non-PyPI dep, and `>=` floors on FastAPI/uvicorn/etc. are wide enough that minor PyPI bumps shouldn't break the wheel. But the `uv.lock` file in the build context is a Chekhov's gun: future readers will assume the docker build is fully locked. It isn't.
- **Suggested fix:** Either (a) accept the looser-but-tagged shape (current state) and add a comment in the Dockerfile explicitly disclaiming "runtime resolves PyPI freshly; pin upper bounds in pyproject.toml if a regression bites", OR (b) use `uv pip install --frozen` against `uv.lock` in the runtime stage instead of `pip install` against the wheel — but that changes the install model from "install a self-contained wheel" to "install dependencies from lock then the wheel", which is an architecture decision worth discussing with the user before flipping. (a) is the lower-effort honest path.

## B-21 — `Dockerfile` installs `git` + `ca-certificates` in both `wheel` and `runtime` stages
- **Status:** ✅ **Fixed in iter 17 (2026-05-06)** — runtime stage now
  installs `git ca-certificates`, runs the two-pass `pip install`
  (wheel + frozen requirements per B-20), removes the staged files,
  and `apt-get purge --autoremove -y git ca-certificates` — all in a
  single RUN so the final image layer's net contribution is the
  installed Python wheels and *not* the git binary. Wheel stage still
  installs both packages (uv needs git to resolve the pd-book-tools
  git source during `uv export`), but the wheel stage isn't part of
  the final image. New regression test
  `test_runtime_stage_does_not_keep_git_installed`: if the runtime
  slice contains an `apt-get install … git` line, it must also
  contain a matching `apt-get purge`/`remove` line (so a regression
  that drops the purge fails the test rather than silently shipping
  a fatter image).
- **Severity:** nit
- **Where:** `Dockerfile:33-35` (wheel stage apt-get) + `Dockerfile:78-80` (runtime stage apt-get).
- **Issue:** The wheel stage installs `git ca-certificates` to let `uv` fetch the `pd-book-tools` git source during `uv build`. The runtime stage installs the same packages because `pip install /tmp/*.whl` re-resolves and re-fetches the same git source. Each apt-get layer is ~10MB+ pre-cleanup; the runtime image keeps `git` installed (the cleanup only drops the apt cache), so the final image carries git for no runtime reason. Not a correctness bug; build-time/image-size waste.
- **Why it matters:** Cosmetic. The runtime image is larger than necessary because git stays installed after the install step.
- **Suggested fix:** In the runtime stage, wrap the install step in a single RUN that installs git + ca-certificates, runs `pip install /tmp/*.whl && rm /tmp/*.whl`, then `apt-get purge --autoremove -y git ca-certificates && rm -rf /var/lib/apt/lists/*`. That keeps the install-time deps available without bloating the final layer. Cross-check with pgdp-prep's Dockerfile to keep the pattern consistent.

## B-22 — Iter-12 commit message claims "iter-10 review backlog now zero" but B-11's underlying class remains (see B-17)
- **Status:** ✅ **Fixed in iter 16 (2026-05-06)** — paired with B-17.
  B-11's Status line now reads "extended in iter 16 to cover
  rewrite/checkout (see B-17)" so future readers don't take the
  iter-12 framing at face value. No code change needed for B-22
  itself; the fix is a doc-honesty annotation.
- **Severity:** nit
- **Where:** `e83bda1` commit message body (`**iter-10 review backlog now zero**`).
- **Issue:** B-11 was titled "stale `__version__` after intermediate commits". The post-commit hook closes the *symptom* path observed at iter-10 (vanilla `git commit` not refreshing the install). It doesn't close the *class* (any non-`git commit` ref-changing operation, see B-17). The commit message overstates the fix. Iter-15 (this checkpoint) is the appropriate place to record the gap rather than letting it propagate as "B-11 is fully solved" into M1.
- **Why it matters:** Future code-review checkpoints take the BUGS_FOUND.md "Status: ✅ Fixed" lines at face value. If a future iter searches for "stale version" and finds B-11 marked closed, they may not re-discover the rebase/amend gap. Filing B-17 explicitly closes that loop.
- **Suggested fix:** Pair-fix with B-17. When iter-N picks B-17, update B-11's "Status: ✅ Fixed" line to "✅ Fixed (post-commit only — see B-17 for rewrite/checkout coverage)". No code change needed for B-22 specifically.

## Non-findings (checked, no bug)

- **`spa` → `wheel` static handoff path correctness.** `Dockerfile:54` (`COPY --from=spa /work/dist/ ./src/pd_ocr_labeler_spa/static/`) lands the SPA exactly where `build_hooks/spa_check.py:42` checks (`SPA_INDEX_REL = src/pd_ocr_labeler_spa/static/index.html`). The hook's check is for `index.html`'s **existence and non-zero size**, which Vite's default build always produces. Confirmed correct.
- **`hatch-vcs` bypass via `ARG VERSION`/sed.** `Dockerfile:51-65` substitutes `dynamic = ["version"]` for `version = "${VERSION}"` so hatch-vcs is never invoked in the Docker context (where `.git/` is excluded by `.dockerignore:11`). The `grep -E '^(version|dynamic)' pyproject.toml` check after the sed is a sanity gate; if the substitution failed, the next `uv build --wheel` would fail on the unresolved `dynamic = ["version"]`. Safe enough; mirrors pgdp-prep.
- **`EXPOSE 8080` matches `Settings.port` (default 8080).** Confirmed `src/pd_ocr_labeler_spa/settings.py:42` (`port: int = 8080`) and `__main__.py` `--port` default (8080).
- **`pd-ocr-labeler-ui` entrypoint matches `pyproject.toml [project.scripts]`.** Confirmed `pyproject.toml:36` (`pd-ocr-labeler-ui = "pd_ocr_labeler_spa.__main__:main"`); the dockerfile test reads this live.
- **Iter 11 nit fixes are reverse-stable.** Walked through each: B-13 walker now visits Assign/AugAssign/AnnAssign; reversing to Assign-only would cause `test_ast_scanner_catches_all_three_assignment_forms` to fail. B-14 reframed test passes for "no settings param" (M0) and "settings param + body reads it" (M2); the misleading "param + ignores body" shape fails. B-15 unconditional credentials assertion would fail if `allow_credentials=True` is added regardless of origin shape. All three regression-stable.
- **`tailwind.config.js` major pin.** `^3.4.0` allows `<4.0.0` and that's correct (Tailwind v4 is a CSS-first rewrite incompatible with `@tailwind` directive syntax). The test pins `tailwindcss` major to `3` which would catch a stray `^4` upgrade.
- **`.dockerignore` exclusion of `src/pd_ocr_labeler_spa/static/`.** Iter 14 excludes the static dir from the build context — correct, because the wheel stage gets its `static/` from `COPY --from=spa /work/dist/`, not from the local repo. If both were copied, a stale local `static/` could shadow the freshly built one. Confirmed safe.
- **DEVELOPMENT.md M0/M1+ split.** Walked the doc against actual M0 reality: `/healthz` exists, `/env.js` exists, `GET /` 404s (only `/openapi.json`, `/docs`, `/redoc`, `/healthz`, `/env.js` are mounted), `--frontend-dev` stores a URL with no consumer. Doc says exactly this. The `test_development_doc_is_honest_about_m0_limits` shape pin would fail if a future doc edit re-introduced the "make dev opens the SPA" promise.
- **`PD_LABELER_SKIP_SPA_CHECK` escape-hatch env name.** Inconsistent with the `PDLABELER_` Settings prefix (note the underscore), but this env is consumed by the build hook (not Settings) and is intentionally undocumented. Not worth fixing — different layer, never user-facing. Flag here for posterity only.

## Summary

7 findings: 0 blocker, **1 high** (B-16 Dockerfile env prefix mismatch with Settings), **2 medium** (B-17 post-commit hook misses rebase/amend, B-19 npm install vs ci + missing lockfile), **2 low** (B-18 Tailwind glob test rigidity, B-20 uv.lock not used in docker), **2 nit** (B-21 duplicate apt-get, B-22 iter-12 commit message overstatement). Top concerns:

1. **B-16** — the Dockerfile encodes `PD_LABELER_*` (with underscore) while `Settings` reads `PDLABELER_*` (no underscore). The image still boots correctly because `--host 0.0.0.0` is in argv, but the `ENV` lines are dead code, and the test in `test_dockerfile.py` cements the wrong contract. This is the kind of mistake that propagates — anyone copying the Dockerfile pattern for M1 storage env vars will hit it. **Fix first.**
2. **B-19** — the Dockerfile uses `npm install` against an absent lockfile (and would still use `install` not `ci` once the lockfile lands). Reproducibility hole that's part of the M0 acceptance gate per spec. Fix once Q-A8 unblocks frontend-install.

Iter 16 should pick **B-16** first (one-line `PDLABELER_` rename + tightened test, low-risk). Then either B-17 (post-rewrite/post-checkout hook stages) or resume scaffolding (`make docker-*` targets, install scripts, release.yml). All four iter 11–14 commits otherwise actually fixed/landed what they claimed; the doc-honesty pin (B-12) is a particularly nice piece of regression engineering.

---

# Code-review checkpoint, iter 20 (2026-05-06)

Review scope: commits `c9b9f6f` (iter 16 — B-16/B-17/B-22),
`e7fe5ef` (iter 17 — B-20/B-21 + B-22 doc cleanup), `b1ac8d5` (iter
18 — `make docker-*` targets), `f540c62` (iter 19 — `install.sh`).
Reviewer ran `uv run pytest` (92/92 green, 0.17s), `uv run ruff
check` (clean), `python -c "from pd_ocr_labeler_spa.bootstrap
import build_app; build_app()"` (clean), `bash -n install.sh` +
`bash -n scripts/refresh_version_git_hook.sh` (both clean), `make
-n docker-build` (exit 0, parses + renders cleanly).

Pre-commit-stage research: `pre_commit/clientlib.py` lists
`post-commit`, `post-rewrite`, `post-checkout`, `prepare-commit-msg`
as supported stages (verified by inspection at
`.venv/lib/python3.13/site-packages/pre_commit/clientlib.py`).
`uv run pre-commit validate-config` is silent (config OK). The
B-17 fix's stage names are real.

Cross-checked `uv export --frozen --no-emit-project --no-dev
--no-hashes` actually excludes the project-itself entry but still
mentions it in `# via` comments, which `pip install -r` ignores
(comment lines). The B-20 two-pass install pattern is sound.

`apt-get install ... && pip install ... && apt-get purge --autoremove`
all live in a **single RUN** at `Dockerfile:106-113`. Layer
contribution = installed wheels minus git/ca-certificates. Verified
B-21 actually shrinks the runtime layer.

5 findings filed below — 0 blocker, 0 high, 1 medium, 2 low, 2
nit. Top concerns: B-23 (no `uv lock --check` gate anywhere — the
B-20 fix shifts the lockfile-drift failure from runtime PyPI
fetch to docker-build-time `uv export --frozen` failure, which
is *better* but still surfaces only at `docker build`, not at
local CI), B-26 (ROADMAP.md's M0 sub-task checkboxes are stale —
iters 18+19 landed but their boxes still read `[ ]`).

## B-23 — No CI/pre-commit gate for `uv.lock` ↔ `pyproject.toml` drift; B-20 hides drift until `docker build`
- **Status:** ✅ **Fixed in iter 21 (2026-05-06)** — added a
  `uv-lock-check` pre-commit hook (entry: `uv lock --check`,
  `language: system`, `files: ^(pyproject\.toml|uv\.lock)$`,
  `pass_filenames: false`) to the `repo: local` block of
  `.pre-commit-config.yaml`. `uv lock --check` exits non-zero when
  the lockfile is out of sync with `pyproject.toml` and does NOT
  modify the lockfile, which is exactly the behaviour we want from a
  pre-commit gate (in contrast `--frozen` errors when other
  resolution flags are also passed; `--check-exists` only verifies
  presence). New `tests/unit/test_uv_lock_check.py` pins two
  invariants: (1) the hook exists with the right entry, language,
  pass_filenames=False, and a `files:` regex that matches both
  `pyproject.toml` and `uv.lock`; (2) the *current* lockfile passes
  `uv lock --check` as a subprocess, so `make test` catches drift
  even if a contributor bypasses hooks (`git commit --no-verify`).
  Subprocess test is `pytest.skip`-guarded on `shutil.which("uv")`
  so a stripped CI image without uv doesn't fail with a tooling
  error. Verified end-to-end: `uv run pre-commit validate-config`
  passes; both new tests pass; total 92→94. Chose pre-commit over
  `make ci` per B-23's recommendation: catches drift at commit time
  rather than CI time.
- **Severity:** medium
- **Where:** absence — `.pre-commit-config.yaml` (no `uv lock --check` hook), `Makefile` `ci` target line 186 (no `uv lock --check`), `tests/` (no test that asserts lock freshness).
- **Issue:** Iter-17 (`e7fe5ef`) wired the Dockerfile to `uv export --frozen ...` which fails loudly if `uv.lock` is out of date relative to `pyproject.toml`. That's the right fail-mode — **but it only fires inside `docker build`**, which neither `make ci` nor `make test` runs. A contributor who adds a new direct dep to `pyproject.toml` without running `uv lock` would: (a) pass all 92 unit tests; (b) pass ruff; (c) commit; (d) pass the post-commit refresh-version hook because that calls `uv pip install -e .` (which ignores `uv.lock`); (e) only learn about the drift when a CI/release pipeline that actually runs `docker build` fires. There's no `make ci` step nor pre-commit hook that runs `uv lock --check` (or `uv sync --locked`, which is the modern equivalent).
- **Why it matters:** Reproducibility is the whole point of the B-20 fix. Today the lockfile is decorative for everyone except docker-build. M1+ work that adds backend deps will routinely ship with a stale `uv.lock` and the contributor won't notice until the release pipeline lights up. Severity medium because (a) `uv.lock` is in the repo and reviewers can spot drift in PR diffs, (b) the in-image build catches it before publish, (c) M0 has no published release yet so impact is bounded — but the gap exists *now* and grows with M1.
- **Suggested fix:** Add a `uv lock --check` (or `uv sync --locked --no-install-project`) step to either (a) a new pre-commit hook in `.pre-commit-config.yaml` `local` repo (mirrors how `pd-prep-for-pgdp` does this — worth checking peer parity), or (b) `make ci` after `make setup`. Option (a) is friendlier because it catches the drift at commit time rather than CI time. Either way, add a unit test that asserts the gate exists (text-grep for `uv lock --check` or `uv sync --locked` in either the Makefile `ci` recipe or the pre-commit-config hook list).

## B-24 — `make docker-build/run/shell` fail with bare `command not found` when Docker isn't on PATH
- **Status:** ✅ **Fixed in iter 22 (2026-05-06)** — added a `_docker`
  macro to the Makefile (parallels `_npm`) that runs `command -v
  docker` and emits a friendly options block (Docker Desktop /
  Colima / devcontainer feature) before exiting 1 if docker is
  missing. All three docker-* recipes now dispatch via `$(call
  _docker,…)` instead of calling `docker …` directly. New tests in
  `tests/unit/test_makefile_docker.py`: `test_makefile_defines_docker_macro`
  pins both the `define _docker` line and the `command -v docker`
  preflight; `test_docker_targets_invoke_docker_macro` (parametrised
  across all three targets) walks each recipe block and asserts
  `_docker` appears, so a regression that copies a recipe and
  forgets the macro fails cleanly. Verified via `make -n
  docker-build` — rendered recipe still contains
  `pd-ocr-labeler-spa:dev` and `-p 8080:8080` so the existing
  three-way port-alignment + image-tag invariants still hold.
- **Severity:** low
- **Where:** `Makefile:209-216` (the three docker-* recipes) — neither has a guard like the `_npm` macro's "no npm available; here are your options" fallback.
- **Issue:** The frontend targets (`frontend-install`, `frontend-build`, `frontend-dev`, `frontend-test`) go through the `_npm` macro at `Makefile:98-112` which checks for `mise` then `npm` and prints a friendly options block ("run `make mise-setup`", "install Node 24 yourself", "add the devcontainer node feature") before exiting 1. The new docker targets don't. On a devcontainer that lacks docker (the current state — `which docker` returns nothing in this environment), the recipes shell out to `docker build …` and the user gets bash's terse `make: docker: No such file or directory`. The `_npm` macro is exactly the cure — a `_docker` macro pattern would be ~6 lines and parallel.
- **Why it matters:** UX. M0 contributors who follow `docs/DEVELOPMENT.md` and try the docker targets without docker installed get a confusing error rather than a pointer ("install Docker Desktop / Colima / `add docker-in-docker feature to .devcontainer/`"). Not a correctness bug.
- **Suggested fix:** Add a `_docker` macro analogous to `_npm` that verifies `command -v docker` first and prints a one-line suggestion if not. Wrap each `docker build`/`docker run` call. Optional but a nicer cross-repo pattern. Alternatively, just one-line guard at the top of each recipe: `@command -v docker >/dev/null 2>&1 || { echo "docker not on PATH; install Docker Desktop or Colima first"; exit 1; }`.

## B-25 — `install.sh` mentions Python 3.13 only in a comment; the test asserting "references pinned Python" only proves the comment exists
- **Status:** ✅ **Fixed in iter 22 (2026-05-06)** — chose option (b)
  from the suggested-fix menu: added an actual Python preflight to
  `install.sh` that calls `python3 -c "import sys; print(...)"` to
  check the system Python's major.minor and prints an informational
  note if it isn't 3.13 (the check is intentionally non-gating —
  `uv tool install` auto-downloads 3.13 — but the check now exists
  rather than being purely a comment). The legacy
  `test_install_sh_mentions_pinned_python_major` test stays (still
  enforces comment-presence drift-coupled to mise.toml), and a new
  `test_install_sh_runs_python_version_preflight` test pins the
  behavioural invariant: install.sh must invoke `python3 -c …` and
  reference `sys.version_info`. Future contributors reading the test
  names now see one for "comment drift" and one for "behaviour
  exists" — no more false sense of safety.
- **Severity:** low
- **Where:** `install.sh:16` (`# Python 3.13+ is required (pyproject.toml requires-python).`); `tests/unit/test_install_sh.py::test_install_sh_mentions_pinned_python_major` (substring-match for `3.13`).
- **Issue:** The test docstring says "If we bump Python in mise.toml, the installer's user-facing comment block needs to follow — otherwise users running the script see stale prerequisite info." That's true but very weak — the script itself does not check the user's Python at all (it relies on `uv tool install` auto-downloading 3.13 because `requires-python` says so). The test gives a false sense of safety: a future contributor reading "test_install_sh_mentions_pinned_python_major" will assume the script enforces 3.13, when in fact only the comment does. This is the same anti-pattern flagged in B-14 (a hostile gate that pins absence of a feature rather than the actual invariant).
- **Why it matters:** Mostly a documentation / test-honesty nit. The functional path *is* correct (uv handles Python download), so the lack of explicit version check is fine — the test name and docstring just oversell what's being verified. If a future iter adds `python_requires` checks to the script, this test would still pass with the comment alone. The peer pgdp-prep installer has the same shape, so this is "honest about parity, but parity is itself somewhat lax."
- **Suggested fix:** One of: (a) rename the test to `test_install_sh_documents_python_pin_in_comment` and adjust docstring to match what's verified; (b) add an actual Python-version preflight to the script (`if ! command -v python3.13 >/dev/null && ! uv python find 3.13 …; then echo "Python 3.13 required" …`) — but this fights uv's automatic download model and is probably overkill; (c) leave as is and add a note in the docstring acknowledging the test is "comment-presence, not behaviour-check." (a) is the cleanest path.

## B-26 — `docs/ROADMAP.md` M0 sub-task checkboxes are stale: iters 18 + 19 landed but boxes still read `[ ]`
- **Status:** ✅ **Fixed in iter 21 (2026-05-06)** — flipped both M0
  sub-task checkboxes in `docs/ROADMAP.md` from `[ ]` to `[x]` and
  added one-line notes citing the iter / commit sha that landed each
  (`b1ac8d5` for `make docker-*`, `f540c62` for `install.sh`). Also
  split out a new `[ ] install.ps1 (Windows uv tool installer)`
  bullet so the Windows pending-work is visible without dragging
  down the Linux/macOS checkbox.
- **Severity:** nit
- **Where:** `docs/ROADMAP.md:174-176` — the lines `- [ ] Makefile docker-build / docker-run targets …` and `- [ ] install.sh / install.ps1 (uv tool installer).` are unchecked even though `b1ac8d5` (iter 18) added the `make docker-*` targets and `f540c62` (iter 19) added `install.sh`. The narrative cell in the M0 status row at line 12 *does* mention iter 18 + iter 19, so the contradictions are within a single doc.
- **Why it matters:** Cosmetic but the ROADMAP is meant to be a single-glance status board. A reader scanning checkboxes (the natural human pattern) sees "docker targets and installer not done" while the narrative says they are. Future iter 21+ pickers may waste cycles "starting" a task that's already shipped.
- **Suggested fix:** Tick the two boxes at `ROADMAP.md:174-176`. Add a sub-item under `install.sh` saying `install.ps1` (Windows) is still TBD. Maintain the convention going forward: every iter that completes a sub-task also flips its checkbox.

## B-27 — `install.sh` resolves the latest tag via `/repos/X/tags`, not `/repos/X/releases/latest`; pre-1.0 retags can return the wrong "latest"
- **Status:** ✅ **Fixed in iter 22 (2026-05-06)** — switched
  `install.sh` from the two-call shape (`/repos/X/tags` →
  `/repos/X/releases/tags/<tag>`) to a single
  `/repos/X/releases/latest` call. That endpoint returns the most
  recently *published* release (ignoring drafts/prereleases) and
  embeds the asset URLs directly, so we save a curl round-trip and
  fix the dormant pre-1.0 retag footgun (B-09's history retagged
  `v0.0` → `v0.0.0`; `/tags` orders by commit-date and would have
  returned the wrong "latest" the moment we shipped a hot-fix
  release branch). New `test_install_sh_uses_releases_latest_endpoint`
  pins both halves: the new endpoint must appear, and the bare
  `/repos/X/tags` shape must NOT (the regex tolerates
  `/releases/tags/<tag>` if a future iter wants to fetch a specific
  release by tag name). Cross-repo: peer `pd-prep-for-pgdp/install.sh`
  *still* uses the `/tags` shape — that's a divergence we accept
  here rather than block on a cross-repo flip. The peer install.sh
  has its own scope/agent and the pattern can propagate when that
  agent picks up parity work.
- **Severity:** nit
- **Where:** `install.sh:28-29` (`curl … "https://api.github.com/repos/${REPO}/tags" … | grep '"name"' | head -1`).
- **Issue:** The GitHub `/tags` endpoint returns refs ordered by **commit date of the tagged sha**, not by semver. Two relevant pre-1.0 quirks: (a) re-tagging an existing tag (B-09's history has exactly this — `v0.0` was deleted and `v0.0.0` recreated at the iter-1 sha) means the "latest" by tag date may be older than the actual newest commit. (b) Hot-fix back-port flows that tag a release branch can leave `/tags` ordered counter-intuitively. The peer `pd-prep-for-pgdp/install.sh:44` uses the *same* shape, so this is parity — but parity to a slightly fragile pattern. The `releases/latest` endpoint returns the most recently *published* (not most recently *tagged*) release and is the GitHub-blessed shape for installers.
- **Why it matters:** Today the repo has exactly one tag (`v0.0.0`) and no published Releases, so the script fails with "no .whl asset attached" regardless of which endpoint it hits. The bug is dormant. It activates the moment a hot-fix flow ships v0.1.1 from a release branch while v0.2.0 already exists on main — `/tags` will return v0.1.1 (newest commit-date) over v0.2.0 (older tag date but higher semver).
- **Suggested fix:** Either (a) switch to `https://api.github.com/repos/${REPO}/releases/latest` which returns the most recently published release and embeds the wheel URLs directly (saves the second curl call too), or (b) accept parity with pgdp-prep and leave this. (a) is cleaner; (b) preserves the cross-repo sameness the iter-19 commit message values. If keeping (b), add a regression test that the selected tag is the *latest semver* not just the *first listed*. Cross-repo discussion needed before flipping pgdp-prep.

## Non-findings (checked, no bug)

- **`pre-commit` framework supports `post-commit`, `post-rewrite`, `post-checkout` stages.** Verified by inspecting `pre_commit/clientlib.py` in the installed venv — all three appear in the supported-stages list. `uv run pre-commit validate-config` accepts the YAML.
- **`scripts/refresh_version_git_hook.sh` is executable + has shebang + fail-soft semantics.** `ls -l` shows mode `0755`, line 1 is `#!/usr/bin/env bash`, lines 42-46 fail-soft when `make` is missing (`echo … >&2 ; exit 0`). Won't block a commit/rebase/checkout if the toolchain isn't there.
- **Refresh hook uses `set -u` not `set -euo pipefail`.** Deliberate — the script must not propagate failures (a `make refresh-version` error during `git rebase` would be very disruptive). Fail-soft is the correct mode for post-* git hooks.
- **B-20 two-pass `pip install` pattern doesn't conflict with `--no-deps`.** `uv export --no-emit-project` excludes the project itself from `requirements.txt` (verified by running it: `pd-ocr-labeler-spa==…` does not appear, only `# via pd-ocr-labeler-spa` comment lines which pip ignores). Pass 1 installs all transitive deps at locked versions; pass 2 adds the project wheel with `--no-deps`. No conflict.
- **B-21 `apt-get purge` actually shrinks the layer.** Lines 106-113 are a single `RUN`. The layer's net contribution is the post-purge state. Final image carries no git binary — confirmed by reading the recipe (would also be confirmed by `docker history` if docker were available).
- **`/bin/bash` exists in `python:3.13-slim-bookworm`.** Debian slim variants keep bash by default; only Alpine and busybox-based slim images drop it. The `docker-shell` `--entrypoint /bin/bash` invocation is fine.
- **`install.sh` uses `set -euo pipefail` correctly with curl pipelines.** Pipelines that may fail under pipefail (`curl … | grep | head | sed`) all end with `|| true` to swallow non-zero exits, then check the resulting variable for emptiness. No `read` prompts (would need stdin on a piped install). uv-not-installed branch auto-installs uv before continuing.
- **Three-way port alignment test introspects `Settings().port` live.** `tests/unit/test_makefile_docker.py::test_settings_port_matches_dockerfile_expose` and `…::test_docker_run_maps_settings_port_into_container` both read the int from `Settings().port` rather than hardcoding 8080. A future port-bump that updates Settings but forgets EXPOSE or the Makefile `-p` flag fails the test cleanly.
- **`docker-build` depends on `frontend-build`.** Confirmed at `Makefile:209` (`docker-build: frontend-build`). Mirrors pgdp-prep. The Dockerfile's `spa` stage rebuilds anyway, but forcing a local `frontend-build` first means the same SPA artefact lands in both `src/pd_ocr_labeler_spa/static/` (for `make build`/wheel) and the docker image (via `COPY --from=spa`). Defensive; correct.
- **Test count growth is meaningful, not shape-pin spam.** Iters 16-19 added 26 tests across 4 commits (66→92): tightening the env-prefix pin to read live from Settings, hook-stage coverage shape, dockerfile uv-export/two-pass-install, three-way port alignment introspection, install.sh size budget. All are parameterised against the actual sources of truth (Settings/pyproject.toml/mise.toml) rather than hardcoded literals — a regression in any of those triggers a clean diagnostic.
- **BUGS_FOUND.md is long (631 lines) but not stale.** Spot-checked: every "✅ Fixed" Status line cites the iter that fixed it; B-11's annotation correctly references B-17 extension; B-22 was an annotation-only fix (no code) and is reflected. B-18, B-19 are still open and explicitly tracked as remaining items in the iter-15 + iter-17 summaries.

## Summary

5 findings: 0 blocker, 0 high, **1 medium** (B-23 no `uv lock
--check` gate), **2 low** (B-24 docker-* targets fail terse without
docker, B-25 install.sh python-pin test is comment-presence not
behaviour), **2 nit** (B-26 ROADMAP checkbox staleness, B-27
install.sh `/tags` vs `/releases/latest`).

Top concerns:
1. **B-23** — the lockfile-drift gate is missing. The B-20 fix
   transformed a runtime PyPI-resolution risk into a build-time
   `uv export --frozen` failure, which is correct architecturally,
   but the failure surfaces only inside `docker build` — neither
   `make ci` nor any pre-commit hook catches lockfile drift today.
   M1+ will start adding deps; the longer this gap stays open the
   more invisible drift accrues. Fix this before M1.
2. **B-26** — purely cosmetic but the M0 ROADMAP checkboxes are
   actively misleading. Two-line fix.

All four iter 16–19 commits actually fixed/landed what they
claimed. The B-16/B-17 fixes are particularly nice (Settings-as-
source-of-truth tightening, three-stage hook with shared shell
script). install.sh follows peer parity faithfully.

Iter 21 should pick **B-23 first** (one pre-commit hook + one
test, low risk, M1-load-bearing), then **B-26** (two-line ROADMAP
checkbox flip), then resume scaffolding (`install.ps1`, or
`release.yml`, or shadcn primitives once Q-A8 lands).

---

# Code-review checkpoint — iter 25 (2026-05-06)

Review scope: commits since `52d8d89` (iter 20 checkpoint):

- `c96e1ed` — iter 21: B-23 `uv-lock-check` pre-commit hook + B-26 ROADMAP checkboxes.
- `5b21e1d` (+ws `b3509ab`) — iter 22: B-24 `_docker` macro; B-25
  install.sh python preflight; B-27 `/releases/latest` flip.
- `d2bab21` — iter 23: install.ps1 Windows installer + 9 shape pins.
- `8a848c8` — iter 24: `.github/workflows/release.yml` + 12 shape pins.

Smoke-test:
- `uv run pytest tests/ --ignore=tests/e2e` → **121 passed in 0.23s**.
- `uv run ruff check` → clean.
- `uv run pre-commit validate-config` → clean.
- `python -c "from pd_ocr_labeler_spa.bootstrap import build_app; build_app()"` → OK.
- `bash -n install.sh` → OK.
- `make -n docker-build` → recipe expands cleanly with `_docker` macro.
- `uv lock --check` (uv 0.11.9) → **does** detect drift and exit
  non-zero; manually broke `pyproject.toml` and observed the expected
  "lockfile needs to be updated" failure. B-23 hook is real.
- `curl /repos/.../releases/latest` against this repo (no release yet)
  → 404, install.sh's `set -euo pipefail` + `|| true` + empty-string
  guard prints a clear "Has a release been published yet?" message and
  exits 1 (not a confusing JSON dump).

Findings filed below. **Do not fix this iteration** — iter 26+ picks
from the list. Severity legend: blocker > high > medium > low > nit.

## B-28 — `release.yml` runs `npm ci`, but `frontend/package-lock.json` does not exist
- **Status:** ✅ **Fixed in iter 26 (2026-05-06)** — paired with B-19.
  Release workflow's "Build SPA bundle" step rewritten to a two-pass
  install: `if [ ! -f package-lock.json ]; then npm install
  --package-lock-only; fi && npm ci && npm run build`. The `--package-
  lock-only` form generates a lockfile in-place from `package.json`
  (does not touch `node_modules/`), so the first tag push succeeds even
  while Q-A8 keeps Node out of the devcontainer. Once a real lockfile
  is committed, the bootstrap branch is a no-op and `npm ci` runs from
  the committed lock — same CI-safe semantics the original `npm ci`
  was reaching for. The Dockerfile `spa` stage uses byte-aligned shell
  logic (B-19 fix) so docker builds and CI publishes can no longer
  drift in opposite directions on the lockfile question. Three new
  regression tests: `test_uses_two_pass_install_with_lockfile_fallback`
  (release workflow, pins both bootstrap + guard); the existing
  `test_uses_npm_ci_not_npm_install` was loosened to allow the
  bootstrap form while still forbidding bare `npm install`;
  `test_spa_stage_uses_npm_ci_with_lockfile_fallback` (Dockerfile
  side); and `test_dockerfile_and_release_workflow_agree_on_npm_install_logic`
  cross-file alignment guard so future tightenings can't drift the two.
- **Severity:** **high** (release pipeline is dead on first execution)
- **Where:** `.github/workflows/release.yml:62` (`cd frontend && npm ci && npm run build`); `frontend/` has no `package-lock.json` (ls confirmed).
- **Issue:** `npm ci` requires an existing `package-lock.json` and fails fast with `Missing: ... from lock file` if it isn't present. The repo currently has `frontend/package.json` but no lockfile (Q-A8: Node never ran here). The first `git push` of a `v*` tag will run release.yml, immediately fail at the `npm ci` step, and produce neither wheel nor sdist nor Release. The 12 shape-pin tests in `test_release_workflow.py` actively assert `npm ci` (and forbid `npm install`), so they cement the broken-on-first-run shape.
- **Why it matters:** Iter 24's whole purpose was to establish a publish path so install.sh / install.ps1 can fetch a real wheel. As shipped, the publish path can't run end-to-end even once. Pre-1.0 it's invisible (no tag has been pushed since iter 24 landed); the moment someone tags `v0.1.0` it surfaces as a red CI run with no Release attached. B-19 already noted the same `npm install` vs `npm ci` story for the Dockerfile but in the *opposite* direction — the Dockerfile uses `npm install` (which works without a lockfile but doesn't pin), so the two are now inconsistent: docker build works, GitHub Actions release won't. Pick one.
- **Suggested fix:** Either (a) generate `frontend/package-lock.json` once (run `npm install` interactively, commit the result) which unblocks both `npm ci` here and tightens the Dockerfile concurrent with B-19; or (b) have release.yml use `npm install` with a comment explaining the lockfile gap; or (c) loosen the test to `npm ci || npm install` until Q-A8 unblocks. (a) is the right answer. Coupled fix with B-19.

## B-29 — `release.yml` `tags: ["v*"]` trigger is too permissive
- **Status:** ✅ **Fixed in iter 27 (2026-05-06)** — `release.yml`
  `on.push.tags` tightened to `["v[0-9]+.[0-9]+.[0-9]+",
  "v[0-9]+.[0-9]+.[0-9]+-*"]`. The renamed test
  `test_release_workflow_triggers_on_pep440_release_tags` pins both
  globs are present AND forbids the loose `v*` / `v[0-9]*` / `v?*`
  forms so a future widening can't silently re-introduce the
  footgun. `vfeature-test`, `vbeta`, `v0.0` no longer fire the
  workflow.
- **Severity:** medium
- **Where:** `.github/workflows/release.yml:17`.
- **Issue:** The pattern `v*` matches any tag starting with `v`, including `v0.0` (the deprecated retag-target B-09 explicitly removed), `vNEXT`, `vfeature-test`, `vbeta`, `v0.1-rc1`, etc. Any of these would trigger a wheel build + Release publish under the matching tag name, producing junk Releases that install.sh's `/releases/latest` would then surface to end users. The `test_release_workflow_triggers_on_v_tags` pin uses `assert any("v*" in t for t in tags)` (loose substring) — would still pass if the trigger were `["v*", "vfeature-*"]` or similar.
- **Why it matters:** `/releases/latest` is "most recent published release"; a stray `vfeature` tag pushed by accident → workflow fires → Release published → install.sh installs that. Pre-1.0 the impact is small (no users yet), but post-1.0 it's a footgun on every contributor's first stray tag.
- **Suggested fix:** Tighten the glob to PEP-440-compatible release shapes: `tags: ["v[0-9]+.[0-9]+.[0-9]+", "v[0-9]+.[0-9]+.[0-9]+-*"]` (covers `v1.2.3` and `v1.2.3-rc1`). Tighten the test to assert the regex form, not just `v*` substring.

## B-30 — `release.yml` has no `concurrency:` block; tag-race could double-publish
- **Status:** ✅ **Fixed in iter 27 (2026-05-06)** — added a
  workflow-scope `concurrency: { group: release-${{ github.ref }},
  cancel-in-progress: false }` block. `cancel-in-progress: false`
  because release jobs aren't safely cancellable mid-upload — better
  to queue the second run than abort the first mid-Release-asset
  upload. New test `test_release_workflow_has_concurrency_block`
  pins the block exists, the group references `${{ github.ref }}`,
  and `cancel-in-progress` is explicitly `false`.
- **Severity:** low
- **Where:** `.github/workflows/release.yml:13-22`.
- **Issue:** Without `concurrency: { group: release-${{ github.ref }}, cancel-in-progress: false }`, two near-simultaneous `git push --tags` operations (or a re-trigger via "Re-run all jobs") could run two publish jobs in parallel. `softprops/action-gh-release@v2` is upsert-by-tag, so the second run might race with the first when uploading the same asset name, surfacing as `409 Conflict` from the GitHub API mid-publish.
- **Why it matters:** Mostly theoretical for a one-author repo; real once contributors have tag-push permission, or if a flaky CI re-run is triggered. Cheap belt-and-braces.
- **Suggested fix:** Add a workflow-level `concurrency` block keyed on `${{ github.ref }}`. One-line change.

## B-31 — `release.yml` does not cache `~/.cache/uv` or `~/.npm`; cold runs are needlessly slow
- **Status:** ✅ **Fixed in iter 27 (2026-05-06)** — `actions/setup-
  node@v4` now declares `cache: "npm"` +
  `cache-dependency-path: frontend/package-lock.json` (the lockfile
  lives under `frontend/`, not the repo root, so without the
  explicit dependency-path the cache key would never resolve).
  `astral-sh/setup-uv@v4` now declares `enable-cache: true`. Two new
  tests pin both: `test_setup_node_enables_npm_cache` (cache + path)
  and `test_setup_uv_enables_cache`. Pre-B-28-lockfile-landing the
  npm cache is a graceful no-op (no key → cache miss); once the
  real lockfile is committed, warm runs save ~30–60s on `npm ci`.
- **Severity:** nit (performance, not correctness)
- **Where:** `.github/workflows/release.yml:41-51`.
- **Issue:** `actions/setup-node@v4` accepts `with: cache: 'npm'` (and `cache-dependency-path: frontend/package-lock.json` once B-28 lands), and `astral-sh/setup-uv@v4` accepts `with: enable-cache: true`. Neither is wired. Each tag push re-resolves and re-downloads everything from scratch.
- **Why it matters:** A release.yml run currently spends ~30-60s in `npm ci` and ~20s in `uv build` deps that could be primed from cache on the second-and-later runs. Pre-1.0 with one tag a month it doesn't matter; once releases are routine it's free latency win.
- **Suggested fix:** Add `with: cache: 'npm'` to setup-node and `with: enable-cache: true` to setup-uv after B-28 lands a lockfile (npm cache is a no-op without one).

## B-32 — `install.ps1` `Test-Command` returns multiple values; works by accident
- **Status:** ✅ **Fixed in iter 28 (2026-05-06)** — `Test-Command` is
  now `function Test-Command { param([string]$Name); return $null -ne
  (Get-Command -Name $Name -ErrorAction SilentlyContinue) }`. The
  `$null -ne (...)` form returns exactly one Boolean (vs the previous
  array-on-success-path). Two new tests in
  `tests/unit/test_install_ps1.py::test_test_command_returns_explicit_boolean`
  pin both the `$null -ne (...)` / `[bool](...)` shape AND forbid the
  `ForEach-Object { return $true }` anti-pattern. Call sites updated
  to pass `-Name` explicitly.
- **Severity:** low (correctness-by-accident)
- **Where:** `install.ps1:19-22`.
- **Issue:** The function is:
  ```
  function Test-Command($name) {
      Get-Command $name -ErrorAction SilentlyContinue | ForEach-Object { return $true }
      return $false
  }
  ```
  PowerShell's `return $true` inside `ForEach-Object {...}` only exits *the script block*, not the enclosing function. When `Get-Command` succeeds, the function emits `$true` from the foreach AND `$false` from the trailing `return` — the function returns `@($true, $false)`, an array. Callers `if (-not (Test-Command "uv"))` still produce the right boolean only because PowerShell's `-not` against a non-empty array yields `$false` (the array's truthy), and `-not $false` (the `Get-Command` miss path returning a single `$false`) yields `$true`. Both arms happen to do the right thing, but the semantics are:
    - tool found → returns `@($true, $false)` (intended `$true`)
    - tool missing → returns `$false` (correct)
- **Why it matters:** Anyone refactoring this helper (e.g. switching the foreach to `Where-Object` or replacing with `[bool](Get-Command ...)`) will see the array-return shape and assume "must be intentional", or worse, copy the pattern to a new helper where the boolean coercion doesn't accidentally save them.
- **Suggested fix:** Replace with `[bool](Get-Command $name -ErrorAction SilentlyContinue)` — a single-expression function that returns exactly `$true` or `$false`. Three lines → one line, and removes the accidental-correctness footgun.

## B-33 — `install.ps1` Python preflight does not detect Microsoft Store stub Python
- **Status:** ✅ **Fixed in iter 28 (2026-05-06)** — preflight now
  invokes `& python --version 2>&1` and matches against the regex
  `^Python \d+\.\d+\.\d+$` via `-notmatch`. When the output doesn't
  match (the Microsoft Store stub case, or any non-functional
  `python.exe` on PATH), the script prints a clear message naming the
  stub redirector and pointing at python.org / `winget install
  Python.Python.3.13`, then falls through to `uv tool install`'s
  built-in Python provisioning. New test
  `test_install_ps1_detects_ms_store_stub_python` pins both the
  `python --version` probe AND the `\d+\.\d+\.\d+` regex AND the
  `-notmatch` branching keyword. Size budget bumped 120 → 140 to
  accommodate the new branch.
- **Severity:** nit
- **Where:** `install.ps1:34-44`.
- **Issue:** On Windows 10/11 with no real Python installed, `python.exe` resolves to `%LocalAppData%\Microsoft\WindowsApps\python.exe` — a Store reparse-point stub that, when invoked with arguments (e.g. `python -c "..."`), exits with code 9009 ("not recognized as an internal or external command") rather than running. `Test-Command "python"` returns `$true` (the stub exists on disk) and the `try { python -c ... }` swallows the failure non-fatally — so the user sees no preflight note despite having no Python at all. Then `uv tool install` proceeds to download Python 3.13 (which is fine) but the user-visible message about "system python is X.Y" never fires for the case it most needs to (no real Python).
- **Why it matters:** Behavioural mirror with `install.sh` is the goal; install.sh's `python3` is rarely a stub. Real consequence is small (uv handles it) but the asymmetry means the test `test_install_ps1_runs_python_version_preflight` enforces a behaviour that does nothing on the most common Windows configuration.
- **Suggested fix:** After resolving `$sysPy`, also check `& python -c "import sys; sys.exit(0)" 2>$null; $LASTEXITCODE` and if non-zero, print "system python is the Microsoft Store redirector; uv will install a real Python 3.13." (Optional: wrap into the existing try/catch so the message surfaces from the catch path.)

## B-34 — `release.yml` `astral-sh/setup-uv@v4` `python-version: 3.13` is redundant with uv's auto-download
- **Status:** ✅ **Fixed in iter 28 (2026-05-06)** — `python-version`
  dropped from the `astral-sh/setup-uv@v4` `with:` block. The
  workflow only invokes `uv build`, which spawns a build-isolated
  PEP 517 env that provisions its own Python; setup-uv's pre-
  provision was redundant (~5s wasted CI per run). The previous
  `test_python_version_matches_mise` pin was renamed to
  `test_python_pin_in_release_workflow` and loosened to accept the
  pin appearing either as a `python-version:` key (for a future
  setup-python step) OR as a comment that names the version — so a
  `mise.toml` Python bump still fails the test loudly. New test
  `test_setup_uv_does_not_set_python_version` walks the parsed YAML
  and asserts setup-uv's `with:` block has no `python-version` key
  (regex-over-text would have false-positive on the explanatory
  comment).
- **Severity:** nit (no behaviour impact, just code clarity)
- **Where:** `.github/workflows/release.yml:47-51`.
- **Issue:** `astral-sh/setup-uv@v4` only installs the `uv` binary. The `python-version` parameter on setup-uv is for setting up a uv-managed Python in advance — handy if you want `uv run` to skip the auto-download cost. But `uv build` doesn't need a system Python (it shells out to a build-isolated env), and the workflow doesn't otherwise call `uv run`. The pin is functionally a no-op that costs ~5s of Python download per CI run. The `test_python_version_matches_mise` test pins this value, so future bumps still drift-check, but the workflow could equally drop the line entirely.
- **Why it matters:** It works; the cost is one wasted step per release. Worth flagging for cleanup once B-31 (caching) lands and someone is in the workflow file anyway.
- **Suggested fix:** Either (a) drop `python-version` from setup-uv and adjust `test_python_version_matches_mise` to look elsewhere (e.g. assert the comment in the workflow names mise.toml's pin); or (b) leave as-is with a comment noting it's a deliberate cache-priming step. (b) is fine.

## B-35 — `test_install_ps1_uses_uv_tool_install` is too loose: matches the substring without `--reinstall` or `<wheel>`
- **Status:** ✅ **Fixed in iter 27 (2026-05-06)** — both
  `test_install_ps1_uses_uv_tool_install` and
  `test_install_sh_uses_uv_tool_install` now assert
  `re.search(r"uv tool install\s+--reinstall\s+\S+", text)`. A
  regression that drops `--reinstall` (so the second installer run
  silently fails because the tool already exists) or that drops the
  wheel-file argument now fails the test. Verb + flag + arg are all
  load-bearing; pinning all three makes the assertion match how a
  reviewer reads the line.
- **Severity:** nit
- **Where:** `tests/unit/test_install_ps1.py::test_install_ps1_uses_uv_tool_install`; same loose-match in `test_install_sh.py::test_install_sh_uses_uv_tool_install`.
- **Issue:** The assertion is `assert "uv tool install" in text`. Would pass if the script said `# we considered uv tool install but use pip instead` or `Write-Host "Try uv tool install yourself"`. The peer test in install.sh has the same shape. The actual call in install.ps1 is `& uv tool install --reinstall $wheelFile` (and in install.sh, `uv tool install --reinstall "$WHEEL_FILE"`), which has three load-bearing parts: the verb, the `--reinstall` flag (idempotent re-run of the installer), and a wheel-file path argument. Only the verb is pinned.
- **Why it matters:** A regression that drops `--reinstall` (so the second run of the installer silently fails because the tool already exists) would pass the test. Same for dropping the wheel-file arg. Low impact pre-1.0 but the behavioural pin should match how a reviewer reads the line.
- **Suggested fix:** Tighten to `assert re.search(r"uv tool install\s+--reinstall\s+\S+", text)` in both tests. One-line change per file.

## B-36 — `release.yml` workflow comment claims "M0 doesn't yet have a branch CI lane" but iter 25's review confirms M0 *does* run `make ci` locally; comment risks future confusion
- **Status:** ✅ **Fixed in iter 27 (2026-05-06)** — drive-by while
  in the file for B-29/B-30/B-31. The header comment now reads
  "GitHub Actions branch-CI is not yet configured for this repo
  (no `ci.yml` workflow exists); `make ci` is the local equivalent
  and runs in pre-commit / on contributor laptops today." Future-
  contributor-confusion risk addressed without adding a separate
  test (the comment's wording is reviewable by reading the file;
  pinning prose tends to ratchet without value).
- **Severity:** nit
- **Where:** `.github/workflows/release.yml:9-11`.
- **Issue:** The header comment says "M0 doesn't yet have a branch CI lane." Strictly true for *GitHub Actions* (no `ci.yml` workflow exists), but a future contributor reading just this comment might assume M0 has no CI at all and re-add a duplicate lint/test pipeline here. The Makefile's `make ci` target IS the canonical CI lane; the GitHub Actions side is a separate question.
- **Why it matters:** Doc-honesty paper-cut. Catches a future contributor mid-thought.
- **Suggested fix:** Re-word to: "GitHub Actions branch-CI is not yet configured (see future ci.yml); `make ci` is the local equivalent and runs in pre-commit / contributor laptops today."

---

## Summary — iter 25

**9 findings: 0 blocker, 1 high (B-28), 1 medium (B-29), 2 low (B-30, B-32),
5 nit (B-31, B-33, B-34, B-35, B-36).**

Top concerns:

1. **B-28 (high)** — `release.yml` calls `npm ci` against an absent
   `frontend/package-lock.json`. The release pipeline cannot succeed
   on first execution. This is M0-blocking for the acceptance gate
   "wheel installable from a tagged release". Fix in coordination with
   B-19 (the Dockerfile's `npm install` ↔ this workflow's `npm ci`
   inconsistency): generate the lockfile once, then both stages can
   use `npm ci`.
2. **B-29 (medium)** — `tags: ["v*"]` is too permissive. `vfeature-test`
   would publish a Release. Tighten to `v[0-9]+.[0-9]+.[0-9]+(-*)?`.

The other 7 are quality-of-life: better caching (B-31), tighter test
pins (B-35), cleaner PowerShell helpers (B-32), and doc honesty
(B-36). None block M1.

**BUGS_FOUND.md staleness audit:** spot-checked iter-21..24 fix
annotations, all reference the right commit shas. B-19 is genuinely
still open and is now coupled with B-28. No findings need to be flipped
to `Fixed`.

**OPEN_QUESTIONS.md staleness audit:** Q-A8 (frontend toolchain) is
still relevant — Node still not on PATH in the devcontainer; coupled
to B-28's lockfile gap (you can't generate a `package-lock.json`
without a working `npm`). Q-A10 (PyPI publish) is correctly deferred
and the workflow + test pin both honour the deferral. No question
should be closed yet.

**Test-suite size:** 94 → 121 across iters 21–24 (+27); still <0.25s.
The new tests are mostly genuine shape pins (B-23 + 2, B-25 + 1,
B-27 + 1, B-24 + 4, install.ps1 + 9, release.yml + 12). B-35 flags
the only outright-too-loose pin in the new batch.

**Iter 26 should pick B-28 first** — it's M0-load-bearing (the
acceptance gate clause "make build produces a wheel" is moot if the
*release* pipeline can't produce a wheel), and the fix is small if
Q-A8 is unblocked first. Then **B-29** (one regex tighten) bundled
with **B-35** (two assertion tightens). B-30..B-36 can be picked up
opportunistically.

**M0 done?** Not yet. Acceptance gate clauses (`docs/ROADMAP.md`):
- `make ci` green: ✅
- `make build` produces a wheel containing
  `pd_ocr_labeler_spa/static/index.html`: ✅ in principle (build
  hook + tests pin it), but in practice **blocked on Q-A8** (no Node
  to run `make frontend-build` locally) and **B-28** (release.yml
  can't run `npm ci`).
- `pd-ocr-labeler-ui --no-browser --port 8080` answers /healthz: ✅.
- `make openapi-export` regenerates `frontend/src/api/types.ts`: not
  yet runtime-verified end-to-end (Q-A8 blocker).
- ESLint passes clean: still pending Q-A9 + the eslint.config.ts
  file that closes it.

Two open Qs (Q-A8, Q-A9) and one new high (B-28) keep M0 from being
declarable complete. Iter 26 should pick B-28; an M0-close iteration
needs Node availability resolved first.

---

# Code-review checkpoint — iter 30 (2026-05-06)

Review scope: commits since iter-25 checkpoint `b4899f7`:

- `eba093e` — iter 26: B-28 + B-19 paired (two-pass `npm install
  --package-lock-only && npm ci` in release.yml + Dockerfile +
  cross-file anti-drift guard).
- `c6eabad` — iter 27: B-29 (PEP-440 tag regex) + B-30 (concurrency
  block) + B-31 (uv/npm cache) + B-35 (tightened installer tests) +
  B-36 (header comment).
- `5778103` — iter 28: B-32 (Test-Command explicit bool) + B-33 (MS
  Store stub Python detection) + B-34 (drop redundant setup-uv
  python-version).
- `400aead` — iter 29: B-18 (Tailwind glob contains-not-equals) +
  `docs/M0-acceptance.md` + 6 shape pins.

Going into this review BUGS_FOUND.md had **0 open items**. After
iter-25's checkpoint flagged B-28 as the M0-load-bearing high, iters
26–29 worked the entire backlog to closure.

Smoke-test:
- `uv run pytest tests/ --ignore=tests/e2e` → **136 passed in 0.24s**.
- `uv run ruff check` → clean.
- `uv run pre-commit validate-config` → clean.
- `uv run python -c "from pd_ocr_labeler_spa.bootstrap import build_app; build_app()"` → OK.
- `bash -n install.sh` → OK.
- `make -n docker-build` → renders cleanly with `_docker` macro.

Despite the "all backlog closed" framing, the iters introduced one
real **high-severity regression** during the iter-27 caching change
that almost certainly breaks the very M0-acceptance path iter 26 just
fixed. Filed as B-37 below. Plus four lower-severity findings.

## B-37 — `actions/setup-node@v4` with `cache: "npm"` + `cache-dependency-path: frontend/package-lock.json` fails when the lockfile is absent — **undoes the iter-26 B-28 fix on first tag push**
- **Status:** Fixed in iter 31 — dropped `cache: "npm"` and
  `cache-dependency-path: frontend/package-lock.json` from
  `actions/setup-node@v4`'s `with:` block in `release.yml`. Inline
  comment explains the deferral and points the next maintainer at
  Q-A8: "npm cache disabled until Q-A8 unblocks a checked-in
  `frontend/package-lock.json`. Re-enable in the iter that closes
  Q-A8." The uv cache (`enable-cache: true` on `astral-sh/setup-uv`)
  is the valid caching path today — `uv.lock` exists and the cache
  primes without a setup-step hard-fail. Replaced
  `test_setup_node_enables_npm_cache` with
  `test_setup_node_npm_cache_disabled_until_lockfile_lands` (YAML-walk
  forbidding both `cache:` and `cache-dependency-path:` in the
  setup-node `with:` block; flip when Q-A8 lands the real lockfile).
- **Severity:** **high** (re-breaks the M0 release pipeline that iter 26 just unbroke)
- **Where:** `.github/workflows/release.yml:61-73` (the `actions/setup-node@v4` `with:` block).
- **Issue:** `actions/setup-node@v4` errors out when `cache:` is set
  but the `cache-dependency-path` doesn't resolve to an existing file.
  The error is `Error: Dependencies lock file is not found in
  /home/runner/work/.../frontend/package-lock.json. Supported file
  patterns: package-lock.json,npm-shrinkwrap.json,yarn.lock` — and
  the workflow halts at the setup-node step. This happens **before**
  the "Build SPA bundle" step that's supposed to bootstrap the
  lockfile via `npm install --package-lock-only`. The iter-27 commit
  message and BUGS_FOUND annotation both claim "the lookup fails
  gracefully (no key → cache miss → no-op)" — that's incorrect.
  setup-node treats missing-lockfile as a hard error, not a graceful
  miss.

  Reproducer: tag-push `v0.1.0` to a clean repo without
  `frontend/package-lock.json`. The `release` job fails at "Setup
  Node.js" before reaching "Build SPA bundle". Same outcome iter 25
  filed B-28 for: `release.yml` cannot run end-to-end on first
  execution. The whole point of iter 26's two-pass install was to
  bootstrap the lockfile inside the workflow; iter 27's caching pull
  that bootstrap out from under itself.

  This is documented behaviour, not theoretical — see
  `actions/setup-node` issue tracker (e.g. #569, #1318) and the
  action's source: when `cache-dependency-path` is set, it calls
  `glob` on the path and fails-not-warns when the result is empty.
- **Why it matters:** M0 acceptance gate clause "wheel installable
  from a tagged release" depends on `release.yml` actually completing
  end-to-end. As shipped today, the first tag push will fail at the
  setup-node step with no Release published, no wheel attached, and
  install.sh/install.ps1 broken (they look for the wheel asset which
  was never created). The iter 26 review claimed B-28 closed; the
  iter 27 caching addition silently re-opens it through a different
  code path. Pre-1.0 the impact is bounded (no users), but the
  acceptance gate is the criterion that flips M0 from in-progress to
  done.
- **Suggested fix:** Three options, in order of preference:
  (a) Drop `cache: "npm"` + `cache-dependency-path` from
  `actions/setup-node@v4` until Q-A8 lands a real lockfile. The
  caching benefit is moot today (no warm cache exists yet) and the
  cost is a hard CI failure. Add a TODO comment: "re-enable
  `cache: 'npm'` once `frontend/package-lock.json` is committed
  (Q-A8 unblock)".
  (b) Move the cache enablement to a SECOND setup-node step that
  runs AFTER the bootstrap install — but setup-node only runs once
  per job and a second invocation overwrites the first.
  (c) Pre-create an empty `package-lock.json` via a step before
  setup-node (e.g. `cd frontend && touch package-lock.json` — but
  this would be parsed as an invalid lockfile by the cache action).

  (a) is the right fix. Update
  `test_setup_node_enables_npm_cache` to a conditional ("if
  `frontend/package-lock.json` exists, then cache must be enabled")
  or remove the cache assertion entirely until Q-A8 lands.

## B-38 — `--include=dev` asymmetry between Dockerfile and `release.yml`; cross-file alignment test passes anyway
- **Status:** Fixed in iter 31 — added `--include=dev` to BOTH npm
  invocations in `release.yml`'s "Build SPA bundle" step (the
  `--package-lock-only` bootstrap and the `npm ci` execution), so
  the Dockerfile and the workflow are now flag-set-symmetric.
  Tightened
  `test_dockerfile_and_release_workflow_agree_on_npm_install_logic`
  to assert each non-comment `--package-lock-only` line AND each
  `npm ci` line in BOTH files contains `--include=dev` — so a future
  runner setting `NODE_ENV=production` (or a future GHA default
  change) can't silently break `npm run build` on one side without
  failing the test. Updated the inline comment in `release.yml` to
  document why the flag is explicit (vite/tsc are devDeps; `npm run
  build` needs them).
- **Severity:** low
- **Where:** `Dockerfile:29,31` (`npm install --package-lock-only --include=dev` + `npm ci --include=dev`); `.github/workflows/release.yml:115-118` (no `--include=dev` flag); cross-file guard at `tests/unit/test_dockerfile.py::test_dockerfile_and_release_workflow_agree_on_npm_install_logic`.
- **Issue:** The Dockerfile's spa stage explicitly uses
  `--include=dev` on both passes. release.yml does not. Functionally
  both work today because `npm ci` defaults to including
  devDependencies unless `NODE_ENV=production` is set in the
  environment — but the alignment is implicit, not pinned. The
  cross-file test asserts "both files contain `npm ci` AND
  `--package-lock-only`" but says nothing about `--include=dev`,
  `--omit=dev`, `--prefer-offline`, or any other flag. So a future
  CI runner that sets `NODE_ENV=production` (or a future GHA runner
  default change) would silently break `npm run build` (which needs
  vite + tsc dev-deps) in release.yml without breaking the
  Dockerfile.
- **Why it matters:** The iter-26 commit message frames this as
  "byte-aligned shell logic" — that overstates the alignment. The
  test enforces token-presence parity, not flag-set parity. A
  reviewer reading the test name "agree_on_npm_install_logic" will
  assume both files install the same set of packages with the same
  flags; today they don't (the explicit `--include=dev` in
  Dockerfile is asymmetric).
- **Suggested fix:** Either (a) drop `--include=dev` from the
  Dockerfile (rely on the `npm ci` default like release.yml does),
  or (b) add `--include=dev` to release.yml's `npm install
  --package-lock-only` and `npm ci`, AND tighten the cross-file test
  to assert the flag-set is symmetric. (b) is the more defensive
  posture (immune to a future runner setting `NODE_ENV=production`)
  and is the right answer for a "byte-aligned" claim. The test
  tightening is one extra `assert "--include=dev" in text` line per
  file.

## B-39 — `test_python_pin_in_release_workflow` accepts any `3.13` substring; the loosened pin is now near-meaningless
- **Status:** ✅ **Fixed in iter 32 (2026-05-06)** — chose suggestion
  (b). Test renamed
  `test_python_pin_in_release_workflow` →
  `test_python_pin_in_release_workflow_matches_mise_if_set`. New
  assertion walks parsed YAML, collects every step's `with` block
  containing a `python-version` key, and requires each value (str-
  coerced — YAML can parse `3.13` as a float) to equal
  `_mise_pin("python")`. Today (no `python-version:` key anywhere)
  the assertion is a no-op; if a future iter re-adds setup-python or
  re-pins setup-uv, the new key is drift-checked against `mise.toml`.
  Updated the explanatory comment in `release.yml` to reference the
  renamed test. The prose-coupling assertion is gone — comment-only
  tests were exactly the fragility B-25/B-39 flagged.
- **Severity:** nit
- **Where:** `tests/unit/test_release_workflow.py::test_python_pin_in_release_workflow` (after iter-28 loosening).
- **Issue:** The test was loosened from "must have `python-version:
  3.13`" to "must have `python-version: 3.13` OR have `3.13`
  somewhere in the file." With the iter-28 setup-uv pin removal,
  the only remaining mention of `3.13` is in a single comment line
  (`# `python-version` pin would download Python 3.13 only to ...`).
  If a future iter cleans up the comment as part of an unrelated
  refactor, the test starts failing for a non-substantive reason —
  but more concerning, today the test passes because `3.13` appears
  in prose, NOT because the workflow actually pins Python anywhere.
  The drift-check claim ("a mise.toml bump fails this test loudly")
  is now load-bearing on a comment that isn't shape-pinned itself.
- **Why it matters:** The test name suggests the workflow has a
  Python pin; today it has none (B-34 dropped it). The "loosen to
  accept comment-mention" framing trades a real assertion for a
  prose-coupling assertion. If `mise.toml` bumps to 3.14, the test
  *would* fail (the comment still says 3.13, but `_mise_pin("python")`
  returns 3.14). So the drift gate technically still works — but
  the gate's failure mode tells the contributor "update the
  comment", not "update the workflow." Misleading.
- **Suggested fix:** Either (a) delete the test entirely (the
  workflow doesn't pin Python anymore; `uv build`'s PEP 517
  isolation is the source of truth and lives outside the
  workflow), or (b) reshape the test to assert a more meaningful
  invariant — e.g. "if a `python-version:` key exists anywhere in
  the workflow, it must match `mise.toml`'s pin" (no failure
  if the workflow has no pin at all). (a) is honest; (b)
  preserves the drift gate for future workflows that re-introduce
  a setup-python step. Either beats the current fragile
  prose-coupling.

## B-40 — `install.ps1` MS Store stub regex `^Python \d+\.\d+\.\d+$` rejects pre-release Python (3.14.0a1) and mislabels it as a stub
- **Status:** ✅ **Fixed in iter 32 (2026-05-06)** — loosened the
  regex to `^Python \d+\.\d+(\.\d+)?` (anchor on `Python <maj>.<min>`,
  optional patch group, allow ANY trailing characters). `Python
  3.13.0`, `Python 3.14.0a1`, `Python 3.14.0rc2`, `Python 3.13.0+`
  (pyenv-built) all match. The Microsoft Store stub's "Python was
  not found" reparse-point output does not start with that shape and
  is still detected. Also reworded the diagnostic message to lead
  with what was actually checked (`python --version` did not return
  the expected `Python <X>.<Y>.<Z>` shape) before naming the most
  common cause (Store stub) — more honest about the inference.
  Updated `test_install_ps1_detects_ms_store_stub_python` to assert
  presence of the more permissive `\d+\.\d+` literal (with any
  stricter form acceptable); the bare-`Python `-substring anti-pattern
  is still forbidden via the unchanged `-notmatch` keyword pin.
- **Severity:** nit
- **Where:** `install.ps1:54` (`if ($pyVersionOutput -notmatch '^Python \d+\.\d+\.\d+$')`).
- **Issue:** The regex requires exactly three dot-separated digit
  groups with nothing trailing. `python --version` outputs:
  - `Python 3.13.0` → matches (release version)
  - `Python 3.14.0a1` → does NOT match (alpha pre-release)
  - `Python 3.14.0rc2` → does NOT match (release candidate)
  - `Python 3.13.0+` → does NOT match (the `+` indicates a Python
    built from a non-release tag — common with pyenv-built Pythons)

  Any user running a pre-release Python (e.g. testing 3.14 alpha
  on Windows) gets the misleading message "`python` on PATH is the
  Microsoft Store stub redirector (or otherwise non-functional)"
  followed by remediation pointing at python.org / winget — when
  in fact they have a real Python that just happens to be a
  pre-release.
- **Why it matters:** The user impact is small (uv still installs
  3.13 for the tool, the install proceeds), but the diagnostic
  message is actively wrong for early-adopters running pre-release
  Pythons. A better regex would tolerate the standard
  `\d+\.\d+\.\d+(\D.*)?$` shape (any non-digit suffix is fine).
- **Suggested fix:** Loosen the regex to `^Python \d+\.\d+(\.\d+)?`
  (anchor only the leading "Python <maj>.<min>" form; allow any
  trailing characters). Also adjust the diagnostic message to
  say "`python --version` did not return the expected
  `Python <X>.<Y>.<Z>` shape" — which is more honest about what
  was checked and leaves the user-facing reasoning to them.

## B-41 — Cross-file `--package-lock-only` pin is planned-obsolete; future Q-A8-unblock iter must remove it from BOTH files AND the test
- **Status:** ✅ **Fixed in iter 32 (2026-05-06)** — added explicit
  PLANNED-OBSOLESCENCE breadcrumb docstring sections to BOTH affected
  tests (`test_uses_two_pass_install_with_lockfile_fallback` in
  `test_release_workflow.py` and
  `test_dockerfile_and_release_workflow_agree_on_npm_install_logic`
  in `test_dockerfile.py`) naming Q-A8 as the unblock trigger and
  enumerating the four-place cleanup that must land in a single
  commit (drop bootstrap from `release.yml` + `Dockerfile` spa stage,
  delete the workflow-side assertion, drop the `--package-lock-only`
  clauses from the cross-file test). The `npm ci` + `--include=dev`
  symmetry pins explicitly remain post-cleanup. Cosmetic-only —
  no test-shape change, no source-file change.
- **Severity:** low
- **Where:** `tests/unit/test_dockerfile.py::test_dockerfile_and_release_workflow_agree_on_npm_install_logic` and `tests/unit/test_release_workflow.py::test_uses_two_pass_install_with_lockfile_fallback`.
- **Issue:** Both tests pin `--package-lock-only` as a required
  token in their respective files. Once Q-A8 unblocks and a real
  `frontend/package-lock.json` is committed, the bootstrap branch
  becomes a permanent no-op. A future iter's natural cleanup —
  remove the now-dead `if [ ! -f package-lock.json ]; then npm
  install --package-lock-only; fi` block from BOTH files — would
  fail both tests, and a hasty fix that updates only one
  (e.g. cleans up release.yml but not Dockerfile) would
  re-introduce the iter-25 inconsistency the cross-file test
  was supposed to prevent. Worse: if the future iter removes
  `--package-lock-only` from one file but the test forces them
  to keep it in the other, they may revert the cleanup half-way
  and leave dead code in.
- **Why it matters:** Self-balancing test for current state, but
  the "do this together" coupling depends on a future
  contributor reading the BUGS_FOUND comment that names the
  cleanup pattern. There's no in-test breadcrumb that says "when
  Q-A8 lands, remove this assertion." A future-self reading just
  the test code would reasonably interpret it as "this token
  must always be present" rather than "this token is a
  Q-A8-blocker workaround that can be ripped out together."
- **Suggested fix:** Add a comment in both tests pointing at the
  Q-A8-driven cleanup: `# When Q-A8 unblocks and a real
  package-lock.json is committed, drop this assertion AND the
  --package-lock-only branch in both release.yml and Dockerfile
  in the same commit. See B-19/B-28.` Cosmetic but the test will
  be re-read in the iter that closes Q-A8; that's the high-value
  moment for the comment.

## Non-findings (checked, no bug)

- **B-29 PEP-440 tag glob.** `v[0-9]+.[0-9]+.[0-9]+` is correct
  GitHub Actions filter-pattern syntax (`+` is "1+ of preceding
  character", `.` is literal). Tags `v1.2.3`, `v12.34.56` match;
  `vbeta`, `vfeature-test`, `v0.0` do not. The forbid-list test
  correctly catches a re-widening to `v*` / `v[0-9]*` / `v?*`. The
  pre-release form `v[0-9]+.[0-9]+.[0-9]+-*` accepts the
  dash-separated convention (`v1.2.3-rc1`); rejects the no-dash
  PEP-440-canonical `v1.2.3rc1` form. That asymmetry is acceptable
  — git tags aren't required to follow PEP-440 verbatim, and the
  dash-form is the de-facto convention across the pd-* peer repos.
  Not worth filing.

- **B-30 concurrency block.** `cancel-in-progress: false` is
  correct for release jobs (mid-upload cancel can leave half-
  uploaded assets). Group keyed on `${{ github.ref }}` means
  different tags don't block each other but the same tag re-pushed
  (or "Re-run all jobs") queues. Right shape.

- **B-32 Test-Command explicit boolean.** `$null -ne (Get-Command
  -Name $Name -ErrorAction SilentlyContinue)` returns exactly
  `$true` or `$false` (single Boolean). Correct refactor;
  PowerShell's `-not` no longer accidentally-correct.

- **B-34 setup-uv `python-version` removal.** Correct. `uv build`
  does spawn a build-isolated PEP 517 env that provisions its own
  Python; the setup-uv pin was wasted. (B-39 above is about the
  *test* that the pin removal exposed, not the removal itself.)

- **B-35 installer test tightening.** `re.search(r"uv tool
  install\s+--reinstall\s+\S+", text)` correctly pins all three
  load-bearing parts (verb + flag + arg). Verified against
  `install.sh:64` and `install.ps1:90` (both use exactly that
  shape).

- **B-18 Tailwind contains-not-equals.** The new
  `_parse_tailwind_content_globs` parses string literals out of
  the `content: [...]` array and asserts canonical-glob membership.
  Empty array would fail the existence-of-`./src/**` check (no glob
  scans `./src/**/*.{ts,tsx}` if the array is empty), so the test
  is regression-safe in the "future iter empties the array"
  hypothesis.

- **`docs/M0-acceptance.md`.** All eight spec acceptance criteria
  are reflected in the criteria table. The status section is
  honest about Q-A8/A9 blocking. The sign-off ritual is
  actionable (six shell commands, no external tooling needed
  beyond `make ci` + a workstation with Node). ROADMAP M0 sub-
  task list (`docs/ROADMAP.md:172-217`) is in sync — every
  unchecked item there is also flagged as "gated on Q-A8" in
  M0-acceptance.md. No drift between the two.

- **Test count growth 121 → 136 (+15).** Genuine shape pins, no
  trivially-passing tests:
  - iter 26: +3 (cross-file alignment, dockerfile two-pass,
    release.yml two-pass).
  - iter 27: +3 (concurrency, setup-node cache, setup-uv cache).
  - iter 28: +3 (Test-Command explicit bool, MS Store stub
    detection, setup-uv-no-python-version).
  - iter 29: +6 (M0-acceptance shape pins).
  All assert against actual file contents. None are "if X then
  Y" no-op tests. B-39 above is the only test in the batch with
  a meaningfully-loosened invariant.

- **BUGS_FOUND.md staleness audit.** Spot-checked B-19, B-28,
  B-29..B-36 fix annotations. All cite the iter that landed the
  fix and the right commit-sha. B-19's annotation (covers the
  paired iter-26 fix with B-28) is honest about the remaining
  Q-A8 dependency. No findings need to be flipped to open. (B-37
  above is a NEW issue introduced by iter 27, not a re-opening
  of a previously-closed entry.)

- **OPEN_QUESTIONS.md staleness.** Q-A8 (Node availability) and
  Q-A9 (ESLint config) both genuinely still blocked — no
  `frontend/package-lock.json`, no `frontend/eslint.config.*`,
  `node` and `npm` not on PATH. Q-A10 (PyPI publish)
  intentionally deferred. No question should close yet.

## Summary — iter 30

**5 findings: 0 blocker, 1 high (B-37), 0 medium, 2 low (B-38, B-41), 2 nit (B-39, B-40).**

Top concerns:

1. **B-37 (high)** — `actions/setup-node@v4`'s `cache: "npm"` +
   missing `frontend/package-lock.json` will hard-fail the workflow
   at the Setup Node.js step **before** the iter-26 two-pass install
   gets a chance to bootstrap the lockfile. This silently re-opens
   B-28 (the M0-load-bearing high that iter 26 just fixed). Pre-1.0
   the impact is invisible (no tag pushed yet), but the next tag
   push will produce no Release. **Fix this before any tag push.**

2. **B-38 (low)** — Dockerfile's `--include=dev` is asymmetric with
   release.yml's no-flag `npm ci`. Works today by default, but the
   "byte-aligned" framing in the iter-26 commit message overstates
   the actual symmetry, and the cross-file test only checks two
   tokens.

3. **B-39 / B-40 / B-41** — quality-of-life: a fragile prose-pinning
   test (B-39), a regex that misclassifies pre-release Pythons
   (B-40), and a planned-obsolete test pin without a breadcrumb
   (B-41). None block M0.

**Test suite:** 136/136 green in 0.24s. No flakiness. ruff +
pre-commit clean.

**M0 status (re-assessed):** **Not yet declarable complete.** Three
remaining blockers:

- Q-A8 (frontend toolchain) — gates 4/8 acceptance criteria.
- Q-A9 (ESLint config) — gates 1/8 acceptance criteria.
- **B-37** (the new high) — release pipeline cannot run end-to-end
  due to setup-node hard-failing on missing lockfile.

The good news: B-37 is one-line fix (drop the cache enablement
until Q-A8 lands). The acceptance gate decision is unchanged from
iter 25's checkpoint — Q-A8 + Q-A9 are user-action items
(devcontainer feature, ESLint config decision) and M0 cannot be
self-closed by the /loop. Iter 31 should pick **B-37** first; B-38
can ride along (one-line `--include=dev` add). B-39/B-40/B-41 are
opportunistic.

**Iter 31 picks: B-37 (drop or guard the npm cache), bundled with
B-38 (`--include=dev` symmetry).**

---

# BUGS_FOUND — code-review checkpoint, iter 35 (2026-05-06)

Review scope: commits since `02fd069`:
- `9a2ab99` + `d6ffcd7` — iter 31 (B-37/B-38 closeout, two commits w/ pre-commit auto-fix)
- `7696adf` — iter 32 (B-39/B-40/B-41 batched closeout)
- `2bb956d` + `b00a265` — iter 33: **M1.a** — adapter Protocols (storage, auth, ocr) + filesystem/none/stub impls + 15 tests
- `b70ec57` + `0b3c584` — iter 34: **M1.b** — `RequestIdMiddleware` + `core/logging_config` + 16 tests

Reviewer ran:
- `uv run pytest -q` → 167/167 green in 0.28s
- `uv run ruff check .` → clean
- `python -c "build_app(...); print(len(app.user_middleware))"` → 2 (RequestId at index 0, CORS at 1) — spec §12 ordering confirmed
- `TestClient(...).get('/healthz', headers={'X-Request-ID': 'abc-test'})` → echoed back on response, status 200
- `make -n docker-build` → returns 0
- `pre-commit validate-config` → clean

Findings B-42 through B-49 (8 items: 0 blocker, 0 high, 3 medium, 3 low, 2 nit).

---

## B-42 — `IAuth.verify` signature drifts from spec §7 (`creds: HTTPAuthorizationCredentials | None` → `credentials: str | None`)

- **Severity:** medium
- **Where:** `src/pd_ocr_labeler_spa/adapters/auth/base.py:42`; spec citation `specs/02-backend.md:434`
- **Issue:** Spec §7 fixes the Protocol surface verbatim:
  ```python
  async def verify(self, creds: HTTPAuthorizationCredentials | None) -> UserContext: ...
  ```
  The impl is `async def verify(self, credentials: str | None) -> UserContext: ...` — both the parameter name (`creds` → `credentials`) and the type (`HTTPAuthorizationCredentials | None` → `str | None`) drift. The `IAuth` protocol's docstring acknowledges the deviation ("backends that need structured `HTTPAuthorizationCredentials` should re-parse from the request in their own dependency layer") but per the agent's own rule "specs are the source of truth; if reality forces a change, change the spec first."
- **Why it matters:** When M2/M5 wires `api/dependencies.py::get_user`, the FastAPI dependency `Depends(HTTPBearer())` returns `HTTPAuthorizationCredentials | None`. Current impl forces the dependency layer to do `creds.credentials if creds else None` to flatten to `str` — extra friction at every callsite, exactly the kind of churn Protocols-as-spec are meant to avoid. Also, the method-set drift pin (`test_iauth_protocol_method_set` only checks `verify` exists) does NOT catch this signature drift, so a future "fix" could silently re-widen.
- **Suggested fix:** Either (1) restore the spec signature (import `from fastapi.security import HTTPAuthorizationCredentials`, accept the model directly), or (2) update spec §7 line 434 to match the impl with a one-line "decision: flatten to bearer string at the Protocol surface so the Protocol is FastAPI-agnostic; dependency layer extracts `.credentials`" rationale. Either way, a sig drift-pin test should land — `inspect.signature(IAuth.verify).parameters` matches the spec's named/typed shape.
- **Status:** Fixed in iter 36. Restored the spec signature: `IAuth.verify(self, creds: HTTPAuthorizationCredentials | None) -> UserContext` in `adapters/auth/base.py:50` and `NoneAuth.verify` mirrors. Added `test_iauth_verify_signature_matches_spec` in `tests/unit/test_adapters_auth.py` — uses `typing.get_type_hints(IAuth.verify)` to resolve string annotations (PEP 563) and pins both the parameter name (`creds`) AND the resolved annotation (`HTTPAuthorizationCredentials | None`) AND the return annotation (`UserContext`). A future widening to `str | None` now fails this test loudly. `NoneAuth` test updated to feed an `HTTPAuthorizationCredentials(scheme="Bearer", credentials="ignored")` instance instead of a raw string.

---

## B-43 — Spec §9's per-route audit log (`request_start` / `request_end`) is not implemented in M1.b

- **Severity:** medium
- **Where:** `src/pd_ocr_labeler_spa/api/middleware/request_id.py` (whole file); spec citation `specs/02-backend.md:500-502`
- **Issue:** Spec §9 is two bullets, not one:
  ```
  Verbatim port from pgdp-prep:
  - api/middleware/request_id.py — ...
  - core/logging_config.py — ...
  Per-route audit log (closes pgdp-prep gap):
  - request_start info log on entry (path, method, request_id).
  - request_end info log on exit (status, duration_ms).
  ```
  The iter-34 commit message says "Verbatim ports from pd-prep-for-pgdp per spec §9" and ships the first two bullets — but **the third bullet (the audit log that explicitly "closes the pgdp-prep gap") is silently absent**. The middleware has no `log.info("request_start", ...)` / `log.info("request_end", ...)` calls. Iter-34's ROADMAP entry doesn't mention it as remaining work either; the gap is invisible.
- **Why it matters:** This is the only piece of §9 the spec calls a *new feature beyond pgdp-prep parity*, so quietly skipping it on the "verbatim port" iter means the feature lands when, exactly? It's not in any remaining-M1-sub-tasks list. M1's acceptance test (`test_request_id_echoed`) doesn't catch it. Operational triage of a misbehaving job will be missing path/method/duration_ms breadcrumbs the spec promised.
- **Suggested fix:** Either (1) add the audit-log lines now (`log.info("request_start", extra={"path": ..., "method": ..., "request_id": rid})` on entry, `log.info("request_end", extra={"status": response.status_code, "duration_ms": ...})` in the `finally`-or-after-call-next branch), or (2) explicitly file a follow-on task in the M1 sub-task list naming this gap and a target iter. Don't leave it implicit.
- **Status:** Fixed in iter 36 via approach (1). `RequestIdMiddleware.dispatch` now emits `log.info("request_start", extra={"path", "method"})` on entry (after the contextvar is set, so `RequestIdFilter` tags it with `request_id`) and `log.info("request_end", extra={"path", "method", "status", "duration_ms"})` in the `finally` block (also inside the contextvar scope, BEFORE the token reset, so the tag still applies). `time.monotonic()` is used so wall-clock jumps cannot produce negative `duration_ms`; `status_code` defaults to 500 if `call_next` raises before assignment. Three new tests in `tests/unit/core/test_request_audit_log.py`: `test_request_start_emitted_with_path_method`, `test_request_end_emitted_with_status_duration` (asserts non-negative int `duration_ms`), `test_audit_log_carries_request_id` (uses `RequestIdFilter` on caplog to verify `rid` tag).

---

## B-44 — `FilesystemStorage.delete` / `list_keys` / `put_bytes` parent-mkdir use sync FS calls under `async def` — defeats async I/O on those methods

- **Severity:** medium
- **Where:** `src/pd_ocr_labeler_spa/adapters/storage/filesystem.py:62-65, 67-84, 56`
- **Issue:** The Protocol declares `delete`, `list_keys` etc. as `async`. The filesystem impl mostly delegates through `anyio.Path` (good), but three paths run sync-on-the-event-loop:
  - `delete`: `path.exists()` and `path.unlink()` — both `pathlib.Path` sync calls.
  - `list_keys`: `base.exists()`, `base.is_file()`, `base.rglob("*")`, `path.is_file()`, `path.relative_to()` — all sync.
  - `put_bytes`: `path.parent.mkdir(parents=True, exist_ok=True)` — sync (the comment acknowledges this with "anyio's Path proxy doesn't offer mkdir(parents=True) cleanly without an extra hop").
- **Why it matters:** Under any concurrency at all (Vite-dev hot-reload, test parallelism, the eventual SSE notifications endpoint), these sync calls block the event loop while the kernel reads the directory. `list_keys` against a populated `<cache_root>/page-images/` (one file per page-image, hundreds of files for a long book) is the worst — sync `rglob` walks every entry. The labeler's single-user shape masks the cost in v1, but importing this pattern into M3+ where job-runner concurrency is real means the labeler is silently slow in places the spec says are async. The comment in `put_bytes` confirms the author knew but accepted the shortcut.
- **Suggested fix:** Wrap each sync block in `await anyio.to_thread.run_sync(lambda: ...)`. For `list_keys` specifically, doing the whole rglob inside one `to_thread.run_sync` is fine (one threadpool dispatch). For `delete` and `put_bytes` parent-mkdir, same. Cost ~6 lines, removes the only correctness/performance lie in the impl. Add a regression test that the sync FS calls don't appear inside `async def` bodies via AST scan, or assert via a basic concurrency probe (two `delete` calls scheduled together don't serialize).

---

## B-45 — Path-traversal guard's docstring claims absolute-path keys (`/etc/passwd`) are "guarded" but the impl silently re-roots them under `self._root`

- **Severity:** low
- **Where:** `src/pd_ocr_labeler_spa/adapters/storage/filesystem.py:30-46`; corresponding test gap in `tests/unit/test_adapters_storage.py:78-97`
- **Issue:** The docstring at lines 33-35 says
  ```
  Two attack shapes guarded:
  - ``../../etc/passwd`` (relative escape via parent dir refs)
  - ``/etc/passwd`` (absolute key reinterpreted under root)
  ```
  But "reinterpreted under root" is not the same as "guarded against." Verified by hand:
  ```
  $ fs.put_bytes("/etc/passwd", b"pwned")  # no exception
  $ ls <root>/etc/passwd                    # exists, contains "pwned"
  ```
  The `lstrip("/")` on line 40 silently converts an absolute key into a relative one. The path-traversal test (line 78) only exercises `../../etc/passwd` (the first attack shape), never `/etc/passwd` — so the test passes but the docstring's second claim is unverified.
- **Why it matters:** Security invariant (no escape from `self._root`) IS preserved, so the bug is mostly cosmetic — a caller passing `/etc/passwd` won't read `/etc/passwd` from the host. But the docstring misleads a future reader into thinking the absolute-path case throws. If the routing layer (M3+) uses absolute-key form anywhere, files end up at unexpected on-disk locations without an error, and ops debugging "why is `<root>/etc/foo` showing up?" wastes time.
- **Suggested fix:** Either (1) tighten the impl: raise `ValueError` if `key.startswith("/")` BEFORE `lstrip` — making the docstring true; or (2) reword the docstring: "absolute-path keys are silently treated as relative under root (no escape, but the leading `/` is stripped)." Add a test asserting the chosen behavior — `put_bytes("/etc/passwd")` either raises OR creates `<root>/etc/passwd` and not anywhere else. Today neither variant is pinned.

---

## B-46 — Inconsistency: OCR impls subclass `IOCREngine` (Protocol) explicitly; storage and auth impls rely on structural typing

- **Severity:** low
- **Where:**
  - `src/pd_ocr_labeler_spa/adapters/ocr/{local_doctr,modal,shared_container}.py` — `class LocalDoctrOCR(IOCREngine):` etc.
  - `src/pd_ocr_labeler_spa/adapters/auth/none_.py:13` — `class NoneAuth:` (no base)
  - `src/pd_ocr_labeler_spa/adapters/storage/filesystem.py:21` — `class FilesystemStorage:` (no base)
- **Issue:** Two different conformance styles within the same M1.a iter. Subclassing a `@runtime_checkable` Protocol turns the impl into a nominal subtype (still type-checks structurally, but `isinstance(LocalDoctrOCR(), IOCREngine)` returns `True` via MRO not runtime structural-check); not subclassing leaves it pure-structural. The functional difference is small, but the *style* difference is jarring.
- **Why it matters:** A future agent reading these three packages in order will pattern-match "OCR inherits, the others don't, why?" and either (a) add inheritance to the others "for consistency" (potentially shadowing default arguments via Protocol class attributes) or (b) drop inheritance from OCR (breaking any `isinstance` check that doesn't yet exist but might land in M3 dispatcher wiring). Neither break is dramatic, but the inconsistency itself is the bug.
- **Suggested fix:** Pick one style for the codebase and apply it. PEP 544 best-practice and pgdp-prep both lean toward *no* inheritance (pure structural typing) — drop `(IOCREngine)` from the three OCR impls. Add a one-line comment in `adapters/__init__.py` documenting the policy ("impls match Protocols structurally; do not subclass").

---

## B-47 — `test_request_id.py` lacks the `_reset_managed_handlers` autouse cleanup that `test_logging_config.py` has — `build_app(...)` calls in this file leak managed handlers across the test session

- **Severity:** low
- **Where:** `tests/unit/core/test_request_id.py` (whole file, no autouse fixture); cf. `tests/unit/core/test_logging_config.py:224-231`
- **Issue:** `test_logging_config.py` has the autouse fixture
  ```python
  @pytest.fixture(autouse=True)
  def _reset_managed_handlers():
      yield
      root = logging.getLogger()
      for h in list(root.handlers):
          if getattr(h, "_pdlabeler_managed", False):
              root.removeHandler(h)
  ```
  to keep tests hermetic. `test_request_id.py` does NOT — but it has *three* tests that call `build_app(Settings(...))`, which calls `configure_logging(...)`, which leaves a managed handler on the root logger. Only `test_build_app_calls_configure_logging` does explicit cleanup at the very end (line 186). The other two (`test_build_app_registers_request_id_outermost`, `test_build_app_request_id_uses_settings_header`) leak.
- **Why it matters:** Within today's two-file `tests/unit/core/` directory the leak is benign (the other file's autouse fixture cleans up at its own test boundaries, and ordering happens to land favorably). But pytest doesn't guarantee a file-order, and any future test in any other file that introspects the root logger's handlers will see a stale managed handler from whatever `test_request_id.py` test ran last. This is exactly the failure mode the sentinel + autouse pattern was meant to prevent.
- **Suggested fix:** Lift the `_reset_managed_handlers` fixture into `tests/unit/core/conftest.py` (so both files share it) — or copy-paste it into `test_request_id.py`. Two-line fix.
- **Status:** Fixed in iter 36. New `tests/unit/core/conftest.py` hosts the autouse `_reset_managed_handlers` fixture (yield-then-cleanup form, identifies handlers by the `_pdlabeler_managed` sentinel attribute so caplog/uvicorn handlers are left alone). The duplicate copy in `test_logging_config.py` has been removed (replaced by a one-line breadcrumb comment pointing to conftest.py); the unused `import pytest` was also dropped from that file. Now applies session-wide to every test in `tests/unit/core/` — including the new `test_request_audit_log.py`.

---

## B-48 — `test_request_id_tagged_on_log_lines` cleanup `caplog.handler.removeFilter(caplog.handler.filters[-1])` is positional, not identity-based

- **Severity:** nit
- **Where:** `tests/unit/core/test_request_id.py:91-113`
- **Issue:** The test does:
  ```python
  caplog.handler.addFilter(RequestIdFilter())   # line 91
  ...
  finally:
      caplog.handler.removeFilter(caplog.handler.filters[-1])   # line 113
  ```
  The cleanup removes whichever filter is currently last in the list — not necessarily the one we added. If anything between lines 91 and 113 (the `try` block, the TestClient call, the FastAPI startup hooks) appends a filter to caplog's handler, this line removes the wrong one.
- **Why it matters:** Today nothing inserts a filter — the test passes. But the pattern is fragile: someone adds a `caplog.handler.addFilter(...)` for a different purpose in this test or in a sibling fixture, and the cleanup silently leaks the RequestIdFilter (now pinned forever onto pytest's caplog handler), which then changes log records for every subsequent test in the session that uses caplog.
- **Suggested fix:** Capture the filter instance at `addFilter` time:
  ```python
  rid_filter = RequestIdFilter()
  caplog.handler.addFilter(rid_filter)
  try:
      ...
  finally:
      caplog.handler.removeFilter(rid_filter)
  ```
  One-line refactor; identity-based removal is robust.

---

## B-49 — `test_request_id_var_default_is_empty_string` is circular: it sets `""` then asserts `""`, never tests the documented default

- **Severity:** nit
- **Where:** `tests/unit/core/test_logging_config.py:30-39`
- **Issue:** The test:
  ```python
  def test_request_id_var_default_is_empty_string() -> None:
      token = request_id_var.set("")
      try:
          assert request_id_var.get() == ""
      finally:
          request_id_var.reset(token)
  ```
  This sets the contextvar to `""` and confirms it's `""`. It does NOT verify that the *declared default* on `ContextVar("request_id", default="")` is `""`. Any future `default=None` or `default="<unset>"` would still pass (the test sets `""` first).
- **Why it matters:** The docstring claims this pins the spec §9 invariant ("empty-string default keeps the JSON field type-stable"). It doesn't. The drift it claims to catch (someone changing the `default=` kwarg) goes undetected.
- **Suggested fix:** Test the default directly:
  ```python
  fresh = ContextVar[str]("test_default_check", default=...)  # don't actually re-create it
  # OR: import the module attribute that holds the default and assert
  import pd_ocr_labeler_spa.core.logging_config as lc
  # The contextvar's name + default are accessible via _name / _default
  # But cleaner: just call .get() in a fresh context, e.g. via contextvars.copy_context()
  import contextvars
  ctx = contextvars.Context()
  assert ctx.run(lambda: request_id_var.get()) == ""
  ```
  The `contextvars.Context()` form is the canonical "fresh context" idiom and tests the real default without setting the var first.

---

## Cross-cutting checks (NEW for iter 35)

- **Test count growth: 136 → 167 (+31).** Suite still 0.28s. No flakiness across three runs. Genuine shape pins, none of the 31 new tests are no-op tautologies (B-49 is a single weak test, not a category).
- **Module layout adherence to spec §1.** Spot-checked all M1.a/M1.b new files against `specs/02-backend.md:14-67`: every path matches verbatim. `adapters/auth/none_.py` (with trailing underscore) matches the spec layout exactly (avoids shadowing `none` keyword). `core/logging_config.py`, `api/middleware/request_id.py` — both at the spec-named locations. ✓
- **Protocol vs concrete-class export surface.** `adapters/storage/__init__.py` exports `IStorage` + `FilesystemStorage`. `adapters/auth/__init__.py` exports `IAuth` + `UserContext` + `NoneAuth`. `adapters/ocr/__init__.py` exports `IOCREngine` + `OCRProvenance` + the three impls. Both Protocols and concrete classes are exported. The `__all__` is set in all three. ✓
- **`UserPageEnvelope` v2.1.** Per `specs/16-milestones.md:220-221` lands in **M3** (`core/persistence/user_page_envelope.py`), not M1. The agent description's mention is forward-context, not a current obligation. Not a finding.
- **CORS allow_credentials.** `bootstrap.py:71-76` — `allow_credentials` deliberately omitted with a load-bearing comment citing the CORS-spec rule (wildcard origin + credentials are mutually exclusive). Correct for v1.
- **Middleware ordering correctness.** Verified at runtime: `app.user_middleware[0].cls.__name__ == "RequestIdMiddleware"`, `app.user_middleware[1].cls.__name__ == "CORSMiddleware"`. Spec §12 ordering ("RequestId outermost") satisfied.
- **`X-Request-ID` round-trip.** Verified with a TestClient call: incoming `X-Request-ID: abc-test` is echoed back on the response header. Auto-mint path also verified — missing header yields a uuid4 hex echoed back. ✓
- **`configure_logging` idempotency.** Verified at runtime: 5 successive calls leave exactly 1 managed handler. ✓
- **B-37 anti-drift (mental revert).** Reverted the `--include=dev` on the `release.yml` `npm ci` line in my head; `test_dockerfile_and_release_workflow_agree_on_npm_install_logic` would fail with `release.yml: 'npm ci' line must use '--include=dev' (B-38 symmetry — 'npm run build' needs vite/tsc devDeps); got: ...`. Test correctly catches the regression. ✓
- **B-40 regex check.** Manually traced `^Python \d+\.\d+(\.\d+)?` against:
  - `Python 3.13.0` (real) → matches (full string consumed).
  - `Python 3.14.0a1` (pre-release) → matches (the `0` part consumed; trailing `a1` left unmatched, OK because regex isn't end-anchored).
  - `Python was not found, run "without arguments" to install...` (MS Store stub) → does NOT match (no digit after `Python `; `\d+` fails). Diagnostic still fires. ✓
  - `Python 3.13.0+` (pyenv) → matches. ✓
- **B-39 test rename.** Renamed `test_python_pin_in_release_workflow` → `test_python_pin_in_release_workflow_matches_mise_if_set` and the body now does a YAML-walk for `with: { python-version: ... }` keys. Today's workflow has none, so the test is a passive guard until a future re-introduction. Real refactor (not a rename-only). ✓
- **B-41 breadcrumbs.** `grep -r "PLANNED OBSOLESCENCE" tests/` returns matches in both `test_dockerfile.py` and `test_release_workflow.py`, naming Q-A8. Future Q-A8-closing iter can grep for it. ✓
- **`make -n docker-build`** returns 0 (frontend-build, COPY, docker build). Recipe shape unchanged. ✓
- **`pre-commit validate-config`** clean. ✓
- **OPEN_QUESTIONS.md staleness.** Q-A8 (Node) still genuinely blocked — no `frontend/package-lock.json`, no `node` on PATH. Q-A9 (ESLint config) still genuinely blocked. Both correctly remain open.

## Summary — iter 35

**8 findings: 0 blocker, 0 high, 3 medium (B-42, B-43, B-44), 3 low (B-45, B-46, B-47), 2 nit (B-48, B-49).**

Top concerns:

1. **B-43 (medium)** — Spec §9's audit-log enhancement (`request_start` / `request_end` log lines) was *quietly skipped* on the iter-34 "verbatim port from pgdp-prep per spec §9" commit. The spec's third bullet under §9 explicitly says "closes pgdp-prep gap" — it's NEW behavior beyond the verbatim port. Iter-34 didn't ship it and didn't file a follow-on. This is the kind of silent spec-vs-code drift the agent's mandate ("specs are source of truth") was meant to prevent. Should land before M1 closes.

2. **B-42 (medium)** — `IAuth.verify` parameter type drifted from `HTTPAuthorizationCredentials | None` (spec) to `str | None` (impl) without a corresponding spec-edit-first decision. Will force every dependency-layer callsite in M2 to flatten the FastAPI `HTTPBearer()` return value. The Protocol method-set drift-pin doesn't catch signature drift, so a future re-widening would be invisible too.

3. **B-44 (medium)** — `FilesystemStorage.delete` / `list_keys` / `put_bytes` parent-mkdir use sync FS calls under `async def`. The labeler's single-user shape masks the cost today, but `list_keys` against a populated image-cache will block the event loop. Easy 6-line fix with `anyio.to_thread.run_sync(...)`.

**Test suite:** 167/167 green in 0.28s. No flakiness. ruff + pre-commit clean. ✓
**Test count growth audit:** 136 → 167 (+31). All genuine shape pins.
**Spec adherence audit:** 4 spec-drift findings (B-42, B-43, B-45's docstring lie, plus B-46's inconsistency between adjacent files). M1 layout (file paths) matches spec §1 verbatim — the drift is in *behaviors*, not *file locations*.

**M1 progress estimate:** **roughly 35%** complete.
- ✅ M1.a: Adapter Protocols (storage/auth/ocr) + filesystem/none/stub impls.
- ✅ M1.b: RequestIdMiddleware + structured logging.
- ⬜ M1.c: `error_handler` middleware (spec §8).
- ⬜ M1.d: `core/app_state` skeleton + `api/dependencies` (`get_storage`, `get_app_state`, `get_user`).
- ⬜ M1.e: Full `bootstrap.build_app` wiring (spec §2 steps 2-6 and 9-12: build adapters, build job runner stubs, build AppState, lifespan, stash adapters on `app.state`, install error handlers + routers, image-cache mount, SPA fallback).
- ⬜ M1.f: `core/persistence/{paths,session_state,__init__}.py`.
- ⬜ M1.g: `__main__.py` CLI flag wiring.
- ⬜ M1.h: Frontend `HeaderBar` + `EmptyProjectState` + `RootPage` (Q-A8-blocked).

**Iter 36 picks:**

1. **First: B-43** (audit log) — single-medium, clean spec-anchored fix; ~10 lines in `request_id.py` middleware + 2-3 tests; closes a spec gap quietly introduced last iter. Pairs naturally with B-47 (autouse cleanup) since both touch the same test file.
2. **Then: B-42** (IAuth signature) — forces a spec-vs-impl decision. Either edit `specs/02-backend.md:434` to match impl (with rationale comment) OR widen the impl signature. Should NOT be deferred to M2 wiring iter — the longer it sits, the more callsites embed the drift.
3. **Or pivot to M1.c (error_handler middleware)** if the agent prefers code-progress over backlog cleanup. B-43 + B-42 are the spec-gap fixes; M1.c is the next adapter-axis sub-task.

Iter 40 = next code-review checkpoint.

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
- **Severity:** low
- **Where:** `frontend/tailwind.config.js:10-13` (`content: ["./index.html", "./src/**/*.{ts,tsx}"]`); pinning test in `tests/unit/test_tailwind_config.py`.
- **Issue:** The glob `./src/**/*.{ts,tsx}` *does* recurse, so any future `src/components/ui/**.tsx` file is technically scanned. **However**, shadcn/ui's `init` writes a `tailwind.config.js` whose content array explicitly lists `./components/**/*.{ts,tsx}`, `./app/**/*.{ts,tsx}`, `./pages/**/*.{ts,tsx}`, and `./src/**/*.{ts,tsx}` — and the `components.json` `cli.tailwind.config` field points at a config the CLI parses. When iter N runs `npx shadcn@latest init` (currently blocked on Q-A8), the CLI may either (a) detect the existing config and merge cleanly, or (b) overwrite the file with its own template. If the test pins a literal substring of the content array, a shadcn overwrite that *expands* the globs would fail the test and force the iter author to manually patch the test rather than accept the more inclusive globs.
- **Why it matters:** Mild future-tax. The wider concern is the test pattern: pinning a literal substring of a glob list is fragile in the face of additive evolution. Today's globs are sufficient (single-source-tree React app), but the test is set up to fight shadcn rather than accept it.
- **Suggested fix:** Loosen the content-globs assertion to require `"./src/**/*.{ts,tsx}"` is present *as one entry* (superset check), rather than as the full content of the array. The `^3.4.0` major pin is correct (v4 is a breaking-change rewrite); no action there.

## B-19 — `Dockerfile` `wheel` stage uses `npm install` (not `npm ci`) and tolerates missing `package-lock.json`
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
- **Severity:** low
- **Where:** `Makefile:209-216` (the three docker-* recipes) — neither has a guard like the `_npm` macro's "no npm available; here are your options" fallback.
- **Issue:** The frontend targets (`frontend-install`, `frontend-build`, `frontend-dev`, `frontend-test`) go through the `_npm` macro at `Makefile:98-112` which checks for `mise` then `npm` and prints a friendly options block ("run `make mise-setup`", "install Node 24 yourself", "add the devcontainer node feature") before exiting 1. The new docker targets don't. On a devcontainer that lacks docker (the current state — `which docker` returns nothing in this environment), the recipes shell out to `docker build …` and the user gets bash's terse `make: docker: No such file or directory`. The `_npm` macro is exactly the cure — a `_docker` macro pattern would be ~6 lines and parallel.
- **Why it matters:** UX. M0 contributors who follow `docs/DEVELOPMENT.md` and try the docker targets without docker installed get a confusing error rather than a pointer ("install Docker Desktop / Colima / `add docker-in-docker feature to .devcontainer/`"). Not a correctness bug.
- **Suggested fix:** Add a `_docker` macro analogous to `_npm` that verifies `command -v docker` first and prints a one-line suggestion if not. Wrap each `docker build`/`docker run` call. Optional but a nicer cross-repo pattern. Alternatively, just one-line guard at the top of each recipe: `@command -v docker >/dev/null 2>&1 || { echo "docker not on PATH; install Docker Desktop or Colima first"; exit 1; }`.

## B-25 — `install.sh` mentions Python 3.13 only in a comment; the test asserting "references pinned Python" only proves the comment exists
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


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
5. Remaining: **B-04** (settings mutation), **B-05** (eslint script
   without eslint installed), **B-06** (openapi:gen path drift),
   **B-07** (`_build_env(settings)` ignores arg), **B-08**
   (tsconfig includes test files in prod build). All deferrable
   until M1 starts touching the surrounding code; B-05 + B-08 are
   the closest to "block M1 frontend work" so iter 8 should pick
   from those if no higher-priority task surfaces.

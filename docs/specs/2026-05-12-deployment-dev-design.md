# pd-ocr-labeler-spa: Deployment + Developer Workflow

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#34

## TL;DR

Single-wheel install via `install.sh` + `uv tool install`. Console scripts: `pd-ocr-labeler-ui`,
`pd-ocr-labeler-spa-export`, `pd-ocr-labeler-spa-prefetch`. Dev loop: `make setup` then two
terminals (uvicorn + vite). CI: lint → test-backend → test-frontend → test-e2e → build-wheel
→ openapi-drift. `Makefile` has `upgrade-deps` (canonical) and `upgrade-deps-local` (dev-local
aware: refuses-with-message when editable `pd-book-tools` detected). `hatch-vcs` version from
git tags. Docker multi-stage: spa builder → wheel builder → slim runtime.

## Context

The deployment pattern mirrors `pd-prep-for-pgdp` throughout: same Makefile structure, same
`build_app(settings)` test seam, same SPA-presence build hook, same openapi-drift CI gate.
The `pd-ocr-labeler-ui` console script name is preserved from the legacy so end users swap
binaries without learning a new command. Node is provided via `mise.toml` (pinned at 24);
`_npm` macro dispatches through `mise exec` when available, falls back to PATH otherwise.

## Constraints

- **`uv tool install` as the install primitive.** No pip, no conda, no system Python.
- **`make frontend-build` before `make build`.** The SPA build hook (`build_hooks/spa_check.py`)
  raises at wheel-build time if `static/index.html` is absent.
- **`upgrade-deps` must refuse in a dev-local venv.** Three detection probes: editable
  `pd-book-tools` (`uv pip show` check), `.venv/.pd-dev-local` marker, `PD_DEV_LOCAL=1` env.
  Refusing silently would be worse than blocking.
- **`openapi-drift` CI gate is required.** Closes the pgdp-prep gap where `types.ts` silently
  diverged from the backend schema.
- **`UV_PYTHON: "3.13"` pinned in CI.** uv-discovered 3.14 has a known anyio/SQLite teardown
  segfault (same fix as pgdp-prep).
- **Wheel-only install path.** Sdist drops the SPA; building a wheel from sdist trips the hook.
  Intentional — mirrors pgdp-prep.

## Decision

### Console scripts

`pyproject.toml [project.scripts]`:
`pd-ocr-labeler-ui = "pd_ocr_labeler_spa.__main__:main"`,
`pd-ocr-labeler-spa-export = "pd_ocr_labeler_spa.operations.export.cli:main"`,
`pd-ocr-labeler-spa-prefetch = "pd_ocr_labeler_spa.prefetch:main"`.

### Boot flags

`pd-ocr-labeler-ui` accepts: `--data-root`, `--projects-root`, `--host` (default 127.0.0.1),
`--port` (default 8080), `--reload`, `--no-browser`, `--frontend-dev <URL>`, `--debugpy`,
`--verbose / -v` (count 0–3), `--page-timing`.

### Dev workflow

`make setup`: uv sync + npm install + pre-commit install + playwright install chromium.
Two-terminal dev: `make dev-backend` (uvicorn + `--frontend-dev http://localhost:5173`) and
`make dev-frontend` (Vite HMR + proxy to :8080). `make openapi-export` after any backend
wire-shape change; runs `openapi-typescript` to regenerate `frontend/src/api/types.ts`.

### upgrade-deps guard

`make upgrade-deps`: probes in order — (1) `uv pip show pd-book-tools | grep "Editable
project location"`, (2) `.venv/.pd-dev-local` marker, (3) `PD_DEV_LOCAL=1`. On any match:
print refusal message naming the probe, exit non-zero without touching the venv.

`make upgrade-deps-local`: `uv lock --upgrade` → `uv sync --group dev` → dev-local restore
(editable siblings + GPU torch index) → write `.venv/.pd-dev-local`.

### Build hook

`build_hooks/spa_check.py`: `SpaCheckHook.initialize` checks `static/index.html` exists;
skips on editable install and `PD_LABELER_SKIP_SPA_CHECK=1`. If absent: raises `RuntimeError`
with message "SPA bundle not found. Run make frontend-build first.".

### Docker

Multi-stage: `node:24` → build SPA → `python:3.13-slim` → `uv build --wheel` (with SPA
copied in) → `python:3.13-slim` runtime (install wheel, expose 8080, ENTRYPOINT with
`--host 0.0.0.0 --no-browser`).

### CI pipeline

6 required jobs: `lint` (ruff + eslint + `tsc --noEmit`), `test-backend` (pytest
unit+integration+conformance), `test-frontend` (vitest + frontend build), `test-e2e`
(playwright), `build-wheel` (assert `static/index.html` in wheel zip), `openapi-drift`
(`make openapi-export` + `git diff --exit-code frontend/src/api/types.ts
frontend/openapi.json`). `build-container` and `release` jobs trigger on tag push only.

### Logging

Default log file: `<data_root>/logs/session_<YYYYMMDD_HHMMSS>.log`. `[rid=...]` tags.
`--log-format json` for NDJSON. `make clean-logs` purges logs older than 7 days.

### Versioning

`hatch-vcs` from git tags: `v0.1.0` → `0.1.0`; commits between tags → `0.1.0.dev<n>+<sha>`.
Envelope/project schema versions are independent; see `specs/01-data-models.md §4`.

## Contract / Acceptance

- `install.sh | bash` installs `pd-ocr-labeler-ui` onto PATH via `uv tool install`.
- `pd-ocr-labeler-ui --no-browser --port 8080` serves 200 at `/healthz` and SPA at `/`.
- `make build` produces a wheel; `python -m zipfile -l <whl>` shows `static/index.html`.
- `upgrade-deps` refuses-with-message in a dev-local venv; succeeds in canonical venv.
- `upgrade-deps-local` leaves venv with editable `pd-book-tools` intact + marker present.
- `openapi-drift` CI job fails when `types.ts` is out of sync with backend schema.
- Pre-commit hooks pass clean on the full repo.

## Trade-offs considered

**`uv tool install` vs pip install.** `uv tool install` manages isolation automatically;
reinstall is idempotent. Pip requires the user to manage their own venv. Chosen: uv.

**`upgrade-deps` refuse vs warn.** Silently degrading a dev-local venv is worse than a hard
stop. Refuse with a clear message pointing at `upgrade-deps-local`. Chosen: refuse.

**`mise exec` dispatch vs hard require `mise`.** Hard require would break developers with their
own Node 24 on PATH. Dispatch-with-fallback keeps the Makefile usable both ways. Chosen:
fallback.

**openapi-drift in pre-push vs every commit.** Regen on every commit slows the inner loop.
Pre-push is the last gate before sharing code; CI is the backstop. Chosen: pre-push hook +
required CI job.

## Consequences

- Every PR that changes backend wire shapes must run `make openapi-export` and include the
  updated `types.ts` in the diff.
- The `PD_LABELER_SKIP_SPA_CHECK=1` escape hatch is for CI jobs that build the wheel before
  running `make frontend-build` — document in DEVELOPMENT.md.
- `upgrade-deps-local` depends on the workspace-level dev-local restore script (TBD) being
  available; if it doesn't exist yet, `upgrade-deps-local` prints a "workspace script not
  found" error and exits cleanly.

## Open questions

None.

## References

- `specs/15-deployment-dev.md` — legacy feature doc (full Makefile targets, Dockerfile, CI YAML)
- `specs/14-testing.md §7` — CI gate details
- `pd-prep-for-pgdp/` — structural reference (Makefile, install.sh, Dockerfile, build_hooks)
- `build_hooks/spa_check.py` — SPA presence build hook

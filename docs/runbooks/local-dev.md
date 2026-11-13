---
kind: runbook
status: active
owner: maintainers
created: 2026-05-31
last_verified: 2026-11-13
---

# Local Development Runbook

Practical recipes for developing `pdomain-ocr-labeler-spa` locally.

End users running the published wheel need none of this — the wheel ships
with a pre-built frontend bundle. For the design rationale see
[`docs/architecture/00-overview.md`](../architecture/00-overview.md).

---

## Prerequisites

| Tool | Version | How to get |
|------|---------|------------|
| Python | 3.13 | mise (`mise install`) or system package |
| Node | 24 | mise (`mise install`) |
| pnpm | 11 | mise (`mise install`) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | any | system package |

mise pins Node and Python versions via `mise.toml`. From outside the
devcontainer: `curl https://mise.run | sh` then `mise install` in the repo
root.

---

## First-time setup

```sh
mise install            # Node 24 + Python 3.13 per mise.toml
just setup              # uv sync + pre-commit install + version refresh
```

For frontend work, also run:

```sh
just frontend-install   # pnpm install inside frontend/
```

---

## Running the app

### Production SPA (simplest)

```sh
just run
# builds frontend if needed, starts backend, opens browser at :8080
```

### Backend only (no frontend bundle needed)

```sh
uv run pdomain-ocr-labeler-ui --no-browser --port 8080
curl http://127.0.0.1:8080/healthz
```

### Vite HMR dev loop (frontend development)

Two terminals:

```sh
# Terminal 1 — backend with auto-reload
just dev               # uvicorn --reload on :8080

# Terminal 2 — Vite dev server with HMR
just frontend-dev      # Vite on :5173; proxies /api and /image-cache to backend
```

Open `http://localhost:5173`. The Vite proxy reads `.pdlabeler-port` (written
by the backend at startup) and forwards API calls automatically.

---

## Tests

```sh
just test              # unit + conformance; fast; no real OCR
just integration       # slow tests with real DocTR (~10 min; GPU optional)
just e2e               # builds the SPA, then runs Playwright
just frontend-test     # Vitest jsdom tests

AI=1 just ci           # full CI pipeline; run before every commit
```

---

## Lint and typecheck

```sh
just lint              # Python lint fixes
just frontend-lint     # ESLint fixes
just frontend-typecheck # application and test TypeScript projects
just typecheck         # basedpyright only
just format            # Python format only
just frontend-format   # Prettier (writes in place)
just pre-commit-check  # all pre-commit hooks on every tracked file
```

Pre-commit runs automatically on `git commit` after `just setup`.

---

## After changing FastAPI models

```sh
just openapi-export
# exports /openapi.json → regenerates frontend/src/api/types.ts
```

CI regenerates the types and runs the TypeScript checks. Inspect the generated diff before committing;
there is no separate git-diff refusal step or pre-push OpenAPI hook in the current configuration.

---

## Editable sibling development

When iterating on `pdomain-book-tools` or `pdomain-ui` alongside this repo:

```sh
just local-setup           # clone sibling repos if missing
just local-dev             # switch Python to editable + link npm sibling
just local-check           # print current mode + per-sibling resolution
just local-frontend-build  # build frontend against local pdomain-ui
just local-run             # run app against local workspace
```

To revert to registry deps, run from the canonical checkout root:

```sh
uv sync --locked --group dev && just frontend-install && \
  rm -f "${UV_PROJECT_ENVIRONMENT:-.venv}/.pdomain-local-mode" \
        "${UV_PROJECT_ENVIRONMENT:-.venv}/.pdomain-dev-local"
```

Clear the local-mode markers only after both locked installs succeed.

---

## Building a distributable wheel

```sh
just frontend-build    # writes SPA bundle into src/pdomain_ocr_labeler_spa/static/
just build             # OpenAPI + SPA + explicit sdist, then wheel → dist/
```

`build_hooks/spa_check.py` refuses to produce a wheel if `static/` is empty —
a forgotten `just frontend-build` cannot ship a blank page.

---

## Environment variables

All variables use the `PDLABELER_` prefix (`settings.py`).

| Variable | Default | Notes |
|----------|---------|-------|
| `PDLABELER_HOST` | `127.0.0.1` | Bind host |
| `PDLABELER_PORT` | next free from 8080 | Bind port |
| `PDLABELER_DATA_ROOT` | `${XDG_DATA_HOME:-~/.local/share}/pdomain-ocr-labeler-spa` | Data root. If `~/pdomain-ocr-labeler-spa` exists and this directory does not, the legacy directory is used instead. |
| `PDLABELER_SOURCE_PROJECTS_ROOT` | `<data_root>/labeler-books` | Books folder. When set, overrides `config.yaml`. When unset, an absolute `config.yaml` path wins; otherwise the default is created at startup if missing. |
| `PDLABELER_LOG_LEVEL` | `info` | Log level |
| `PDLABELER_FRONTEND_DEV_URL` | — | Set to `http://localhost:5173` when using Vite proxy |
| `CUDA_VISIBLE_DEVICES` | — | Set to `""` to disable GPU for DocTR (CI default) |

---

## Common issues

| Symptom | Fix |
|---------|-----|
| "SPA not built" error on `just run` | `just frontend-build` |
| `ModuleNotFoundError` after merging a worktree | `uv sync --locked --group dev && just local-setup-py` |
| pnpm link not applying after `just local-dev` | `just local-frontend-install` to restore the link overlay while preserving the lock |
| Port conflict on startup | Set `PDLABELER_PORT=NNNN` or let the port-probing pick the next free port |
| TypeScript errors after `just openapi-export` | Regenerated `types.ts` may expose new type gaps — fix them before committing |

## Trigger

Use this runbook when developing this SPA against editable or linked sibling
`pd-*` repositories instead of registry packages.

## Preconditions

Run `just local-setup` so required siblings exist. Preserve the current lockfile
and any intentional local links before switching modes.

## Steps

Run `just local-dev`, inspect resolution with `just local-check`, and use
`just local-run` or the local frontend targets documented above.

## Verification

Require `just local-check` to report the intended editable Python and linked npm
sources. Run the focused tests for any changed sibling integration.

## Rollback

Leave local mode by running the normal locked setup/install targets, which
restore registry resolution. Do not delete sibling checkouts or unrelated work.

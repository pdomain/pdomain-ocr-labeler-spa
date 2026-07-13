---
kind: runbook
status: active
owner: maintainers
created: 2026-05-31
last_verified: 2026-07-13
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
make setup              # uv sync + pre-commit install + version refresh
```

For frontend work, also run:

```sh
make frontend-install   # pnpm install inside frontend/
```

---

## Running the app

### Production SPA (simplest)

```sh
make run
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
make dev               # uvicorn --reload on :8080

# Terminal 2 — Vite dev server with HMR
make frontend-dev      # Vite on :5173; proxies /api and /image-cache to backend
```

Open `http://localhost:5173`. The Vite proxy reads `.pdlabeler-port` (written
by the backend at startup) and forwards API calls automatically.

---

## Tests

```sh
make test              # unit + conformance; fast; no real OCR
make integration       # slow tests with real DocTR (~10 min; GPU optional)
make e2e               # Playwright (requires: make frontend-build first)
make frontend-test     # Vitest jsdom tests

make ci AI=1           # full CI pipeline; run before every commit
```

---

## Lint and typecheck

```sh
make lint              # ruff (Python) + eslint + tsc (TypeScript)
make typecheck         # basedpyright only
make format            # ruff format + prettier (writes in place)
make pre-commit-check  # all pre-commit hooks on every tracked file
```

Pre-commit runs automatically on `git commit` after `make setup`.

---

## After changing FastAPI models

```sh
make openapi-export
# exports /openapi.json → regenerates frontend/src/api/types.ts
```

CI gates on `git diff --exit-code frontend/src/api/types.ts` after re-running
this, so any drift fails the build.

---

## Editable sibling development

When iterating on `pdomain-book-tools` or `pdomain-ui` alongside this repo:

```sh
make local-setup           # clone sibling repos if missing
make local-dev             # switch Python to editable + link npm sibling
make local-check           # print current mode + per-sibling resolution
make local-frontend-build  # build frontend against local pdomain-ui
make local-run             # run app against local workspace
```

To revert to registry deps:

```sh
make local-uninstall
```

---

## Building a distributable wheel

```sh
make frontend-build    # writes SPA bundle into src/pdomain_ocr_labeler_spa/static/
make build             # uv build --wheel → dist/*.whl
```

`build_hooks/spa_check.py` refuses to produce a wheel if `static/` is empty —
a forgotten `make frontend-build` cannot ship a blank page.

---

## Environment variables

All variables use the `PDLABELER_` prefix (`settings.py`).

| Variable | Default | Notes |
|----------|---------|-------|
| `PDLABELER_HOST` | `127.0.0.1` | Bind host |
| `PDLABELER_PORT` | next free from 8080 | Bind port |
| `PDLABELER_DATA_ROOT` | `~/.local/share/pdomain/ocr-labeler` | Project data root |
| `PDLABELER_SOURCE_PROJECTS_ROOT` | — | Initial project discovery root |
| `PDLABELER_LOG_LEVEL` | `info` | Log level |
| `PDLABELER_FRONTEND_DEV_URL` | — | Set to `http://localhost:5173` when using Vite proxy |
| `CUDA_VISIBLE_DEVICES` | — | Set to `""` to disable GPU for DocTR (CI default) |

---

## Common issues

| Symptom | Fix |
|---------|-----|
| "SPA not built" error on `make run` | `make frontend-build` |
| `ModuleNotFoundError` after merging a worktree | `uv sync && make local-setup-py` |
| pnpm link not applying after `make local-dev` | `rm -rf frontend/node_modules frontend/pnpm-lock.yaml && pnpm install` inside `frontend/` |
| Port conflict on startup | Set `PDLABELER_PORT=NNNN` or let the port-probing pick the next free port |
| basedpyright errors after `make openapi-export` | Regenerated `types.ts` may expose new type gaps — fix them before committing |

## Trigger

Use this runbook when developing this SPA against editable or linked sibling
`pd-*` repositories instead of registry packages.

## Preconditions

Run `make local-setup` so required siblings exist. Preserve the current lockfile
and any intentional local links before switching modes.

## Steps

Run `make local-dev`, inspect resolution with `make local-check`, and use
`make local-run` or the local frontend targets documented above.

## Verification

Require `make local-check` to report the intended editable Python and linked npm
sources. Run the focused tests for any changed sibling integration.

## Rollback

Leave local mode by running the normal locked setup/install targets, which
restore registry resolution. Do not delete sibling checkouts or unrelated work.

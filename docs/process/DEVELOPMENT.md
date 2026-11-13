---
kind: process
status: active
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-13
---

# Development

How to set up `pdomain-ocr-labeler-spa` for hacking. End users running the
published wheel don't need any of this — the wheel ships with a
pre-built frontend bundle. See the project [`README.md`](../../README.md)
for the user-facing pitch and [`specs/`](../../specs/README.md) for the
authoritative design notes.

> **Status note (2026-05-07).** Backend is feature-rich (M0 scaffold +
> M1 settings/adapters/AppState/middleware/error-handler/lifespan-clean;
> M2 slice 2 wired). The frontend scaffold exists but has never been
> `npm install`-ed or `npm run build`-ed — the SPA bundle is not yet
> committed. `make build` will refuse to produce a wheel until
> `make frontend-build` populates `src/pdomain_ocr_labeler_spa/static/`.
> The SPA fallback route + `/image-cache` route are wired and
> degrade gracefully (helpful 404) until that bundle lands.

## Prerequisites

This repo uses **[mise](https://mise.jdx.dev/)** to pin the runtime
toolchain. `mise.toml` declares Node 24 and Python 3.13; running
`mise install` (or just letting mise auto-activate when you `cd` into
the repo) gives you both.

- **mise** — `curl https://mise.run | sh` if you don't have it.
- **Python 3.13** — managed by mise via `mise.toml`.
- **Node 24** — managed by mise via `mise.toml`.
- **`uv`** — Astral's Python package manager. The shared devcontainer
  has it pre-installed at `/usr/local/bin/uv`. Outside the
  devcontainer: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
  `mise` is intentionally **not** used to manage `uv` (see the
  `mise.toml` comment for why — the aqua-backed installer recently
  broke verifying Astral's release attestations).

`just --list` lists the available recipes. Where
this doc says "run `pnpm ...`" it means under mise — either with mise
auto-activation in your shell, or explicitly via `mise exec -- pnpm
...` from a non-activated session.

## First-time setup

```sh
mise install         # installs Node 24 + Python 3.13 per mise.toml
just setup           # uv sync + install pre-commit hooks + refresh version
just frontend-install  # frozen pnpm install inside frontend/
```

`just setup` runs `uv sync --locked --group dev`, installs the pre-commit hooks, and forces
`hatch-vcs` to re-derive the package version from the current git
state. `just frontend-install` runs `pnpm install --frozen-lockfile` inside `frontend/`, through mise when available.

(For users who can't or won't install mise, `just mise-setup` is a
fallback that downloads a vendored mise binary and runs `mise
install` for you. End users running the published wheel never need
mise — the wheel ships with the SPA bundle prebuilt.)

## Running the dev server

### Backend-only (today's default)

The FastAPI side is fully wired: SPA fallback, `/healthz`, `/env.js`,
`/image-cache/{key:path}`, request-id middleware, structured logging.
When the frontend bundle is missing, `GET /` returns a diagnostic 503. `just run` builds the bundle
when needed; a direct backend-only development launch can run without it.

```sh
just test            # pytest — main backend feedback loop
just lint            # ruff lint fixes
uv run pdomain-ocr-labeler-ui --no-browser --port 8080
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/env.js
```

### Two-process dev loop (Vite + FastAPI)

Once you've run `just frontend-install`, the standard pgdp-prep-style
dev loop works:

```sh
# terminal 1 — FastAPI on :8080 with --reload
just dev

# terminal 2 — Vite dev server on :5173. The Vite-side proxy
# forwards /api, /image-cache, /env.js back to :8080 (see
# `frontend/vite.config.ts`).
just frontend-dev
```

Open `http://localhost:5173` in a browser. The FastAPI side will
still 404 on `/` until you `just frontend-build` to populate
`static/`, but Vite at :5173 serves the SPA shell directly during
development.

## Tests

```sh
just test            # pytest (excludes e2e/, slow, and integration markers)
just frontend-test   # vitest (jsdom)
just e2e             # Playwright — requires `playwright install chromium`
```

Both `just test` and `just frontend-test` are part of `just ci`.

## Lint / format

```sh
just lint            # ruff lint fixes
just format          # ruff format (writes)
just pre-commit-check  # all pre-commit hooks on every tracked file
```

Pre-commit runs automatically on `git commit` once `just setup` has
installed the hooks.

## Building a wheel

```sh
just build           # OpenAPI export + SPA build + explicit sdist, then wheel
```

`just build` prepares the SPA before packaging. `build_hooks/spa_check.py`
rejects a direct wheel build when the bundle is missing or empty.

## Regenerating typed API client

After changing FastAPI request/response models:

```sh
just openapi-export  # exports /openapi.json then regenerates frontend/src/api/types.ts
```

This keeps the TypeScript surface in lock-step with the Python models.

## CI

```sh
just ci   # locked setup, Python/frontend checks, tests, behavior coverage, build, strict docgraph
```

This is the local repository gate. Release runs through the [local release script](../runbooks/release.md);
the former GitHub workflows are removed.

## Record outcomes on close

Track bugs in the issue tracker and unresolved design choices in
[`OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md). When work closes, remove stale
open-state prose and record durable rationale in
[`docs/context/decisions.md`](../context/decisions.md). Git history preserves
execution transcripts and retired ledgers without exposing them as current
retrieval truth.

## Useful references

- [`docs/architecture/00-overview.md`](../architecture/00-overview.md) — goals, non-goals,
  tech stack, milestone contract.
- [`specs/16-milestones.md`](../../specs/16-milestones.md) — milestone
  acceptance gates.
- [`OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md) — deferred decisions.
- [`specs/16-milestones.md`](../../specs/16-milestones.md) — implementation status by
  milestone.
- [`docs/context/current-state.md`](../context/current-state.md) — current work and risks.
- [`docs/context/intent-map.md`](../context/intent-map.md) — active, deferred, and blocked intent.
- [`docs/context/decisions.md`](../context/decisions.md) — durable outcomes and retirement tombstones.

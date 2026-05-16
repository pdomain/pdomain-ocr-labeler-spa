# Development

How to set up `pd-ocr-labeler-spa` for hacking. End users running the
published wheel don't need any of this — the wheel ships with a
pre-built frontend bundle. See the project [`README.md`](../README.md)
for the user-facing pitch and [`specs/`](../specs/) for the
authoritative design notes.

> **Status note (2026-05-07).** Backend is feature-rich (M0 scaffold +
> M1 settings/adapters/AppState/middleware/error-handler/lifespan-clean;
> M2 slice 2 wired). The frontend scaffold exists but has never been
> `npm install`-ed or `npm run build`-ed — the SPA bundle is not yet
> committed. `make build` will refuse to produce a wheel until
> `make frontend-build` populates `src/pd_ocr_labeler_spa/static/`.
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

`make help` lists every target with a one-line description. Where
this doc says "run `npm ...`" it means under mise — either with mise
auto-activation in your shell, or explicitly via `mise exec -- npm
...` from a non-activated session.

## First-time setup

```sh
mise install         # installs Node 24 + Python 3.13 per mise.toml
make setup           # uv sync + install pre-commit hooks + refresh version
make frontend-install  # npm install inside frontend/
```

`make setup` runs `uv sync`, installs the pre-commit hooks, and forces
`hatch-vcs` to re-derive the package version from the current git
state. `make frontend-install` runs `npm install` inside `frontend/`.

(For users who can't or won't install mise, `make mise-setup` is a
fallback that downloads a vendored mise binary and runs `mise
install` for you. End users running the published wheel never need
mise — the wheel ships with the SPA bundle prebuilt.)

## Running the dev server

### Backend-only (today's default)

The FastAPI side is fully wired: SPA fallback, `/healthz`, `/env.js`,
`/image-cache/{key:path}`, request-id middleware, structured logging.
Until the frontend bundle is built (next iteration), `GET /` will
return a helpful 404 explaining how to populate `static/`.

```sh
make test            # pytest — main backend feedback loop
make lint            # ruff check
uv run pd-ocr-labeler-ui --no-browser --port 8080
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/env.js
```

### Two-process dev loop (Vite + FastAPI)

Once you've run `make frontend-install`, the standard pgdp-prep-style
dev loop works:

```sh
# terminal 1 — FastAPI on :8080 with --reload
make dev

# terminal 2 — Vite dev server on :5173. The Vite-side proxy
# forwards /api, /image-cache, /env.js back to :8080 (see
# `frontend/vite.config.ts`).
make frontend-dev
```

Open `http://localhost:5173` in a browser. The FastAPI side will
still 404 on `/` until you `make frontend-build` to populate
`static/`, but Vite at :5173 serves the SPA shell directly during
development.

## Tests

```sh
make test            # pytest (unit + integration; excludes e2e/)
make frontend-test   # vitest (jsdom)
make e2e             # Playwright — requires `playwright install chromium`
```

Both `make test` and `make frontend-test` are part of `make ci`.

## Lint / format

```sh
make lint            # ruff check
make format          # ruff format (writes)
make pre-commit-check  # all pre-commit hooks on every tracked file
```

Pre-commit runs automatically on `git commit` once `make setup` has
installed the hooks.

## Building a wheel

```sh
make frontend-build  # writes the SPA bundle into src/pd_ocr_labeler_spa/static/
make build           # produces the wheel; refuses without a populated static/
```

The build refusal is enforced by [`build_hooks/spa_check.py`](../build_hooks/spa_check.py)
— intentional, so a forgotten `make frontend-build` can't ship a blank
page.

## Regenerating typed API client

After changing FastAPI request/response models:

```sh
make openapi-export  # exports /openapi.json then regenerates frontend/src/api/types.ts
```

This keeps the TypeScript surface in lock-step with the Python models.

## CI

```sh
make ci   # setup + test + frontend-test + build
```

Mirrors the `.github/workflows/release.yml` pipeline.

## Archive on close

`docs/BUGS_FOUND.md` and `OPEN_QUESTIONS.md` track *currently-open* findings
and questions only. When you close one, **move its full entry to the matching
archive file in the same commit that lands the close** — don't leave it in
the active list with a `(closed)` tag. Active docs are for in-flight work;
[`docs/archive/`](archive/) is the historical record.

The recipe:

1. Land the fix (or the resolution ADR).
2. In the same commit that closes the entry, edit the active doc:
   - For a bug: cut the full `## B-NN — …` block from `docs/BUGS_FOUND.md`
     and paste it (verbatim, plus the closing-commit hash and iter number on
     the **Status** line) into `docs/archive/BUGS_RESOLVED.md`, preserving
     numeric `B-NN` order.
   - For a question: cut the full `## Q-NN — …` block (or the
     Resolved-pending entry) from `OPEN_QUESTIONS.md` and paste it into
     `docs/archive/QUESTIONS_RESOLVED.md`, plus add a row to the
     Resolution-log table at the bottom.
3. Keep the active doc's pointer to the archive — don't strip it; new
   contributors find the historical record through that link.

Why: every prior code-review checkpoint left closed entries accumulating in
the active doc; by iter 50 `BUGS_FOUND.md` had ~70 closed entries and ~2
open ones, so finding the current backlog meant scrolling past 2,300 lines
of resolved work. The same was happening to `OPEN_QUESTIONS.md`. The
"archive on close" rule keeps both docs short and discoverable.

## Useful references

- [`docs/architecture/00-overview.md`](architecture/00-overview.md) — goals, non-goals,
  tech stack, milestone contract.
- [`specs/16-milestones.md`](../specs/16-milestones.md) — milestone
  acceptance gates.
- [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) — deferred decisions.
- [`specs/16-milestones.md`](../specs/16-milestones.md) — implementation status by
  milestone.
- [`docs/BUGS_FOUND.md`](BUGS_FOUND.md) — open code-review findings;
  closed entries archived in
  [`docs/archive/BUGS_RESOLVED.md`](archive/BUGS_RESOLVED.md).
- [`docs/archive/`](archive/) — closed bugs + resolved questions.

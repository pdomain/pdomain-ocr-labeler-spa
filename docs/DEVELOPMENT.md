# Development

How to set up `pd-ocr-labeler-spa` for hacking. End users running the
published wheel don't need any of this — the wheel ships with a
pre-built frontend bundle. See the project [`README.md`](../README.md)
for the user-facing pitch and [`specs/`](../specs/) for the
authoritative design notes.

> **Status note.** As of M0 this repo has a backend skeleton (FastAPI
> `/healthz` + `/env.js`) and a frontend scaffold (Vite + React + TS),
> but the SPA bundle isn't wired into the wheel yet. `make build` will
> refuse to produce a wheel until `make frontend-build` populates
> `src/pd_ocr_labeler_spa/static/`. See [`ROADMAP.md`](ROADMAP.md) for
> what's in flight.

## Prerequisites

- **Python 3.13** — pinned in [`mise.toml`](../mise.toml).
- **Node 24** — also pinned in `mise.toml`.
- **`uv`** — Astral's Python package manager. The shared devcontainer
  has it pre-installed at `/usr/local/bin/uv`. Outside the
  devcontainer: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
  Note that `mise` is intentionally **not** used to manage `uv` (see
  the `mise.toml` comment for why).
- **`mise`** *(optional)* — if you want pinned-version isolation
  matching CI exactly. Run `make mise-setup` to download mise and
  install Node 24 + Python 3.13. Skip this if Node 24 and Python 3.13
  are already on your `PATH`.

`make help` lists every target with a one-line description.

## First-time setup

```sh
make mise-setup     # optional: download mise + install pinned Node/Python
make setup          # uv sync + install pre-commit hooks + refresh version
make frontend-install
```

`make setup` runs `uv sync`, installs the pre-commit hooks, and forces
`hatch-vcs` to re-derive the package version from the current git
state. `make frontend-install` runs `npm install` inside `frontend/`.

## Running the dev server

### What you'll see in M0

M0 ships only the FastAPI skeleton. There is no SPA route on the
backend yet — `GET /` returns 404. The only working endpoints are
`GET /healthz` and (in `mode != "api_only"`) `GET /env.js`. The
`--frontend-dev` CLI flag stores a URL on `settings.frontend_dev_url`
but no consumer reads it yet — backend-side proxying of unknown asset
paths to Vite is M1 work.

The Vite dev server (`make frontend-dev`) is itself blocked on
[Q-A8](../OPEN_QUESTIONS.md) until Node lands in the devcontainer,
so for now the practical M0 dev loop is pytest plus curl:

```sh
make test            # pytest — the main M0 feedback loop
make lint            # ruff check
uv run pd-ocr-labeler-ui --no-browser --port 8080
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/env.js
```

### What's coming in M1+

The intended two-process loop, once M1 wires the SPA mount + the
backend-side passthrough that `--frontend-dev` configures:

```sh
# terminal 1 — FastAPI on :8080 with --reload; in M1+ this will proxy
# unknown asset paths to the Vite dev server at $frontend_dev_url
make dev

# terminal 2 — Vite dev server on :5173. The Vite-side proxy already
# forwards /api, /image-cache, /env.js back to :8080 (see
# `frontend/vite.config.ts`) so this half is already correct.
make frontend-dev
```

In M1 you'll open `http://localhost:5173` in a browser. Until then,
the FastAPI side has no `/` route and the Vite side has no real SPA
to serve, so neither URL is interesting on its own.

For backend-only or headless work today (M0):

```sh
uv run pd-ocr-labeler-ui --no-browser --port 8080
```

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

Mirrors the `.github/workflows/release.yml` pipeline (forthcoming —
tracked in [`ROADMAP.md`](ROADMAP.md)).

## Useful references

- [`specs/00-overview.md`](../specs/00-overview.md) — goals, non-goals,
  tech stack, milestone contract.
- [`specs/16-milestones.md`](../specs/16-milestones.md) — milestone
  acceptance gates.
- [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) — deferred decisions.
- [`docs/ROADMAP.md`](ROADMAP.md) — implementation status by
  milestone.
- [`docs/BUGS_FOUND.md`](BUGS_FOUND.md) — code-review checkpoint
  findings.

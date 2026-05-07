# pd-ocr-labeler-spa

A FastAPI + React/Vite/TypeScript replacement for the NiceGUI-based
[`pd-ocr-labeler`](../pd-ocr-labeler/). Functionally identical to the
current labeler, structurally modelled on
[`pd-prep-for-pgdp`](../pd-prep-for-pgdp/).

> **Status (2026-05-07):** M0 scaffold + M1 backend (settings,
> adapters, AppState, middleware, error handler, lifespan-clean,
> CLI flags) shipped; M2 startup-discovery at slice 2/4
> (`resolve_initial_project` + `ActiveProjectCarrier` wired,
> lifespan hook + `POST /api/projects/load` still pending).
> Frontend scaffold exists but the SPA bundle has not been built or
> runtime-verified end-to-end. Implementation is milestone-driven and
> AI-implementable — see
> [`docs/ROADMAP.md`](docs/ROADMAP.md),
> [`docs/PARITY_STATUS.md`](docs/PARITY_STATUS.md),
> [`specs/16-milestones.md`](specs/16-milestones.md), and
> [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

## Why

The NiceGUI labeler works, but it has accreted complexity that gets in
the way:

- **Single-process server-rendered Quasar over websockets.** Big-text
  editors and word-match rebuilds are slow because every diff round-trips.
- **No REST surface.** The only contract is DOM `data-testid`s + URL
  shape, so non-browser clients (e.g. `pd-ocr-labeler-driver`) have to
  drive the UI through Playwright.
- **Per-tab Python session state.** Multi-tab isolation works but is
  expensive; every disconnect needs careful teardown.
- **Inconsistent notification, modal, and styling primitives.** Three
  notification paths, hand-rolled overlays, no toast library.

A React SPA with a typed FastAPI backend gives:

- **A contract-first REST + SSE surface** that the driver agent (and
  any future tooling) can use without a browser.
- **Typed wire shapes** generated from FastAPI `openapi.json` →
  `frontend/src/api/types.ts`, with a CI drift check.
- **Snappier editing** — local React state for big-text editors, Konva
  for image overlays, `react-query` for server-state caching.
- **Single-wheel distribution** that ships the built SPA inside the
  Python wheel (the `pgdp-prep` pattern), so end users still install
  with `uv tool install`.

## What changes for end users

Almost nothing. The same `pd-ocr-labeler-ui` console script keeps
working; the page tree under `/`, `/project/{id}`, and
`/project/{id}/page/{n}` remains stable; every `data-testid` carries
over (see [`specs/13-driver-contract.md`](specs/13-driver-contract.md)).
Saved-project files (`<project>_NNN.json`) are read and written in the
same `pd_ocr_labeler.user_page` v2.1 envelope (see
[`specs/01-data-models.md`](specs/01-data-models.md)).

## Repository layout (planned)

```
pd-ocr-labeler-spa/
├── pyproject.toml                 # hatchling + uv, console scripts
├── Makefile                       # setup / test / frontend-build / build
├── mise.toml                      # pinned Node 24 / Python 3.13
├── Dockerfile                     # two-stage: Node build → Python wheel
├── install.sh / install.ps1       # GitHub-Release wheel installer
├── build_hooks/spa_check.py       # refuse wheel without built SPA
├── specs/                         # design specs (this repo's source of truth)
├── docs/                          # architecture writeup, diagrams
├── src/pd_ocr_labeler_spa/
│   ├── __main__.py                # console-script entry point
│   ├── bootstrap.py               # build_app(settings)
│   ├── settings.py                # PDLABELER_* env (pydantic-settings)
│   ├── api/                       # FastAPI routers
│   ├── adapters/                  # storage / auth / ocr backends
│   ├── core/                      # domain models, services, persistence
│   └── static/                    # populated by `make frontend-build`
├── frontend/
│   ├── package.json
│   ├── vite.config.ts             # proxy /api + /image-cache → backend
│   ├── tsconfig.app.json
│   ├── tailwind.config.ts
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/{client,types}.ts
│       ├── pages/                 # one per route
│       ├── components/            # PageImageCanvas, WordMatchView, etc.
│       ├── features/              # feature-folders for clusters of state
│       ├── hooks/
│       └── lib/
└── tests/
    ├── conftest.py                # TestClient(build_app(settings))
    ├── unit/                      # backend unit tests
    ├── integration/               # backend integration tests
    └── e2e/                       # Playwright (browser regression)
```

## Spec index

| Spec | Topic |
|---|---|
| [`00-overview.md`](specs/00-overview.md) | Goals, non-goals, tech stack, milestone contract |
| [`01-data-models.md`](specs/01-data-models.md) | Pydantic + on-disk schemas |
| [`02-backend.md`](specs/02-backend.md) | FastAPI router map, endpoint contract |
| [`03-frontend.md`](specs/03-frontend.md) | React shell, routing, state, generated client |
| [`04-image-viewport.md`](specs/04-image-viewport.md) | Konva canvas, overlays, drag modes |
| [`05-word-matches.md`](specs/05-word-matches.md) | Right-pane line cards + per-word editing |
| [`06-toolbar-actions.md`](specs/06-toolbar-actions.md) | Scope-action grid, style/component apply, add-word |
| [`07-word-edit-dialog.md`](specs/07-word-edit-dialog.md) | Preview, nudge, crop, refine, erase |
| [`08-page-actions.md`](specs/08-page-actions.md) | Reload OCR / Save / Load / Rematch GT |
| [`09-persistence.md`](specs/09-persistence.md) | UserPageEnvelope, image cache, session state |
| [`10-export.md`](specs/10-export.md) | DocTR export dialog + endpoint |
| [`11-notifications.md`](specs/11-notifications.md) | Toast queue, busy overlays, SSE jobs |
| [`12-hotkeys-a11y.md`](specs/12-hotkeys-a11y.md) | Keybinding catalogue + a11y rules |
| [`13-driver-contract.md`](specs/13-driver-contract.md) | data-testid + URL invariants for `pd-ocr-labeler-driver` |
| [`14-testing.md`](specs/14-testing.md) | pytest + Vitest + Playwright strategy |
| [`15-deployment-dev.md`](specs/15-deployment-dev.md) | Build, devcontainer, install |
| [`16-milestones.md`](specs/16-milestones.md) | M0…M9 milestone breakdown |
| [`17-decisions.md`](specs/17-decisions.md) | ADRs / open decisions log |

## Where to start

1. Read [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) — these are decisions
   the spec authors deferred to the human. Resolve before starting M1.
2. Read [`specs/00-overview.md`](specs/00-overview.md) for the
   overall shape.
3. For implementation: pick the next milestone in
   [`specs/16-milestones.md`](specs/16-milestones.md). Each milestone
   names: files to create/touch, acceptance tests to satisfy, and the
   specs that govern it.

---
kind: process
status: active
owner: maintainers
created: 2026-05-06
last_verified: 2026-07-13
---

# pdomain-ocr-labeler-spa

Repository guidance is in [`AGENTS.md`](AGENTS.md); release history is in
[`CHANGELOG.md`](CHANGELOG.md); documentation starts at
[`docs/README.md`](docs/README.md).

A FastAPI + React/Vite/TypeScript replacement for the NiceGUI-based
`pd-ocr-labeler` legacy sibling repository. Functionally identical to the
current labeler, structurally modelled on
the `pdomain-prep-for-pgdp` sibling repository.

> **Status (2026-05-21):** Cut-over complete. Hi-fi P1–P5 shipped;
> smoke run triaged; legacy `pd-ocr-labeler` superseded. The retired cut-over
> checklist remains in Git history. Known issues are tracked in
> [`docs/context/open-findings.md`](docs/context/open-findings.md).

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

Almost nothing. The same `pdomain-ocr-labeler-ui` console script keeps
working; the page tree under `/`, `/project/{id}`, and
`/project/{id}/page/{n}` remains stable; every `data-testid` carries
over (see [`docs/architecture/13-driver-contract.md`](docs/architecture/13-driver-contract.md)).
Saved-project files (`<project>_NNN.json`) are read and written in the
same `pd_ocr_labeler.user_page` v2.1 envelope (see
[`docs/architecture/01-data-models.md`](docs/architecture/01-data-models.md)).

## Repository layout (planned)

```
pdomain-ocr-labeler-spa/
├── pyproject.toml                 # hatchling + uv, console scripts
├── Makefile                       # setup / test / frontend-build / build
├── mise.toml                      # pinned Node 24 / Python 3.13
├── Dockerfile                     # two-stage: Node build → Python wheel
├── install.sh / install.ps1       # GitHub-Release wheel installer
├── build_hooks/spa_check.py       # refuse wheel without built SPA
├── specs/                         # design specs (this repo's source of truth)
├── docs/                          # architecture writeup, diagrams
├── src/pdomain_ocr_labeler_spa/
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

Specs are split into two trees as of 2026-05-14:

- **`specs/`** — active design docs (living roadmap, ADR log, unimplemented work).
- **`docs/architecture/`** — specs that describe **implemented** functionality.

### Active specs (`specs/`)

| Spec | Topic |
|---|---|
| [`16-milestones.md`](specs/16-milestones.md) | M0…M9 milestone breakdown (living) |
| [`17-decisions.md`](specs/17-decisions.md) | ADRs / decisions log (append-only) |
| [`20-glyph-annotations.md`](specs/20-glyph-annotations.md) | Glyph-level annotations (not yet implemented; blocked on `pdomain-book-tools` upstream) |

### Architecture (implemented — `docs/architecture/`)

| Spec | Topic |
|---|---|
| [`00-overview.md`](docs/architecture/00-overview.md) | Goals, non-goals, tech stack, milestone contract |
| [`01-data-models.md`](docs/architecture/01-data-models.md) | Pydantic + on-disk schemas |
| [`02-backend.md`](docs/architecture/02-backend.md) | FastAPI router map, endpoint contract |
| [`03-frontend.md`](docs/architecture/03-frontend.md) | React shell, routing, state, generated client |
| [`04-image-viewport.md`](docs/architecture/04-image-viewport.md) | Konva canvas, overlays, drag modes |
| [`05-word-matches.md`](docs/architecture/05-word-matches.md) | Right-pane line cards + per-word editing |
| [`06-toolbar-actions.md`](docs/architecture/06-toolbar-actions.md) | Scope-action grid, style/component apply, add-word |
| [`26-right-panel-detail.md`](docs/architecture/26-right-panel-detail.md) | Persistent word/line detail editing |
| [`08-page-actions.md`](docs/architecture/08-page-actions.md) | Reload OCR / Save / Load / Rematch GT |
| [`09-persistence.md`](docs/architecture/09-persistence.md) | UserPageEnvelope, image cache, session state |
| [`10-export.md`](docs/architecture/10-export.md) | DocTR export dialog + endpoint |
| [`11-notifications.md`](docs/architecture/11-notifications.md) | Toast queue, busy overlays, SSE jobs |
| [`12-hotkeys-a11y.md`](docs/architecture/12-hotkeys-a11y.md) | Keybinding catalogue + a11y rules |
| [`13-driver-contract.md`](docs/architecture/13-driver-contract.md) | data-testid + URL invariants for `pd-ocr-labeler-driver` |
| [`14-testing.md`](docs/architecture/14-testing.md) | pytest + Vitest + Playwright strategy |
| [`15-deployment-dev.md`](docs/architecture/15-deployment-dev.md) | Build, devcontainer, install |
| [`18-text-normalization.md`](docs/architecture/18-text-normalization.md) | Long-S / ligature normalization |
| [`19-auto-rotation.md`](docs/architecture/19-auto-rotation.md) | Manual + auto page rotation |
| [`21-konva-renderer.md`](docs/architecture/21-konva-renderer.md) | Konva renderer for `PageImageCanvas` + `BBoxOverlay` |
| [`22-page-surface-wireup.md`](docs/architecture/22-page-surface-wireup.md) | `ProjectPage` real labeling surface assembly |
| [`23-page-payload-backend.md`](docs/architecture/23-page-payload-backend.md) | Real backend page payload + 19 mutation endpoints |
| [`24-shell-layout.md`](docs/architecture/24-shell-layout.md) | Studio shell — Rail, Drawer, Breadcrumb, QuickSearch |
| [`25-drawer-worklist.md`](docs/architecture/25-drawer-worklist.md) | Drawer — Worklist, Hierarchy, BulkActions |
| [`26-right-panel-detail.md`](docs/architecture/26-right-panel-detail.md) | Right-panel detail views — Word / Line / Block |
| [`27-right-panel-sections.md`](docs/architecture/27-right-panel-sections.md) | Right-panel action sections — BBox / Rebox / Erase / CharRanges / CharFixer / Structure |
| [`28-palettes-pickers.md`](docs/architecture/28-palettes-pickers.md) | StylePalette, ComponentPalette, UnicodePicker, useLayerColors |

## Quick start (just run the labeler)

```bash
make setup     # one-time: sync deps + install pre-commit hooks
make run       # builds the SPA if missing, then serves via FastAPI
```

`make run` is the single-command "I just want to use it" target — it
builds the SPA bundle into `src/pdomain_ocr_labeler_spa/static/` if it
doesn't exist yet, then launches `pdomain-ocr-labeler-ui` (no `--reload`,
no Vite). At startup the server prints a one-line `device: …` banner
(e.g. `device: cuda:0 (NVIDIA …)` or `device: cpu`) so you can confirm
whether torch picked up the local GPU before kicking off OCR. The
default URL is <http://127.0.0.1:8080> and a browser tab opens
automatically once the listener is up.

To force a fresh frontend bundle, run `make frontend-build` before
`make run`. For frontend hacking (Vite HMR on :5173) use `make dev`
instead.

## Where to start

1. Read [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) — these are decisions
   the spec authors deferred to the human. Resolve before starting M1.
2. Read [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md) for the
   overall shape.
3. For implementation: pick the next milestone in
   [`specs/16-milestones.md`](specs/16-milestones.md). Each milestone
   names: files to create/touch, acceptance tests to satisfy, and the
   specs that govern it.

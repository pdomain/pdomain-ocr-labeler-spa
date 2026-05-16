# 00 — Overview

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#4

`pd-ocr-labeler-spa` reimplements the existing
`pd-ocr-labeler` (NiceGUI, server-rendered Quasar UI) as a
**FastAPI + React/Vite/TypeScript SPA**, structurally modelled on
`pd-prep-for-pgdp`.

This document is the entry point for every other spec. Read it once,
then jump to the per-area spec for whatever you're implementing.

---

## Goals

1. **Functional parity** with the current labeler. Every interactive
   capability (project load, page nav, OCR, GT alignment, word
   editing, bbox edit, refine, validation, export) must work end-to-
   end, on the same on-disk artefacts.
2. **Stable contract** for the `pd-ocr-labeler-driver` Playwright agent.
   `data-testid`s, URL shape, notification semantics carry over
   ([`13-driver-contract.md`](13-driver-contract.md)).
3. **Typed REST + SSE surface.** Every UI action has a documented
   FastAPI endpoint; the SPA consumes it via a generated TS client.
   ([`02-backend.md`](02-backend.md))
4. **Single-wheel distribution.** End users still install with
   `uv tool install pd-ocr-labeler-spa` and get a single binary that
   serves both API and SPA. ([`15-deployment-dev.md`](15-deployment-dev.md))
5. **Milestone-implementable by AI agents.** Each milestone in
   [`16-milestones.md`](../../specs/16-milestones.md) is bounded enough that a
   single coding agent can pick it up, deliver it, and verify against
   the acceptance tests in this spec set.

## Non-goals

> **Scope freeze (2026-05-07).** Per user directive, the network /
> multi-user / managed-adapter axes below are **deferred to the far
> future**. Active milestones (M1–M9) are local-mode only. See
> [D-042](../../specs/17-decisions.md#d-042--postgresmanaged-adapter-axes-deferred-to-far-future-2026-05-07)
> for the explicit list and rationale.

- **No multi-user collaboration.** One user, possibly multiple browser
  tabs against the same backend, sharing in-memory state.
  ([D-023](../../specs/17-decisions.md), [D-042](../../specs/17-decisions.md))
- **No database / Postgres / SQLAlchemy.** Persistence is filesystem-
  only via atomic-rename JSON sidecars + `config.yaml`. No
  `database/` adapter axis, no migrations, no ORM. The schema seam is
  "ready if we ever add one" but adding one is far-future work.
  ([D-042](../../specs/17-decisions.md))
- **No public API contract.** The REST surface is intentionally
  unstable across SPA versions. Internal use only — the SPA frontend
  and the driver agent are the only known consumers.
- **No NiceGUI / Quasar.** Drop the entire NiceGUI stack. UI = React,
  styling = Tailwind + shadcn/ui ([D-004](../../specs/17-decisions.md)).
- **No DocTR replacement in v1.** OCR continues through `pd-book-tools` →
  DocTR via `local_doctr`. The full `IOCREngine` adapter axis
  (`local_doctr | modal | shared_container`) is wired in v1 with the
  latter two as `NotImplementedYet` stubs ([D-018](../../specs/17-decisions.md)).
- **No new persistence schema.** `UserPageEnvelope` schema
  `pd_ocr_labeler.user_page` v2.1 is preserved byte-for-byte
  ([`09-persistence.md`](09-persistence.md)).
- **No new image formats / coordinate systems.** Bbox geometry,
  refine algorithms, coordinate transforms are delegated unchanged to
  `pd-book-tools` ([D-026](../../specs/17-decisions.md); refactor delegated).

## Tech stack

### Backend

| Layer | Choice | Why |
|---|---|---|
| Web framework | **FastAPI** | Same as pgdp-prep. Native async, OpenAPI export, Pydantic v2. |
| Server | **uvicorn[standard]** | Same as pgdp-prep. |
| Persistence | **Filesystem only** | Single-user; no DB needed for v1. Schema seam ready if we ever add one. |
| Storage adapter | **`IStorage` Protocol** with `filesystem` impl + `s3` `NotImplementedYet` stub | Image cache served via the adapter, not raw StaticFiles. ([D-019](../../specs/17-decisions.md)) |
| Auth | **`IAuth` Protocol**, `none` impl only | Seam in place; no JWT for v1. ([D-005](../../specs/17-decisions.md)) |
| OCR | `IOCREngine` Protocol + `local_doctr` impl + `modal` / `shared_container` `NotImplementedYet` stubs | Wraps `pd_book_tools.ocr.document.Document.from_image_ocr_via_doctr`. ([D-018](../../specs/17-decisions.md)) |
| Long jobs | **In-process job runner**, SSE for progress | Mirrors pgdp-prep `core/job_runner.py` minus DB persistence (in-memory dict is enough since we have no batch path). ([D-006](../../specs/17-decisions.md)) |
| Logging | stdlib JSON + `RequestIdMiddleware` | Verbatim port from pgdp-prep. |

### Frontend

| Layer | Choice | Why |
|---|---|---|
| Build | **Vite** | Same as pgdp-prep. |
| Framework | **React 19** | Same as pgdp-prep. |
| Lang | **TypeScript** strict | Same as pgdp-prep `tsconfig.app.json`. |
| Routing | **`react-router-dom` v7** | Same as pgdp-prep. |
| Server state | **`@tanstack/react-query` v5** | Same as pgdp-prep. |
| Local state | `useState` + `useReducer`; **`zustand`** for cross-page UI prefs (filter toggle, layer visibility, panel split). | pgdp-prep declares zustand but doesn't use it; we will. |
| Styling | **Tailwind 3.4** + **shadcn/ui** primitives (`@radix-ui` under the hood) | Closes the "spec mentions shadcn but code doesn't use it" gap from pgdp-prep. ([D-004](../../specs/17-decisions.md)) |
| Forms | None — controlled inputs + `useMutation` | Match pgdp-prep. Validate via Pydantic on the server, surface `details` array per-field via the toast system. |
| Toasts | **`sonner`** | One-liner; pgdp-prep ships nothing for this. Closes the gap. |
| Hotkeys | **`react-hotkeys-hook`** | Closes the legacy gap; see [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md). ([D-009](../../specs/17-decisions.md), [D-022](../../specs/17-decisions.md)) |
| Image canvas | **raw `<canvas>` (default)** with research spike at M4 to confirm | Konva is the alternate option; final choice deferred per [D-020](../../specs/17-decisions.md). |
| Plain editors | **`<textarea readOnly>`** + monospace CSS | Drop CodeMirror; not earning its weight. ([D-008](../../specs/17-decisions.md)) |
| Virtualisation | **`@tanstack/react-virtual`** | For the line-card list on heavy pages. (Q7 → resolved as part of frontend stack) |
| Testing (unit) | **Vitest** + **@testing-library/react** | Same as pgdp-prep. |
| HTTP mocking | **msw** | Same as pgdp-prep. |
| E2E | **Playwright** (Chromium) | Same as pgdp-prep / legacy labeler. |

### Tooling

| Tool | Notes |
|---|---|
| Python build | `hatchling` + `hatch-vcs` (pgdp-prep). |
| Wheel-with-SPA | `force-include = src/pd_ocr_labeler_spa/static` + `build_hooks/spa_check.py`. |
| Lockfile | `uv.lock`. |
| Lint | `ruff` (Python) + `eslint` flat config (TS) — pgdp-prep is missing the eslint config; we add one. |
| Format | `ruff format` + `prettier`. |
| Type-check | TypeScript `strict`; **`pyright`** added (closes pgdp-prep's gap). |
| Pre-commit | Same hooks as pgdp-prep + ESLint. |
| CI | Single `release.yml` mirroring pgdp-prep: lint → test → frontend-build → wheel-build (with SPA assertion) → on tag, attach wheel to GitHub Release. |
| Versions | `mise.toml` pinning Node 24 + Python 3.13. |

---

## Architectural shape

```
┌──────────────────────────────────────────────────────┐
│  Browser (SPA)                                       │
│  ┌───────────────┐ ┌───────────────┐ ┌────────────┐  │
│  │ Page viewport │ │ Word matches  │ │ Toolbar +  │  │
│  │  (Konva)      │ │  (virtualised)│ │  dialogs   │  │
│  └───────────────┘ └───────────────┘ └────────────┘  │
│         │                  │                  │      │
│         └──────── react-query (server state) ─┘      │
│                          │                           │
└──────────────────────────┼───────────────────────────┘
                           │ HTTP/JSON + SSE
┌──────────────────────────┼───────────────────────────┐
│  FastAPI (single process)                            │
│  ┌──────────────────────┐  ┌────────────────────────┐│
│  │  /api/projects/*     │  │  /api/jobs/*           ││
│  │  /api/pages/*        │  │  /api/page/{idx}/...   ││
│  │  /api/words/*        │  │  /api/export/*         ││
│  └──────────────────────┘  └────────────────────────┘│
│                          │                           │
│  ┌────────── core (in-memory) ───────────────────┐   │
│  │  AppState ─ ProjectState ─ PageState[]        │   │
│  └───────────────────────────────────────────────┘   │
│                          │                           │
│  ┌─────── adapters ────────────────────────────┐     │
│  │  IStorage(filesystem)  IAuth(none)          │     │
│  │  IOCREngine(local-doctr)                    │     │
│  └─────────────────────────────────────────────┘     │
│                          │                           │
└──────────────────────────┼───────────────────────────┘
                           │ Python imports
                  ┌────────▼─────────┐
                  │  pd-book-tools   │
                  │  (Page, Block,   │
                  │   Word, BBox,    │
                  │   PGDPResults,   │
                  │   DocTR support) │
                  └──────────────────┘
```

### Key design rules

1. **`build_app(settings)` factory.** Same as pgdp-prep
   `bootstrap.py:144-268`. Every test wires its own `Settings`
   explicitly. The `__main__` script reads env vars itself.
2. **In-memory state on `app.state`.** `AppState` lives there; routers
   pull it via `Depends(get_app_state)`. No global singleton.
3. **One state mutation per HTTP request.** Bulk operations land as
   single endpoints (e.g.
   `POST /api/page/{idx0}/words/validate-batch`) so the SPA can do one
   round-trip + one optimistic update. Mirrors the legacy
   `set_words_validated` pattern (single batched call → single
   autosave).
4. **Autosave is server-side.** The SPA calls a single mutation endpoint
   per user action; the server writes through to disk + image cache.
   No client-side autosave timer.
5. **OpenAPI is source of truth.** `make openapi-export` regenerates
   `frontend/src/api/types.ts`. CI gate: `git diff --exit-code` after
   re-running. Closes the pgdp-prep drift-check gap.
6. **`IStorage` keys are project-scoped.** Same sandboxing primitive as
   pgdp-prep `api/data/assets.py:45`.
7. **No backwards-compat shims.** New repo. We only need to read +
   write the legacy `UserPageEnvelope` v2.1; we don't preserve any
   transient v1 envelopes (they all auto-upgrade on save).
8. **Driver-facing surface is part of the contract.** Every
   `data-testid` and URL shape lives in
   [`13-driver-contract.md`](13-driver-contract.md) and has a
   conformance test.

---

## State model

The legacy labeler has three nested state objects:

- `AppState` (per-tab today; will become **per-process** in the SPA)
  — knows projects-root, selected project, OCR config, notifications.
- `ProjectState` (per project) — knows the loaded `Project`, the
  current page index, the per-page-index `PageState` map, the GT map.
- `PageState` (per page) — knows the `pd_book_tools.ocr.page.Page`
  object, dirty flags, line/word selection sets, the in-memory image,
  per-line / per-word event hooks.

Per-tab isolation in the SPA is moved to the **frontend**:

- Backend keeps a single `AppState` with one `ProjectState` per
  project the user has opened in this server lifetime.
- Frontend keeps per-tab UI state (selection, filter toggle, layer
  visibility, splitter position, current page index) in either local
  state or zustand. Two tabs on the same page share document state
  (same `PageState` on the server) but each has independent UI.

`PageState` mutations on the server fan out via SSE so other tabs
viewing the same project converge eventually. ([D-023](../../specs/17-decisions.md))

---

## Dataflow per user action

The shape `(user action) → (HTTP/SSE) → (server logic) → (client refetch)`
applies uniformly. Examples:

### Click "Validate" on a single word

- SPA optimistically toggles `is_validated` in the cached query result.
- `POST /api/projects/{id}/pages/{idx0}/words/{line_idx}/{word_idx}/validate`
  with `{validated: true}`.
- Server: `PageState.toggle_word_validated` → autosave to image cache.
- Server returns the updated `WordMatch` for that word.
- SPA reconciles cache; if the optimistic update was wrong, the server
  response wins.

### Click "Refine all bboxes on this page"

- SPA calls `POST /api/projects/{id}/pages/{idx0}/refine-bboxes`.
- Long-running (>500ms typical). Server returns `202 Accepted` with a
  `job_id`.
- SPA opens `EventSource(/api/jobs/{job_id}/events)` for progress.
- Server's `JobRunner` runs `PageState.refine_all_bboxes`, emits
  `progress(current, total, message)` events, terminal `complete` event.
- On terminal: SPA invalidates the page-state query for this page;
  refetch hydrates the new bboxes.

### Reload OCR (Edited image)

- Same shape as Refine, with `use_edited_image=true` payload.
- Server: `PageState.reload_page_with_ocr(use_edited_image=True)`.
- Different from "refine" only in handler; same job-runner shape.

---

## Milestone contract for AI agents

Every milestone in [`16-milestones.md`](../../specs/16-milestones.md) follows this
format:

```
## Mn — short title

**Outcome.** One paragraph describing what works at end of milestone.

**Files to create / modify.**
- src/pd_ocr_labeler_spa/api/...
- frontend/src/pages/...
- tests/...

**Specs that govern this milestone.**
- specs/0X-foo.md  (the must-read parts)

**Acceptance tests.**
- pytest: tests/unit/test_foo.py::test_bar
- vitest: frontend/src/.../foo.test.tsx
- playwright: tests/e2e/test_milestone_n.py

**Rollback.** Anything that's not isolated to the listed files.

**Pre-conditions.** What earlier milestones must already exist.
```

The spec author's bet is that an AI agent given just (a) the listed
spec files, (b) the listed acceptance tests, and (c) the previous
milestone's working state can deliver the milestone in a single coding
session. If a milestone is too big, split it.

---

## Running spec list (must read before coding)

| If you're touching… | Required reading |
|---|---|
| Anything | `00-overview.md`, `OPEN_QUESTIONS.md` |
| Backend route | `01-data-models.md`, `02-backend.md` |
| New page in SPA | `03-frontend.md`, `13-driver-contract.md` |
| Page viewport / overlays | `04-image-viewport.md`, `12-hotkeys-a11y.md` |
| Word matches view | `05-word-matches.md`, `01-data-models.md` |
| Toolbar | `06-toolbar-actions.md`, `13-driver-contract.md` |
| Word edit dialog | `07-word-edit-dialog.md` |
| Save / load / OCR | `08-page-actions.md`, `09-persistence.md` |
| Disk format | `09-persistence.md` |
| DocTR export | `10-export.md` |
| Notifications | `11-notifications.md` |
| Hotkeys / a11y | `12-hotkeys-a11y.md` |
| Driver-agent compat | `13-driver-contract.md` |
| Tests | `14-testing.md` |
| Build / install | `15-deployment-dev.md` |
| Roadmap | `../../specs/16-milestones.md` |
| ADR log | `../../specs/17-decisions.md` |
| Text normalization | `18-text-normalization.md` |
| Auto-rotation (M9.1/M9.2) | `19-auto-rotation.md` |
| Glyph annotations (M11) | `../../specs/20-glyph-annotations.md` |
| Konva renderer impl | `../../specs/21-konva-renderer.md` |
| Page surface wire-up | `../../specs/22-page-surface-wireup.md` |
| Page payload backend impl | `../../specs/23-page-payload-backend.md` |

If a question isn't answered by the linked spec, **stop and add it to
[`OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md)** rather than guessing.

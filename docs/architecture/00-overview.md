---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-13
---

# 00 — Overview

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#4

`pdomain-ocr-labeler-spa` reimplements the existing
`pd-ocr-labeler` (NiceGUI, server-rendered Quasar UI) as a
**FastAPI + React/Vite/TypeScript SPA**, structurally modelled on
`pdomain-prep-for-pgdp`.

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
   `uv tool install pdomain-ocr-labeler-spa` and get a single binary that
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
- **Managed database adapters remain deferred.** Current local persistence uses
  SQLite events at `.pd-pages/events.db` and content-addressed blobs. This shipped
  local store does not introduce Postgres, SQLAlchemy, or a managed-adapter axis.
  ([D-042](../../specs/17-decisions.md))
- **No public API contract.** The REST surface is intentionally
  unstable across SPA versions. Internal use only — the SPA frontend
  and the driver agent are the only known consumers.
- **No NiceGUI / Quasar.** Drop the entire NiceGUI stack. UI = React,
  styling = Tailwind + shadcn/ui ([D-004](../../specs/17-decisions.md)).
- **No DocTR replacement in v1.** OCR continues through `pdomain-book-tools` →
  DocTR via `local_doctr`. The full `IOCREngine` adapter axis
  (`local_doctr | modal | shared_container`) is wired in v1 with the
  latter two as `NotImplementedYet` stubs ([D-018](../../specs/17-decisions.md)).
- **Source inputs are separate from current persistence.** Current page edits
  use the event/blob store
  ([`09-persistence.md`](09-persistence.md), [`29-page-loading-and-history.md`](29-page-loading-and-history.md)).
- **No new image formats / coordinate systems.** Bbox geometry,
  refine algorithms, coordinate transforms are delegated unchanged to
  `pdomain-book-tools` ([D-026](../../specs/17-decisions.md); refactor delegated).

## Tech stack

### Backend

| Layer | Choice | Why |
|---|---|---|
| Web framework | **FastAPI** | Same as pgdp-prep. Native async, OpenAPI export, Pydantic v2. |
| Server | **uvicorn[standard]** | Same as pgdp-prep. |
| Persistence | **Local SQLite events + content-addressed blobs** | `LabelerPageStore` owns project page persistence; jobs remain in memory. |
| Storage adapter | **`IStorage` Protocol** with `filesystem` impl + `s3` `NotImplementedYet` stub | Image cache served via the adapter, not raw StaticFiles. ([D-019](../../specs/17-decisions.md)) |
| Auth | **`IAuth` Protocol**, `none` impl only | Seam in place; no JWT for v1. ([D-005](../../specs/17-decisions.md)) |
| OCR | `IOCREngine` Protocol + `local_doctr` impl + `modal` / `shared_container` `NotImplementedYet` stubs | Wraps `pdomain_book_tools.ocr.document.Document.from_image_ocr_via_doctr`. ([D-018](../../specs/17-decisions.md)) |
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
| Styling | **Tailwind** + **shadcn/ui** primitives (`@radix-ui` under the hood) | Closes the "spec mentions shadcn but code doesn't use it" gap from pgdp-prep. ([D-004](../../specs/17-decisions.md)) |
| Forms | None — controlled inputs + `useMutation` | Match pgdp-prep. Validate via Pydantic on the server, surface `details` array per-field via the toast system. |
| Toasts | **`sonner`** | One-liner; pgdp-prep ships nothing for this. Closes the gap. |
| Hotkeys | **`react-hotkeys-hook`** | Closes the legacy gap; see [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md). ([D-009](../../specs/17-decisions.md), [D-022](../../specs/17-decisions.md)) |
| Image canvas | **Shared `PdUiPageImageCanvas` Konva host** | Labeler owns domain overlays and gestures; see [renderer ownership](21-konva-renderer.md). |
| Plain editors | **`<textarea readOnly>`** + monospace CSS | Drop CodeMirror; not earning its weight. ([D-008](../../specs/17-decisions.md)) |
| Virtualisation | **`@tanstack/react-virtual`** | For the line-card list on heavy pages. (Q7 → resolved as part of frontend stack) |
| Testing (unit) | **Vitest** + **@testing-library/react** | Same as pgdp-prep. |
| HTTP mocking | **msw** | Same as pgdp-prep. |
| E2E | **Playwright** (Chromium) | Same as pgdp-prep / legacy labeler. |

### Tooling

| Tool | Notes |
|---|---|
| Python build | `hatchling` + `hatch-vcs` (pgdp-prep). |
| Wheel-with-SPA | Global Hatch artifacts include `static/`; `build_hooks/spa_check.py` rejects a missing bundle. |
| Lockfile | `uv.lock`. |
| Lint | `ruff` (Python) + `eslint` flat config (TS) — pgdp-prep is missing the eslint config; we add one. |
| Format | `ruff format` + `prettier`. |
| Type-check | TypeScript application and test projects; configured **basedpyright** backend gate. |
| Pre-commit | Same hooks as pgdp-prep + ESLint. |
| CI | `just ci` runs local Python/frontend checks, tests, build and strict docgraph. Release scripts create GitHub assets; index publication is separate. |
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
                  │  pdomain-book-tools   │
                  │  (Page, Block,   │
                  │   Word, BBox,    │
                  │   PGDPResults,   │
                  │   DocTR support) │
                  └──────────────────┘
```

### Key design rules

1. Adapters isolate storage/auth/OCR; managed deployment axes remain deferred under D-042.
2. AppState contains frozen wiring. ActiveProjectCarrier and ProjectState carry separate mutable state.
3. Batch routes and background jobs are explicit public contracts in the generated schema.
4. Mutations persist current content/sidecars through the local event/blob store. Selection is session state.
5. OpenAPI export regenerates types; CI typechecks them. The current recipe has no standalone git-diff gate.
6. Blob/image paths and source-root selection retain their implemented sandbox/verified-image boundaries.
7. Compatibility is specific: legacy URLs have 301 redirects, while removed typography payloads are rejected.
8. The mounted driver contract belongs in architecture 13; static selector checks are not exhaustive
   feature/e2e verification.

## State model

The backend's frozen AppState wires services and settings. ActiveProjectCarrier and ProjectState hold
active project/page state separately. PageState contains hydrated OCR content, sidecars and generation/dirty
tracking; per-page locks synchronize mutations and relevant payload reads.

Each browser tab owns its selection and presentation state. Tabs can share persisted document state without
a content mutation navigating another viewer. Application events and query invalidation refresh affected
views. UI preference persistence is field-specific; the entire store is not a universal localStorage contract.

## Dataflow per user action

The common path is action → API/job → persistence where appropriate → query refresh. A word validation
request reaches the actual validated/validate-batch route, saves current content and returns page state.
Page refine uses `/refine`, queues a job and reports lifecycle through Job-plus-event SSE.
Reload OCR Edited passes use_edited_image to a job that reads persisted edited pixels.

[Backend](02-backend.md), [page mutation ownership](23-page-payload-backend.md),
[history/loading](29-page-loading-and-history.md) and [runtime flows](runtime-flows.md) own the precise paths.

## Shipped milestones

M0 through M11 shipped by the 2026-05-21 cut-over, including M9.1, M9.2, and M9.5. The acceptance write-ups remain in
[`specs/16-milestones.md`](../../specs/16-milestones.md) as history. They are not the live roadmap.

Future work is the [roadmap](../context/intent-map.md). Repository ownership is [repository boundaries](30-repository-boundaries.md).

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
| Word and line detail editing | [`26-right-panel-detail.md`](26-right-panel-detail.md) |
| Save / load / OCR | `08-page-actions.md`, `09-persistence.md` |
| Disk format | `09-persistence.md` |
| DocTR export | `10-export.md` |
| Notifications | `11-notifications.md` |
| Hotkeys / a11y | `12-hotkeys-a11y.md` |
| Driver-agent compat | `13-driver-contract.md` |
| Tests | `14-testing.md` |
| Build / install | `15-deployment-dev.md` |
| Roadmap | [`../context/intent-map.md`](../context/intent-map.md) |
| ADR log | [`../../specs/17-decisions.md`](../../specs/17-decisions.md) |
| Text normalization | `18-text-normalization.md` |
| Auto-rotation (M9.1/M9.2) | `19-auto-rotation.md` |
| Glyph annotations (M11) | [`20-glyph-annotations.md`](20-glyph-annotations.md) |
| Konva renderer impl | `21-konva-renderer.md` |
| Page composition | `24-shell-layout.md` |
| Page payload backend impl | `23-page-payload-backend.md` |
| Shell / Studio layout | `24-shell-layout.md` |
| Drawer (Worklist / Hierarchy / Bulk) | `25-drawer-worklist.md` |
| Right-panel detail views | `26-right-panel-detail.md` |
| Right-panel action sections | `27-right-panel-sections.md` |
| Palettes and pickers | `28-palettes-pickers.md` |
| Page loading and history | [`29-page-loading-and-history.md`](29-page-loading-and-history.md) |
| Repository ownership | [`30-repository-boundaries.md`](30-repository-boundaries.md) |
| Typography review | [`31-typography-review.md`](31-typography-review.md) |

If a question isn't answered by the linked spec, **stop and add it to
[`OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md)** rather than guessing.

## Current implementation evidence

- Code: `core/persistence/page_store.py::LabelerPageStore`, `bootstrap.py::build_app`,
  and `frontend/src/components/PageImageCanvas.tsx` establish local storage, app wiring, and the shared canvas host.
- Tests: `tests/integration/test_save_page_route_roundtrip.py::test_save_page_route_persists_content_for_fresh_store_reload`
  and `frontend/src/components/PageImageCanvas.test.tsx` cover durable writes and the canvas skeleton.
- Build and gates: `pyproject.toml`, `build_hooks/spa_check.py`, and `justfile`.
- Verified: 2026-11-13 by source and test inspection during the architecture migration.

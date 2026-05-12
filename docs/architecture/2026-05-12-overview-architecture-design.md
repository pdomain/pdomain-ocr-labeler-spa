# pd-ocr-labeler-spa: SPA Architecture Overview

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#4

## TL;DR

Replace the NiceGUI `pd-ocr-labeler` with a FastAPI + React/Vite/TypeScript SPA that ships
as a single Python wheel (`pd-ocr-labeler-ui`). Preserve `UserPageEnvelope` v2.1 on-disk
compatibility with the legacy labeler. Deliver milestone-by-milestone (M0–M9) in a form
where each milestone is implementable by a single AI coding agent. Local-mode only for all
active milestones; multi-user/cloud adapters are deferred stubs.

## Context

The existing `pd-ocr-labeler` is built on NiceGUI (server-rendered Quasar UI). It works but
has three limitations that motivate a rewrite:

1. **No stable REST API.** The driver agent (`pd-ocr-labeler-driver`) must scrape UI state
   through Playwright. A typed FastAPI surface makes every action scriptable and testable
   without a browser.
2. **Hard to test.** NiceGUI's server-rendered model makes unit and integration testing
   cumbersome. FastAPI + pytest + `TestClient` is well-understood and mirrors
   `pd-prep-for-pgdp`.
3. **No type safety across the stack.** OpenAPI → generated TypeScript client closes the
   server/client contract gap.

`pd-prep-for-pgdp` is the reference implementation: FastAPI backend, React/Vite/TS frontend,
single-wheel distribution via `hatchling` + `hatch-vcs`. This project mirrors that pattern
exactly where it applies, and documents every deliberate divergence.

The on-disk format (`UserPageEnvelope` v2.1) must not change: the legacy labeler and the SPA
share the same `<data>/labeled-projects/` directory tree so users can switch binaries without
losing work (decision D-003).

## Constraints

- **Envelope compatibility (D-003).** `UserPageEnvelope` schema `pd_ocr_labeler.user_page`
  v2.1 is preserved byte-for-byte. The SPA may not introduce a v2.2 bump without a migration
  path that keeps the legacy labeler able to read the files.
- **Local-mode only for M0–M9 (D-042).** Postgres, S3, managed OCR, and multi-user axes are
  deferred. Every adapter interface has a seam but only the local impl ships active.
- **Single-wheel distribution.** End-users install with `uv tool install pd-ocr-labeler-spa`.
  The SPA frontend must be built into the wheel (`src/pd_ocr_labeler_spa/static/`).
- **Stable driver testid contract.** Every `data-testid` and URL shape consumed by
  `pd-ocr-labeler-driver` is listed in `specs/13-driver-contract.md` and covered by a
  conformance test. Breaking a testid is a breaking change.
- **`pd-book-tools` as the only OCR/layout primitive.** The SPA never reaches into DocTR
  or OpenCV directly; it delegates to `pd_book_tools` APIs.
- **No backwards-compat shims.** New repo; clean slate. Only the envelope schema is
  frozen by D-003.

## Decision

### Backend

**FastAPI + uvicorn** — mirrors pgdp-prep; native async, OpenAPI export, Pydantic v2.

**`build_app(settings)` factory** — same as `pgdp-prep/bootstrap.py`. Every test wires its
own `Settings`; `__main__` reads env vars. No global singleton; `AppState` lives on
`app.state` and is injected via `Depends(get_app_state)`.

**Three adapter protocols**:

- `IStorage` — `filesystem` impl (reads/writes local paths); `s3` stub raises
  `NotImplementedYet`.
- `IAuth` — `none` impl (no-op); JWT seam ready.
- `IOCREngine` — `local_doctr` impl (wraps `pd_book_tools.ocr`); `modal` and
  `shared_container` stubs raise `NotImplementedYet`.

**Three-level state tree**: `AppState` (process-global) → `ProjectState` (one per open project)
→ `PageState` (one per page, lazy-loaded). Mutations go through `AppState`-level lock.

**In-process job runner + SSE** for operations >500 ms (OCR reload, refine-bboxes, save-project,
export). Returns `202 Accepted` + `job_id`; SPA opens
`EventSource(/api/jobs/{job_id}/events)`.

**One mutation per HTTP request.** Bulk operations land as single endpoints (e.g.
`POST /api/page/{idx}/words/validate-batch`) so one round-trip per user action.

**Autosave is server-side.** Each mutation endpoint writes through to disk + image cache.
No client-side debounce timer.

### Frontend

**React 19 + Vite + TypeScript strict** — mirrors pgdp-prep.

**`@tanstack/react-query` v5** for server state; **`zustand`** for cross-page UI prefs
(filter toggle, layer visibility, panel split position).

**Tailwind 3.4 + shadcn/ui** (`@radix-ui` primitives) for styling.

**`sonner`** for toasts; **`react-hotkeys-hook`** for hotkeys; **`@tanstack/react-virtual`**
for the virtualised line-card list.

**Konva** for the image viewport canvas (D-020: renderer choice — Konva vs raw `<canvas>` —
deferred to a research spike at M4 start; Konva is the planned default pending that spike).

**OpenAPI → generated TS types.** `make openapi-export` regenerates
`frontend/src/api/types.ts`. CI gate: `git diff --exit-code` after re-running.

### Toolchain

`hatchling` + `hatch-vcs`; `uv` lockfile; `ruff` + `eslint` flat config; `pyright` strict;
`mise.toml` pinning Node 24 + Python 3.13. CI: lint → pytest → vitest → wheel build (SPA
assertion) → GitHub Release on tag.

## Contract / Acceptance

- `make ci` passes: ruff, pyright, pytest, vitest, `make frontend-build`, `make build`
  (with SPA assertion).
- `pd-ocr-labeler-ui` starts, serves the React SPA at `/`, and exposes `/openapi.json`.
- `make openapi-export` regenerates `frontend/src/api/types.ts`; CI gate reports zero diff.
- All `data-testid` values in `specs/13-driver-contract.md` are present in the live DOM and
  covered by a Playwright conformance test.
- `UserPageEnvelope` round-trip golden test passes against legacy fixture envelopes from
  `pd-ocr-labeler/tests/`.
- M0–M9 milestone acceptance tests (defined in `specs/16-milestones.md`) pass in sequence.

## Trade-offs considered

**Full rewrite vs NiceGUI incremental migration.** Incremental migration would preserve the
existing UI surface while gradually adding a REST API, but NiceGUI's event model makes it
very hard to expose a clean typed REST surface alongside the server-push model. Full rewrite
chosen: cleaner contract, easier to test, lets us adopt pgdp-prep patterns wholesale.

**React/Tailwind/shadcn vs Quasar (keep legacy stack).** Quasar would let us reuse some
existing NiceGUI/Quasar component knowledge, but it ties us to a Vue-style build pipeline
and makes the pgdp-prep reference inapplicable. React chosen for consistency across
`pd-*` web UIs and better Playwright testing story.

**Filesystem vs Postgres for v1 persistence.** Postgres would enable multi-user and history.
But single-user use case doesn't need it; adding a schema migration step to installation
would significantly raise the barrier to entry. Filesystem chosen; schema seam ready for
a future Postgres adapter.

**Global singleton `AppState` vs factory pattern.** Global singletons make parallel test
execution impossible. Factory pattern (same as pgdp-prep) chosen; each test `TestClient`
gets its own `AppState` via `Settings`.

**Raw `<canvas>` vs Konva for the image viewport.** Raw canvas gives maximum control but
requires hand-rolling hit detection, drag handling, and layer management. Konva provides
a scene-graph abstraction that makes bbox overlay and interaction modes tractable. D-020
logged the deferred decision; D-020 spike at M4 start will confirm or revise this choice.

## Consequences

- All implementation follows the M0–M9 milestone sequence in `specs/16-milestones.md`.
- The legacy `pd-ocr-labeler` remains the behavioral reference; `docs/PARITY_STATUS.md`
  tracks parity gaps (to be deleted once tracking moves fully to GitHub issues, #94).
- Every new adapter impl (S3, JWT, Modal OCR) requires adding to `IStorage`/`IAuth`/
  `IOCREngine` and wiring in `build_app`; no other files need to change.
- The `data-testid` contract is a breaking-change boundary: renaming a testid requires a
  coordinated update to `pd-ocr-labeler-driver` and a version bump.
- `pd-book-tools` is a hard dependency; any OCR/layout primitive needed by the SPA must be
  added there first, not in this repo.

## Open questions

None — all architecture decisions resolved in `specs/17-decisions.md`.

## References

- `specs/00-overview.md` — legacy feature-description doc (precursor to this design spec)
- `specs/17-decisions.md` — ADR log for all numbered design decisions (D-001–D-042+)
- `../pd-prep-for-pgdp/` — reference implementation for FastAPI + React single-wheel pattern
- `specs/13-driver-contract.md` — stable testid and URL contract for the Playwright driver
- `specs/16-milestones.md` — M0–M9 milestone acceptance gates
- `specs/09-persistence.md` — `UserPageEnvelope` v2.1 schema and compatibility rules

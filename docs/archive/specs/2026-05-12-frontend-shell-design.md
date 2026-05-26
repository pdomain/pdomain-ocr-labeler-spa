# pdomain-ocr-labeler-spa: React/Vite/TS Frontend Shell

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pdomain-ocr-labeler-spa#10

## TL;DR

The SPA shell: Vite 6 build, React 19, TypeScript strict, react-router-dom v7 for routing,
TanStack Query v5 for server state, zustand for cross-page UI preferences, Tailwind 3.4 +
shadcn/ui for styling, Konva for the image canvas, msw for test mocking. Two routes:
`/` (RootPage) and `/projects/:id/pages/pageno/:n` (ProjectPage). All component and hook
boundaries are defined here; per-component detail lives in sibling specs.

## Context

The SPA replaces NiceGUI's server-rendered Quasar UI with a client-rendered React app.
The shell governs the parts that cut across every page: the router, the `QueryClient`
configuration, the `HeaderBar` chrome, and the generated TypeScript API client. These
decisions cascade into every component spec, so they are locked here and referenced
rather than redecided per feature.

`pdomain-prep-for-pgdp` is the reference implementation for the build pipeline, TypeScript
config, Vitest setup, and msw handler structure. Divergences from pgdp-prep are noted
explicitly.

## Constraints

- **Generated TS types, not handwritten.** `frontend/src/api/types.ts` is always produced
  by `make openapi-export`; no manual edits. CI gate: zero diff after re-running.
- **`data-testid` contract.** Every testid consumed by `pd-ocr-labeler-driver` is listed
  in `specs/13-driver-contract.md` and must be present in the live DOM. Renaming is a
  breaking change.
- **DPSansMono font bundled.** `public/fonts/DPSansMono.ttf` — verbatim copy from legacy
  labeler. Not fetched from a CDN.
- **Two routes only for M1.** `/` and `/projects/:id/pages/pageno/:n`. Additional routes
  added in later milestones (export dialog as modal, not a route).
- **Konva only in canvas components.** `react-konva` imports are confined to
  `PageImageCanvas` and `WordEditDialog`; no Konva in list or toolbar components.
- **msw 2.x for all HTTP mocking in tests.** No `fetch` spies or module mocks for
  API calls; all mocking via `setupServer` in `test/server.ts`.

## Decision

### Project layout

`frontend/` at repo root. Key files: `vite.config.ts` (proxy `/api` + `/image-cache` to
`VITE_API_URL`), `vitest.config.ts` (separate file to avoid Vite 6 / Vitest 2 type clash),
`tsconfig.app.json` (strict, ES2022, jsx=react-jsx, verbatimModuleSyntax). Source tree:
`src/api/` (client + generated types), `src/stores/` (zustand), `src/hooks/`,
`src/pages/`, `src/components/`, `src/lib/`, `src/test/`.

### Routing

`routes.ts` exports a typed route table. `App.tsx` mounts a `<BrowserRouter>` with two
`<Route>` entries:

- `/` → `<RootPage>` — checks if a project is selected; redirects to `pageno/1` or
  renders `<EmptyProjectState>`.
- `/projects/:projectId/pages/pageno/:pageNo` → `<ProjectPage>` — the main labeling
  surface.

### Server state (`@tanstack/react-query`)

One `QueryClient` in `main.tsx`: `staleTime: 30_000`, `refetchOnWindowFocus: false`.
Invalidation strategy: each mutation's `onSuccess` callback calls
`queryClient.invalidateQueries({queryKey: [...]})` for the affected resource.

### Cross-page UI preferences (zustand)

`stores/ui-prefs.ts` — persists within a browser session (not `localStorage`): line
filter selection, layer visibility toggles (paragraph/line/word), panel split position,
selection mode. `stores/selection.ts` — mirrors backend `Selection` with optimistic
updates; reset on page navigation.

### API client (`api/client.ts`)

Thin `fetch` wrapper with:

- Base URL from `window.__ENV__.API_BASE` (set by `/env.js`).
- JSON serialisation and `Content-Type: application/json` header.
- Throws `ApiError` (status + parsed body) on non-2xx.
- No auth header for v1 (`IAuth none`).

### Hooks

- `useProject(projectId)` — wraps `GET /api/projects/{id}`.
- `usePage(projectId, pageIndex, lineFilter)` — wraps `GET /api/.../pages/{idx}`.
- `useJobProgress(jobId)` — opens `EventSource`, returns `JobProgress | null`.
- `useNotificationStream()` — opens `EventSource`, pushes to sonner toaster.
- `useHotkey(key, handler, options)` — thin wrapper over `react-hotkeys-hook`.

### Testing

Vitest with jsdom. Each component gets a `.test.tsx` sibling. `test/server.ts` defines
msw handlers for the happy-path API responses. Playwright E2E lives in `tests/e2e/`
(pytest harness).

## Contract / Acceptance

- `make frontend-test` (vitest) passes with coverage on all hooks and lib utilities.
- `make frontend-build` produces `dist/` with no TS errors (`tsc --noEmit`).
- `make openapi-export` is idempotent: re-running produces zero `git diff`.
- All `data-testid` values in `specs/13-driver-contract.md` appear in the M1 DOM (verified
  by Playwright conformance test).
- `DPSansMono.ttf` loads without 404 in both dev and production modes.
- Vitest coverage: `src/lib/` utilities ≥ 90% line coverage.

## Trade-offs considered

**BrowserRouter vs HashRouter.** HashRouter works without server-side catch-all config but
produces ugly `/#/` URLs. The FastAPI server already serves the SPA catch-all; BrowserRouter
chosen for clean URLs.

**TanStack Query vs SWR vs raw `useState`.** SWR would reduce bundle size. TanStack Query
is already in pgdp-prep and provides mutation helpers, optimistic update primitives, and a
richer invalidation API that pays off for the labeler's many mutation types. Chosen.

**Global zustand store vs React Context for UI prefs.** Context re-renders the entire tree
on every update. Zustand gives granular subscriptions; two components subscribing to
different slices don't trigger each other's renders. Chosen for cross-page prefs.

**Separate `vitest.config.ts` vs unified `vite.config.ts`.** Vite 6 and Vitest 2 have
conflicting type declarations when combined in one config. Separate file chosen to avoid
the type clash (same solution as pgdp-prep after the Vite 6 upgrade).

## Consequences

- Every new API endpoint requires `make openapi-export` before the frontend can consume it;
  CI gate catches drift automatically.
- Adding a new route requires an entry in `routes.ts` and a corresponding `data-testid`
  registration in `specs/13-driver-contract.md`.
- The `useJobProgress` hook holds an `EventSource` open; components that unmount before
  job completion must close it in a `useEffect` cleanup.

## Open questions

None.

## References

- `specs/03-frontend.md` — legacy feature-description doc
- `specs/13-driver-contract.md` — testid and URL contract
- `specs/04-image-viewport.md` through `specs/12-hotkeys-a11y.md` — per-component specs
- `../pdomain-prep-for-pgdp/frontend/` — reference implementation

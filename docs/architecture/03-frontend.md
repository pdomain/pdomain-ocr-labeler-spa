---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-07-13
---

# 03 — Frontend (React/Vite/TS)

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#10

The SPA half of `pdomain-ocr-labeler-spa`. Built with Vite, served from the
FastAPI wheel in production, served via Vite dev-server with proxy in
development.

This spec covers the **shell**: routing, state stores, generated API
client, app chrome, and the page tree. Per-component specs (image
viewport, word matches, toolbar, dialog, etc.) deepen each piece.

---

## 1. Project layout

```
frontend/
├── package.json
├── package-lock.json
├── index.html             # loads /env.js then /src/main.tsx
├── vite.config.ts         # @vitejs/plugin-react; proxy /api + /image-cache
├── vitest.config.ts       # separate file (vitest 2 vs vite 6 type clash)
├── tsconfig.json
├── tsconfig.app.json      # strict, ES2022, jsx=react-jsx
├── tsconfig.node.json
├── tailwind.config.ts
├── postcss.config.js
├── eslint.config.ts       # closes pgdp-prep gap
├── components.json        # shadcn/ui config
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css
│   ├── routes.ts          # the canonical route table (testable)
│   ├── api/
│   │   ├── client.ts
│   │   ├── types.ts       # AUTO-GENERATED from openapi.json
│   │   └── *.test.ts
│   ├── stores/            # zustand stores
│   │   ├── ui-prefs.ts    # filter toggle, layer visibility, splitter
│   │   ├── selection.ts   # mirrors backend Selection (optimistic)
│   │   └── *.test.ts
│   ├── hooks/
│   │   ├── useProject.ts
│   │   ├── usePage.ts
│   │   ├── useJobProgress.ts
│   │   ├── useNotificationStream.ts
│   │   ├── useHotkey.ts   # thin wrapper over react-hotkeys-hook
│   │   └── *.test.tsx
│   ├── pages/             # one per route
│   │   ├── RootPage.tsx
│   │   ├── ProjectPage.tsx
│   │   └── *.test.tsx
│   ├── components/        # shared, presentational
│   │   ├── HeaderBar.tsx
│   │   ├── ProjectLoadControls.tsx
│   │   ├── SourceFolderDialog.tsx
│   │   ├── OCRConfigModal.tsx
│   │   ├── ProjectNavigationControls.tsx
│   │   ├── PageActions.tsx
│   │   ├── PageImageCanvas.tsx
│   │   ├── BBoxOverlay.tsx
│   │   ├── ContentArea.tsx
│   │   ├── WordMatchView.tsx
│   │   ├── LineCard.tsx
│   │   ├── WordCell.tsx
│   │   ├── WordEditDialog.tsx
│   │   ├── ToolbarActionGrid.tsx
│   │   ├── ApplyStyleRow.tsx
│   │   ├── AddWordRow.tsx
│   │   ├── ExportDialog.tsx
│   │   ├── BusyOverlay.tsx
│   │   ├── ProjectLoadingOverlay.tsx
│   │   ├── SaveStatus.tsx
│   │   └── ui/              # shadcn-generated primitives (button, dialog, ...)
│   ├── lib/
│   │   ├── coords.ts        # display↔source pixel transforms
│   │   ├── marquee.ts       # rect-overlap helper (port from pgdp-prep)
│   │   ├── wordOffsets.ts   # text↔bbox char-offset index (port)
│   │   ├── lineDiff.ts      # LCS line diff (port)
│   │   └── *.test.ts
│   ├── test/
│   │   ├── setup.ts
│   │   ├── server.ts
│   │   └── handlers.ts
│   └── styles/
│       └── fonts.css        # @font-face for DPSansMono
└── public/
    └── fonts/
        └── DPSansMono.ttf   # bundled — verbatim copy from legacy
```

---

## 2. Tech stack details

| Layer | Choice | Notes |
|---|---|---|
| Build | Vite 6 | `@vitejs/plugin-react`, `vite-tsconfig-paths` (closes pgdp-prep gap). |
| Lang | TypeScript 5.x | `strict: true`, `noUnusedLocals`, `noUnusedParameters`, `verbatimModuleSyntax`. |
| Framework | React 19 | StrictMode in dev. |
| Routing | `react-router-dom` v7 | BrowserRouter. |
| Server state | `@tanstack/react-query` v5 | One `QueryClient` in `main.tsx` with `refetchOnWindowFocus: false`, `staleTime: 30_000`. |
| Local state | `useState`/`useReducer` | Per-component. |
| Cross-page UI prefs | `zustand` | `stores/ui-prefs.ts` (filter, layer visibility, splitter, selection_mode), `stores/selection.ts` (mirror of backend selection w/ optimistic updates). |
| Styling | Tailwind 3.4 | `tailwind.config.ts` content globs. |
| Components | shadcn/ui | Generated under `components/ui/` via `npx shadcn add ...`. Radix primitives under the hood. |
| Forms | controlled inputs + `useMutation` | No form library. |
| Toasts | `sonner` | One `<Toaster />` in `App.tsx`. |
| Hotkeys | `react-hotkeys-hook` | Thin `useHotkey()` wrapper. |
| Image canvas | `react-konva` 19 | Used only by `PageImageCanvas` + `WordEditDialog`. |
| Plain text editors | `<textarea readOnly>` | Replace legacy CodeMirror. |
| Virtualisation | `@tanstack/react-virtual` | Only in `WordMatchView` for line cards. |
| Test (unit) | Vitest + @testing-library/react + jest-dom | jsdom env. |
| HTTP mocking | msw 2.x | `setupServer` in `test/server.ts`. |
| E2E | Playwright (Chromium) | Pytest harness, see [`14-testing.md`](14-testing.md). |

Vite path aliases (closes pgdp-prep gap): `@/*` → `src/*`. Configured
in both `vite.config.ts` (via `vite-tsconfig-paths`) and
`tsconfig.app.json`.

---

## 3. Routes

Source of truth: `src/routes.ts`. Every other module imports from
here so the route table is testable.

**D-030** moved the SPA to pgdp-prep's plural convention with explicit
sub-routes.

```ts
export const routes = {
  root:             '/',
  project:          '/projects/:projectId',
  pageByNumber:     '/projects/:projectId/pages/pageno/:pageNumber',  // 1-based, canonical
  pageByIndex:      '/projects/:projectId/pages/index/:pageIndex',    // 0-based
  pageBare:         '/projects/:projectId/pages/:pageNumber',         // → 301 → pageno
  // legacy compat:
  legacyProject:    '/project/:projectId',                            // → 301
  legacyPage:       '/project/:projectId/page/:pageNumber',           // → 301
} as const;

export const buildProjectUrl = (id: string) =>
  `/projects/${encodeURIComponent(id)}`;
export const buildPageNumberUrl = (id: string, oneBased: number) =>
  `/projects/${encodeURIComponent(id)}/pages/pageno/${oneBased}`;
export const buildPageIndexUrl = (id: string, zeroBased: number) =>
  `/projects/${encodeURIComponent(id)}/pages/index/${zeroBased}`;
```

`App.tsx`:

```tsx
<Routes>
  <Route path={routes.root} element={<RootPage />} />
  <Route path={routes.project} element={<ProjectPage />} />
  <Route path={routes.pageByNumber} element={<ProjectPage />} />
  <Route path={routes.pageByIndex} element={<ProjectPage />} />
  <Route path={routes.pageBare} element={<RedirectToPageNumber />} />
  <Route path={routes.legacyProject} element={<LegacyRedirect />} />
  <Route path={routes.legacyPage} element={<LegacyRedirect />} />
</Routes>
```

`RootPage` and `ProjectPage` are the **only** two real top-level
pages. The two `*Redirect` components are tiny shims that emit
`<Navigate to=... replace />` to the canonical form.

URL invariants — see [`13-driver-contract.md`](13-driver-contract.md) §1
for the full rule set.

- `/` — placeholder when no project; otherwise redirects to the
  last-loaded project's last page via `pageno`.
- `/projects/{id}` — same as `/projects/{id}/pages/pageno/1`.
- `/projects/{id}/pages/pageno/{n}` — canonical 1-based.
- `/projects/{id}/pages/index/{idx0}` — alternate 0-based.
- `/projects/{id}/pages/{n}` — bare; 301 → `pageno`.
- Legacy `/project/...` paths — 301 redirected.

If `projectId` doesn't match a discovered project, render an inline
"Project not found" panel; **don't 404 the route** — the driver expects
the chrome to remain present.

---

## 4. Bootstrap

`src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import App from "@/App";
import "@/index.css";

const qc = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={qc}>
        <App />
        <Toaster richColors />
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>
);
```

`index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>pd-ocr-labeler</title>
    <link rel="icon" href="/favicon.ico" />
  </head>
  <body>
    <div id="root"></div>
    <script src="/env.js"></script>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`/env.js` is served by FastAPI (`api/env_js.py`) and shapes
`window.__ENV__ = {API_BASE: "", API_TOKEN: null}`. The SPA reads it
once via `client.ts`.

---

## 5. App shell (`App.tsx`)

```tsx
export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <HeaderBar />
      <main className="flex-1">
        <Routes>...</Routes>
      </main>
      <NotificationStream />     {/* hidden, drives sonner */}
      <ProjectLoadingOverlay />   {/* portal, gated on app_state.loading */}
      <BusyOverlay />             {/* portal, gated on busy */}
    </div>
  );
}
```

`HeaderBar` is chrome-only (D-047, 2026-06-14): logo, app name, project
breadcrumb, and the resolved project-root path label. The AppShell injects the
LauncherSlot + SettingsSlot ⚙ (which owns theme via the Appearance panel,
D-048) into the header zone. Document/page-scoped controls live in the body:
page navigation, page actions, and the metrics strip moved into the
`WorkspaceToolbar` band (a pdomain-ui `StageToolbar`,
`data-testid="workspace-toolbar"`) at the top of the project route; the ⌘K
`QuickSearch` moved into the Drawer worklist header
(`data-testid="drawer-worklist-header"`). No tabs, no nav chrome at the app
level — the legacy is a single page and we preserve that look.

> Note: the snippet above predates the pdomain-ui AppShell adoption (Phase 2.4).
> In the shipped app `App.tsx` mounts the pdomain-ui `AppShell` with
> `header` / `rail` / `main` slots rather than a hand-rolled flex column.

---

## 6. State stores

### `stores/ui-prefs.ts`

```ts
type LayerVisible = { paragraphs: boolean; lines: boolean; words: boolean };
type SelectionMode = "paragraph" | "line" | "word";
type LineFilter = "unvalidated" | "mismatched" | "all";

interface UiPrefsStore {
  layerVisible: LayerVisible;
  selectionMode: SelectionMode;
  lineFilter: LineFilter;
  splitterPercent: number;          // 50 default
  zoomLevel: 1 | 2 | 5 | 10;        // dialog zoom default 2
  setLayerVisible(v: Partial<LayerVisible>): void;
  setSelectionMode(m: SelectionMode): void;
  setLineFilter(f: LineFilter): void;
  setSplitterPercent(p: number): void;
}
```

Persisted to `localStorage` via the `zustand/middleware/persist` adapter.
Per-browser today (D-021). When auth lands (D-005 follow-up), migrate
to a per-user backend store via `GET/PUT /api/user/prefs`.

### `stores/selection.ts`

Mirror of backend `Selection`. Applies optimistic updates — `useMutation`
calls invalidate the store + re-query.

```ts
interface SelectionStore {
  selectionMode: "paragraph" | "line" | "word";
  selectedParagraphs: Set<number>;
  selectedLines: Set<number>;
  selectedWords: Set<string>;       // "<lineIdx>:<wordIdx>"
  ...
}
```

Backend keeps the canonical copy; the SPA just optimistically reflects
clicks until the server confirms. (Server keeps it because two tabs
viewing the same page need consistent toolbar disabled-states.)

---

## 7. API client

### `src/api/client.ts`

Hand-written fetch wrapper. Verbatim shape from pgdp-prep
`frontend/src/api/client.ts:11-79`:

```ts
type Opts = { body?: unknown; query?: Record<string, string | number | boolean | undefined>; headers?: HeadersInit };

function getApiBase(): string {
  return (window as any).__ENV__?.API_BASE ?? "";
}

function getAuthToken(): string | null {
  return localStorage.getItem("pdlabeler.api_token") ?? (window as any).__ENV__?.API_TOKEN ?? null;
}

async function request<T>(method: string, path: string, opts: Opts = {}): Promise<T> {
  const url = new URL(getApiBase() + path, window.location.origin);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined) url.searchParams.set(k, String(v));
  }
  const headers = new Headers(opts.headers);
  if (opts.body !== undefined) headers.set("Content-Type", "application/json");
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(url.toString(), {
    method,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const e = new Error(detail?.message ?? res.statusText);
    (e as any).status = res.status;
    (e as any).detail = detail;
    throw e;
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string, opts?: Opts) => request<T>("GET", path, opts),
  post: <T>(path: string, opts?: Opts) => request<T>("POST", path, opts),
  put: <T>(path: string, opts?: Opts) => request<T>("PUT", path, opts),
  patch: <T>(path: string, opts?: Opts) => request<T>("PATCH", path, opts),
  delete: <T>(path: string, opts?: Opts) => request<T>("DELETE", path, opts),
};
```

### `src/api/types.ts`

Auto-generated from `frontend/openapi.json` via `openapi-typescript`.
**Don't hand-edit.** CI gate: `make openapi-export` then
`git diff --exit-code` (closes pgdp-prep drift gap).

Imports look like:

```ts
import type { PagePayload, WordMatch, LineMatch } from "@/api/types";
import { api } from "@/api/client";

const page = await api.get<PagePayload>(`/api/projects/${id}/pages/${idx}`);
```

---

## 8. Hooks

### `usePage(projectId, pageIndex, lineFilter)`

```ts
useQuery({
  queryKey: ["page", projectId, pageIndex, lineFilter],
  queryFn: () =>
    api.get<PagePayload>(
      `/api/projects/${projectId}/pages/${pageIndex}`,
      { query: { line_filter: lineFilter } }
    ),
});
```

### `useProjects()`

`api.get<ListProjectsResponse>("/api/projects")`. Static after first
fetch unless invalidated by `set-source-root` mutation.

### `useJobProgress(jobId)`

Verbatim port of pgdp-prep
`frontend/src/hooks/useJobProgress.ts:36-95`. SSE
`EventSource('/api/jobs/{id}/events')`, `JSON.parse(message.data)`,
fallback to one-shot `GET /api/jobs/{id}` on EventSource error.

### `useNotificationStream()`

Mounted once at the top of `App.tsx` via `<NotificationStream />`.
Opens `EventSource('/api/notifications/stream')`, dispatches each
event to `sonner.toast.<kind>(message)`. Persists across route
changes. **Don't dismount** — the legacy 50ms-poller is replaced by
this single long-lived SSE.

### `useHotkey(map)`

Wrapper over `react-hotkeys-hook` that takes a `Record<string, Handler>`
and binds them all. Respects active form-control focus by default
(no Ctrl+S triggers from inside an `<input>`). See
[`12-hotkeys-a11y.md`](12-hotkeys-a11y.md) for the full keymap.

---

## 9. Component organisation

Three folders:

- `pages/` — one per route. Owns top-level data fetching. Composes
  components.
- `components/` — presentational + small bits of state. **Re-usable**
  across pages.
- `components/ui/` — shadcn-generated primitives (button, dialog,
  toast, tooltip, popover, select). **Don't hand-edit beyond what
  shadcn allows.**

Feature folders (`features/words/`, etc.) are NOT used in v1. Pages
flat-by-kind, same as pgdp-prep. Revisit if the repo passes ~20 pages.

---

## 10. Mutation patterns

Every server-mutating action follows this shape:

```tsx
const qc = useQueryClient();
const mutation = useMutation({
  mutationFn: (req: ApplyStyleRequest) =>
    api.post<WordMatch>(
      `/api/projects/${pid}/pages/${idx}/words/${l}/${w}/style`,
      { body: req }
    ),
  onMutate: async (req) => {
    // optimistic: patch the cached PagePayload
    await qc.cancelQueries({ queryKey: ["page", pid, idx] });
    const prev = qc.getQueryData<PagePayload>(["page", pid, idx]);
    if (prev) {
      qc.setQueryData<PagePayload>(["page", pid, idx], optimisticApplyStyle(prev, req));
    }
    return { prev };
  },
  onError: (_e, _req, ctx) => {
    if (ctx?.prev) qc.setQueryData(["page", pid, idx], ctx.prev);
    toast.error("Apply style failed");
  },
  onSuccess: (updated) => {
    // server canonicalised the WordMatch — patch into the cache
    qc.setQueryData<PagePayload>(["page", pid, idx], (cur) =>
      cur ? replaceWordMatch(cur, updated) : cur
    );
  },
});
```

Key rules:

- **Always** invalidate (or patch) the relevant query on success.
- Never rely on `refetchOnWindowFocus`.
- When the server returns `PagePayload` (multi-word effects),
  `qc.setQueryData(["page", pid, idx], updated)` directly — no refetch.

---

## 11. Modals + dialogs

shadcn `Dialog` for everything modal:

- `<OCRConfigModal />`
- `<SourceFolderDialog />`
- `<WordEditDialog />`
- `<ExportDialog />`

shadcn ships:

- Focus trap (Radix).
- Escape closes (Radix).
- Background scroll lock (Radix).
- ARIA labels.

Closes pgdp-prep `ProjectListPage.tsx:106-168` hand-rolled-modal gap.

---

## 12. Toasts

`sonner` configured with `richColors`. Helper:

```ts
import { toast } from "sonner";
export const apiToast = {
  ok: (m: string) => toast.success(m),
  err: (m: string) => toast.error(m),
  warn: (m: string) => toast.warning(m),
  info: (m: string) => toast(m),
};
```

The `useNotificationStream` hook in `App.tsx` feeds this from the
backend `NotificationKind` enum; mutation `onError` callbacks use it
directly.

Z-index: handled by sonner; never compete with `BusyOverlay`. Sonner's
default z-index is well above shadcn's modal portal.

---

## 13. Image cache URL helpers

```ts
export const imageCacheUrl = (filename: string) => `/image-cache/${filename}`;
export const overlayUrl = (cached: CachedImageSet, kind: keyof CachedImageSet) =>
  cached[kind] ? imageCacheUrl(cached[kind]!) : null;
```

`PagePayload.image_url` and `PagePayload.overlay_urls` are already
fully-qualified by the backend; the helper is only used for cases
where we have raw filenames (e.g. browsing the cache for diagnostics).

---

## 14. Coordinate transforms

`src/lib/coords.ts`:

```ts
export interface DisplayDims { width: number; height: number; }
export interface BBox { x: number; y: number; width: number; height: number; }

export function srcToDisplay(b: BBox, scale: number): BBox { ... }
export function displayToSrc(b: BBox, scale: number): BBox { ... }
```

`scale` comes from `PagePayload.encoded.scale`. The Konva `<Stage>` is
sized to `(encoded.display_width, encoded.display_height)`; bbox rects
are converted via these helpers. Source-pixel coordinates are sent on
the wire (matches the backend's image-coordinate space).

---

## 15. Error handling

- Errors from `api.*` throw `Error & {status, detail}`.
- `ProjectPage` and dialogs render an inline error panel for fatal
  cases (project not found, page out of range).
- `useMutation` `onError` callbacks toast with `apiToast.err(...)`.
- Unhandled errors (React) bubble to a top-level `<ErrorBoundary>`
  installed in `App.tsx`. The boundary renders a "Something broke"
  panel + a "Reload" button.
- 401 responses redirect to nothing (no auth in v1) but log a console
  warning. Keep the 401 handling stub for future JWT.

---

## 16. Performance budget

- First paint < 1s on dev hardware (cold cache, with full SPA bundle).
- Switch page within a project < 300ms (cache hit) / < 5s (OCR run).
- Apply word style < 100ms perceived (optimistic update).
- Render line-cards for a 200-line page < 200ms — virtualise.
- Word-match table re-render on a single-word edit: only that word's
  cell repaints. Use `useMemo` + stable keys aggressively; verify
  with React DevTools profiler in M5.

If any of these regress, file an issue + add a benchmark — don't
patch around it.

---

## 17. Accessibility

- Every interactive element has a label (`aria-label`, visible text,
  or shadcn primitive default).
- Focus management owned by shadcn Dialog (focus trap, Escape, focus
  return on close).
- `role="status"` `aria-live="polite"` slot in `App.tsx` for
  screen-reader narration of bulk changes ("Validated 5 words").
- See [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md) for the full a11y
  catalogue.

---

## 18. Build output

`npm run build` →`frontend/dist/`. `make frontend-build` then copies
`frontend/dist/.` → `src/pdomain_ocr_labeler_spa/static/` so the wheel
`force-include` picks it up.

Vite sourcemaps: `sourcemap: true` so production stack traces are
debuggable. (Same as pgdp-prep `vite.config.ts:11-25`.)

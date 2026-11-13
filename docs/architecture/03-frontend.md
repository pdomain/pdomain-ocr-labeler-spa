---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-13
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

`TypographySection` is the sole inline-typography authoring surface. It uses
the server taxonomy and extended-grapheme map, fetches the current head before
each append, and reloads after stale-head `409` responses. Retired style and
character-range hooks are unsupported.

---

## 1. Project layout

```
frontend/
├── package.json
├── pnpm-lock.yaml
├── index.html             # loads /env.js then /src/main.tsx
├── vite.config.ts         # @vitejs/plugin-react; proxy /api + /image-cache
├── vitest.config.ts       # separate file (test and build configuration are separate)
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
│   │   ├── ToolbarActionGrid.tsx
│   │   ├── right-panel/sections/TypographySection.tsx
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
│       └── fonts.css        # @font-face for JetBrains Mono
└── public/
    └── fonts/
        └── JetBrains Mono.ttf   # bundled — verbatim copy from legacy
```

---

## 2. Tech stack details

| Layer | Choice | Notes |
|---|---|---|
| Build | Vite | React plugin and explicit resolve aliases in `vite.config.ts`; versions live in `package.json`. |
| Lang | TypeScript | `strict: true`, `noUnusedLocals`, `noUnusedParameters`, `verbatimModuleSyntax`. |
| Framework | React 19 | StrictMode in dev. |
| Routing | `react-router-dom` v7 | BrowserRouter. |
| Server state | `@tanstack/react-query` v5 | One `QueryClient` in `App.tsx` with `refetchOnWindowFocus: false`, `staleTime: 30_000`. |
| Local state | `useState`/`useReducer` | Per-component. |
| Cross-page UI prefs | `zustand` | `stores/ui-prefs.ts` (filter, layer visibility, splitter, selection_mode), `stores/selection-store.ts` (client-owned selection). |
| Styling | Tailwind | `tailwind.config.ts` content globs. |
| Components | shadcn/ui | Generated under `components/ui/` via `npx shadcn add ...`. Radix primitives under the hood. |
| Forms | controlled inputs + `useMutation` | No form library. |
| Toasts | `sonner` | One `<Toaster />` in `App.tsx`. |
| Hotkeys | `react-hotkeys-hook` | Thin `useHotkey()` wrapper. |
| Image canvas | `react-konva` 19 | Used only by `PageImageCanvas` and the right panel's `EraseCanvas`. |
| Plain text editors | `<textarea readOnly>` | Replace legacy CodeMirror. |
| Virtualisation | `@tanstack/react-virtual` | Only in `WordMatchView` for line cards. |
| Test (unit) | Vitest + @testing-library/react + jest-dom | jsdom env. |
| HTTP mocking | msw 2.x | `setupServer` in `test/server.ts`. |
| E2E | Playwright (Chromium) | Pytest harness, see [`14-testing.md`](14-testing.md). |

Vite path aliases (closes pgdp-prep gap): `@/*` → `src/*`. Configured
in both `vite.config.ts` (explicit resolve aliases) and
`tsconfig.app.json`.

### Shared primitive ownership

`@pdomain/pdomain-ui` owns compatible general-purpose primitives. The SPA
imports `Input`, `TriStateChip`, and `Button` directly, and the former local
implementations have been deleted. Their HTML attributes, refs, event behavior,
and driver-facing testids continue to pass through the shared components.

Tabs remain behind `components/ui/tabs.tsx`, a compatibility re-export of the
shared `Tabs`, `TabsList`, `TabsTrigger`, and `TabsContent`. This boundary keeps
existing imports stable while `pdomain-ui` owns the DOM behavior and
`primitives.css` classes, including active state and count badges.

The SPA still owns domain-specific behavior that is not a general primitive:
the Sonner toast helper, the long-lived notification SSE consumer, and the
`--status-*` and `--layer-*` semantic token aliases.

Evidence:

- Code: `frontend/src/components/ui/tabs.tsx`,
  `frontend/src/components/right-panel/OcrGtCompareRow.tsx`,
  `frontend/src/components/right-panel/ChipPalette.tsx`,
  `frontend/src/lib/toast.ts`, `frontend/src/hooks/useNotificationStream.tsx`,
  and `frontend/src/styles/tokens.css`; local `Input.tsx`, `Chip.tsx`, and
  `button.tsx` are absent
- Tests: `frontend/src/components/ui/Input.test.tsx`,
  `frontend/src/components/ui/Chip.test.tsx`,
  `frontend/src/components/ui/Button.test.tsx`,
  `frontend/src/components/ui/Tabs.test.tsx`,
  `frontend/src/hooks/useNotificationStream.test.tsx`, and
  `frontend/src/styles/tokens.test.ts`
- Commits: `799fc0b` (Input), `fcab138` (Chip), `b312a68` (Button), and
  `cedb967` (Tabs)
- Verified: 2026-07-19 against current code, tests, and Git history

---

## 3. Routes

`frontend/src/lib/routes.ts` is the route catalogue. `App.tsx` mounts the root project list, project page
workbench and typography worklist. Canonical project/page routes are plural and include explicit page-number
and index forms. Legacy singular URLs receive backend 301 redirects; removed editing surfaces do not return.
See the [driver contract](13-driver-contract.md) for mounted controls and selectors.

## 4. Bootstrap

`main.tsx` imports the Inter and JetBrains Mono fonts and renders `App`. `App.tsx` owns BrowserRouter,
QueryClientProvider, the shared AppShell, compute settings, suite navigation and long-lived notifications.
Server data belongs to TanStack Query; local selection, viewport modes and preferences have separate stores.

## 5. App shell (`App.tsx`)

The shared `pdomain-ui` AppShell owns the header, rail, drawers, dock and layout primitives. Labeler adapters
supply job/status controls, the suite launcher and application panels. ProjectPage owns domain selection,
canvas overlays, mutations and its local right-panel frame. See [shell layout](24-shell-layout.md) and
[repository boundaries](30-repository-boundaries.md). This is the mounted shell, not a second layout proposal.

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

### `stores/selection-store.ts`

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

Hand-written fetch wrapper. `ApiClient` is a class constructed with a fixed
`baseUrl`; there is **no auth token and no `Authorization` header** — this app is
no-auth by design (D-005 / D-042, see `specs/17-decisions.md`). The shape below
originated from the pgdp-prep scaffold but has since diverged; it is transcribed
from the real `frontend/src/api/client.ts`:

```ts
export class ApiError extends Error {
  constructor(
    public status: number,
    public error: string,
    public override message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    method: string,
    path: string,
    options?: { body?: unknown },
  ): Promise<T> {
    const url = new URL(path, this.baseUrl).toString();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const fetchOptions: RequestInit = { method, headers };
    if (options !== undefined && "body" in options) {
      fetchOptions.body = JSON.stringify(options.body);
    }
    const res = await fetch(url, fetchOptions);
    if (!res.ok) {
      // parse the error envelope and throw ApiError(status, error, message, details)
    }
    if (res.status === 204 || res.headers.get("content-length") === "0") {
      return null as T;
    }
    const responseText = await res.text();
    if (!responseText) return null as T;
    return JSON.parse(responseText) as T;
  }

  get<T>(path: string): Promise<T> { /* request("GET", path) */ }
  post<T>(path: string, body?: unknown): Promise<T> { /* request("POST", path, { body }) */ }
  put<T>(path: string, body?: unknown): Promise<T> { /* request("PUT", path, { body }) */ }
  delete<T>(path: string): Promise<T> { /* request("DELETE", path) */ }
  // plus a domain helper: setCurrentPageIndex(...)
}
```

There is no `query`-param support, no `getAuthToken`, and no module-level `api`
singleton — callers construct an `ApiClient` with a base URL.

Falsy JSON values remain valid request bodies. The client serializes a body
whenever the caller supplies the `body` key. Tests cover `0`, `false`, and an
empty string; the same key-presence branch serializes `null`.

Successful responses return `null` without JSON parsing when the status is 204,
the `Content-Length` header is `0`, or the response text is empty. Other
successful responses are parsed from their text as JSON.

Evidence:

- Code: `frontend/src/api/client.ts`
- Tests: `frontend/src/api/client.test.ts` — `falsy body serialization (Bug 1)`
  covers `0`, `false`, and an empty string; `empty / no-content response
  handling (Bug 2)` covers empty successful responses
- Commit: `9ac12bafedca636303923bf96a039d1f4b6b663d`
- Verified: 2026-07-19 against the migration export for GitHub issue #449

### `src/api/types.ts`

Auto-generated from `frontend/openapi.json` via `openapi-typescript`.
**Don't hand-edit.** CI gate: `just openapi-export` then
`git diff --exit-code` (closes pgdp-prep drift gap).

Imports look like:

```ts
import type { components } from "@/api/types";

type PagePayload = components["schemas"]["PagePayload"];
```

---

## 8. Hooks

### `usePage(projectId, pageIndex, lineFilter)`

`usePage.ts` builds query parameters with URLSearchParams and fetches with AbortSignal. Reload epochs and
payload ordering guards prevent an old project/page response from replacing newer state. The hook defaults
to all lines; the mounted workbench filters the returned line matches locally. The handwritten client has
no `query` option and no module-level `api` singleton.

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
- `components/ui/` — compatibility wrappers for shared primitives and local
  primitives that remain application-specific. Keep wrappers only where the
  labeler contract differs from `pdomain-ui`.

Feature folders (`features/words/`, etc.) are NOT used in v1. Pages
flat-by-kind, same as pgdp-prep. Revisit if the repo passes ~20 pages.

---

## 10. Mutation patterns

Typography append uses its actual head-aware hook:

```tsx
export function useAppendTypographyCorrection(
  projectId: string,
  pageIndex: number,
  wordId: string,
) {
  const queryClient = useQueryClient();
  return useMutation<TypographyHead, TypographyApiError, TypographySubmission>({
    retry: false,
    mutationFn: (submission) =>
      apiJson<TypographyHead>(
        `${pageBase(projectId, pageIndex)}/words/${encodeURIComponent(wordId)}/corrections`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(submission),
        },
      ),
    onSuccess: (head) => {
      queryClient.setQueryData(["typography-head", projectId, pageIndex, wordId], head);
      void queryClient.invalidateQueries({
        queryKey: ["typography-review", projectId, pageIndex],
      });
    },
    onError: (error) => {
      if (error.status === 409) {
        void queryClient.invalidateQueries({
          queryKey: ["typography-head", projectId, pageIndex, wordId],
        });
      }
    },
  });
}
```

Key rules:

- **Always** invalidate (or patch) the relevant query on success.
- Never rely on `refetchOnWindowFocus`.
- When the server returns `PagePayload` (multi-word effects),
  `queryClient.setQueryData(["page", projectId, pageIndex], updated)` directly
  — no refetch.

---

## 11. Modals + dialogs

shadcn `Dialog` for everything modal:

- `<OCRConfigModal />`
- `<SourceFolderDialog />`
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

`npm run build` →`frontend/dist/`. `just frontend-build` then copies
`frontend/dist/.` → `src/pdomain_ocr_labeler_spa/static/` so the wheel
`force-include` picks it up.

Vite sourcemaps: `sourcemap: true` so production stack traces are
debuggable. (Same as pgdp-prep `vite.config.ts:11-25`.)

## Compute settings and suite integration

The shared Compute panel lists CPU, usable CUDA devices, and detected NVIDIA hardware that cannot run CUDA. It
provides a reset for forced CPU settings and inline CUDA setup guidance. OCR configuration remains a separate
panel. Startup warms the suite device endpoint once, before the settings panel opens.

The suite launcher uses the installed-app and launch endpoints through the local suite adapter. Shared shell
components own application chrome. The labeler owns its document workspace, domain panels, and worklist adapter. It
does not adopt PGDP's pipeline stages or a shared workbench layout.

### Evidence

- Code: `frontend/src/App.tsx`, `frontend/src/api/suite.ts`, and `frontend/src/components/drawer/Worklist.tsx`.
- Tests: `frontend/src/App.test.tsx` and `tests/integration/test_suite_device_routes.py`.
- Verified: 2026-11-07 by source inspection against the completed compute-settings plan and September decisions.

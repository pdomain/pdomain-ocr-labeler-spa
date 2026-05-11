# 21 — HeaderBar + ProjectLoadControls

> **Status**: Draft
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#83

---

## TL;DR

`HeaderBar` is a controls-only `<header>` shell that renders
`ProjectLoadControls`. `ProjectLoadControls` fetches `GET /api/projects`,
manages dropdown selection state, and posts to `/api/projects/load`.
Four driver-contract data-testids must be present. A minimal
`api/client.ts` is created in this PR as a prerequisite.

---

## Context

M1.h is the final frontend gate before M1 closes. The backend is fully
implemented (`GET /api/projects`, `POST /api/projects/load`,
`GET /api/projects/{id}`). `App.tsx` is a 17-line M0 stub with no
routing, no HeaderBar, no API client. This spec covers creating the
two header components and the minimal API client they depend on.

The legacy NiceGUI labeler header shows: project dropdown (pick project
under configured root), folder-browse icon (set source root), LOAD
button, OCR-config tune icon. The SPA replicates this layout without
tabs or navigation elements (`specs/03-frontend.md:261`).

---

## Constraints

- Four data-testids from `specs/13-driver-contract.md §2.1` are **stable
  invariants** — must be present exactly:
  - `project-select` — Radix Select trigger
  - `load-project-button` — LOAD button
  - `source-folder-button` — folder-icon button
  - `ocr-config-trigger-button` — tune-icon button
- `HeaderBar` contains `ProjectLoadControls`. No tabs, no nav
  (`specs/03-frontend.md:261`).
- Header is controls-only — no app title visible in the bar.
- `SourceFolderDialog` and `OCRConfigModal` are **out of scope** for this
  spec (stub triggers only — the buttons exist and carry their testids,
  but clicking them does nothing until their respective specs land).
- Accessibility keymap is **out of scope** (`specs/12-hotkeys-a11y.md`).
- Auth/managed-adapter axes deferred (D-042).

---

## Decision

### Component split

`HeaderBar.tsx` is a pure presentational shell:

```tsx
export default function HeaderBar() {
  return (
    <header className="flex items-center gap-2 border-b px-4 py-2">
      <ProjectLoadControls />
    </header>
  );
}
```

`ProjectLoadControls.tsx` owns all data-fetching and interaction:

```tsx
export default function ProjectLoadControls() {
  // useQuery → GET /api/projects
  // useMutation → POST /api/projects/load
  // local selectedRoot: string | null
  // renders: project-select, source-folder-button, load-project-button,
  //           ocr-config-trigger-button
}
```

Rationale: separating the chrome shell from the data-fetching component
keeps `HeaderBar` independently testable (render with any
`ProjectLoadControls` mock), and matches the spec component tree
(`specs/03-frontend.md:58-59`).

### API client (prerequisite)

Create `frontend/src/api/client.ts` with a minimal typed wrapper:

```ts
const API_BASE = (window as any).__ENV__?.API_BASE ?? "";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw await res.json();
  return res.json() as Promise<T>;
}

export async function apiPost<B, T>(path: string, body: B): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await res.json();
  return res.json() as Promise<T>;
}
```

Inline types for `ListProjectsResponse` and `LoadProjectRequest` are
sufficient for this slice; `make openapi-export` and a full `types.ts`
generation follow in a later pass (noted in Consequences).

### Dropdown empty state

When `GET /api/projects` returns `projects: []`:

- The Radix Select trigger renders with `disabled` attribute.
- Display text: "No projects found".
- `load-project-button` is also disabled.
- `source-folder-button` remains enabled so the user can configure a
  source root.

### Disabled states

| State | `project-select` | `load-project-button` |
|---|---|---|
| Loading (fetch in-flight) | disabled | disabled |
| No projects found (empty list) | disabled | disabled |
| Projects found, none selected | enabled | disabled |
| Project selected | enabled | **enabled** |
| Load mutation in-flight | enabled | disabled |
| Load mutation error | enabled | enabled (retry) |

### Data flow

```
ProjectLoadControls
  ├── useQuery(['projects'], () => apiGet('/api/projects'))
  │     → ListProjectsResponse { projects, selected, projects_root }
  ├── useState: selectedRoot = response.selected ?? null
  │     (re-init when query data arrives)
  └── useMutation(root => apiPost('/api/projects/load', { project_root: root }))
        onSuccess → queryClient.invalidateQueries(['projects'])
```

`selected` from the response marks the active project (backend's
carrier snapshot). The dropdown re-reflects it on every refetch.

### Wiring into App.tsx

`App.tsx` is rewritten for M1.h to include routing and the HeaderBar
shell per `specs/03-frontend.md §5`. This is the App.tsx from that spec
(abbreviated):

```tsx
export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <HeaderBar />
      <main className="flex-1">
        <Routes>
          <Route path={routes.root} element={<RootPage />} />
          {/* ... other routes */}
        </Routes>
      </main>
      <NotificationStream />
      <ProjectLoadingOverlay />
      <BusyOverlay />
    </div>
  );
}
```

`NotificationStream`, `ProjectLoadingOverlay`, `BusyOverlay`, and full
routing land in their own specs. This spec only requires that
`<HeaderBar />` is imported and rendered in the `App.tsx` rewrite.

---

## Contract / Acceptance

### Vitest tests — `HeaderBar.test.tsx`

All tests run with msw 2.x mock server (`test/server.ts`).

| Test | Description |
|---|---|
| `renders_four_testids` | All four driver-contract testids are in the DOM |
| `load_button_disabled_before_selection` | `load-project-button` has `disabled` attribute when no project is selected |
| `load_button_enabled_after_selection` | `disabled` removed after user selects a project from dropdown |
| `load_button_disabled_during_mutation` | `disabled` while POST is in-flight (mutation pending) |
| `empty_projects_shows_disabled_placeholder` | When GET returns `projects: []`, `project-select` is disabled |
| `source_folder_button_always_enabled` | `source-folder-button` is never disabled by this component |

### Make targets

- `make frontend-test` — green (no regressions)
- `make frontend-build` — green (TypeScript strict, no unused locals)

### Driver-contract sanity (M1 acceptance)

From `specs/16-milestones.md`:

> `data-testid="project-load-button"` exists on the header even though
> it's disabled.

This is verified by the `renders_four_testids` + `load_button_disabled_before_selection` pair.

---

## Trade-offs considered

**Single file vs. two files:**
Putting everything in `HeaderBar.tsx` is simpler to scaffold but conflicts
with `specs/03-frontend.md:58-59` (separate entries) and grows the file
with unrelated concerns. Two files chosen.

**Inline types vs. full openapi-generated `types.ts`:**
`make openapi-export` requires a running backend. Running it in the bot
workspace during implementation is feasible but adds friction. Inline
types for just `ListProjectsResponse`/`LoadProjectRequest` unblock
this slice; a follow-up `make openapi-export` pass keeps things in sync.
This is a known controlled deviation, not a shortcut.

**`fetch` directly vs. axios/ky:**
The spec doesn't mandate a HTTP library. A thin typed `apiGet`/`apiPost`
wrapper over native `fetch` avoids a new dependency and is sufficient for
the two calls this component makes.

---

## Consequences

- `frontend/src/api/client.ts` is created; `frontend/src/api/types.ts`
  is NOT generated in this PR (deferred until a convenience `make
  openapi-export` run can happen or a dedicated chore is filed).
- `App.tsx` is rewritten from the M0 stub to the M1 shell layout
  (HeaderBar + Routes placeholder). Full routing requires `routes.ts`,
  `RootPage`, and `ProjectPage` — those land in separate M1.h specs.
  This PR wires in only what's needed to mount `<HeaderBar />`.
- The four data-testids are stable from this point forward; any rename
  requires an OPEN_QUESTIONS.md entry per `specs/13-driver-contract.md §2`.

---

## Open questions

None — all design questions resolved in this spec.

---

## References

- `specs/03-frontend.md §5` — App shell layout, HeaderBar placement
- `specs/03-frontend.md:58-59` — Component tree (HeaderBar + ProjectLoadControls as separate files)
- `specs/03-frontend.md:261` — "HeaderBar contains ProjectLoadControls. No tabs, no nav."
- `specs/13-driver-contract.md §2.1` — Stable data-testid catalogue for header controls
- `specs/02-backend.md §5.2` — GET /api/projects and POST /api/projects/load contracts
- `specs/01-data-models.md §2` — ListProjectsResponse, ProjectKey, LoadProjectRequest wire shapes
- `specs/14-testing.md` — Vitest + msw test structure

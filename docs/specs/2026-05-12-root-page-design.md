# pd-ocr-labeler-spa: RootPage Component

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#85

## TL;DR

`<RootPage />` is the React route element for `/`. On mount it calls `GET /api/session-state`;
if a `last_project_path` + `last_page_index` is found it redirects (replace mode) to
`/projects/{id}/pages/pageno/{n}`; otherwise it renders `<EmptyProjectState />`. In-flight
loading shows nothing (HeaderBar remains visible). Session-state fetch failure falls back to
`<EmptyProjectState />`.

## Context

`specs/03-frontend.md §176` defines the `/` route behaviour. `specs/13-driver-contract.md §1`
defines the URL invariants. The legacy `pd-ocr-labeler` uses `_initialize_from_url` to detect
and redirect to the last-viewed page on startup; the SPA replicates this via the session-state
endpoint. `HeaderBar` is mounted in `App.tsx` above `<RootPage />`, not inside it — RootPage
controls only its own content area.

## Constraints

- **Replace-mode redirect.** `router.navigate(url, { replace: true })` for session-state-
  driven auto-redirects. Prevents the user from pressing Back and getting stuck in a redirect
  loop. Cross-project navigation pushes (not replace).
- **HeaderBar always visible.** RootPage renders only the content below the header. It must
  not touch or unmount the HeaderBar.
- **Session-state failure → EmptyProjectState (no error banner).** A fetch failure on the
  session-state endpoint is benign (first run, cleared state, network hiccup) and should
  silently fall back to the empty state. The user can always load a project manually.
- **Loading state: render nothing (blank content area).** While the session-state fetch is
  in-flight, RootPage renders an empty `<div />` (the HeaderBar is visible). A spinner would
  flash on fast connections; blank is cleaner for this sub-100ms fetch.
- **`GET /api/session-state` is the authority.** RootPage does not read session state from
  localStorage or zustand; it always defers to the backend endpoint.

## Decision

### Session-state endpoint

`GET /api/session-state` returns:

```json
{
  "schema_version": "1.0",
  "last_project_path": "/abs/path/to/project" | null,
  "last_page_index": 0
}
```

If `last_project_path` is null (no previous session): 200 with `last_project_path: null`.
If the file doesn't exist: 200 with `last_project_path: null` (same response, no 404).

### RootPage logic

```tsx
export function RootPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["session-state"],
    queryFn: () => api.getSessionState(),
    retry: false,
  });

  useEffect(() => {
    if (!data?.last_project_path) return;
    const projectId = deriveProjectId(data.last_project_path);
    const pageNo = (data.last_page_index ?? 0) + 1;
    navigate(`/projects/${projectId}/pages/pageno/${pageNo}`, { replace: true });
  }, [data, navigate]);

  if (isLoading) return <div />;                  // blank; HeaderBar visible above
  if (isError || !data?.last_project_path)
    return <EmptyProjectState />;
  return <div />;                                  // redirect pending (effect fires next tick)
}
```

`deriveProjectId` converts the absolute path to the project directory name (basename of
`last_project_path`). This matches how `AppState` registers discovered projects.

### EmptyProjectState

`<EmptyProjectState />` renders a centred message: "No project loaded. Select a project from
the dropdown above to get started." No buttons (the HeaderBar already has the LOAD button).
testid: `empty-project-state`.

### When session-state describes a missing project

If the redirect target resolves to a project that doesn't exist in the discovered list, the
`<ProjectPage />` component renders an inline "Project not found" banner (per
`specs/13-driver-contract.md §1.3`). RootPage does not handle this — it redirects
unconditionally and lets ProjectPage resolve the discrepancy.

## Contract / Acceptance

- `GET /api/session-state` with no prior session → 200, `last_project_path: null`.
- RootPage renders `<EmptyProjectState />` (testid `empty-project-state`) when no last project.
- RootPage redirects to `/projects/{id}/pages/pageno/{n}` (replace mode) when session state
  has a last project.
- HeaderBar (testid `header-bar`) remains visible in both states.
- Session-state fetch failure → `<EmptyProjectState />` renders (no error banner, no 500 page).
- In-flight: content area is blank (no spinner flash).
- `RootPage.test.tsx`: `renders_empty_state` (msw returns null last_project);
  `redirects_to_last_project` (msw returns valid session state).

## Trade-offs considered

**Blank vs spinner during loading.** Session-state fetch is typically < 50ms (local disk
read). A spinner would flash and disappear before the user sees it — more distracting than
useful. Chosen: blank (the HeaderBar provides visual stability).

**Client localStorage vs backend session-state.** localStorage is per-browser; the legacy
`session_state.json` is per-machine and survives browser clear/new browser. Backend authority
is correct for a single-user local tool. Chosen: backend endpoint.

**Redirect on mount vs lazy redirect.** Waiting for user interaction before redirecting breaks
the legacy "restore last session" UX. Redirect on mount (after fetch) matches the legacy
`_initialize_from_url` behaviour. Chosen: immediate redirect on mount.

**Error banner vs EmptyProjectState on fetch failure.** An error banner implies something is
wrong and the user should act. A session-state failure is benign (first run); EmptyProjectState
is the natural first-run experience. Chosen: silent fallback to EmptyProjectState.

## Consequences

- `deriveProjectId` must be consistent with how `AppState.discover_projects` registers project
  IDs. If the registration logic changes, the derivation must change too.
- If the user manually navigates back after a session-state redirect, the browser history entry
  is the replaced `/` — they land on the empty state, not on the redirected page (correct;
  replace mode is intentional).
- `GET /api/session-state` must be registered in the msw test server mock; failing to do so
  will cause the Vitest test to fail with `onUnhandledRequest: "error"`.

## Open questions

None.

## References

- `specs/03-frontend.md §176` — `/` route behaviour
- `specs/13-driver-contract.md §1` — URL invariants including `/` redirect cases
- `specs/09-persistence.md §session_state.json` — sidecar file that the backend reads
- `frontend/src/pages/RootPage.tsx` — implementation
- `frontend/src/pages/RootPage.test.tsx` — unit tests

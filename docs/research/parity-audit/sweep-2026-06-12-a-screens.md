# Parity sweep 2026-06-12 — Dimension A (screens / nav / chrome / global hotkeys)

Live-verified browser audit at commit `d0ba846` (includes SEL-3 rail↔radio fix).
Server: standalone uvicorn seeded via `_ingest_ocr_result` event-store pattern
(exercise-fixture, 8 pages, real line_matches). Fresh `make frontend-build`
confirmed (`/healthz` → `0.2.1.dev63+gd0ba846d6`).

Verdict key: PASS = visible + enabled + real effect observed.
PARTIAL = reachable but degraded/incomplete. FAIL = no working reachable path.
N-A = not applicable (capability retired/moved by design with CT sign-off).

| # | Capability | Verdict | Evidence |
|---|---|---|---|
| A-01 | Session restore (GET `/` → last project/page) | PASS | Fresh browser → `/` redirected to `/projects/exercise-fixture/pages/pageno/1` (POST load + navigate). |
| A-02 | Reach project list from a project page ("Projects" header link) | FAIL | Clicked "Projects" link → landed on `/` → session-redirect immediately bounced back to the project page. `HeaderBar.tsx:146` `Link to="/"` passes no `skipSessionRedirect`; `RootPage.tsx:501` redirects whenever a session exists. **Project list is unreachable via UI while a session exists** (only the 404 path or a failed load shows it) — so switching projects via the card grid is impossible in normal use. Legacy header dropdown was always reachable (`project_load_controls.py:91`). |
| A-03 | Unknown project route → toast + redirect to root | PASS | `/projects/does-not-exist/pages/pageno/1` → redirected to `/` (~5–10 s, query retries) with 1 sonner toast; grid rendered (skipSessionRedirect honored). |
| A-04 | RootPage project grid + project cards | PASS | `root-projects-grid` + `project-card-exercise-fixture` visible. |
| A-05 | Hero band | PASS | `root-hero-band` visible. |
| A-06 | Project search filters grid + empty-search state | PASS | "zzz-no-match" → `root-empty-search` shown; "exercise" restores card. |
| A-07 | Project filter chips (all/active/complete/archived) | PARTIAL | Chips render and toggle, but `RootPage.tsx:316-319` comment: non-"all" status filters **show all projects** (no API status field) — chips are cosmetic no-ops. |
| A-08 | Project card action menu (Delete / Archive entries) | PASS | Menu opens; `project-card-delete/archive-exercise-fixture` visible+enabled (effects = dim C). |
| A-09 | OCR config from root / no-project context (#405) | PASS | `ocr-config-trigger-button` visible on root; click opens the modal. S6 fix confirmed live — #405 can close. |
| A-10 | Source-folder dialog (open, browse, Use Current, Cancel) | PASS | "Open source folder" button on grid opens dialog; all 8 `source-folder-*` controls visible; Up changed path `/tmp/.../source` → `/tmp/...`; Use Current copied current path into input; Cancel closed. Note: trigger button itself has **no testid**. |
| A-11 | Legacy project select dropdown + LOAD button | PASS (re-mapped) | Capability (pick project + load) lives in the card grid (`project-card-open-*`, verified A-13). The legacy surface `ProjectLoadControls.tsx` is **dead code — never imported/mounted**, yet driver-contract §2.1 (13-driver-contract.md:89-97) still lists `project-select` / `load-project-button` / `source-folder-button` as "real". Contract-doc gap. |
| A-12 | Theme chips Dark/Light/System | PASS | Clicking Light/Dark flips `document.documentElement.dataset.theme` `light` ↔ `dark`. |
| A-13 | Project card Open → project page | PASS | Click `project-card-open-exercise-fixture` → navigated to `/projects/exercise-fixture/pages/pageno/1`, loading overlay cleared. |
| A-14 | Resolved project path label in header (S6.2) | PASS | `project-root-label` visible on project route, text `/tmp/.../source/exercise-fixture`. (Renders only after projectQ settles — briefly absent right after navigation.) |

### Cross-cutting findings (batch 1)

- **NEW — duplicate testids: hidden HeaderBar driver stubs shadow real dialog controls.** `HeaderBar.tsx` hidden-stub block renders `source-folder-up-button` etc. with `data-testid-stub="true"`; when the real SourceFolderDialog is open, page-level `[data-testid=…]` matches 2 elements and `.first` resolves to the invisible stub (Playwright click times out). Driver must scope queries inside `source-folder-dialog`. Contract should either drop the stubs or document the scoping requirement.
- **NEW — console error spam on project page:** `Konva has no node with the type div. Group will be used instead.` repeated ≥5× on every project-page load — a DOM `<div>` is being rendered inside a react-konva tree somewhere. Not user-visible but indicates a real rendering bug.

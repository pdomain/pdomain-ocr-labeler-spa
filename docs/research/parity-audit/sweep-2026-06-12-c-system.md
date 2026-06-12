# Sweep 2026-06-12 — Dimension C (document / project / system actions)

Live-verified refresh of the dimension-C parity rows. Method: seeded
exercise-fixture server (event-store seed via `_ingest_ocr_result` +
`_register_page_in_project`, same as `tests/e2e/exercise_real_project.py`),
driven in a real Chromium via Playwright MCP; durability checked via API
re-fetch and files on disk.

Acceptance per row = **VISIBLE + ENABLED + real EFFECT** (durable where
applicable). A testid existing is not parity.

Server: worktree `agent-ae30520f4d388f99c` @ `d0ba846` (rebased onto local
main), fresh `make frontend-build`, `http://127.0.0.1:8931`,
data roots under `/tmp/c-audit/run/`.

## Verdict table

| Row | Capability (legacy ref) | Verdict | Evidence |
|---|---|---|---|
| C01 | List/select projects (legacy C-09 dropdown) | PASS (resurfaced) | RootPage card grid replaces dropdown; `project-card-exercise-fixture` visible; search + filter chips work. No `project-select`/`load-project-button` testids anywhere (legacy testids dropped — driver-contract note). |
| C02 | Load/open project (C-10) | PASS | `project-card-open-…` click → POST /api/projects/load 200 → navigates to `/projects/{id}/pages/pageno/1`. |
| C03 | Open source-folder dialog (C-01) | PASS (resurfaced) | "Open source folder" button on RootPage filter bar (no testid; legacy `source-folder-button` exists only as hidden `data-testid-stub`). Dialog opens with all controls visible+enabled. |
| C04 | Picker: browse into child dir (C-02) | PASS | `fs-ls-entry-dummy-proj` click descends; current-path label updates. |
| C05 | Picker: Home (C-03) | PASS | label → `~` (home) after click. |
| C06 | Picker: Up (C-04) | PASS | `/tmp/c-audit/run/source` → `/tmp/c-audit/run`. |
| C07 | Picker: Open Typed Path (C-05) | PASS | typed `/tmp/c-audit/alt-source` + click → browses there *without* applying. |
| C08 | Picker: Use Current (C-06) | PASS | copies browsed dir into path input. |
| C09 | Apply source root (C-07) | PARTIAL | Works on default port 8080: POST /source-root 200, `config.yaml` written (`source_projects_root` line verified on disk), project list re-scanned (dummy-proj card appears), restore round-trip OK. **BUG: on any non-default port the browser POST 403s** — `LocalTrustMiddleware` (`middleware/local_trust.py:64`) rejects any `Origin` not in a fixed allowlist (8080/5173/bare) even when `Sec-Fetch-Site: same-origin` passed. Reproduced: `Origin: http://127.0.0.1:8931` + `Sec-Fetch-Site: same-origin` → 403; same POST with `Origin: …:8080` → 200. e2e suites miss it because they seed via httpx (no Origin) and run on random ports. Dialog shows "Request failed (403)" and root never changes. |
| C10 | Cancel source-folder dialog (C-08) | PASS | typed `/tmp` then Cancel → GET /api/projects root unchanged. |
| C11 | Deep link `/projects/{id}` (C-12) | PASS | redirects to `pageno/1`. |
| C12 | Deep link `/projects/{id}/pages/pageno/{n}` (C-13) | PASS | pageno/3 loads page 3 (`nav-page-input` = 3). 0-based `/pages/index/2` → `pageno/3` redirect also works. |
| C13 | Switch project while one is loaded (legacy header select, C-09/C-10) | FAIL | Project-route header has NO project-select / source-folder / change-project control (`change-project-button` exists only in a comment, ProjectLoadControls.tsx:15). `projects-home-link` click → `/` → session auto-resume bounces straight back to the loaded project (verified live). The RootPage grid is only reachable through the 404-redirect error path (`skipSessionRedirect`). A user cannot switch projects from the UI without restarting the server or hand-typing another project's URL. |
| C14 | Project delete / archive (SPA-new; backend DELETE exists) | FAIL | `project-card-delete-…` and `project-card-archive-…` render in card menu but `onClick` only closes the menu (RootPage.tsx:265–281) — pure stubs; `DELETE /api/projects/{id}` never called from UI. |

## Notes

- Hidden `data-testid-stub="true"` duplicates exist for many legacy testids
  (source-folder-\*, ocr-\* etc.). Selectors must exclude them
  (`:not([data-testid-stub])`); they otherwise mask the real elements.
- Playwright MCP browser wedged on this host (stale-DISPLAY issue per
  `tests/e2e/conftest.py`); sweep driven with repo-pinned Playwright +
  `DISPLAY` popped.

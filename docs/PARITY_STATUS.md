# Parity status — pd-ocr-labeler-spa vs pd-ocr-labeler

**Snapshot:** 2026-05-14 (post-iter-7 loop: `POST /api/projects/discover` +
`POST /api/projects/source-root` (config.yaml persistence) shipped; B-58
closed — `SessionState extra="ignore"` + WARNING-level dropped-keys log +
`persist_page_to_file` + `_resolve_save_directory` Save-lane helpers landed).
**Audience:** user, deciding next priorities.
**Scope:** what the SPA replacement covers today vs what the legacy
NiceGUI labeler ships.

---

## 1. One-paragraph status

The SPA is **scaffolding-complete; M1 done (~99%); M2 ~85% shipped**.
M1: settings + adapters + AppState + middleware + lifespan; B-51/B-58 both
closed. M2 backend routes: `GET /api/projects` + `POST /api/projects/load`
(full persistence I/O — image scan, ground-truth read, `project.json`
merge, `SessionState` writeback), `GET /api/projects/{id}`, `DELETE
/api/projects/{id}`, `POST /api/projects/discover` (force-rescan),
`POST /api/projects/source-root` (config.yaml persistence via
`core/persistence/config_yaml.py` + `SourceRootCarrier`). Save-lane
helpers (`persist_page_to_file`, `_resolve_save_directory`) landed;
`ensure_page_model` dispatcher (labeled → cached → OCR precedence)
landed. Still stub (501): `GET .../pages/{idx}`, `POST .../pages/{idx}/save`,
`POST .../pages/{idx}/load` — blocked on M3 OCR plumbing.
**Zero user-facing domain endpoints emit real page data yet** (no OCR,
no GT editing, no save/load payload, no export) — M3+ work.
**Q-A8 has now eased**: `mise` is installed in this dev environment
(verified `mise --version` 2026.5.1, `mise exec -- node --version`
v24.15.0, `mise exec -- npm --version` 11.12.1), so the previously
"can't iterate at all" frontend story is now "needs a single iter to
run `mise install` + `npm install` + commit `package-lock.json`".
That iteration hasn't run yet — the frontend (currently a single
smoke test) is still not built or runtime-verified, so the M0/M1
frontend acceptance bars remain ungated. Backend parity is
constrained to M2's prerequisite seams — adapters, request-id, audit
log, error envelope, image-cache route shape — none of which yet
read or write a real project.

---

## 2. Backend parity table

| Capability | Status | Notes |
|---|---|---|
| CLI entry (`pd-ocr-labeler-ui`) | ✅ done | `__main__.main()` parses `--host/--port/--reload/--data-root/-v/--no-browser`; opens browser; iter 47. Q-A13 deferred (`--log-level` not wired). |
| Healthcheck `/healthz` | ✅ done | M0; `tests/unit/test_healthz.py`. |
| Lifespan + shutdown clean | ✅ done | iter 48 closed the M1 acceptance gate; `tests/integration/test_lifespan.py`. B-69 (filter scoping) resolved iter 51. |
| Settings (env-driven, frozen) | ✅ done | `PDLABELER_*`; spec §3 fields filled iter 51 (B-63 closed). |
| Storage adapter (filesystem) | ✅ done | Path-traversal guard; B-44/B-45/B-53/B-54 mostly closed. No S3/cloud impl (per D-019). |
| Auth adapter (none) | ✅ done | B-42 still open re: `verify` signature drift from spec §7. |
| OCR adapter Protocol | 🟡 partial | Protocol + `none_`/`local_doctr`/`modal`/`shared_container` files exist; **bodies are `NotImplementedYet`**. Real OCR lands M3. |
| Request-ID middleware + audit log | ✅ done | Raw-ASGI rewrite iter 41 (B-50); `request_start`/`request_end` iter 36; B-43/B-50/B-56 closed. |
| Error handler (500 envelope) | ✅ done | Catch-all wired; B-51 closed iter 53 (`Settings.debug_unhandled_traceback` flag — D-040). |
| Image-cache HTTP route | 🟡 partial | Route shape + 404-on-OSError logic landed (B-57); **no images served yet** because no project loads. |
| Static SPA fallback | ✅ done | `index.html` carries `Cache-Control: no-store` (B-62); reserved-prefix carve-out per spec §10 (B-66 resolved iter 51). |
| `/env.js` | ✅ done | Mode-gated; B-01 closed. |
| Project discovery (scan project root) | 🟡 partial | M2 slices 1+2+3+4+5 shipped. Slice 1 (iter 52): pure `resolve_initial_project` + `validate_project_dir`. Slice 2 (iter 53): `ActiveProjectCarrier` + DI + bootstrap. Slice 3 (iter 55): FastAPI lifespan startup hook so CLI/session boot opens a project. Slice 4 (loop iter-2/3): `core/project_enumeration.py` + `api/projects.py` `GET /api/projects` + `POST /api/projects/load` (interim stub). **Slice 5 (loop iter-5)**: persistence I/O wired — `POST /api/projects/load` now reads `pages.json`/`pages_manifest.json` (`core/persistence/ground_truth.py`), scans images + reads optional `project.json` to build a full `Project` model (`core/persistence/project_envelope.py`), mutates the new `ProjectState` carrier (`set_loaded_project` → seeds cursor, resets per-page-state map), and returns spec-canonical `LoadProjectResponse{project, current_page_index, generation}` (replacing slice-4 stub). `current_page: PagePayload` deferred to M3 (PagePayload requires PageRecord/EncodedDims/LineMatch[]/image-cache-URLs); slice 5 ships `current_page_index: int` instead — URL stable so M3 expansion is field-rename only. 41 new tests across `tests/unit/core/persistence/test_ground_truth.py`, `tests/unit/core/persistence/test_project_envelope.py`, and `tests/integration/test_projects_router.py` (422 → 463). **Iter 6 closeout**: `GET /api/projects/{id}` reader landed (`c49f14f` — returns active `LoadProjectResponse` or 404); session-state writeback on `POST /api/projects/load` landed (`885ccf0` — atomic write per spec §02-backend §5.2 + §09-persistence §6). **Iter 7 (this session)**: `POST /api/projects/discover` (force-rescan variant of GET list) + `POST /api/projects/source-root` (reads/writes `config.yaml` via new `core/persistence/config_yaml.py` + `core/source_root_state.py` carrier; validates path, atomically persists, updates runtime carrier). Legacy: `operations/persistence/project_discovery_operations.py`, `project_operations.py`. |
| Session restore (last project, last page) | ✅ done | `core/persistence/session_state.py` reader (iter 44) + lifespan caller (iter 55) + writer wired into `POST /api/projects/load` (loop iter 6, `885ccf0`) — every load now persists `last_project_path` so next boot restores it. **B-58 closed** (iter 7): `extra="ignore"` + WARNING-level `session_state_extras_dropped` log (D-041). |
| Page enumeration (`pages.json` / manifest) | ✅ done | `core/persistence/ground_truth.py` (loop iter-5) — byte-compat re-implementation of legacy `load_ground_truth_from_directory`: manifest-first with offset-remap, single-file `pages.json` fallback, PGDP normalization, lowercase + extension-less aliases, every failure mode → warn-and-empty. |
| OCR overlay data (paragraphs/lines/words + bboxes) | ⬜ not started | M3–M4. |
| Ground-truth editing endpoint | ⬜ not started | M5 (`POST /api/.../words/{wid}/ground-truth`). |
| Word/line/paragraph batch ops + role labels | ⬜ not started | M6 toolbar + role-label preservation (per user-memory rule). |
| Refine bboxes (page + project) | ⬜ not started | M7 job; `pd-book-tools` `bbox.refine_robust` is the upstream dep (D-026, delegated). |
| Save / atomic-write `<project>_NNN.json` | ⬜ not started | M8; `UserPageEnvelope` v2.1 byte-compat. |
| Save Project (multi-page job) | ⬜ not started | M8 SSE job. |
| Export (per-style `labels.json`) | ⬜ not started | M9. |
| Notification SSE | ⬜ not started | M9. |
| Auto-rotation pass | ⬜ not started | M9.2; gated on pd-book-tools `rotation` module + Q-A1 envelope bump. |

---

## 3. Frontend parity table

Almost every row reads ⛔ **Q-A8** (mise is now installed but the
frontend has not yet been bootstrapped — `mise install` + `npm
install` + `package-lock.json` commit + first `npm run build` haven't
run; the rows below stay ⛔ until that iteration lands).

| Capability | Status | Notes |
|---|---|---|
| Vite + React 19 + Vitest scaffold | 🟡 partial | Files exist (App.tsx + smoke test); **never built or run end-to-end**. |
| Tailwind / shadcn pin | 🟡 partial | `tailwind.config.js` content-glob test passes by inspection (B-18 resolved); shadcn not actually installed. |
| ESLint config | ⬜ not started | Q-A9 picked (A) by default; `eslint.config.ts` not yet authored. |
| Header bar + EmptyProjectState | ⛔ Q-A8 | M1 acceptance test specifies `data-testid="project-load-button"`; not authored. |
| Project load controls + dropdown | ⛔ Q-A8 | M2. |
| SourceFolderDialog | ⛔ Q-A8 | M2. |
| OCRConfigModal | ⛔ Q-A8 | M3. |
| Page image canvas (Konva) | ⛔ Q-A8 | M3 base + M4 overlays. |
| BBox overlays (paragraph/line/word) + drag selection | ⛔ Q-A8 | M4; legacy color-parity required (`image_tabs.py:280-285`). |
| WordMatchView (virtualised) + LineCard + WordCell | ⛔ Q-A8 | M5. |
| Inline GT edit (Tab/Shift-Tab/Enter) | ⛔ Q-A8 | M5. |
| Toolbar action grid (page/paragraph/line/word scopes) | ⛔ Q-A8 | M6. |
| WordEditDialog (split/merge/erase/nudge/refine) | ⛔ Q-A8 | M7. |
| Save/Load/Rematch GT buttons + SaveStatus | ⛔ Q-A8 | M8. |
| Driver-contract `data-testid` conformance | ⛔ Q-A8 | M8 conformance test; legacy testids must be byte-identical. |
| Export dialog | ⛔ Q-A8 | M9. |
| Hotkey help modal + full keyboard audit | ⛔ Q-A8 | M9.5 (D-022). |

---

## 4. Outstanding blockers (user-decision queue)

| Q | Why it gates work |
|---|---|
| **Q-A8** Frontend toolchain | **Eased 2026-05-07.** mise is now installed in the dev container; `mise exec -- node` and `mise exec -- npm` resolve cleanly. The remaining work is mechanical: a single iteration that runs `mise install` + `mise exec -- npm install` inside `frontend/`, commits `frontend/package-lock.json`, runs `mise exec -- npm run build` once to populate `src/pd_ocr_labeler_spa/static/`, then verifies `make frontend-test`/`make frontend-build`/`make build` end-to-end. After that lands, M0 acceptance criteria 2-6 can flip green and the M1 `data-testid="project-load-button"` driver-contract test becomes runnable. |
| **Q-A12** `session_state.json` extras-tolerance | **Closed** 2026-05-14 — `extra="ignore"` + WARNING-level `session_state_extras_dropped` log implemented (D-041). B-58 closed. |

(Q-A11 — 500 redact-vs-verbatim — **resolved + implemented** iter 53 per
D-040; B-51 closed. Q-A13 `--log-level` resolved (D) drop; no action
needed.)

---

## 5. Open bugs of consequence (medium+)

| ID | Severity | One-line |
|---|---|---|
| **B-42** | low | `IAuth.verify` signature drifts from spec §7 (`creds: HTTPAuthorizationCredentials \| None` → `credentials: str \| None`). One-line spec/impl alignment. |

(B-72 closed iter 7 — test isolation fixed before this snapshot. B-58 closed iter 7 — `extra="ignore"` + WARNING log implemented.)

Everything else open is **nit/low** (B-68 browser-open race, B-70
empty-string `--host` bypass, B-71 `_keepalive` micro-leak). Full table
in `docs/BUGS_FOUND.md`. **B-51 closed iter 53** (D-040 impl).

---

## 6. Recommendation: next priorities

(B-58, B-72, Q-A12 all closed as of 2026-05-14. Remaining medium work:)

1. **Bootstrap the frontend toolchain (Q-A8 mechanical
   close)** (~30 min, requires outbound network for the npm
   registry). Run `mise install` (Node 24 + Python 3.13 per
   `mise.toml`), then `mise exec -- npm install` inside `frontend/`,
   commit `frontend/package-lock.json`, run `mise exec -- npm run
   build` once to populate `src/pd_ocr_labeler_spa/static/`, then
   verify `make frontend-test` + `make frontend-build` + `make build`.
   This flips M0 acceptance criteria 2-6 green and the M1
   `data-testid="project-load-button"` driver-contract sanity test
   from `specs/16-milestones.md:144` becomes runnable.
2. **Close B-42** (~5 min). `IAuth.verify` signature drift — one-line
   spec/impl alignment.
3. **M3 OCR plumbing** — wire `LocalDoctrPageLoader` + `GET /api/projects/{id}/pages/{idx}`
   real impl. Requires `pd_book_tools` OCR adapter.

---

## 7. Risk register

1. **Frontend backlog compounds until the Q-A8 bootstrap iter
   runs.** mise is installed (2026-05-07) but `npm install` /
   `package-lock.json` / first `npm run build` haven't happened yet.
   Every iter that lands a backend endpoint without its frontend
   half widens the gap that one bursty session has to close.
   **Mitigation:** schedule the bootstrap iter soon so frontend +
   backend can co-evolve; in the meantime, keep frontend work
   tightly tied to its spec (write the component .tsx by inspection
   the day the endpoint lands) so the eventual catch-up is
   mechanical, not design-from-scratch.
2. **`UserPageEnvelope` v2.1 byte-compat is unproven.** No
   round-trip test against a legacy-written file exists yet; M8 will
   discover divergence late if M3's reader/writer drifts. **Mitigation:**
   ship `tests/integration/test_envelope_round_trip.py` (golden
   file from a real legacy save) **the same iter** the M3
   reader/writer lands, not at M8.
3. **OCR adapter is currently a Protocol with no tested
   implementation.** The first M3 iter will discover whether
   `Document.from_image_ocr_via_doctr` integrates cleanly into the
   adapter shape, or whether the protocol needs revision. **Mitigation:**
   stand up `tests/integration/test_first_ocr.py` against a tiny
   fixture image (one page, no real model) before M3 closes; the
   real-model path can stay slow/marked.

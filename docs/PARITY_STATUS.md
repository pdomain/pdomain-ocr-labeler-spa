# Parity status — pd-ocr-labeler-spa vs pd-ocr-labeler

**Snapshot:** 2026-05-07 (post-iter-6 loop: M2 slice 5 persistence I/O
wired into POST /api/projects/load + `GET /api/projects/{id}` reader +
`session_state.json` writeback on load).
**Audience:** user, deciding next priorities.
**Scope:** what the SPA replacement covers today vs what the legacy
NiceGUI labeler ships.

---

## 1. One-paragraph status

The SPA is **scaffolding-complete and ~97% through M1** (settings +
adapters + AppState + middleware + lifespan; B-51 closed iter 53 per
D-040). **M2 startup-discovery: slice-4 router shipped, M2-proper state
in progress** (slice 1: `resolve_initial_project` +
`validate_project_dir`; slice 2: `ActiveProjectCarrier` + DI providers

+ bootstrap wiring; slice 3: FastAPI lifespan startup hook calls
`resolve_initial_project(settings, session_state=load_session_state(...))`
and feeds the result into
`app.state.active_project_carrier.set_active_project()`, so a CLI-or-
session-restored project is now actually opened on boot. Slice 4 (iter
2): pure `core/project_enumeration.py` scanner. Slice 4 router (iter 3):
`api/projects.py` with `GET /api/projects` + `POST /api/projects/load`
(interim slim `LoadProjectResponseStub` because spec-canonical
`Project` + `PagePayload` models are M2-proper). M2-proper container
(iter 4): `core/project_state.py` skeleton + `core/models.py::Project`
landed — `ProjectState` carrier ready to hold the loaded `Project` +
per-page-state map, awaiting slice-5 persistence I/O to actually
construct one from disk. HTTP project swaps work end-to-end against
the carrier; the SPA can drive load + dropdown re-mark, but no page
graph yet).
**Zero user-facing domain endpoints exist yet** (no project discovery
list, no OCR, no GT editing, no save/load, no export) — every legacy
capability past "boots and serves `/healthz`" is **not started**.
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
| Project discovery (scan project root) | 🟡 partial | M2 slices 1+2+3+4+5 shipped. Slice 1 (iter 52): pure `resolve_initial_project` + `validate_project_dir`. Slice 2 (iter 53): `ActiveProjectCarrier` + DI + bootstrap. Slice 3 (iter 55): FastAPI lifespan startup hook so CLI/session boot opens a project. Slice 4 (loop iter-2/3): `core/project_enumeration.py` + `api/projects.py` `GET /api/projects` + `POST /api/projects/load` (interim stub). **Slice 5 (loop iter-5)**: persistence I/O wired — `POST /api/projects/load` now reads `pages.json`/`pages_manifest.json` (`core/persistence/ground_truth.py`), scans images + reads optional `project.json` to build a full `Project` model (`core/persistence/project_envelope.py`), mutates the new `ProjectState` carrier (`set_loaded_project` → seeds cursor, resets per-page-state map), and returns spec-canonical `LoadProjectResponse{project, current_page_index, generation}` (replacing slice-4 stub). `current_page: PagePayload` deferred to M3 (PagePayload requires PageRecord/EncodedDims/LineMatch[]/image-cache-URLs); slice 5 ships `current_page_index: int` instead — URL stable so M3 expansion is field-rename only. 41 new tests across `tests/unit/core/persistence/test_ground_truth.py`, `tests/unit/core/persistence/test_project_envelope.py`, and `tests/integration/test_projects_router.py` (422 → 463). **Iter 6 closeout**: `GET /api/projects/{id}` reader landed (`c49f14f` — returns active `LoadProjectResponse` or 404); session-state writeback on `POST /api/projects/load` landed (`885ccf0` — atomic write per spec §02-backend §5.2 + §09-persistence §6). **Still deferred**: `POST /api/projects/discover` + `POST /api/projects/source-root` (YAML config plumbing — M2-proper). Legacy: `operations/persistence/project_discovery_operations.py`, `project_operations.py`. |
| Session restore (last project, last page) | ✅ done | `core/persistence/session_state.py` reader (iter 44) + lifespan caller (iter 55) + writer wired into `POST /api/projects/load` (loop iter 6, `885ccf0`) — every load now persists `last_project_path` so next boot restores it. **B-58 open** (extras-tolerance for legacy fields beyond `UserPageEnvelope`; D-041 decided, impl pending). |
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
| Header bar + EmptyProjectState | 🟡 spec written | #83 → `specs/21-header-bar.md`; #85 → `specs/22-root-page.md` |
| Project load controls + dropdown | 🟡 spec written | Covered in #83 (`specs/21-header-bar.md`) |
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
| **Q-A12** `session_state.json` extras-tolerance | **Resolved** 2026-05-07 → option (A) with WARNING-level drift signal (D-041). **Implementation pending.** B-58 still open: one-line code change (`extra="ignore"` + `logger.warning("session_state_extras_dropped …")`) + spec §6 amend. Iter 54 candidate. |

(Q-A11 — 500 redact-vs-verbatim — **resolved + implemented** iter 53 per
D-040; B-51 closed. Q-A13 `--log-level` resolved (D) drop; no action
needed.)

---

## 5. Open bugs of consequence (medium+)

| ID | Severity | One-line |
|---|---|---|
| **B-72** | medium | `tests/unit/api/test_static_mounts.py` `test_spa_static_asset_does_not_set_no_store` + `test_spa_fallback_serves_static_asset_directly` call `asset.parent.rmdir()` on `static/assets/` — fails after `make frontend-build` populates the dir. Real `make test` regression. |
| **B-58** | medium | `SessionState` `extra="forbid"` breaks D-003 forward-compat; D-041 decided (A), impl pending. |
| **B-42** | low | `IAuth.verify` signature drifts from spec §7 (`creds: HTTPAuthorizationCredentials \| None` → `credentials: str \| None`). One-line spec/impl alignment. |

Everything else open is **nit/low** (B-68 browser-open race, B-70
empty-string `--host` bypass, B-71 `_keepalive` micro-leak). Full table
in `docs/BUGS_FOUND.md`. **B-51 closed iter 53** (D-040 impl).

---

## 6. Recommendation: morning priorities

1. **Close B-72** (~5 min, this iter). Two test-isolation cases that
   `rmdir()` `static/assets/` and now break `make test` whenever a
   real frontend bundle is present. Stop-the-bleed on a green CI.
2. **Close B-58 per D-041** (~15 min, no Node needed). One-line
   `extra="ignore"`, WARNING-level dropped-keys log, spec §6 amend,
   one regression test. Locks in the D-003 contract before M2 starts
   writing session_state.
3. **M2 slice 3 — lifespan wiring** (~30 min, no Node needed). Add
   the FastAPI lifespan startup hook that calls
   `resolve_initial_project(settings, session_state=load_session_state(...))`
   and feeds the result into `app.state.active_project_carrier
   .set_active_project()`. Brings slice 1 + slice 2 + iter-44
   `session_state.load` together for the first time. Pin via a new
   `tests/integration/test_lifespan.py` row.
4. **Bootstrap the frontend toolchain (Q-A8 mechanical
   close)** (~30 min, requires outbound network for the npm
   registry). Run `mise install` (Node 24 + Python 3.13 per
   `mise.toml`), then `mise exec -- npm install` inside `frontend/`,
   commit `frontend/package-lock.json`, run `mise exec -- npm run
   build` once to populate `src/pd_ocr_labeler_spa/static/`, then
   verify `make frontend-test` + `make frontend-build` + `make build`.
   This flips M0 acceptance criteria 2-6 green and the M1
   `data-testid="project-load-button"` driver-contract sanity test
   from `specs/16-milestones.md:144` becomes runnable. (mise
   itself is already on PATH as of 2026-05-07; the gap is just the
   single bootstrap iteration.)
5. **M2 slice 5 — persistence I/O + wire the loaded `Project`
   through `POST /api/projects/load`**. The spec-proper M2 split
   (delivered iter-by-iter): slice 4 starter (iter 2) shipped pure
   `core/project_enumeration.py`; slice 4 router (iter 3) shipped
   `api/projects.py`; iter 4 shipped `core/project_state.py` +
   `core/models.py::Project` (the M2-proper carrier). **Remaining
   iter-5 work**: `core/persistence/{project_envelope, ground_truth}.py`
   to read `pages.json` / `pages_manifest.json` + scan GT files +
   build a `Project`; then extend the `POST /api/projects/load`
   handler to `state.set_loaded_project(project)` and replace
   `LoadProjectResponseStub` with the spec-canonical
   `LoadProjectResponse{project, current_page}`; then `api/pages.py`
   (record-only payload). Acceptance test
   `tests/integration/test_project_load.py::test_load_real_fixture`
   needs only Python. The frontend half waits on Q-A8 but the
   integration tests + GT-variant matching tests carry over from
   legacy `test_ground_truth.py` and ship pure-Python value today.

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

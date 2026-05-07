# Parity status — pd-ocr-labeler-spa vs pd-ocr-labeler

**Snapshot:** 2026-05-07, after iter 54 of the spec-driven /loop.
**Audience:** user, deciding next priorities.
**Scope:** what the SPA replacement covers today vs what the legacy
NiceGUI labeler ships.

---

## 1. One-paragraph status

The SPA is **scaffolding-complete and ~97% through M1** (settings +
adapters + AppState + middleware + lifespan; B-51 closed iter 53 per
D-040). **M2 startup-discovery is at slice 2/4** (`resolve_initial_project`
+ `validate_project_dir` from slice 1, plus `ActiveProjectCarrier` +
DI providers + bootstrap wiring from slice 2 — but **no lifespan hook
yet** to actually call `set_active_project` from
`resolve_initial_project`'s output, and **no `/api/projects/load`
route**, so end-to-end "open a project" still doesn't work).
**Zero user-facing domain endpoints exist yet** (no project discovery
list, no OCR, no GT editing, no save/load, no export) — every legacy
capability past "boots and serves `/healthz`" is **not started**. The dominant blocker is **Q-A8**: the
devcontainer has no Node/npm/mise, so the entire frontend (currently a
single smoke test) cannot be built or runtime-verified, which gates M2
acceptance and everything past it. Backend parity is constrained to
M2's prerequisite seams — adapters, request-id, audit log, error
envelope, image-cache route shape — none of which yet read or write a
real project.

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
| Project discovery (scan project root) | 🟡 partial | M2 slice 1 (iter 52) shipped pure `resolve_initial_project` + `validate_project_dir`; M2 slice 2 (iter 53) shipped `ActiveProjectCarrier` + DI providers + `app.state.active_project_carrier` wiring. **No enumeration of `source_projects_root`** (M2-proper `core/project_state.py`) and **no lifespan hook** invoking the resolver yet. Legacy: `operations/persistence/project_discovery_operations.py`. |
| Session restore (last project, last page) | 🟡 partial | `core/persistence/session_state.py` reader exists (iter 44); writer + lifespan caller not wired; **B-58 open** (extras-tolerance; D-041 decided, impl pending). |
| Page enumeration (`pages.json` / manifest) | ⬜ not started | M2. |
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

Almost every row reads ⛔ **Q-A8** (no Node/npm/mise in the devcontainer
and `make mise-setup` requires outbound network not available in /loop).

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
| **Q-A8** Frontend toolchain | Without Node/npm in the dev environment, **no frontend iteration is verifiable**. Either add `ghcr.io/devcontainers/features/node:1` to `.devcontainer/devcontainer.json` (workspace-owner action, outside this repo), or run `make mise-setup && make frontend-install` from an interactive shell with network. Until resolved, M2 cannot close acceptance and M3–M9 cannot start their frontend halves. |
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
| **B-42** | low | `IAuth.verify` signature drifts from spec §7 (`creds: HTTPAuthorizationCredentials | None` → `credentials: str | None`). One-line spec/impl alignment. |

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
4. **Resolve Q-A8** (workspace-owner action). The single biggest
   unblock available. Until Node is on PATH, every iteration past M1
   is **backend-only**, and M1 itself can't fully close (the
   `data-testid="project-load-button"` driver-contract sanity test
   from `specs/16-milestones.md:144` is unverifiable). Adding the
   devcontainer Node feature is a one-line edit to a file outside
   this repo's edit boundary.
5. **M2 slice 4 — `core/project_state.py` + `api/projects.py`** (the
   spec-proper M2 work). Author `core/project_state.py`,
   `core/persistence/{project_envelope, ground_truth}.py`,
   `api/projects.py`, `api/pages.py` (record-only payload).
   Acceptance test `tests/integration/test_project_load.py
   ::test_load_real_fixture` needs only Python. The frontend half
   waits on Q-A8 but the integration tests + GT-variant matching
   tests carry over from legacy `test_ground_truth.py` and ship
   pure-Python value today.

---

## 7. Risk register

1. **Frontend backlog compounds while Q-A8 is unresolved.** Every
   iter that lands a backend endpoint without its frontend half
   widens the gap that someone has to close in one bursty session
   when Node finally arrives. **Mitigation:** keep frontend work
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

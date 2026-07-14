---
kind: plan
status: draft
owner: maintainers
created: 2026-07-14
last_verified: 2026-07-14
---

# Labeler SPA confirmed bug fixes (2026-07-14)

## Agent Index

- **Kind:** plan
- **Status:** draft
- **Read when:** wiring the suite compute-device pref into OCR execution, adding
  the reload_ocr timeout / OCR concurrency cap, or fixing the stale api-client doc.
- **Search terms:** device pref, PredictorCache device_resolver, reload_ocr
  timeout, OCR concurrency cap, api client doc, pin deferral.

## Goal

Fix four confirmed bugs; defer the blocked pin bump. Do NOT add auth (no-auth by v1 design D-005/D-042). Do NOT touch the suite app_id mount (already correct here).

## Architecture

- **Device pref (Task 1):** new `core/ocr/device_pref.py::resolve_ocr_device_override()` reads the suite pref via `resolve_effective_device(LocalFilePrefs(), "pdomain-ocr-labeler-spa")`, normalizes to a torch device string or None ("local"/unset → None = keep auto-detect). `PredictorCache` gains an optional `device_resolver` kwarg and applies it via a uniform post-build `predictor.to(device)` (verified: `get_default_doctr_predictor` has no `device` param, so `.to()` is the seam, not a factory kwarg). `bootstrap.py` wires it; `describe_device()` gains an optional override for an honest startup banner.
- **Timeout (Task 2):** `Settings.ocr_timeout_s: float = 900.0` (`PDLABELER_OCR_TIMEOUT_S`, <=0 disables); wrap `reload_ocr.py`'s `asyncio.to_thread(loader.run_ocr,...)` in `asyncio.wait_for`; on TimeoutError queue a NEGATIVE notification + re-raise (existing failure path). Honest limitation: the OS thread survives.
- **Concurrency cap (Task 3):** `JobRunner` gains `max_concurrent_ocr_jobs: int = 1` + an `asyncio.Semaphore` acquired in `_run_one` ONLY for `{reload_ocr, rotate_page, auto_rotate_all}` (the handlers that call run_ocr). save_project/export/refine_bboxes stay unbounded. <=0 disables.
- **Stale doc (Task 4):** rewrite `docs/architecture/03-frontend.md` §7 to match the real `ApiClient` (no getAuthToken, no Authorization — no-auth by design); bump last_verified; docgraph reindex+check.

## Tech Stack

FastAPI 0.139, Pydantic v2 (`PDLABELER_` env prefix), asyncio job runner, pdomain-ops suite prefs (resolve_effective_device / LocalFilePrefs — present in the installed version), pytest (`asyncio_mode=auto`), Vitest.

## Global Constraints

- No auth. No touching the suite app_id mount. This app uses its own PredictorCache, not LocalStageDispatcher.
- TDD with real fixtures (stub_doctr_support, _FakePageLoader, the settings env-clear pattern). `make ci AI=1` before each commit; never bare pytest. Conventional commits. Worktree isolation. Nothing pushed.
- Collisions: Task 1 edits bootstrap.py:~483 (predictor cache); Task 3 edits bootstrap.py:~349 (runner) + settings.py; Task 2 edits settings.py + reload_ocr.py. Run Tasks 2+3 in one agent (shared settings.py/bootstrap.py); Task 1 in another (disjoint bootstrap region). Task 4 (doc) + Task 5 (pin comment) are done last, no overlap.
- After doc edits: docgraph reindex + check same-turn.

## Task 1 — Wire suite compute-device pref into OCR execution

Clean fix (vocabulary cpu/cuda:N/mps matches torch). `device_info.py:33-60` and `PredictorCache._build` (`predictor.py:145`) resolve device via raw torch and never read the pref. Add `device_pref.py` (best-effort, never raises), a `device_resolver` kwarg on PredictorCache applying `predictor.to(device)` post-build (swallow+log failures), wire in bootstrap, extend describe_device for the banner. TDD: pref "cpu" forces cpu even when torch.cuda monkeypatched available; unset/"local" preserves current behavior; `.to()` failure swallowed. Commit: `feat(compute): suite device preference governs OCR predictor`.

## Task 2 — Timeout on reload_ocr

`reload_ocr.py:274-289` awaits `asyncio.to_thread(loader.run_ocr,...)` with no timeout. Add `Settings.ocr_timeout_s`; wrap in `asyncio.wait_for`; `except TimeoutError` (before `except Exception`) queues NEGATIVE notification + re-raises so JobRunner marks ERROR. Document the OS-thread-survival limitation on the setting. TDD: integration test with a slow loader → job errors with "timed out". Commit: `fix(jobs): bound reload_ocr with PDLABELER_OCR_TIMEOUT_S`.

## Task 3 — Concurrency cap for OCR-heavy jobs

`runner.py:run_forever` spawns unbounded create_task. Add `Settings.max_concurrent_ocr_jobs=1` + a semaphore acquired in `_run_one` only for `{reload_ocr, rotate_page, auto_rotate_all}`; other job types stay unbounded. Wire from settings in bootstrap. TDD: 3 reload_ocr jobs → peak concurrency 1; 3 save_project → peak 3. Commit: `fix(jobs): cap concurrent OCR-heavy jobs`.

## Task 4 — Correct stale 03-frontend.md api-client section

`docs/architecture/03-frontend.md` §7 documents a fictional getAuthToken/Bearer client; the real `frontend/src/api/client.ts` is a plain ApiClient (no auth). Rewrite §7 to match, stating no-auth is by design (D-005/D-042); bump last_verified; docgraph reindex+check. Commit: `docs(frontend): re-verify api client against code`.

## Task 5 — Pin deferral (comment only)

`pyproject.toml` pins pdomain-ops>=0.11.0; 0.11.1 hard-pins fastapi<0.137+starlette==1.0.0, incompatible with this app's fastapi 0.139 (ocr-container-meta#399). Add a comment; no version change. Task 1 needs no version bump (resolve_effective_device already present). Commit: `docs: record pdomain-ops pin deferral (#399)`.

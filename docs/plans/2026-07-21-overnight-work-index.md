---
kind: plan
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
disposition: Overnight execution index for residual open work.
---

# Overnight work index — 2026-07-21

## Agent Index

- **Kind:** plan
- **Status:** active
- **Read when:** choosing what to implement next after open-issue review, or
  resuming overnight autonomous work.
- **Search terms:** overnight plan, open issues, backlog index, residual work

## Context

The GitHub Issues tracker for `pdomain/pdomain-ocr-labeler-spa` is empty. Open
work lives in local docs:

| Source | What it holds |
| --- | --- |
| `docs/issues/` | Former GH #430, #433 (active); #437, #460 (implemented) |
| `docs/context/open-findings.md` | Product/test defects still open |
| `docs/context/current-state.md` | High-level open work summary |
| `docs/plans/2026-06-14-labeler-spa-pgdp-alignment-backlog.md` | PGDP/ui alignment (partial) |
| `specs/20-glyph-annotations.md` | M11 glyph annotations (scaffold only) |
| Closed archive (git `5cdb276`) | Historical #366, #404, #267–#270 bodies |

**Stale pointers to ignore:**

- `AGENTS.md` still lists #366, #404, and “glyph FE not shipped” as open. #404
  already has `docs/process/lint-deviations.md`. Glyph components exist but are
  not fully wired. Prefer this index and the plans below over AGENTS.md for
  residual work.
- Issue tracker migration handoff (`docs/handoff/2026-07-17-…`) is largely done
  for the four open issues (migrated into `docs/issues/`).

## Cross-cutting prioritization (prefer when sequences conflict)

Deep multi-agent review roadmap (data integrity → export loop → M11 → findings
→ CI → PGDP chrome):

[`2026-07-21-deep-code-review-continuation.md`](2026-07-21-deep-code-review-continuation.md).

That plan is the **prioritization authority** for residual work. This overnight
index remains the short-horizon stream map for parallel night work that does
not touch store serialization.

## Plans produced this session

| Plan | Covers | Effort | Overnight priority |
| --- | --- | --- | --- |
| [`2026-07-21-deep-code-review-continuation.md`](2026-07-21-deep-code-review-continuation.md) | Full pipeline gap review + Waves 0–6 | L (roadmap) | **Authority for order** |
| [`2026-07-21-ci-openapi-gates.md`](2026-07-21-ci-openapi-gates.md) | Former #430 + #433 | S (~1–2 h) | Night-1 parallel-safe |
| [`2026-07-21-open-findings-fixes.md`](2026-07-21-open-findings-fixes.md) | BUG-KBD-1/5, SMOKE-3, RELOAD-1, HIER-1 | ~1 day | Night-1 parallel-safe |
| [`2026-07-21-tsconfig-test-strictness.md`](2026-07-21-tsconfig-test-strictness.md) | Residual #366 | S–M (~2–4 h) | Night-1 if CI free |
| [`2026-07-21-glyph-annotations-completion.md`](2026-07-21-glyph-annotations-completion.md) | M11 residual (~35% scaffold / ~20% usable) | L (multi-session) | After Wave 0 strategy (or T1 alone) |
| [`2026-07-21-pgdp-alignment-remaining.md`](2026-07-21-pgdp-alignment-remaining.md) | 14/16 PGDP items remaining | L | Night-1 docs + suite wire |

## Not work (already done)

| Item | Status | Evidence |
| --- | --- | --- |
| Former #437 OpenAPI schema quality | Implemented | `tests/conformance/test_response_models.py`, `tests/unit/api/test_route_conformance.py` |
| Former #460 resolver narrowing | Implemented | `api/words.py` / `api/pages.py` + `docs/context/decisions.md` |
| Former #404 lint-deviations.md | Implemented | `docs/process/lint-deviations.md` |
| BUG-KBD-4 ConfirmDialog Escape | Fixed | pdomain-ui Radix `AlertDialog` focus trap + Escape |

## Recommended overnight sequence

Cross-cutting order lives in
[`2026-07-21-deep-code-review-continuation.md`](2026-07-21-deep-code-review-continuation.md)
(**Wave 0 data integrity before chrome**). This index is the night stream map.

Execute with `superpowers:subagent-driven-development`. One worktree per
independent stream if parallelizing. Always `make ci AI=1` before commit. Do
not push unless explicitly asked.

### Hard gate (adversarial recheck 2026-07-21)

| Stream | May start without Wave 0? | Notes |
| --- | --- | --- |
| **A CI** | **Yes** | No store serialization |
| **B findings** (hotkeys, HIER-1, RELOAD UX) | **Yes** | Avoid `save_project` / sidecar mutators |
| **B+ XDG data_root** | Prefer after note | Migration note only if changing defaults |
| **C glyph T1 inject only** | **Yes** | Read-path only; **no T3 persist** until Wave 0.1 decision |
| **C glyph T3+ durable** | **No** | Requires Wave 0.1 strategy |
| **D PGDP docs / suite launcher** | **Yes** | Suite launcher is Wave 5 / item 5 |
| **E job SSE (new)** | **Yes** | Parallel-safe Wave 3a |
| **Wave 0 / 1 (sidecar, rematch, export CLI)** | Prefer **first** if capacity | Highest data-loss / closed-loop value |

### Stream A — CI hygiene (parallel-safe)

1. Implement [`2026-07-21-ci-openapi-gates.md`](2026-07-21-ci-openapi-gates.md)
   - Diff only `frontend/src/api/types.ts` in openapi-drift
   - Add `pre-commit` job + knip step
2. Optionally [`2026-07-21-tsconfig-test-strictness.md`](2026-07-21-tsconfig-test-strictness.md)
   after CI stream is green
3. Note residual: `behavior-coverage` is local-`make ci` only (P1-BEHAVIOR-COV)

### Stream B — Open findings (product correctness)

1. BUG-KBD-1 (`mod+,` → OCR Config)
2. BUG-KBD-5 (`mod+j` → focus page input)
3. BUG-SMOKE-3 (XDG `data_root`)
4. BUG-RELOAD-1 (zero-area / empty OCR)
5. BUG-HIER-1 (hierarchy E2E waits)
6. Update `docs/context/open-findings.md` (include BUG-KBD-4 resolved)
7. If capacity: canvas erase wire (**P1-CANVAS-ERASE**), image_drift banner
   (**P1-IMAGE-DRIFT**), J/K `selectLine` (**P1-MATCH-NAV**)

### Stream C — Glyph M11 (highest product value residual)

Start with critical backend read-path bug, then FE wiring:

1. Inject `glyph_annotations_map` / predictions into page payload (**T1** OK anytime)
2. Integration tests for glyph routes (**T2**)
3. Durable save/reload for glyph maps — **only after Wave 0.1** (**T3**)
4. FE mutation hooks + WordDetail mount
5. Chip click → panel; bulk invalidate
6. E2E later if time remains
7. Align scorecard wording to ~20% usable / ~35% scaffold

Do **not** rebuild glyph components; they already exist under
`frontend/src/components/glyph/`.

### Stream D — PGDP night-1 (docs + small code)

From [`2026-07-21-pgdp-alignment-remaining.md`](2026-07-21-pgdp-alignment-remaining.md):

1. Item 9 — formalize no-archive / permanent-delete decision (docs)
2. Item 2 — UI wrapper migration matrix (docs)
3. Item 3 residual — driver/drawer doc refresh
4. Item 5 — wire suite launcher shims to real `/api/suite/*`
5. Item 6 honesty — localStorage/`persistApp` intentional under D-042 (no prefs API)

Defer large items (workbench extract, U-M7 history panel, full jobs chrome) to
later sessions. Jobs pill needs **P1-JOBS-API** contract first.

### Stream E — Job SSE contract (new; parallel-safe)

From deep-plan Wave 3a:

1. Normalize flat backend SSE ↔ nested FE `JobProgressEvent`
2. Handle `snapshot` / `cancelled` event types
3. Pass real job type into BusyOverlay (not hard-coded `reload_ocr_page`)
4. Tests with flat backend fixtures

## Parallelism map

```text
Night start
├── Wave 0 data integrity ────── prefer if capacity (sidecar/rematch/save_project)
├── Stream A (CI) ────────────── independent
├── Stream B (findings) ──────── independent of A; avoid store mutators
├── Stream E (job SSE) ───────── independent
├── Stream C (glyph) ─────────── T1–T2 anytime; T3 after Wave 0.1
│                                avoid FE conflict with B on ProjectPage
└── Stream D (PGDP docs/suite) ─ suite wire may touch App.tsx; serialize vs C if needed
```

Safe concurrent pairs: **A + B**, **A + C(T1)**, **A + D**, **A + E**, **E + B**.
Avoid concurrent **B + C** on shared ProjectPage wiring without coordination.
Do **not** run glyph **T3** concurrent with Wave 0.2–0.4 without one owner.

## Exit criteria for a successful overnight run

- [ ] CI plan merged or local PR-ready: remote gates include pre-commit + knip;
      openapi-drift only checks `types.ts`
- [ ] At least keyboard findings KBD-1 and KBD-5 fixed with unit tests
- [ ] Glyph payload inject merged with failing→passing tests (Tasks 1–2 of glyph plan)
- [ ] PGDP night-1 docs items committed; suite launcher either fixed or
      explicitly deferred with reason
- [ ] This index updated with “Done tonight” / “Blocked” notes

## Done tonight / Blocked

*(Fill in after execution.)*

| Stream | Result |
| --- | --- |
| A CI | |
| B Findings | |
| C Glyph | |
| D PGDP | |
| E Job SSE | |
| Wave 0 data integrity | |

## Meta-tracker issues (out of this repo)

Open issues on `ConcaveTrillion/ocr-container-meta` that are **not** owned by
this SPA (do not plan here unless scoped):

- #400 trainer-spa compute-device
- #395–#398 simple-gui / ops
- #393 basedpyright roll-out
- #291 lint-deviation roll-out (this repo already has the catalogue)
- #267 family pd-ocr-trainer retirement milestone
- #210 / #257 versioning discipline

Workspace-wide items stay on the meta tracker.

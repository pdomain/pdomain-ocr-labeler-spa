---
kind: plan
status: active
owner: maintainers
created: 2026-07-14
last_verified: 2026-07-14
---

# PageRecord Import Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` to implement this plan task by task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

## Goal

Remove the Labeler's temporary `core.models.PageRecord` and `RotationSource`
compatibility exports after moving every caller to the shared
`pdomain_ops.pages` owner.

## Architecture

Keep Labeler-owned models in `core.models`. Import shared page lifecycle types
directly from `pdomain_ops.pages` at each production and test call site. This
changes import ownership only; wire and persistence shapes stay unchanged.

## Tech Stack

Python 3.12, Pydantic, FastAPI, pytest, basedpyright, and Ruff.

## Agent Index

- **Kind:** plan
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-14
- **Read when:** removing the PageRecord compatibility re-export.
- **Search terms:** PageRecord import convergence, pdomain_ops, core.models,
  compatibility facade.

---

## Global Constraints

- Do not change the PageRecord schema, API wire shape, or persisted payloads.
- Keep Labeler-only state in `extensions["labeler"]`.
- Preserve all tests and quality gates.
- Work locally on the isolated branch. Do not merge or push.

### Task 1: Prove the compatibility export is still present

**Files:**

- Modify: `tests/unit/core/test_models_no_local_pagerecord.py`

- [ ] **Step 1: Tighten the structural test**

  Replace the compatibility-accepting assertion with direct absence checks for
  `PageRecord` and `RotationSource` on `core.models`.

- [ ] **Step 2: Run the focused test and verify RED**

  Run:
  `uv run pytest tests/unit/core/test_models_no_local_pagerecord.py -q`

  Expected: two failures because both names are still exported.

### Task 2: Move callers to the shared owner and remove the facade

**Files:**

- Modify: `src/pdomain_ocr_labeler_spa/api/pages.py`
- Modify: `src/pdomain_ocr_labeler_spa/core/page_to_line_matches.py`
- Modify: `src/pdomain_ocr_labeler_spa/core/models.py`
- Modify: `tests/integration/test_rotate_router.py`

- [ ] **Step 1: Import shared types directly**

  Import `PageRecord` from `pdomain_ops.pages` in `api/pages.py` and
  `core/page_to_line_matches.py`. Import `PageRecord` and `RotationSource`
  directly in the rotation integration test.

- [ ] **Step 2: Remove the compatibility names**

  Remove the `pdomain_ops.pages` import and both names from `core.models.__all__`.

- [ ] **Step 3: Run focused tests and verify GREEN**

  Run:
  `uv run pytest tests/unit/core/test_models_no_local_pagerecord.py tests/unit/core/test_page_to_line_matches.py tests/integration/test_rotate_router.py tests/integration/test_validation_persist_round_trip.py -q`

  Expected: all selected tests pass with no failures.

- [ ] **Step 4: Run source quality gates**

  Run `make lint AI=1`, `make pre-commit-check AI=1`, and `make ci AI=1`.
  Expected: each command exits 0.

### Task 3: Record the completed convergence

**Files:**

- Modify: `docs/context/current-state.md`
- Modify: `docs/context/intent-map.md`
- Modify: `docs/decisions/2026-07-13-shared-page-record-boundary.md`

- [ ] **Step 1: Update durable context**

  Record direct shared imports as shipped state. Move the convergence item from
  active to done. Complete the decision record's consequences and supersession
  sections without changing the schema boundary.

- [ ] **Step 2: Run docgraph governance**

  Reindex with the docgraph MCP tool, then run `docgraph_check(strict=true)` and
  index health. Expected: zero issues and a healthy index.

- [ ] **Step 3: Run the final CI gate and commit**

  Run `make ci AI=1`, verify a clean diff, and create a truthful local commit.
  Do not merge or push.

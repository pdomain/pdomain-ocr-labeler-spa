---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-13
---

# 14 — Testing Strategy

The local gate combines backend pytest, frontend type/lint/format/unit checks, behavior coverage, packaging
and strict docgraph. Optional browser exercises remain a separate proof stage.

## Current test seams

Backend source is tested under `tests/unit`, `tests/integration` and `tests/conformance`. The latter
uses Ops PagePayload plus LabelerPageExtension contracts in `test_new_contract.py`, response models and
region/block round trips; the removed universal UserPageEnvelope read/write suites are not current gates.
Frontend tests use Vitest/jsdom, strict MSW handlers and ResizeObserver/matchMedia/EventSource stubs.

## Commands and coverage

`just test` invokes:

```sh
uv run pytest tests/ -v --ignore=tests/e2e -m "not slow and not integration" -n auto
```

The selection includes unmarked Docker integration tests. Coverage/branch reporting comes from existing
pytest addopts. The former 85% backend and 100% persistence statements are targets, not configured
fail-under thresholds in the current pyproject. They are not newly claimed passing coverage gates.

`just frontend-test` runs `vitest run`, without `--passWithNoTests` or `--coverage`. Vitest configuration
retains 80% global and 100% library thresholds for coverage-enabled runs. The ordinary CI recipe does not
activate those thresholds. `just frontend-typecheck` checks both application and test TypeScript projects.
Generated API types remain excluded from formatting; lint-check recipes are read-only.

## Browser fixtures and limits

`tests/e2e/conftest.py` seeds tiny-fixture page 0 through LabelerPageStore with four words, The quick brown fox,
on a generated 1200×1600 image; other pages retain placeholders. This is not the former three fully
populated pages/30-word fixture. `just e2e` builds the SPA and runs the optional Playwright dependency group.
It is not part of ordinary `ci` or current `ci-slow`.

`tests/e2e/test_viewport_perf.py` exercises 4,000 rectangles and an rAF callback-count target of at least 55.
That target is not a per-frame timing guarantee. A fresh browser acceptance run, cross-binary legacy
comparison and assistive-technology QA must be identified explicitly rather than inferred from unit tests.

## Gate ownership

`just ci` is the current local process; former GitHub workflows are removed. It retains the existing
Python test selection, behavior coverage, both frontend typechecks, knip, frontend tests, export before
frontend build, and explicit sdist before wheel. Setup installs locked dependencies and CI installs the
frontend once. New feature/bugfix work follows the repo's failing-test-first and focused-verification rules.

## Evidence

- Code/config: `justfile`, `pyproject.toml`, `frontend/vitest.config.ts`, `frontend/src/test/setup.ts`.
- Tests: `tests/conformance/test_new_contract.py`, `test_response_models.py`,
  `test_region_block_round_trip.py`, `tests/e2e/conftest.py` and `test_viewport_perf.py`.
- Verified: 2026-11-13 by source/test/config inspection; this paragraph does not claim fresh e2e execution.

## Historical design receipt

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#32

## Local gates and closed review findings

The owner removed GitHub Actions workflows on 2026-09-13. The old CI-equivalence and OpenAPI-workflow tasks are
therefore moot; documentation cleanup must not restore those workflows. The committed OpenAPI contract is
`frontend/src/api/types.ts`; `frontend/openapi.json` is an ignored intermediate.

All six findings in [the findings record](../decisions/2026-11-13-retire-completed-doc-inventories.md) closed on
2026-09-18. Hierarchy helpers wait
for attached nodes and fail on an unexpectedly empty tree. Unmatched ground-truth placeholders are filtered before
overlays; successful zero-word OCR stays distinguishable from a reviewed blank page. Keyboard registration and
platform data-root behavior are recorded in the feature architecture and decision log.

The test TypeScript project matches the app project and sets `noUncheckedIndexedAccess: true`.
`just frontend-typecheck` runs both application and test checks, including
`tsc -p tsconfig.test.json --noEmit`. Vitest does not type-check, so that command
is the only check on test types.

### Evidence

- Code: `justfile`, `frontend/tsconfig.test.json`, and `frontend/src/components/PageImageCanvas.tsx`.
- Tests: `tests/e2e/test_ui_coverage.py`, `tests/e2e/test_confirm_dialog_keyboard.py`, and
  `tests/unit/test_settings.py`.
- Verified: 2026-11-07 by source inspection and September decision records. These statements do not claim a new
  full browser-suite run.

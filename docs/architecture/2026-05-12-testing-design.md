# pd-ocr-labeler-spa: Testing Strategy

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#32

## TL;DR

Four layers: pytest unit + integration (backend), Vitest (frontend), Playwright E2E, and
conformance golden-file tests against legacy envelopes. Backend ≥85% line coverage, 100% on
`core/persistence/` and `core/page_state.py`. Frontend ≥80%, 100% on `lib/*`. CI pipeline:
lint → test-backend → test-frontend → test-e2e → build-wheel → openapi-drift guard.

## Context

The testing structure mirrors `pd-prep-for-pgdp` (same `conftest.py` seam, same
uvicorn-in-thread E2E pattern). Legacy tests in `pd-ocr-labeler/tests/` are ported where
applicable. Conformance tests ensure `UserPageEnvelope` v2.1 round-trips byte-equal against
frozen legacy fixtures. Most tests use pre-OCR'd fixtures so DocTR doesn't need to run; real-
OCR tests are GPU-gated (`@pytest.mark.skipif("not gpu_available")`).

## Constraints

- **Pre-OCR'd fixtures for most tests.** Running DocTR in every test is slow; fixture projects
  ship with pre-computed envelopes.
- **asyncio_mode = "auto".** Same as pgdp-prep; every async test `await`s naturally.
- **Konva mocked in Vitest.** Visual rendering tested only in Playwright.
- **`onUnhandledRequest: "error"` in msw.** Unhandled API requests fail loudly in Vitest.
- **openapi-drift CI job is required.** Closes the pgdp-prep gap where types.ts drifted from
  the backend schema silently.
- **Milestone discipline: write tests first.** Implementing agents write named acceptance tests
  that fail, then implement until they pass.

## Decision

### Backend test layout

```
tests/
├── conftest.py           # Settings(tmp_path) + TestClient + gpu_available fixture
├── unit/                 # pure Python (no HTTP)
├── integration/          # full FastAPI via TestClient
├── conformance/          # legacy fixture round-trip + golden-file
├── cli/                  # console script tests
└── e2e/                  # Playwright (uvicorn-in-thread + Chromium)
    ├── conftest.py
    ├── helpers.py         # wait_for_app_ready, load_project, wait_for_page_loaded
    └── fixtures/projects/tiny-fixture/
```

`conftest.py` shape: `Settings(data_root=tmp_path/"data", cache_root=tmp_path/"cache",
source_projects_root=tmp_path/"data"/"source-pgdp-data"/"output",
storage_backend="filesystem", auth_mode="none", ocr_engine="local_doctr",
log_format="plain")`. `TestClient(build_app(settings))`.

### Frontend test layout

`frontend/src/**/*.test.{ts,tsx}` (Vitest + jsdom). Setup: `@testing-library/jest-dom`,
`MockResizeObserver`, msw `setupServer`. Konva mocked via `vi.mock("konva", ...)` and
`vi.mock("react-konva", ...)`. Categories: pure functions (`lib/`), hooks, component rendering,
mutation flow, routing, stores.

### E2E conftest

`tests/e2e/conftest.py` mirrors pgdp-prep: uvicorn-in-thread with hermetic `Settings`,
`_pick_free_port()`, `_wait_until` health-check, Playwright Chromium headless. Pre-built SPA
assumed (`make e2e` calls `make frontend-build` first).

### Conformance tests

`tests/conformance/test_legacy_envelopes.py`: parametrize over frozen fixture envelopes from
`pd-ocr-labeler/tests/`; `parse_envelope` + `build_envelope` + assert rebuilt == original
(byte-equal). Any regression = broken v2.1 compat; fix immediately.

### CI pipeline

Lint → test-backend → test-frontend → test-e2e → build-wheel → openapi-drift.
`openapi-drift`: `make openapi-export` then `git diff --exit-code frontend/src/api/types.ts`.

### Coverage targets

Backend ≥85% line, 100% on `core/persistence/` + `core/page_state.py`. Frontend ≥80%,
100% on `lib/*`. `pytest-cov` for Python; Vitest built-in for TS. Coverage summary on each PR.

## Contract / Acceptance

- `uv run pytest tests/unit tests/integration tests/conformance` passes with ≥85% line
  coverage on backend.
- `npm test` (Vitest) passes with ≥80% coverage; all `lib/` files at 100%.
- `uv run pytest tests/e2e` passes on Chromium headless with pre-built SPA.
- `test_legacy_envelopes.py` passes against all frozen fixtures (byte-equal round-trip).
- openapi-drift CI job catches any backend→frontend type schema drift.
- GPU-gated tests skip cleanly on machines without CUDA.

## Trade-offs considered

**msw vs real HTTP for Vitest.** Real HTTP adds server startup; msw intercepts in-process.
Chosen: msw — matches pgdp-prep and keeps tests fast.

**pytest-xdist parallelism.** Adds complexity but drops E2E runtime from ~3 minutes to ~1.
Optional; enabled if CI time becomes a bottleneck.

**Cross-binary automated tests.** Running legacy + SPA together requires subprocess gymnastics.
Out of scope for v1; manual QA in M9.

**100% coverage on `core/persistence/` and `lib/`.** These are the highest-stakes pure
functions (data corruption if wrong). 100% is achievable and worth it. Application-layer code
(routes, UI) gets the lower bar.

## Consequences

- Every milestone PR must include the acceptance tests named in `specs/16-milestones.md`.
- New fixture projects need pre-OCR'd envelopes; document in `tests/fixtures/README.md`.
- If `test_legacy_envelopes.py` fails, the SPA broke v2.1 compatibility — the fix is urgent.

## Open questions

None.

## References

- `specs/14-testing.md` — legacy feature doc (full file tree, conftest shapes, CI YAML)
- `specs/13-driver-contract.md` — driver conformance test (`test_driver_contract.py`)
- `specs/16-milestones.md` — per-milestone acceptance test lists
- `pd-prep-for-pgdp/tests/conftest.py:44-63` — pgdp-prep conftest seam reference

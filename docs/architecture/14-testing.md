---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-07-13
---

# 14 — Testing Strategy

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#32

How the SPA's correctness is asserted: backend pytest, frontend
Vitest, end-to-end Playwright, plus golden-file conformance against
the legacy.

> Cross-refs:
> Legacy tests — `pd-ocr-labeler/tests/`
> pgdp-prep test seam —
> `pdomain-prep-for-pgdp/tests/conftest.py:44-63`
> Driver contract — [`13-driver-contract.md`](13-driver-contract.md)

---

## 1. Test layout

```
tests/
├── conftest.py                  # client + settings + fixtures
├── unit/                        # Python unit tests
│   ├── test_settings.py
│   ├── test_app_factory.py
│   ├── test_request_id.py
│   ├── test_logging.py
│   ├── test_paths.py
│   ├── test_user_page_envelope.py
│   ├── test_image_cache.py
│   ├── test_session_state.py
│   ├── test_navigation_operations.py
│   ├── test_word_match_classify.py
│   ├── test_line_match_build.py
│   ├── test_notification_queue.py
│   └── ...
├── integration/                 # Python integration tests (full FastAPI)
│   ├── test_project_load.py
│   ├── test_first_ocr.py
│   ├── test_save_load_round_trip.py
│   ├── test_save_project.py
│   ├── test_envelope_round_trip.py
│   ├── test_inline_gt_edit.py
│   ├── test_word_validation.py
│   ├── test_toolbar_actions.py
│   ├── test_refine_bboxes.py
│   ├── test_export.py
│   ├── test_jobs_sse.py
│   └── test_notification_sse.py
├── conformance/                 # cross-binary compat
│   ├── test_legacy_envelopes.py # read every legacy fixture, no mutation
│   ├── test_legacy_writes.py    # SPA-saved file readable by legacy (manual)
│   └── fixtures/                # frozen golden envelopes
├── cli/                         # console scripts
│   ├── test_export_cli.py
│   └── test_prefetch_cli.py
└── e2e/                         # Playwright (browser regression)
    ├── conftest.py              # uvicorn-in-thread + Playwright browser
    ├── helpers.py               # wait_for_app_ready, load_project, ...
    ├── test_smoke.py
    ├── test_project_loading.py
    ├── test_navigation.py
    ├── test_image_viewport.py
    ├── test_text_tabs.py
    ├── test_keyboard_shortcuts.py
    ├── test_keyboard_only.py
    ├── test_ocr_config_modal.py
    ├── test_word_match.py
    ├── test_word_match_inline_edit.py
    ├── test_word_match_filter.py
    ├── test_word_match_line_actions.py
    ├── test_word_edit_dialog.py
    ├── test_session_isolation.py
    ├── test_source_folder_dialog.py
    ├── test_toolbar_page_actions.py
    ├── test_toolbar_paragraph_actions.py
    ├── test_toolbar_line_actions.py
    ├── test_toolbar_word_actions.py
    ├── test_page_actions.py
    ├── test_export_dialog.py
    ├── test_busy_overlay.py
    ├── test_hotkeys.py
    ├── test_driver_contract.py
    └── fixtures/
        └── projects/
            └── tiny-fixture/    # deterministic small project
```

Frontend tests live under `frontend/src/**/*.test.{ts,tsx}` (Vitest).

---

## 2. Backend tests (pytest)

### 2.1 `conftest.py` shape

```python
@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        source_projects_root=tmp_path / "data" / "source-pgdp-data" / "output",
        storage_backend="filesystem",
        auth_mode="none",
        ocr_engine="local_doctr",
        log_format="plain",
    )

@pytest.fixture
def client(settings):
    with TestClient(build_app(settings)) as c:
        yield c

@pytest.fixture
def gpu_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False
```

Same shape as pgdp-prep. Tests pass settings explicitly; production
reads env vars.

### 2.2 Fixtures: tiny test project

`tests/fixtures/projects/tiny/` (3 pages, 5 lines/page, ~30
words/page). Pre-OCR'd so tests don't need DocTR loaded.

`tests/fixtures/envelopes/` — golden labeled-projects envelopes
copied from the legacy repo. Used by `conformance/test_legacy_envelopes.py`.

### 2.3 OCR-conditional tests

```python
@pytest.mark.skipif("not gpu_available", reason="DocTR GPU required")
def test_real_ocr(client, settings, ...):
    ...
```

Most tests use **pre-OCR'd fixtures** so OCR doesn't run. Real-OCR
tests are gated.

### 2.4 Async tests

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Same as pgdp-prep. Every async test function `await`s naturally.

### 2.5 Required Python test categories

| Category | Examples |
|---|---|
| Schema/round-trip | `test_user_page_envelope`, `test_atomic_write` |
| State logic | `test_navigation_operations`, `test_word_match_classify` |
| Persistence | `test_save_load_round_trip`, `test_image_cache` |
| Endpoint integration | `test_inline_gt_edit`, `test_toolbar_actions` |
| Long-job behaviour | `test_jobs_sse`, `test_refine_bboxes` |
| Conformance | `test_legacy_envelopes` |
| URL / routing | `test_project_load` (deep-link cases) |

---

## 3. Frontend tests (Vitest)

### 3.1 Setup

`frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { server } from "./server";

class MockResizeObserver { observe() {} unobserve() {} disconnect() {} }
(global as any).ResizeObserver = MockResizeObserver;

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

### 3.2 msw server

`frontend/src/test/server.ts`:

```ts
import { setupServer } from "msw/node";
export const server = setupServer();
```

Per-test: `server.use(http.get("/api/projects", () => HttpResponse.json([...])))`.

### 3.3 Konva mock

```ts
vi.mock("konva", () => ({ /* minimal stubs */ }));
vi.mock("react-konva", () => ({ Stage: ..., Layer: ..., Image: ..., Rect: ..., Transformer: ... }));
```

Konva-driven components are unit-tested for prop wiring and event
dispatch; full visual rendering is e2e-tested via Playwright.

### 3.4 Required frontend test categories

| Category | Examples |
|---|---|
| Pure functions | `lib/coords.test.ts`, `lib/marquee.test.ts`, `lib/wordOffsets.test.ts` |
| Hooks | `hooks/useJobProgress.test.tsx`, `hooks/useNotificationStream.test.tsx` |
| Component rendering | `components/LineCard.test.tsx`, `components/WordCell.test.tsx` |
| Mutation flow | `components/WordCell.test.tsx::validates_optimistically` |
| Routing | `App.test.tsx::renders_route_tree` |
| Stores | `stores/ui-prefs.test.ts`, `stores/selection.test.ts` |

---

## 4. E2E tests (Playwright)

### 4.1 `tests/e2e/conftest.py`

Mirrors pgdp-prep `tests/e2e/conftest.py:47-89`:

```python
@pytest.fixture(scope="session")
def server_url(tmp_path_factory):
    settings = ...   # hermetic
    app = build_app(settings)
    port = _pick_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_until(lambda: requests.get(f"http://127.0.0.1:{port}/healthz").ok)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)

@pytest.fixture(scope="session")
def browser_instance(playwright):
    return playwright.chromium.launch(headless=True, args=["--no-sandbox"])

@pytest.fixture
def page(browser_instance, server_url):
    ctx = browser_instance.new_context()
    page = ctx.new_page()
    page.goto(server_url)
    yield page
    ctx.close()
```

Pre-built SPA assumed (`make e2e` does this).

### 4.2 Helper layer

`tests/e2e/helpers.py`:

```python
def wait_for_app_ready(page): ...        # waits for testid "app-ready"
def load_project(page, project_id): ...  # via dropdown + LOAD
def wait_for_page_loaded(page, ...): ... # waits for page-source-badge != "LOADING…"
def click_word_edit(page, line_idx, word_idx): ...
```

### 4.3 Driver-contract conformance

`tests/e2e/test_driver_contract.py` walks the full UI and asserts
every testid in [`13-driver-contract.md`](13-driver-contract.md) is
present (or stubbed). This is the canonical regression test for the
driver agent.

### 4.4 Performance e2e

`tests/e2e/test_performance.py`:

- Load a 200-line page; assert visible-line render < 200ms (via
  `performance.measure`).
- Validate 100 words via toolbar batch; assert mutation round-trip
  < 1s on the test machine.

These guard the perf budgets in [`03-frontend.md`](03-frontend.md) §16.

---

## 5. Conformance against legacy

`tests/conformance/`:

### 5.1 Read legacy envelopes

Every fixture under `pd-ocr-labeler/tests/browser/fixtures/` is copied
into the SPA test tree. `test_legacy_envelopes.py`:

```python
@pytest.mark.parametrize("fixture", FIXTURES)
def test_load_unmodified(fixture):
    data = json.loads(fixture.read_text())
    env = parse_envelope(data)
    rebuilt = build_envelope(**env.to_kwargs())
    assert rebuilt == data, f"envelope changed under round-trip: {fixture}"
```

If any legacy envelope round-trips with a difference, the SPA broke
compatibility — fix immediately.

### 5.2 SPA writes readable by legacy

Manual test (M9 acceptance criterion):

1. SPA: load fixture, edit words, Save Page, exit.
2. Legacy: open the same project, navigate to the saved page, verify
   it renders.

Automated cross-binary compat is out of scope (no clean way to launch
both binaries from one pytest session without subprocess gymnastics).

---

## 6. Coverage targets

| Layer | Target |
|---|---|
| Backend | ≥85% line coverage, 100% on `core/persistence/` and `core/page_state.py` |
| Frontend | ≥80% line coverage, 100% on `lib/*` (pure functions) |
| E2E | Every page route, every dialog, every action grid cell, full driver-contract |

Coverage tooling: `pytest-cov` for Python, Vitest's built-in for TS.
CI publishes coverage summary on each PR.

---

## 7. Continuous integration

`.github/workflows/release.yml`:

```yaml
jobs:
  lint:
    - ruff check .
    - ruff format --check .
    - npm run lint                      # eslint
    - npx tsc --noEmit                  # type-check (no build)
  test-backend:
    - uv sync
    - uv run pytest tests/unit tests/integration tests/conformance
  test-frontend:
    - npm ci
    - npm test
    - npm run build
  test-e2e:
    - npm run build
    - cp -r frontend/dist/. src/.../static/
    - uv run pytest tests/e2e --tracing on-first-retry
  build-wheel:
    needs: [test-backend, test-frontend]
    - uv build --wheel
    - python -m zipfile -l ... | grep static/index.html  # SPA assertion
  openapi-drift:
    - make openapi-export
    - git diff --exit-code frontend/src/api/types.ts
```

The openapi-drift job is **required** — closes pgdp-prep gap.

---

## 8. Test-driven milestone discipline

Each milestone's "acceptance tests" list (in
[`16-milestones.md`](../../specs/16-milestones.md)) is the minimum bar. Implementing
agents must:

1. Write the named tests **first** (fail).
2. Implement until the tests pass.
3. Add any tests they discovered along the way.
4. Run the full pytest + Vitest suites; CI green.

If a milestone PR can't make the listed tests pass, the milestone is
incomplete — do NOT mark complete.

---

## 9. Open issues

- **Test runtime.** The full e2e suite on Chromium takes ~3 minutes
  on dev hardware. Acceptable. Parallelisation via `pytest-xdist`
  drops it to ~1 minute.
- **OCR fixtures.** Each new fixture project requires running the
  legacy `generate_test_fixtures.py` (or the SPA equivalent) once to
  pre-OCR. Document in `tests/fixtures/README.md`.
- **Cross-binary tests.** Out of scope for v1. Added in M9 manual QA.

---
kind: plan
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
priority: now
repo: pdomain/pdomain-ocr-labeler-spa
source: docs/context/open-findings.md
---

# Open Findings Fixes — Implementation Plan

> **For agentic workers:** implement task-by-task with TDD. Steps use checkbox
> (`- [ ]`) syntax for tracking. Do **not** re-implement items under
> [Already resolved — no work](#already-resolved--no-work).

**Goal:** Close the residual open findings from
[`docs/context/open-findings.md`](../context/open-findings.md) against current
code: register advertised keyboard shortcuts, align `data_root` with the XDG
spec, harden zero-area / empty-OCR handling, and make hierarchy E2E waits
deterministic so WordDetail section coverage cannot silently skip.

**Architecture:** Small, localized fixes over existing seams.

- Keyboard: extend `useGlobalHotkeys` + page-level wiring (same pattern as
  `mod+e` / `mod+k` / QuickSearch focus).
- Paths: change `Settings.data_root` default to match
  [`docs/architecture/01-data-models.md`](../architecture/01-data-models.md) §5;
  no new storage backend.
- Overlay: document and pin the existing caller-side filters; add defensive
  zero-area skip + empty-OCR notification copy.
- E2E: replace fixed `time.sleep` hierarchy setup with explicit
  `wait_for_selector` / node-count waits; fail hard instead of soft-skip when
  the exercise fixture should have hierarchy data.

**Tech Stack:** React 19 + Vite + TS + TanStack Query + Zustand +
`react-hotkeys-hook`; FastAPI + pydantic-settings; pytest + Vitest + Playwright.

**Global Constraints:**

- Specs are source of truth. If code disagrees with a shipped architecture doc,
  fix the code (or change the spec first with user OK).
- Do not implement Auth/S3/Postgres/managed-adapter axes (D-042).
- Prefer `make frontend-test AI=1` / `make test AI=1` / `make e2e AI=1` targets.
- After any settings default change, keep CLI/env override
  (`PDLABELER_DATA_ROOT`, `--data-root`) working.
- Do not resolve open product questions unilaterally beyond the decision
  recorded in this plan for BUG-SMOKE-3 / empty-OCR toast.

---

## Triage summary (2026-07-21)

| ID | Title | Status | Evidence | Planned work |
|---|---|---|---|---|
| BUG-KBD-1 | `Mod+,` advertised, not registered | **Still open** | `hotkeyMap.ts:30`; no `useHotkey("mod+,")` in `useGlobalHotkeys.ts` | Register → `dialogStore.open("ocrConfig")` |
| BUG-KBD-4 | ConfirmDialog Escape/Enter | **Already fixed** | `ConfirmDialog.tsx` uses pdomain-ui Radix `AlertDialog`; Escape → `onOpenChange(false)` → `onCancel` | None (optional test hardening only) |
| BUG-KBD-5 | `Mod+J` advertised, not registered | **Still open** | `hotkeyMap.ts:39`; no `mod+j` registration; `nav-page-input` exists | Focus page input via ref (QuickSearch pattern) |
| BUG-SMOKE-3 | `data_root` not XDG-compatible | **Still open** (spec-vs-impl) | Spec `01-data-models.md:730` vs `settings.py:65` (`~/pdomain-ocr-labeler-spa`) | Align default to XDG path; no auto-migration of legacy `pd-ocr-labeler` |
| BUG-RELOAD-1 | Zero-area unmatched-GT / empty OCR | **Partially fixed** | Zero boxes created `page_to_line_matches.py:532`; overlay skips `word_index === null` (`PageImageCanvas.tsx:429`); structural layers filter area (`:236`); empty OCR still toasts “OCR complete” (`reload_ocr.py:321-324`) | Pin zero-area contract with tests + defensive filter; warn on zero-word OCR |
| BUG-HIER-1 | Hierarchy E2E empty / fixed sleeps | **Still open** | `test_ui_coverage.py:71-151` soft-returns False → six tests `pytest.skip` | Explicit waits; fail if exercise fixture yields no hierarchy |

---

## Already resolved — no work

### BUG-KBD-4 — ConfirmDialog Escape / Enter

**Status:** already fixed (product behavior).

**Evidence:**

- [`frontend/src/components/ConfirmDialog.tsx`](../../frontend/src/components/ConfirmDialog.tsx)
  replaces the hand-rolled modal with `@pdomain/pdomain-ui` `AlertDialog`
  (Radix). Comments at lines 5–7 and 45–53 state native focus trap + Escape
  handling.
- Escape / overlay dismiss → `onOpenChange(false)` with `confirmedRef` false →
  `onCancel()` (lines 71–79).
- Confirm is `AlertDialogAction` (native button activation on Enter when
  focused); Cancel is `AlertDialogCancel`.

**Tests today:** click confirm/cancel only
([`ConfirmDialog.test.tsx`](../../frontend/src/components/ConfirmDialog.test.tsx)).
No product change required. Optional later: one Escape unit test that fires
`keyboard` events if jsdom + Radix allow; otherwise leave to E2E destructive
flows already covered elsewhere (e.g. undo/reload confirm paths).

**Do not re-implement** custom Escape/Enter `useHotkey` bindings on
ConfirmDialog unless a browser regression is filed with a repro.

---

## File map (residual work)

| File | Action | Finding |
|---|---|---|
| `frontend/src/hooks/useGlobalHotkeys.ts` | Modify | KBD-1, KBD-5 |
| `frontend/src/hooks/useGlobalHotkeys.test.tsx` | Modify | KBD-1, KBD-5 |
| `frontend/src/pages/ProjectPage.tsx` | Modify | KBD-1, KBD-5 |
| `frontend/src/components/ProjectNavigationControls.tsx` | Modify | KBD-5 |
| `frontend/src/components/ProjectNavigationControls.test.tsx` | Modify | KBD-5 |
| `frontend/src/components/PageImageCanvas.tsx` | Modify | RELOAD-1 |
| `frontend/src/components/PageImageCanvas.test.tsx` | Modify | RELOAD-1 |
| `src/pdomain_ocr_labeler_spa/settings.py` | Modify | SMOKE-3 |
| `tests/unit/test_settings.py` | Modify | SMOKE-3 |
| `src/pdomain_ocr_labeler_spa/core/jobs/handlers/reload_ocr.py` | Modify | RELOAD-1 |
| `tests/unit/...` (reload / page_to_line_matches as needed) | Modify/Create | RELOAD-1 |
| `tests/e2e/test_ui_coverage.py` | Modify | HIER-1 |
| `tests/e2e/helpers.py` (optional shared helper) | Modify | HIER-1 |
| `docs/context/open-findings.md` | Modify (after ship) | all |

---

## Task 1 — BUG-KBD-1: Register `Mod+,` → OCR Config

**Files:**

- Modify: `frontend/src/hooks/useGlobalHotkeys.ts`
- Modify: `frontend/src/hooks/useGlobalHotkeys.test.tsx`
- Modify: `frontend/src/pages/ProjectPage.tsx` (wire handler)
- Optionally also root-route path: ensure hotkey works when no project is
  loaded (App-level registration or AppShell). Prefer registering where other
  global dialogs open.

**Spec:** [`docs/architecture/12-hotkeys-a11y.md`](../architecture/12-hotkeys-a11y.md) §3
(`Mod+,` → Open OCR config). Map entry already present:
`hotkeyMap.ts` line 30.

**Existing open path:** `dialogStore.open("ocrConfig")` used in
`App.tsx:267` and `PageActionsCompact.tsx:393`.

- [ ] **Step 1: Failing test — Ctrl+, opens OCR config handler**

In `useGlobalHotkeys.test.tsx`, add:

```tsx
it("Ctrl+, fires onOcrConfig", () => {
  const onOcrConfig = vi.fn();
  render(<TestComponent onOcrConfig={onOcrConfig} />);
  fireEvent.keyDown(document, { key: ",", ctrlKey: true, bubbles: true });
  expect(onOcrConfig).toHaveBeenCalledOnce();
});
```

Also assert `disabled=true` suppresses it (mirror existing disabled tests).

- [ ] **Step 2: Run test — expect fail**

```bash
make frontend-test AI=1
# or focused:
cd frontend && pnpm exec vitest run src/hooks/useGlobalHotkeys.test.tsx
```

Expected: fail — `onOcrConfig` not in handlers / hotkey not registered.

- [ ] **Step 3: Implement**

1. Add optional `onOcrConfig?: () => void` to `GlobalHotkeyHandlers`.
2. Register:

```ts
useHotkey("mod+,", () => onOcrConfig?.(), { enabled });
```

3. In `ProjectPage.tsx` `useGlobalHotkeys({...})`, pass:

```ts
onOcrConfig: () => dialogStore.open("ocrConfig"),
```

4. Ensure the same hotkey is available on the root route (OCR config is
   reachable there via `#ocr-config-trigger-button`). Options (pick one,
   prefer smallest):

   - **A (recommended):** mount a thin `useHotkey("mod+,", ...)` next to the
     existing root OCR trigger in `App.tsx` / AppShell, **or**
   - **B:** call `useGlobalHotkeys({ onOcrConfig })` from AppShell for
     dialog-only handlers only when not on a project page.

   Avoid double-registration that opens the dialog twice.

- [ ] **Step 4: Re-run tests**

```bash
cd frontend && pnpm exec vitest run src/hooks/useGlobalHotkeys.test.tsx src/App.test.tsx
```

- [ ] **Step 5: Commit**

```text
fix(hotkeys): register Mod+, for OCR Config (BUG-KBD-1)
```

---

## Task 2 — BUG-KBD-5: Register `Mod+J` → focus page input

**Files:**

- Modify: `frontend/src/components/ProjectNavigationControls.tsx`
- Modify: `frontend/src/components/ProjectNavigationControls.test.tsx`
- Modify: `frontend/src/hooks/useGlobalHotkeys.ts`
- Modify: `frontend/src/hooks/useGlobalHotkeys.test.tsx`
- Modify: `frontend/src/pages/ProjectPage.tsx`

**Spec:** `12-hotkeys-a11y.md` §4 — `Mod+J` focuses page input.
Pattern to copy: `QuickSearch` + `mod+k` in `ProjectPage.tsx:363-367`
(`forwardRef` + `useImperativeHandle` + `focusInput()`).

- [ ] **Step 1: Failing tests**

1. `ProjectNavigationControls`: expose imperative `focusPageInput()`; unit test
   calls ref and expects `document.activeElement` to be `nav-page-input`.
2. `useGlobalHotkeys`: `Ctrl+J` fires `onJumpToPage`.

```tsx
it("Ctrl+J fires onJumpToPage", () => {
  const onJumpToPage = vi.fn();
  render(<TestComponent onJumpToPage={onJumpToPage} />);
  fireEvent.keyDown(document, { key: "j", ctrlKey: true, bubbles: true });
  expect(onJumpToPage).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run — expect fail**

```bash
cd frontend && pnpm exec vitest run \
  src/hooks/useGlobalHotkeys.test.tsx \
  src/components/ProjectNavigationControls.test.tsx
```

- [ ] **Step 3: Implement**

1. Convert `ProjectNavigationControls` to `forwardRef` with:

```ts
export type ProjectNavigationControlsHandle = {
  focusPageInput: () => void;
};
```

   Hold a ref on the `nav-page-input` `<input>` and call `.focus()` /
   `.select()` so the user can type immediately (matches “Jump to page…”).

2. Register `mod+j` in `useGlobalHotkeys` → `onJumpToPage?.()`.

3. In `ProjectPage.tsx`:

```ts
const navControlsRef = useRef<ProjectNavigationControlsHandle>(null);
// ...
useGlobalHotkeys({
  // ...
  onJumpToPage: () => navControlsRef.current?.focusPageInput(),
});
// ...
<ProjectNavigationControls ref={navControlsRef} projectId={...} pageNo={...} />
```

4. Keep `enableOnFormTags: false` (default) so `mod+j` does not steal focus
   from GT inputs while typing — consistent with other global hotkeys.

- [ ] **Step 4: Re-run frontend tests**

```bash
make frontend-test AI=1
```

- [ ] **Step 5: Commit**

```text
fix(hotkeys): register Mod+J to focus page jump input (BUG-KBD-5)
```

---

## Task 3 — BUG-SMOKE-3: XDG-compatible `data_root` default

**Files:**

- Modify: `src/pdomain_ocr_labeler_spa/settings.py`
- Modify: `tests/unit/test_settings.py`
- Docs touch if needed: `docs/architecture/01-data-models.md` is already correct;
  do **not** change the spec. Optionally note override paths in
  `docs/usage/quickstart.md` if it still shows `~/pdomain-ocr-labeler-spa`.

**Product decision (locked for this plan):**

| Choice | Decision |
|---|---|
| Default `data_root` | `${XDG_DATA_HOME:-~/.local/share}/pdomain-ocr-labeler-spa` on Linux (per `01-data-models.md` §5) |
| App directory name | `pdomain-ocr-labeler-spa` (not legacy `pd-ocr-labeler`) |
| Auto-discover `~/.local/share/pd-ocr-labeler/` | **No** — cut-over complete; legacy superseded. Users with legacy data set `PDLABELER_DATA_ROOT` or `--data-root` |
| `config_root` / `cache_root` | Also honor `XDG_CONFIG_HOME` / `XDG_CACHE_HOME` when set (today they hardcode `~/.config` / `~/.cache` without env). Keep scope minimal: **must** fix `data_root`; **should** make all three roots XDG-env-aware for consistency |

- [ ] **Step 1: Failing test**

In `tests/unit/test_settings.py`, replace or extend
`test_path_roots_default_under_user_home` with XDG assertions:

```python
def test_data_root_defaults_to_xdg_data_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in list(os.environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)
    xdg = tmp_path / "xdg-data"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    # Force Settings re-read; if defaults are evaluated at import via Field(default_factory),
    # constructing Settings() after setenv is enough when factory reads os.environ each call.
    s = Settings()
    assert s.data_root == xdg / "pdomain-ocr-labeler-spa"


def test_data_root_defaults_to_local_share_when_xdg_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in list(os.environ):
        if var.startswith("PDLABELER_") or var == "XDG_DATA_HOME":
            monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert s.data_root == Path.home() / ".local" / "share" / "pdomain-ocr-labeler-spa"
```

> Note: current default is `Path.home() / "pdomain-ocr-labeler-spa"`
> (`settings.py:65`), so the second test fails until fixed.

- [ ] **Step 2: Run — expect fail**

```bash
uv run pytest tests/unit/test_settings.py -q
```

- [ ] **Step 3: Implement default factory**

```python
def _default_data_root() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "pdomain-ocr-labeler-spa"

data_root: Path = Field(default_factory=_default_data_root)
```

Mirror the Linux branch pattern already used in
`api/ocr_config.py:133-143` for trainer model store discovery. For macOS /
Windows, match the table in `01-data-models.md` §5 (Application Support /
LOCALAPPDATA). Prefer a single small helper in `settings.py` or
`core/persistence/paths.py` — do not invent a new package.

Also accept explicit env `PDLABELER_DATA_ROOT` (already via pydantic-settings
prefix) and CLI `--data-root` (already in `__main__.py`).

- [ ] **Step 4: Run unit + packaging gates**

```bash
uv run pytest tests/unit/test_settings.py tests/unit/test_adapters_storage.py -q
make test AI=1
```

- [ ] **Step 5: Commit**

```text
fix(settings): default data_root to XDG data home (BUG-SMOKE-3)
```

**Out of scope:** automatic migration / copy from
`~/.local/share/pd-ocr-labeler/` or `~/pdomain-ocr-labeler-spa`. If a one-line
startup log warning when the old home-relative directory exists is desired,
file it as a follow-up — do not block this task.

---

## Task 4 — BUG-RELOAD-1: Zero-area unmatched-GT + empty-OCR clarity

### 4a — Pin zero-area contract (mostly already correct)

**Evidence of current behavior:**

| Layer | Behavior | Location |
|---|---|---|
| Backend creates unmatched GT | `bbox=BBox(x=0,y=0,width=0,height=0)`, `word_index=None` | `page_to_line_matches.py:525-534` |
| Word overlay | skips `word.word_index === null` | `PageImageCanvas.tsx:429` |
| Structural overlays | `visibleWordBoxes` filters `width > 0 && height > 0` | `PageImageCanvas.tsx:235-236` |
| Box-select line union | same area filter | `box-select-handler.ts:52` |
| BBoxOverlay itself | renders whatever items it is given | no area filter |

**Residual risk:** a word with non-null `word_index` and zero area would still
render in the word overlay. Unmatched GT is safe today via `word_index === null`.

- [ ] **Step 1: Failing frontend tests**

In `PageImageCanvas.test.tsx` (or a focused pure helper test if you extract
one):

1. Page with one unmatched_gt (`word_index: null`, zero bbox) + one real word
   → `bbox-overlay-words` `data-item-count` is `1` (not 2).
2. Word with `word_index: 0` and zero bbox is **not** counted (defensive filter).

- [ ] **Step 2: Implement defensive filter**

In `wordOverlayItems` builder (`PageImageCanvas.tsx:423-438`):

```ts
if (word.word_index === null) continue;
if (word.bbox.width <= 0 || word.bbox.height <= 0) continue;
```

Keep structural path on `visibleWordBoxes` as-is.

- [ ] **Step 3: Backend unit pin (already nearly covered)**

Extend `tests/unit/core/test_page_to_line_matches.py::test_unmatched_gt_words_inserted`
to assert zero-area bbox:

```python
assert unmatched.bbox == BBox(x=0, y=0, width=0, height=0)
assert unmatched.word_index is None
```

- [ ] **Step 4: Run**

```bash
cd frontend && pnpm exec vitest run src/components/PageImageCanvas.test.tsx
uv run pytest tests/unit/core/test_page_to_line_matches.py -q
```

### 4b — Empty OCR result messaging

**Evidence:** `reload_ocr.py:320-324` always queues
`POSITIVE` / `"OCR complete for page {n}"` even when the page has no words.

**Decision (locked for this plan):**

- OCR that runs without exception stays job status `complete` (not a hard
  job error — the engine may legitimately return empty on blank images).
- If the applied outcome has **zero** OCR words / empty `line_matches`
  equivalent, queue a **warning** (or `NEGATIVE` if no warning kind exists)
  notification such as:
  `"OCR finished for page {n} but detected no words"`.
- Do **not** show a misleading “success complete” toast alone for the zero-word
  case. Prefer replacing the positive toast, not stacking both.

- [ ] **Step 1: Failing unit/integration test**

Add a handler test (mock loader returns empty page) asserting notification
message / kind. Follow existing reload_ocr test patterns under
`tests/unit` / `tests/integration`.

- [ ] **Step 2: Implement**

In `handle_reload_ocr` after `_apply_reocr_outcome`, inspect the page state /
outcome for word count. Branch notification text/kind.

- [ ] **Step 3: Run**

```bash
uv run pytest tests/unit tests/integration -k reload_ocr -q
```

- [ ] **Step 4: Commit**

```text
fix(ocr): suppress zero-area GT boxes; warn on empty OCR (BUG-RELOAD-1)
```

---

## Task 5 — BUG-HIER-1: Deterministic hierarchy E2E setup

**Files:**

- Modify: `tests/e2e/test_ui_coverage.py` (`_select_first_word_via_hierarchy`)
- Optionally extract shared helper to `tests/e2e/helpers.py` for reuse in
  `test_selection_operations_parity.py`, `test_parity_chrome.py`, etc.
- Scope for this plan: fix the helper used by the six WordDetail section
  tests that soft-skip; mirror the same wait style in the helper only.

**Problem:**

- Helper uses `time.sleep(0.2–0.5)` between expand steps
  (`test_ui_coverage.py:99-144`).
- On empty / not-yet-rendered tree it returns `False`.
- Callers `pytest.skip("No word-cell…")` (lines 874–875, 898–899, 927–928,
  955–956, 979–980, 1026–1027) → six WordDetail section tests can pass CI
  without exercising the UI (issue #403).

**Fixture expectation:** `tests/e2e/fixtures/projects/exercise-fixture/` has
labeled page JSON with Block/Paragraph structure; after load, hierarchy must
have nodes. Soft-skip is wrong for this fixture.

- [ ] **Step 1: Harden helper (no soft-skip on exercise fixture)**

Replace sleeps with explicit waits:

```python
def _select_first_word_via_hierarchy(page: Page, *, require: bool = True) -> bool:
    hier_tab = page.locator('[data-testid="drawer-tab-hierarchy"]').first
    hier_tab.wait_for(state="visible", timeout=10_000)
    hier_tab.click()
    page.wait_for_selector('[data-testid="hierarchy"]', state="visible", timeout=10_000)

    # Prefer waiting for any top-level node rather than sleeping.
    page.wait_for_selector(
        '[data-testid^="hierarchy-node-block-"], [data-testid^="hierarchy-node-para-"]',
        state="visible",
        timeout=10_000,
    )

    # Expand block if present
    block_nodes = page.locator('[data-testid^="hierarchy-node-block-"]')
    if block_nodes.count() > 0:
        first_block = block_nodes.first
        first_block.click()
        first_block.press("ArrowRight")
        page.wait_for_selector('[data-testid^="hierarchy-node-para-"]', state="visible", timeout=10_000)

    para = page.locator('[data-testid^="hierarchy-node-para-"]').first
    para.wait_for(state="visible", timeout=10_000)
    para.click()
    para.press("ArrowRight")
    page.wait_for_selector('[data-testid^="hierarchy-node-line-"]', state="visible", timeout=10_000)

    line = page.locator('[data-testid^="hierarchy-node-line-"]').first
    line.click()
    line.press("ArrowRight")
    page.wait_for_selector('[data-testid^="hierarchy-node-word-"]', state="visible", timeout=10_000)

    word = page.locator('[data-testid^="hierarchy-node-word-"]').first
    word.click()
    page.wait_for_selector('[data-testid="word-detail-accordion"]', state="attached", timeout=10_000)
    return True
```

For the six WordDetail tests: call with `require=True` and **assert** instead
of skip:

```python
assert _select_first_word_via_hierarchy(page), (
    "exercise-fixture page 1 must expose hierarchy word nodes; "
    "got empty tree (BUG-HIER-1)"
)
```

Remove the `pytest.skip("No word-cell…")` branches on those tests.

- [ ] **Step 2: Verify fixture payload has hierarchy fields**

Quick check during implementation:

```bash
# After exercise_server loads page 1, or offline inspect envelope:
python - <<'PY'
import json
from pathlib import Path
p = Path("tests/e2e/fixtures/projects/exercise-fixture/page-images/exercise-fixture_001.json")
data = json.loads(p.read_text())
page = data["payload"]["page"]
assert page["items"], "fixture page must have blocks"
print("blocks", len(page["items"]))
PY
```

If the API path that builds `line_matches` drops `block_index` /
`paragraph_index`, fix that producer (not the test). Hierarchy.tsx builds from
`PagePayload.line_matches` (`Hierarchy.tsx:8-19`).

- [ ] **Step 3: Run focused E2E**

```bash
uv run --group e2e pytest \
  tests/e2e/test_ui_coverage.py \
  -k "char_fixer or char_ranges or bbox_section or rebox or erase or structure" \
  -v
```

Or the full UI coverage module:

```bash
make e2e AI=1
```

Expected: six WordDetail section tests **run and pass**, not skip.

- [ ] **Step 4: Commit**

```text
test(e2e): wait for hierarchy nodes instead of sleep/skip (BUG-HIER-1)
```

---

## Task 6 — Close the loop on open-findings.md

After Tasks 1–5 land and CI is green:

- [ ] Update `docs/context/open-findings.md`:

  - Move resolved IDs to a “Resolved” section with date + PR/commit, **or**
    remove them and point to this plan + git history.
  - Bump `last_verified`.

- [ ] Run full gate before commit:

```bash
make ci AI=1
```

- [ ] Final commit:

```text
docs(context): mark open findings fixed after residual bug plan
```

---

## Related gaps (out of scope for this plan)

| Gap | Note |
|---|---|
| `Mod+O` advertised (`hotkeyMap.ts:31`) but not registered in `useGlobalHotkeys` | Same class of bug as KBD-1; fix opportunistically with KBD-1 if cheap, else separate issue |
| ConfirmDialog Escape unit test missing | Product fixed; optional hardening |
| Legacy `pd-ocr-labeler` data auto-import | Explicitly rejected for SMOKE-3 |
| Broad E2E `time.sleep` cleanup outside hierarchy helper | Only hierarchy soft-skip is BUG-HIER-1 |

---

## Effort estimate

| Finding | Residual status | Effort |
|---|---|---|
| BUG-KBD-1 | Still open | **S** (~0.5–1 h) |
| BUG-KBD-4 | Already fixed | **None** |
| BUG-KBD-5 | Still open | **S** (~1–1.5 h, includes ref plumbing) |
| BUG-SMOKE-3 | Still open | **S–M** (~1–2 h; OS path matrix tests) |
| BUG-RELOAD-1 | Partial | **M** (~2–3 h; FE filter + BE empty-OCR toast) |
| BUG-HIER-1 | Still open | **S–M** (~1–2 h; E2E flakiness buffer) |
| **Total residual** | | **~1 day** for one implementer (including CI) |

Suggested order: **KBD-1 → KBD-5 → SMOKE-3 → RELOAD-1 → HIER-1 → docs**.

---

## Verification checklist (ship bar)

- [ ] `make frontend-test AI=1`
- [ ] `make test AI=1`
- [ ] Focused E2E hierarchy / WordDetail section tests run without skip
- [ ] `make ci AI=1`
- [ ] Manual: `Mod+,` opens OCR Config; `Mod+J` focuses page input; Escape
      dismisses ConfirmDialog (smoke in browser if available)
)

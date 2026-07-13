---
last_verified: 2026-07-13
created: 2026-06-16
owner: maintainers
kind: plan
status: draft
priority: now
repo: pdomain/pdomain-ocr-labeler-spa
---

# pdomain-ui Primitive Migration Plan (Tiers B–F)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace remaining bespoke local primitives in `frontend/src/components/ui/` with their equivalents from `@pdomain/pdomain-ui/primitives`, `@pdomain/pdomain-ui/status`, and `@pdomain/pdomain-ui/worklist`. Eliminates local maintenance burden and keeps the labeler visually consistent with the pdomain-ui design system.

**Tier A (StatusPip) is already shipped** on branch `spike/pdui-0.10.1-primitives-css` as of 2026-06-16.

**Visual note:** Every slice below shifts call sites from bespoke Tailwind classes to `primitives.css` CSS-variable tokens. The components will continue to render correctly because `primitives.css` is already imported globally. A brief visual smoke test (see acceptance section in each slice) is required before merging each slice — CI alone cannot verify visual fidelity.

**Tech Stack:** React 19 + Vite + TS + Tailwind + `@pdomain/pdomain-ui` 0.10.1+, Vitest, Playwright.

---

## File map overview

| Local file | Upstream replacement | Entry point |
|---|---|---|
| `components/BusyOverlay.tsx` | `BlockingOperationOverlay` + `OperationStatusPanel` + `RetryActionPanel` | `@pdomain/pdomain-ui/status` |
| `components/ui/Input.tsx` | `Input` | `@pdomain/pdomain-ui/primitives` |
| `components/ui/Chip.tsx` | `Chip` + `TriStateChip` | `@pdomain/pdomain-ui/primitives` |
| `components/ui/button.tsx` | `Button` / `ButtonGroup` / `IconButton` | `@pdomain/pdomain-ui/primitives` |
| `components/ui/tabs.tsx` | `Tabs` | `@pdomain/pdomain-ui/primitives` |
| `components/ui/accordion.tsx` | `Accordion` | `@pdomain/pdomain-ui/primitives` |

---

## Slice 1 — BusyOverlay → BlockingOperationOverlay + OperationStatusPanel

**Risk:** Low-Medium. The upstream components have a superset API. The cancel-button, SSE job-progress wiring, and ProjectLoadingOverlay distinct states must survive.

**Scope:**
- Delete `components/BusyOverlay.tsx` (exports both `BusyOverlay` and `ProjectLoadingOverlay`)
- Repoint `pages/ProjectPage.tsx` (sole caller of both)
- Update `components/BusyOverlay.test.tsx` (import update + class-assertion rewrites)

**Caller sweep:** `BusyOverlay` and `ProjectLoadingOverlay` are only used in `pages/ProjectPage.tsx` (two call sites). Confirm with: `grep -rn "BusyOverlay\|ProjectLoadingOverlay" frontend/src/`.

**Upstream API verification required before starting:**
- `BlockingOperationOverlay` props: `open`, `title`, `message`, `progress`, `cancelAction`, `bestEffortCancel`, `ariaLabel`, `className`
- `OperationStatusPanel` props: `title`, `message`, `state` (OperationState), `progress`, `details`, `primaryAction`, `secondaryAction`, `className`
- `RetryActionPanel` props: see `@pdomain/pdomain-ui/dist/status/RetryActionPanel.d.ts`
- Local `BusyOverlay` accepts `activeJob` (job record with `title`, `progress`, `stage`) and `isMutating`. Map these fields to `BlockingOperationOverlay` props.
- Local `ProjectLoadingOverlay` accepts `isLoading: boolean`. Map to `BlockingOperationOverlay open={isLoading}`.

**Driver-contract testid verification:** `BusyOverlay` renders `data-testid="busy-overlay"`. Check `docs/architecture/13-driver-contract.md` section on busy/loading overlays. The upstream `BlockingOperationOverlay` does not auto-generate `busy-overlay` — wrap with `data-testid` on the upstream component or pass it via `ariaLabel` / `className` trick. Confirm against e2e tests with `grep -rn "busy-overlay" tests/`.

**Cancel-button preservation:** Local `BusyOverlay` wires a cancel button via SSE job-abort. Map to `cancelAction` prop of `BlockingOperationOverlay`. The cancel flow (POST `/api/jobs/{id}/cancel`) must still fire correctly — do not drop the callback chain.

**Visual acceptance check:** Load a project, trigger an OCR job, verify the overlay appears with title + progress bar + cancel button. Visually compare before/after screenshot.

**Tasks:**
- [ ] Read `BusyOverlay.tsx` + `ProjectPage.tsx` usage context; verify upstream props cover all local uses
- [ ] Write failing vitest test asserting `BlockingOperationOverlay` renders with `data-testid="busy-overlay"` at its root
- [ ] Rewrite `pages/ProjectPage.tsx` to use upstream components; pass `data-testid` explicitly
- [ ] Delete `components/BusyOverlay.tsx`; update `BusyOverlay.test.tsx` (import + assertion update)
- [ ] `make ci AI=1` green; `make e2e AI=1` green
- [ ] Commit

---

## Slice 2 — Input → @pdomain/pdomain-ui/primitives Input

**Risk:** Low. Single caller (`OcrGtCompareRow.tsx`). Upstream Input is a superset.

**Scope:**
- Delete `components/ui/Input.tsx`
- Repoint `components/right-panel/OcrGtCompareRow.tsx`
- Update `components/ui/Input.test.tsx`

**Caller sweep:** One caller confirmed: `OcrGtCompareRow.tsx` imports `Input` from `../ui/Input`. Confirm with: `grep -rn "from \"../ui/Input\"\|from \"./ui/Input\"" frontend/src/`.

**Upstream API differences:**
- Local `Input` is a plain `<input>` wrapper with `font-mono` bespoke class via `className`
- Upstream `Input` adds optional `size` prop (`'sm' | 'md' | 'lg'`; local default is `md`-equivalent), plus `suffix` and `autoFocusRing` props — all additive, no breaking changes
- Pass `className="font-mono"` at the call site to preserve the font-mono styling; confirm visually

**Driver-contract testid verification:** `OcrGtCompareRow.tsx` supplies `data-testid` to `Input` via props. The upstream `Input` extends `React.InputHTMLAttributes`, so the testid passes through. Confirm: `grep -n "data-testid" frontend/src/components/right-panel/OcrGtCompareRow.tsx`.

**Visual acceptance check:** Navigate to a page, select a word, verify the GT edit input renders with mono font and correct sizing.

**Tasks:**
- [ ] Confirm upstream Input exports and prop shape from `@pdomain/pdomain-ui/dist/primitives/Input.d.ts`
- [ ] Repoint `OcrGtCompareRow.tsx`; pass `className="font-mono"` to preserve style
- [ ] Delete `components/ui/Input.tsx`; update `Input.test.tsx`
- [ ] `make ci AI=1` green
- [ ] Commit

---

## Slice 3 — Chip + TriStateChip → @pdomain/pdomain-ui/primitives

**Risk:** Medium. The local `Chip` folds both static and tristate into one component via `variant="tristate"`. The upstream splits them into `Chip` (static badge) and `TriStateChip` (interactive tristate). The `data-tristate` / `data-tristate-value` driver attrs and the `TristateValue` type must survive intact.

**Scope:**
- Delete `components/ui/Chip.tsx`
- Repoint callers: `StylePalette.tsx` (uses `Chip` + imports `TristateValue`), `ComponentPalette.tsx` (imports `TristateValue` type only)
- Update `components/ui/Chip.test.tsx`

**Caller sweep:** `grep -rn "from \"../ui/Chip\"\|TristateValue" frontend/src/`. Confirm no other callers.

**Upstream API verification required before starting:**
- Check `@pdomain/pdomain-ui/dist/primitives/Chip.d.ts` and `TriStateChip.d.ts` for exact prop shape
- Confirm `TriStateChip` emits `data-tristate` and `data-tristate-value={value}` — these are required by driver contract (`docs/architecture/13-driver-contract.md` §word-tag-chip section)
- Confirm upstream `TristateValue` type is `'off' | 'on' | 'mixed'` (identical to local)
- If upstream `TriStateChip` does NOT emit `data-tristate` / `data-tristate-value`, wrap it locally or pass via props — do not silently drop these attrs

**Driver-contract testid verification:** Driver contract references `word-tag-chip-{l}-{w}-{label}` and uses `.word-tag-chip` CSS class selector as a fallback. Confirm the upstream `Chip` sets `className` that includes `.word-tag-chip` or that the existing `data-testid` prop threading works. Run `make e2e AI=1` and explicitly check `test_word_tag_chip` or equivalent.

**API split migration pattern:**
```tsx
// Before (local Chip with variant="tristate")
<Chip variant="tristate" value={v} onChange={onChange} data-testid="...">Label</Chip>

// After (upstream TriStateChip)
<TriStateChip value={v} onChange={onChange} data-testid="...">Label</TriStateChip>

// Before (local Chip static)
<Chip>Label</Chip>

// After (upstream Chip)
<Chip>Label</Chip>
```

**Tasks:**
- [ ] Read upstream `Chip.d.ts` and `TriStateChip.d.ts`; verify `data-tristate*` attrs are forwarded
- [ ] Write failing test asserting `data-tristate-value` on `TriStateChip` wrapper
- [ ] Repoint `StylePalette.tsx` (static `Chip` stays `Chip`; tristate callers switch to `TriStateChip`)
- [ ] Update `ComponentPalette.tsx` type import to use upstream `TristateValue`
- [ ] Delete `components/ui/Chip.tsx`; update `Chip.test.tsx`
- [ ] `make ci AI=1` green; `make e2e AI=1` green (check chip testids)
- [ ] Commit

---

## Slice 4 — Button / ButtonGroup / IconButton → @pdomain/pdomain-ui/primitives

**Risk:** Medium. Many call sites; `IconButton` requires `aria-label`; `ButtonGroup` layout differs. Upstream is a superset of local variants/sizes.

**Scope:**
- Delete `components/ui/button.tsx` (exports `Button`, `buttonVariants`, and related helpers)
- Repoint all callers — likely 15–30+ call sites across most component files
- Update `components/ui/Button.test.tsx`

**Caller sweep (REQUIRED before starting):**
```
grep -rn "from \"../ui/button\"\|from \"./ui/button\"\|from \"../ui/Button\"" frontend/src/ --include="*.tsx" --include="*.ts"
```
Map each caller to the upstream variant it needs. Many will just use `Button`; some may use `IconButton` or `ButtonGroup`.

**Upstream API differences:**
- Local `button.tsx` uses CVA; upstream `Button` uses its own variant system. Confirm variant names match: `default | destructive | outline | secondary | ghost | link` vs. upstream equivalents.
- `IconButton` requires `aria-label` prop (not optional). Every current icon-only button must gain an `aria-label` — audit during the caller sweep.
- `ButtonGroup` may wrap with a flex container — verify visual outcome at the site where it's used (WorkspaceToolbar, PageActionsCompact).
- `buttonVariants` utility: if any caller uses it directly for CSS composition, replace with upstream `cn` + hardcoded class or the upstream equivalent.

**Driver-contract testid verification:** Button testids in the driver contract (e.g. `load-project-button`, `export-button`, `ocr-config-trigger-button`, `rail-hotkeys-button`) are set by callers via `data-testid` prop, not by the button component itself. The upstream `Button` forwards `HTMLButtonElement` attrs, so testids pass through. Confirm with `grep -n "data-testid" frontend/src/` for each driver-contract button.

**Visual acceptance check:** Click through the main actions (Load project, Export, OCR config trigger, rotate buttons) and verify button styles, hover states, and disabled states render correctly.

**Tasks:**
- [ ] Full caller sweep; tally variant usage; note all `IconButton`/`ButtonGroup` sites needing `aria-label` audit
- [ ] Write failing tests for a representative caller (e.g. `load-project-button` renders with correct testid)
- [ ] Batch-repoint all callers, adding `aria-label` where missing
- [ ] Delete `components/ui/button.tsx`; update `Button.test.tsx`
- [ ] `make ci AI=1` green; `make e2e AI=1` green (all button driver-contract testids)
- [ ] Commit

---

## Slice 5 — Tabs → @pdomain/pdomain-ui/primitives Tabs

**Risk:** High. Local `tabs.tsx` uses Radix `data-[state=active]` + `border-b` indicator. Upstream `Tabs` uses `.tabs`/`.tab.active` CSS from `primitives.css`. Active-state styling must be redone. Driver-contract tab testids must survive.

**Scope:**
- Delete `components/ui/tabs.tsx`
- Repoint callers: `LineDetail.tsx` (named imports `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent`), `BlockDetail.tsx` (same imports)
- Update `components/ui/Tabs.test.tsx`

**Caller sweep:** `grep -rn "from \"../ui/tabs\"" frontend/src/`. Confirm only two callers.

**Upstream API verification required before starting:**
- Check `@pdomain/pdomain-ui/dist/primitives/Tabs.d.ts` for exported names (`Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` or equivalent)
- The upstream may export a flat `Tabs` + sub-components or a compound API — adapt call sites accordingly
- Active-state class: upstream applies `.tab.active` or `[data-state=active]` via `primitives.css` selectors. Do NOT replicate the local `border-b` indicator — let upstream handle it via `primitives.css`

**Driver-contract testid verification:** Driver contract references tab testids for line-detail and block-detail tabs (e.g. `line-detail-words-tab`, `line-detail-text-tab`). These are set by `data-testid` on `TabsTrigger` at the call site, not by the Tabs component. Confirm the upstream `TabsTrigger` forwards HTML attrs. Run `make e2e AI=1` and check that tab switching still works.

**Visual acceptance check:** Navigate to a line detail panel, click between Words and Text tabs, verify active tab is visually indicated and content switches correctly.

**Tasks:**
- [ ] Read upstream Tabs API; map to local `Tabs`/`TabsList`/`TabsTrigger`/`TabsContent` names
- [ ] Write failing test asserting tab switching behavior using upstream component
- [ ] Repoint `LineDetail.tsx` and `BlockDetail.tsx`; remove local `border-b` active-style overrides
- [ ] Delete `components/ui/tabs.tsx`; update `Tabs.test.tsx`
- [ ] `make ci AI=1` green; `make e2e AI=1` green (tab switching, tab testids)
- [ ] Commit

---

## Slice 6 — Accordion → @pdomain/pdomain-ui/primitives Accordion

**Risk:** High. Local `accordion.tsx` has a richer trigger: uppercase label + hint text + `KeyCap` inline. The labeler also has a `tag` variant (accent/mismatch) with no pdomain-ui equivalent. Upstream `Accordion` appends its own chevron + `.acc-body` class.

**Scope:**
- Delete `components/ui/accordion.tsx`
- Repoint caller: `WordDetail.tsx` (sole importer)
- Update `components/ui/Accordion.test.tsx`

**Caller sweep:** `grep -rn "from \"../ui/accordion\"" frontend/src/`. Confirm only one caller.

**Upstream API verification required before starting:**
- Check `@pdomain/pdomain-ui/dist/primitives/Accordion.d.ts` for prop shape
- Upstream chevron: the upstream Accordion adds its own chevron via CSS (`::after` or `[data-state=open]`). The local accordion has its own chevron. Remove the local one to avoid duplication.
- `tag` variant: the local accordion has a `tag` prop (`"accent" | "mismatch"`) that colors the trigger border. The upstream has no equivalent. Options in priority order:
  1. Pass `className` to the upstream `Accordion` trigger (preferred — one-liner, no forking)
  2. Wrap the upstream component in a thin local shim that adds the tag color via `className`
  Do NOT fork a local copy of the upstream component.
- `KeyCap` in trigger: the local accordion trigger renders `<KeyCap>` for hotkey hints. Confirm the upstream Accordion accepts arbitrary `ReactNode` as trigger children — it should. If not, use a render-prop or `children` pattern.

**Accordion DOM-removal caveat (pre-existing gotcha):** Radix Accordion removes content from the DOM when closed. Tests must click the trigger to open the accordion before asserting section testids. See `feedback_accordion_content_not_in_dom.md`.

**Driver-contract testid verification:** Check `docs/architecture/13-driver-contract.md` for accordion testids in WordDetail (e.g. word detail section headers). Testids are set on `AccordionTrigger` via `data-testid` at the call site. Run `make e2e AI=1` after the swap.

**Visual acceptance check:** Select a word, verify accordion sections (OCR/GT, Style, etc.) open/close correctly with the upstream chevron, `KeyCap` hints remain visible, and accent/mismatch tag colors still apply.

**Tasks:**
- [ ] Read `WordDetail.tsx` accordion usage; catalog all `tag` usages + `KeyCap` positions
- [ ] Confirm upstream Accordion accepts `ReactNode` trigger children and `className` forwarding
- [ ] Write failing test for accordion open/close with upstream component (remember to click trigger first)
- [ ] Repoint `WordDetail.tsx`; implement `tag` variant via `className` on upstream component; remove local chevron
- [ ] Delete `components/ui/accordion.tsx`; update `Accordion.test.tsx`
- [ ] `make ci AI=1` green; `make e2e AI=1` green
- [ ] Commit

---

## Intentionally out of scope (do not migrate)

- **`toast.ts`** (Sonner toast helper) — intentionally local; Sonner is not in pdomain-ui scope
- **`useNotificationStream`** (SSE consumer) — domain-specific labeler hook, not a UI primitive
- **`--status-*` / `--layer-*` CSS token aliases** in `index.css` — labeler-specific semantic tokens; pdomain-ui does not define these
- **`KeyCap.tsx`** — already deleted; upstream `KeyCap` from `@pdomain/pdomain-ui/primitives` is used directly (Tier A prerequisite)

## Goal

Replace the remaining compatible local UI primitives with maintained
`pdomain-ui` primitives while preserving labeler behavior.

## Architecture

Migrate tier by tier through existing wrappers so shared primitives can land
without a single high-risk rewrite of all consumers.

## Tech Stack

React, TypeScript, Tailwind, Vitest, Playwright, and `@pdomain/pdomain-ui` cover
the migration and its visual/behavioral verification.

## Global Constraints

Preserve accessibility, public wrapper contracts, and exact testids. Keep local
Tabs or Accordion behavior where shared primitives are not contract-compatible.

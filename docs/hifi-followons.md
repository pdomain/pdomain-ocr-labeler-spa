# Hi-fi redesign — follow-on items

Deferred work surfaced during the Slices 0–27 implementation (shipped 2026-05-15).
These are not regressions; the shipped code works and CI is green. Each item is
a known gap between the spec intent and current state, recorded so it can be
picked up as a discrete future slice.

---

## Backend gaps (endpoints not yet in API schema)

### FO-1 — `lines_paragraphs` PATCH endpoint missing
**Surfaced in:** Slice 22 (BlockDetail layout-type save)
**State:** `BlockDetail` renders the layout-type chip selector and "Accept suggestion"
button, but the save path is a labelled no-op stub. The `lines_paragraphs` PATCH
route does not yet exist in the generated `frontend/src/api/types.ts`.
**To fix:** Add the endpoint to the FastAPI backend, re-run `make openapi-export`,
then wire `BlockDetail`'s `onLayoutSave` handler to the generated mutation.

### FO-2 — Char-range positions not persisted to backend
**Surfaced in:** Slice 19 (CharRangesSection)
**State:** `(start, end, styles[])` triples are stored in local component state.
Only the style label is sent to the backend via `apply-style scope:"part"` — no
character positions. The backend `apply-style` endpoint accepts only
`scope: "whole" | "part"` with no coordinate payload.
**To fix:** Add a positioned char-ranges endpoint to the backend; switch
`CharRangesSection`'s POST to the new endpoint. The UI shape and testids are
already forward-compatible.

### FO-3 — Merge-with-line affordance is disabled
**Surfaced in:** Slice 21 (LineDetail)
**State:** "Merge with previous" / "Merge with next" buttons are rendered but
disabled; `useLineMutations` does not yet have a merge endpoint.
**To fix:** Add a merge-lines backend route, add `useMergeLine` to
`useLineMutations`, enable the buttons in `LineDetail`.

---

## Frontend-only gaps

### FO-4 — `BBoxOverlay` uses legacy `LAYER_COLORS` constants, not CSS vars ✅ DONE
**Shipped:** #328 (2026-05-15). `LayerColorSpec` moved to `useLayerColors.ts`
(BBoxOverlay re-exports it). `hexToRgba`, `hexToLayerColorSpec`,
`SELECTION_LAYER_SPEC`, `DRAG_RECT_LAYER_SPEC` added. BBoxOverlay reads layer
colors via `useLayerColors()` through `resolveLayerColorSpec()`. Tests updated.

### FO-5 — `Chip` primitive does not forward `data-testid` ✅ DONE
**Shipped:** #325 (2026-05-15). Chip forwards `data-testid` on both variants;
CharRangesSection uses `<Chip variant="tristate">` instead of duplicate inline impl.

### FO-6 — Legacy `hotkeyMap.ts` entries not bridged into hotkey registry ✅ DONE
**Shipped:** #329 (2026-05-15). `hotkey-bridge.ts` converts all `HOTKEY_MAP`
entries via `buildBridgedEntries()` — `comboToKeyCap` for display tokens,
`scopeToGroup` for routing. `hotkey-registry.ts` seeds from the bridge at
module load. 20 unit tests added.

### FO-7 — Block-level sibling walk is a no-op
**Surfaced in:** Slices 12, 15 (Hierarchy tab, selection-store)
**State:** `path.blockId` is accepted as an opaque string, but `PagePayload` has
no block layer. `nextSibling` at `level === "block"` returns the current path
unchanged. Breadcrumb renders a "Block" chip correctly; navigation just does
nothing.
**To fix:** Expand `PagePayload` with a `block_index` field (or equivalent);
update `selection-walk.ts` to walk blocks when the field exists.

---

## Design decisions to revisit

### FO-8 — `Drawer` subscriber bridge is hand-rolled ✅ DONE
**Shipped:** #324 (2026-05-15). Local `uiPrefsSubscribers` Set removed; Drawer
now uses `useSyncExternalStore(useUiPrefs.subscribe, ...)` directly. `useUiPrefs`
already had `subscribe` — the bridge was redundant.

### FO-9 — `ErasePixelsSection` Apply button permanently disabled
**Surfaced in:** Slice 17 (ErasePixelsSection)
**State:** `backendAvailable={false}` is hardcoded in `WordDetail.tsx`. The spec
notes "disable with tooltip 'Backend not wired' if endpoint absent."
**To fix:** Wire `backendAvailable` to an actual capability check (e.g. a
`/api/refine/available` probe or a capabilities flag from the server info
endpoint) instead of a compile-time constant.

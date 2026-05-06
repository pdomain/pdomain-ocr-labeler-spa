# `pd-ocr-labeler-spa` Specs

Numbered design documents. Read [`00-overview.md`](00-overview.md) first;
it lists every other spec and tells you which to read for any given
implementation task.

> Specs are the **source of truth.** Code that disagrees with a spec is
> wrong; if reality forces a change, change the spec first, then the code.

| # | File | Topic |
|---|---|---|
| 00 | [`00-overview.md`](00-overview.md) | Goals, non-goals, tech stack, milestone contract |
| 01 | [`01-data-models.md`](01-data-models.md) | Pydantic + on-disk schemas (`UserPageEnvelope` v2.1) |
| 02 | [`02-backend.md`](02-backend.md) | FastAPI router map, every endpoint contract |
| 03 | [`03-frontend.md`](03-frontend.md) | React shell, routing, state stores, generated client |
| 04 | [`04-image-viewport.md`](04-image-viewport.md) | Konva canvas, layer overlays, drag modes |
| 05 | [`05-word-matches.md`](05-word-matches.md) | Right-pane line cards + per-word controls |
| 06 | [`06-toolbar-actions.md`](06-toolbar-actions.md) | Scope-action grid, style/component apply, add-word |
| 07 | [`07-word-edit-dialog.md`](07-word-edit-dialog.md) | Preview, nudge, crop, refine, erase |
| 08 | [`08-page-actions.md`](08-page-actions.md) | Reload OCR / Save / Load / Rematch GT |
| 09 | [`09-persistence.md`](09-persistence.md) | UserPageEnvelope, image cache, session state |
| 10 | [`10-export.md`](10-export.md) | DocTR export dialog + endpoint |
| 11 | [`11-notifications.md`](11-notifications.md) | Toast queue, busy overlays, SSE jobs |
| 12 | [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md) | Keybindings + a11y rules |
| 13 | [`13-driver-contract.md`](13-driver-contract.md) | data-testid + URL invariants for `pd-ocr-labeler-driver` |
| 14 | [`14-testing.md`](14-testing.md) | pytest + Vitest + Playwright strategy |
| 15 | [`15-deployment-dev.md`](15-deployment-dev.md) | Build, devcontainer, install |
| 16 | [`16-milestones.md`](16-milestones.md) | M0…M9 milestone breakdown |
| 17 | [`17-decisions.md`](17-decisions.md) | ADRs / decisions log |
| 18 | [`18-text-normalization.md`](18-text-normalization.md) | Long-S / ligature / glyph normalization (D-025) |
| 19 | [`19-auto-rotation.md`](19-auto-rotation.md) | Manual + auto page rotation (D-029) |
| 20 | [`20-glyph-annotations.md`](20-glyph-annotations.md) | Glyph-level side-channel annotations (ligatures, long-s, swash) |

## Conventions in these specs

- **Citations.** Whenever a spec asserts behaviour drawn from the
  legacy labeler or from pgdp-prep, the citation appears as
  `path:line` (e.g. `pd-ocr-labeler/pd_ocr_labeler/state/page_state.py:535`).
- **Endpoints.** Always prefixed `/api/...`. URL shape uses `idx0`
  (0-based) internally; the public route preserves the 1-based
  `/page/{n}` form ([Q19](../OPEN_QUESTIONS.md)).
- **Type names.** Wire models share a name with the domain Pydantic
  model unless the wire shape differs (then `<Verb><Noun>Request` /
  `<Verb><Noun>Response`).
- **`data-testid`.** Every interactive element in the SPA must keep
  its legacy `data-testid` exactly. New testids only when the legacy
  did not have one.
- **Open questions.** Inline as `([Qn](../OPEN_QUESTIONS.md))`. Do not
  pretend they're answered.

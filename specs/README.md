---
kind: spec
status: active
owner: maintainers
created: 2026-05-06
last_verified: 2026-07-13
---

# `pdomain-ocr-labeler-spa` Specs

Numbered design documents.

> **Specs are the source of truth.** Code that disagrees with a spec is
> wrong; if reality forces a change, change the spec first, then the code.

## Layout (2026-05-14 split)

Specs are now organized into two trees:

- **`specs/`** (this directory) — **active** design docs: living roadmap,
  the ADR log, and specs whose functionality has not yet landed.
- **`../docs/architecture/`** — specs that describe **implemented**
  functionality (every child issue closed, code shipped). These remain
  authoritative architecture references; they were moved out of `specs/`
  to keep this directory focused on outstanding work.

## Active specs (in this directory)

| # | File | Topic |
|---|---|---|
| 16 | [`16-milestones.md`](16-milestones.md) | M0…M9 milestone breakdown — living roadmap |
| 17 | [`17-decisions.md`](17-decisions.md) | ADRs / decisions log — append-only |
| 20 | [`20-glyph-annotations.md`](20-glyph-annotations.md) | Glyph-level annotations (open issues #267–#270, blocked on `pdomain-book-tools` upstream) |

## Implemented specs (under `docs/architecture/`)

| # | File | Topic |
|---|---|---|
| 00 | [`../docs/architecture/00-overview.md`](../docs/architecture/00-overview.md) | Goals, non-goals, tech stack |
| 01 | [`../docs/architecture/01-data-models.md`](../docs/architecture/01-data-models.md) | Pydantic + on-disk schemas (`UserPageEnvelope` v2.2) |
| 02 | [`../docs/architecture/02-backend.md`](../docs/architecture/02-backend.md) | FastAPI router map, endpoint contracts |
| 03 | [`../docs/architecture/03-frontend.md`](../docs/architecture/03-frontend.md) | React shell, routing, state, generated client |
| 04 | [`../docs/architecture/04-image-viewport.md`](../docs/architecture/04-image-viewport.md) | Konva canvas, overlays, drag modes |
| 05 | [`../docs/architecture/05-word-matches.md`](../docs/architecture/05-word-matches.md) | Right-pane line cards + per-word controls |
| 06 | [`../docs/architecture/06-toolbar-actions.md`](../docs/architecture/06-toolbar-actions.md) | Scope-action grid, style/component apply |
| 07 | [`../docs/architecture/26-right-panel-detail.md`](../docs/architecture/26-right-panel-detail.md) | Persistent word/line detail editing |
| 08 | [`../docs/architecture/08-page-actions.md`](../docs/architecture/08-page-actions.md) | Reload OCR / Save / Load / Rematch GT |
| 09 | [`../docs/architecture/09-persistence.md`](../docs/architecture/09-persistence.md) | UserPageEnvelope, image cache, session state |
| 10 | [`../docs/architecture/10-export.md`](../docs/architecture/10-export.md) | DocTR export dialog + endpoint |
| 11 | [`../docs/architecture/11-notifications.md`](../docs/architecture/11-notifications.md) | Toast queue, busy overlays, SSE jobs |
| 12 | [`../docs/architecture/12-hotkeys-a11y.md`](../docs/architecture/12-hotkeys-a11y.md) | Keybindings + a11y rules |
| 13 | [`../docs/architecture/13-driver-contract.md`](../docs/architecture/13-driver-contract.md) | `data-testid` + URL invariants for the driver |
| 14 | [`../docs/architecture/14-testing.md`](../docs/architecture/14-testing.md) | pytest + Vitest + Playwright strategy |
| 15 | [`../docs/architecture/15-deployment-dev.md`](../docs/architecture/15-deployment-dev.md) | Build, devcontainer, install |
| 18 | [`../docs/architecture/18-text-normalization.md`](../docs/architecture/18-text-normalization.md) | Long-S / ligature normalization (D-025) |
| 19 | [`../docs/architecture/19-auto-rotation.md`](../docs/architecture/19-auto-rotation.md) | Manual + auto page rotation (D-029) |
| 21 | [`../docs/architecture/21-konva-renderer.md`](../docs/architecture/21-konva-renderer.md) | Konva renderer for `PageImageCanvas` + `BBoxOverlay` (supersedes D-020 via D-043) |
| 22 | [`../docs/architecture/22-page-surface-wireup.md`](../docs/architecture/22-page-surface-wireup.md) | Mount the real labeling surface in `ProjectPage` |
| 23 | [`../docs/architecture/23-page-payload-backend.md`](../docs/architecture/23-page-payload-backend.md) | Real handlers for `GET /pages/{idx}` + 19 mutation endpoints |
| 24 | [`../docs/architecture/24-shell-layout.md`](../docs/architecture/24-shell-layout.md) | Studio shell — 5-zone grid, Rail, Drawer, Breadcrumb, QuickSearch |
| 25 | [`../docs/architecture/25-drawer-worklist.md`](../docs/architecture/25-drawer-worklist.md) | Drawer — Worklist, Hierarchy, BulkActions |
| 26 | [`../docs/architecture/26-right-panel-detail.md`](../docs/architecture/26-right-panel-detail.md) | Right-panel detail views — WordDetail, LineDetail, BlockDetail |
| 27 | [`../docs/architecture/27-right-panel-sections.md`](../docs/architecture/27-right-panel-sections.md) | Right-panel action sections — BBox / Rebox / Erase / CharRanges / CharFixer / Structure |
| 28 | [`../docs/architecture/28-palettes-pickers.md`](../docs/architecture/28-palettes-pickers.md) | StylePalette, ComponentPalette, UnicodePicker, useLayerColors |

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

## Source-code citations

In-source docstrings and comments still reference `specs/<file>` paths
for the specs that moved. These are non-runtime references (editor
navigation only). Updating them en masse is a separate chore — see the
follow-up issue filed in this audit pass.

## Adversarial Review

**Accepted finding:** The active/implemented split remains useful; retired execution artifacts
belong in Git history and the retirement manifest.

**Stage:** migration-time current-state review on 2026-07-13.

**Source:** an independent read-only reviewer compared this document with current
code, tests, architecture, and git history.

**Result:** the review accepted the finding above and used it to declare the
metadata status. Residual risks remain explicit here or in
`docs/context/intent-map.md`; deferred or blocked behavior is not claimed as
shipped.

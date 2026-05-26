# pdomain-ocr-labeler-spa: Auto-Rotation + Manual Rotate

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pdomain-ocr-labeler-spa#42

## TL;DR

Two surfaces: manual rotate buttons (Rotate ↺ / ↻, M9.1) and auto-rotate project-load pass
(M9.2). Manual rotate is 202+job (re-runs OCR). Auto-rotate uses gt-best-match (try 0/90/180/270,
pick best fuzz ratio against GT) or layout-analysis fallback. `PageRecord` gains
`rotation_degrees` + `rotation_source`. Rotation badge in PageActions; hidden when 0°, click-
to-revert on auto. Envelope bumps to v2.2 (additive; legacy tolerance verified first).

## Context

Book scans sometimes arrive sideways or upside-down. The legacy `pd-ocr-labeler` has no
rotation support. The SPA adds it post-GA (M9.1 / M9.2). Manual rotation re-runs OCR because
bboxes change when the image rotates. Auto-rotation is a project-load pass that evaluates all
four cardinal orientations and selects the best. The gt-best-match algorithm lives in
`pd_book_tools.ocr.rotation` (new module, delegated to pdomain-book-tools). Layout fallback
(`layout_only_orientation_score`) also lives in pdomain-book-tools.

## Constraints

- **Manual rotate is 202+job (re-runs OCR).** Bbox positions are meaningless on a rotated
  image without fresh OCR. No shortcut.
- **Auto-rotate is opt-in.** `auto_rotate_on_load = true` in OCR config; default true but
  user can disable.
- **gt-best-match requires GT.** When no GT exists, fall back to layout method automatically.
- **Rotation algorithm lives in pdomain-book-tools.** SPA calls `pd_book_tools.ocr.rotation`; if
  module is absent, auto-rotate is disabled with a warning.
- **Envelope bump to v2.2 is conditional.** Before writing v2.2, verify legacy reader tolerates
  extra nested fields. If it does not, use a sidecar `_rotation.json` file (Q-A1 fallback).
- **Rotate buttons hidden in M0–M8.** DOM presence (CSS `display: none`) with no JS wiring
  until M9.1. testids registered as stubs (`data-testid-stub="true"`).
- **Tilt correction out of scope.** This spec covers only 90° increments; skew/deskew is a
  separate future concern.

## Decision

### PageRecord additions

```python
class PageRecord(BaseModel):
    ...
    rotation_degrees: int = 0                                    # cumulative rotation applied
    rotation_source: Literal["none", "auto", "manual"] = "none"
```

### Manual rotate (M9.1)

`rotate-ccw-button` (Rotate ↺, degrees: -90) and `rotate-cw-button` (Rotate ↻, degrees: +90)
in `<PageActions />`. Optional `rotate-180-button`. Hidden via CSS until M9.1.

`POST /api/projects/{id}/pages/{idx}/rotate` body: `{degrees: -90|90|180, manual: true}`.
Returns 202+job_id. Job: rotate image, re-run OCR, update `PageRecord.rotation_degrees`,
auto-save to cache. `PagePayload` returned on job complete.

### Auto-rotate (M9.2)

`POST /api/projects/{id}/auto-rotate-all` body: `{method: "gt-best-match"|"layout"|null,
overwrite_manual: false}`. Returns 202+job. Iterates pages, runs `find_best_rotation` per page,
applies if confidence exceeds threshold (TBD, suggest 0.6).

GT-best-match algorithm: try each of {0, 90, 180, 270}, call `ocr_engine.ocr_image(rotated,
fast=True)`, compute `fuzz.ratio(normalize(ocr_text), normalize(gt_text)) / 100`, select max
score. Returns `(degrees, confidence)`. Layout fallback: `layout_only_orientation_score(image)`
from pdomain-book-tools; no GT required.

### Rotation badge

`rotation-badge` testid in `<PageActions />` (always present; hidden via CSS when
`rotation_degrees == 0`). Shows: "↻ 90 auto" or "↻ 90 manual". Tooltip: "Auto-rotated 90°
clockwise. Click to revert." (for auto) or "Manually rotated 90° clockwise." (for manual).
Clicking auto-badge: POST `.../rotate {degrees: -rotation_degrees, manual: true}`.
Badge color: gray (auto), blue (manual).

### OCR config additions

New "Auto-rotation" section in `<OCRConfigModal />`:
`auto-rotate-checkbox` (`auto_rotate_on_load`, default true),
`auto-rotate-method-select` (dropdown: `gt-best-match` / `layout` / `auto`).

### Envelope v2.2

```jsonc
{
  "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.2"},
  "source": {
    ...
    "rotation_degrees": 90,
    "rotation_source": "auto"
  }
}
```

Verification: before writing v2.2, test that legacy reader's `extra="ignore"` on nested
provenance tolerates the new fields. If legacy crashes (Q-A1 option B): store in sidecar
`<labeled-projects>/<project_id>_<page:03d>.rotation.json` and keep writing v2.1.

## Contract / Acceptance

- `rotate-cw-button` POST fires; 202 returned; job completes; image visibly rotated in
  viewport; source badge shows OCR; `rotation-badge` shows "↻ 90 manual".
- Rotate +90 four times returns to original orientation (idempotent modulo 360).
- Fixture with sideways scan: auto-rotate selects 90° with confidence ≥ 0.6; `rotation-badge`
  shows "↻ 90 auto"; click-to-revert: badge hides.
- `rotation_degrees` and `rotation_source` persist in envelope (or sidecar if Q-A1 resolves
  option B); survive server restart.
- When pdomain-book-tools rotation module absent: `auto_rotate_on_load` config toggle disabled
  with tooltip; manual rotate still works.

## Trade-offs considered

**Synchronous rotate vs 202+job.** Rotation without OCR re-run is fast, but OCR re-run is
required because bboxes change. OCR is slow; 202+job is mandatory. Chosen: 202+job always.

**Auto-rotate on every load vs first load only.** Every load would recheck and might change
orientation on a user who manually corrected it. Auto-rotate runs on first load only; manual
corrections are never overwritten unless `overwrite_manual=true` is passed explicitly. Chosen:
first-load pass only, `overwrite_manual=false` by default.

**v2.2 envelope vs sidecar.** v2.2 is cleaner but requires legacy compatibility verification.
Sidecar is the fallback if verification fails. Decision deferred to Q-A1 resolution. Chosen:
try v2.2 first; fallback to sidecar if needed.

**Confidence threshold.** 0.6 fuzz ratio is conservative but avoids false rotations on pages
with little GT overlap. The threshold is a config value (not hardcoded) so it can be tuned.

## Consequences

- The `PageRecord` schema change (adding `rotation_degrees`, `rotation_source`) must be
  reflected in `specs/01-data-models.md §3` and `api/types.ts`.
- Rotate buttons are DOM-present (hidden) from M0 onwards; the driver conformance test must
  treat them as stubs until M9.1.
- Auto-rotate adds significant project-load time for large books (4× detection-only OCR per
  page). The job must be cancel-able and show SSE progress.

## Open questions

- **Q-A1 — Envelope schema bump.** Before writing v2.2 envelopes, verify that the legacy
  reader's `extra="ignore"` tolerates new nested fields. If it crashes, fall back to sidecar
  `<project_id>_<page:03d>.rotation.json` (option B). Pending verification. See
  `specs/19-auto-rotation.md §9` and `OPEN_QUESTIONS.md` (entry pending).
- **Q-A3 — Indicator UI placement.** Three options: (A) inline text in toolbar, (B) separate
  badge below nav, (C) tooltip on rotate button. Source spec bet: option B (separate badge).
  Pending confirmation. See `specs/19-auto-rotation.md §9`.

## References

- `specs/19-auto-rotation.md` — legacy feature doc (GT-best-match algorithm, endpoint shapes, tests)
- `specs/17-decisions.md §D-029` — auto-rotation deferred to M9.1/M9.2 decision
- `specs/08-page-actions.md` — rotate button placement in PageActions
- `specs/13-driver-contract.md` — rotation-badge and rotate-button testid additions
- `pd_book_tools.ocr.rotation` — gt-best-match and layout algorithm (pdomain-book-tools team)

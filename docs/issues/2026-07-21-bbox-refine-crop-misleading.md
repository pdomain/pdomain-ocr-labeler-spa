---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I2
---

# BBox Refine / Crop buttons only rebox

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I2
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** Medium — labels advertise refine/crop; actions call rebox only
- **Affected version:** tree as of 2026-07-21 deep code review
- **Read when:** fixing WordDetail BBox section actions or toolbar refine parity.
- **Search terms:** P1-BBOX-UI, bbox-refine-button, bbox-crop-button, Expand + Refine, rebox only, BBoxSection.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md) (Wave
  3b)

## Summary

In `BBoxSection`, the Refine, Expand + Refine, and Crop buttons all call
`commitBbox` (rebox) instead of refine-bbox / expand-and-refine / crop APIs.
Users see action names that do not match backend behavior.

## Impact

- Misleading UI: Refine/Crop look like real operations but only rewrite bbox.
- Power users may think ink-snap refine ran when it did not.
- Driver/tests may assert wrong endpoints if they trust button labels.

## Environment / versions

```
frontend/src/components/right-panel/sections/BBoxSection.tsx
Repo: pdomain-ocr-labeler-spa (2026-07-21)
```

## Evidence

### 1. Buttons call commitBbox only

```
BBoxSection.tsx ~277–315
Refine / Expand+Refine / Crop onClick → commitBbox(draft) or expand then commitBbox
```

`commitBbox` is the rebox mutation path (same as Apply after edit).

### 2. Real refine exists elsewhere

Toolbar / job path can enqueue refine jobs; word-level refine routes may be
absent or unused by this panel (plan residual). Right-panel labels still oversell.

## Root-cause hypotheses

1. **(Most likely)** Gap 33 UI shipped with rebox as temporary stand-in; never
   wired to refine/crop endpoints.
2. Product intentionally collapsed refine into rebox without renaming buttons.

## Defects to fix

1. **Misleading Refine button** — does not call refine API.
2. **Misleading Crop button** — does not crop image.
3. **Expand + Refine** expands then reboxes only (no refine step).

## Recommended next steps

1. Wire each button to the real endpoint **or** rename labels to match rebox
   (e.g. “Apply bbox”, “Expand 4px + apply”).
2. If wiring: use existing refine job / word rebox APIs consistently with
   toolbar; add unit tests on click → mutation URL.
3. Prefer honesty over fake capability if crop is unsupported.

## What is NOT broken

- Manual bbox nudge/Apply rebox path.
- Right-panel Structure / CharFixer other sections.
- Backend refine job registration for page-level refine.

## Resolution

Open. Tracked as **P1-BBOX-UI** in the deep-review plan Wave 3b.

---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# ImageDriftBanner is hard-wired off on ProjectPage

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** Medium — 409 image-drift recovery UX never appears
- **Affected version:** verified 2026-07-21 (Wave 3b code review)
- **Read when:** handling save conflicts, 409 image_drift, inline banners, or
  page reload after source image change.
- **Search terms:** P1-IMAGE-DRIFT, ImageDriftBanner, imageDrift={false},
  409 image_drift, banner-image-drift.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  [`docs/architecture/08-page-actions.md`](../architecture/08-page-actions.md),
  `frontend/src/pages/ProjectPage.tsx`,
  `frontend/src/components/InlineBanners.tsx`

## Summary

`ImageDriftBanner` is mounted on `ProjectPage` but always receives
`imageDrift={false}`, so it never renders. There is no frontend state, save
`onError` path, or other prop that sets the flag true. Architecture and
notifications specs describe sticky inline recovery after `409 image_drift`;
the component and unit tests exist, but production wiring is a permanent off
switch.

Finding ID: **P1-IMAGE-DRIFT** (Wave 3b).

## Impact

- Users do not see the designed sticky warning when the on-disk page image has
  changed under them.
- Architecture’s image-drift recovery story (reload + messaging) is incomplete
  in the SPA even if the backend returns 409.
- Inline banner suite looks implemented in the tree while one of three banners
  is dead in production.

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Verified by static read of current tree, 2026-07-21
- Spec/architecture:
  `docs/architecture/08-page-actions.md` §14,
  `docs/specs/2026-05-12-notifications-design.md` (inline banners)
- Source plan:
  `docs/plans/2026-07-21-deep-code-review-continuation.md` (P1-IMAGE-DRIFT)

## Evidence

1. **Hard-coded false at the only production call site:**

```895:898:frontend/src/pages/ProjectPage.tsx
      <div data-testid="inline-banners" className="flex flex-col gap-1 p-1">
        <OcrFailedBanner ocrFailed={pageRecord?.ocr_failed === true} />
        <ImageDriftBanner imageDrift={false} />
      </div>
```

   Contrast: `OcrFailedBanner` is driven by live page state;
   `ImageDriftBanner` is not.

1. **Component only renders when the prop is true:**

```67:73:frontend/src/components/InlineBanners.tsx
export function ImageDriftBanner({ imageDrift }: ImageDriftBannerProps) {
  if (!imageDrift) return null;
  return (
    <Banner tone="warning" data-testid="banner-image-drift" role="alert">
      Image on disk has changed. Reload the page to continue editing.
    </Banner>
  );
}
```

1. **No other FE consumer of image-drift state.** Search under
   `frontend/src` for `imageDrift` / `image_drift` hits only `ProjectPage.tsx`
   (hard false), `InlineBanners.tsx`, and unit tests that toggle the prop
   directly. No mutation `onError` sets a drift flag.

1. **Save hooks do not special-case image_drift.** `usePageMutations` mentions
   409 for undo/redo bounds, not save-time `reason: "image_drift"`. Architecture
   §14 expects mutation `onError` to intercept `status === 409` with
   `body.reason === "image_drift"`, invalidate the page query, and toast; the
   banner remains a separate sticky surface that is never fed.

1. **Backend/e2e still treat 409 image_drift as real.** Integration/e2e and
   architecture cite `409 image_drift` for save-after-mtime change; the gap is
   client presentation/state, not the concept of drift.

## Root-cause hypotheses

1. **(Most likely) Placeholder mount.** Banner was landed with the
   notifications slice using a constant false prop “until” save-path wiring;
   that follow-up never landed.
2. **Architecture split without FE state.** Spec favors auto-reload + toast;
   the sticky banner was left as a parallel surface without a shared
   `imageDrift` bit on page or mutation error state.

## Defects to fix

1. **`imageDrift={false}` hard-off on ProjectPage** — primary.
2. **No client state or mutation error path** that sets image-drift true (and
   clears it after reload).
3. **Incomplete alignment with `08-page-actions.md` §14** (auto-reload + toast
   and/or sticky banner — pick one coherent recovery UX and implement it).

## Next steps

1. On save (and other write paths that can return image_drift), detect
   `409` + `reason === "image_drift"`.
2. Drive `ImageDriftBanner` from real state (React state, query meta, or
   store); clear on successful page refetch/navigation.
3. Implement or confirm auto-reload + toast per architecture §14 so recovery is
   not banner-only.
4. Add a ProjectPage or mutation test that a simulated 409 sets the banner (or
   toast+reload) path true.

## What is NOT broken

- `ImageDriftBanner` component behavior and unit tests when `imageDrift` is
  true.
- `OcrFailedBanner` wiring from `pageRecord.ocr_failed`.
- Backend concept of image drift / 409 responses (covered elsewhere).
- Banner primitive and `data-testid="banner-image-drift"` contract.

## Resolution

Open. Filed from deep code review Wave 3b (**P1-IMAGE-DRIFT**). No fix landed
in this documentation pass.

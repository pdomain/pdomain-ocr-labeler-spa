---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Canvas erase mode is a no-op on ProjectPage

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — advertised canvas erase path does nothing
- **Affected version:** verified 2026-07-21 (Wave 3b code review)
- **Read when:** wiring PageImageCanvas modes, erase-pixels mutations, or
  viewport erase UX.
- **Search terms:** P1-CANVAS-ERASE, onErasePixels, erase mode, PageImageCanvas,
  ErasePixelsSection, canvas erase no-op.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  `frontend/src/pages/ProjectPage.tsx`,
  `frontend/src/components/PageImageCanvas.tsx`,
  `frontend/src/components/right-panel/WordDetail.tsx`

## Summary

Viewport erase mode is a first-class canvas interaction (`ViewportMode` includes
`"erase"`; drag completion calls `onErasePixels?.(rect)`), but
`ProjectPage` mounts `PageImageCanvas` without `onErasePixels`. A user can
enter erase mode and drag an erase rect; the optional callback is undefined, so
the gesture is a silent no-op. The right-panel `ErasePixelsSection` path is
wired through `useErasePixels` and does POST erase ops.

Finding ID: **P1-CANVAS-ERASE** (Wave 3b).

## Impact

- Canvas erase looks available (mode pill, hotkeys, drag preview) but never
  mutates pixels or calls the API.
- Users who learn erase from the canvas path believe the product is broken;
  only the word-detail panel path works.
- Asymmetry between two advertised erase surfaces confuses support and tests.

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Verified by static read of current `master` tree, 2026-07-21
- Surfaces: React ProjectPage + PageImageCanvas + WordDetail
- Source plan:
  `docs/plans/2026-07-21-deep-code-review-continuation.md` (P1-CANVAS-ERASE)

## Evidence

1. **ProjectPage does not pass `onErasePixels`.** Mount only wires
   `onBoxSelect`, `onAddWord`, and `onRebox`:

```884:893:frontend/src/pages/ProjectPage.tsx
        <PageImageCanvas
          imageUrl={pagePayload?.image_url ?? ""}
          encoded={pagePayload?.encoded_dims ?? null}
          page={pagePayload}
          projectId={projectId}
          pageIndex={idx0}
          onBoxSelect={handleBoxSelect}
          onAddWord={handleAddWord}
          onRebox={handleRebox}
        />
```

   Repo-wide search of `ProjectPage.tsx` for `onErasePixels` / erase handlers
   returns no matches.

1. **PageImageCanvas fires erase only if the prop is set.** On erase-mode drag
   end it optional-chains the callback:

```613:616:frontend/src/components/PageImageCanvas.tsx
      case "erase": {
        onErasePixels?.(rect);
        exitToSelectMode();
        break;
      }
```

   The prop is optional (`onErasePixels?: (rect: BBox) => void`). Without a
   parent handler, mode still exits to select after a drag that did nothing.

1. **Right-panel erase is wired.** `WordDetail` mounts `ErasePixelsSection`
   with `erasePixels.mutateAsync(...)` from `useErasePixels`:

```247:257:frontend/src/components/right-panel/WordDetail.tsx
            <ErasePixelsSection
              backendAvailable={refineAvailable}
              imageUrl={pageImageUrl}
              cropBBox={word.bbox}
              onApply={(ops) =>
                erasePixels.mutateAsync({
                  lineIndex: lineIdx,
                  wordIndex: wordIdx,
                  ops,
                })
              }
            />
```

1. **Erase mode is intentionally product-visible.** `viewport-store` defines
   `"erase"` and toggle helpers; `useViewportHotkeys` documents Shift+E; the
   canvas shows an ERASE mode label and erase drag-preview styling. Component
   tests (`PageImageCanvas.test.tsx` “Erase mode”) only prove the component
   callback contract when a mock is passed — they do not prove ProjectPage
   wiring.

1. **Perf harness passes a stub, not production.** `PerfTestPage` sets
   `onErasePixels={() => undefined}`, confirming the prop is expected at the
   page level while production `ProjectPage` omits it.

## Root-cause hypotheses

1. **(Most likely) Incomplete ProjectPage mount.** Select / rebox / add-word
   got page-level handlers; erase remained optional and never got a sibling
   `handleErasePixels` that maps a page-space rect to word targets +
   `useErasePixels` (or a page-level erase API).
2. **Intentional dual-path product (less likely).** Canvas erase was left as
   mode chrome until a word-scoped rect→word mapping existed, but mode, hotkey,
   and pill were shipped anyway — still a user-facing defect until hidden or
   wired.

## Defects to fix

1. **Missing `onErasePixels` on ProjectPage’s `PageImageCanvas`** — primary.
2. **No page-level erase handler** mapping display rect → selected/intersecting
   word(s) → erase-pixels mutation(s).
3. **Optional:** if full canvas erase is deferred, hide erase mode / hotkey /
   pill so the feature is not advertised.

## Next steps

1. Prefer wiring: implement `handleErasePixels` on `ProjectPage` (or extract
   shared helper), pass it as `onErasePixels`, and reuse `useErasePixels` /
   backend erase-pixels for the hit word(s).
2. Add a ProjectPage-level test that the canvas prop is provided (mirror
   `ProjectPage.rebox.test.tsx` for `onRebox`).
3. If scope is unclear (page-wide white-out vs word-local), document the
   chosen rect→target rule in architecture before coding.
4. Close when canvas erase either mutates via API or erase mode is removed from
   the production surface.

## What is NOT broken

- Right-panel `ErasePixelsSection` + `useErasePixels` mutation path.
- Backend erase-pixels endpoint and OpenAPI operation (panel uses it).
- PageImageCanvas erase-mode drag geometry, preview, and callback contract when
  a parent supplies `onErasePixels`.
- Select, rebox, and add-word canvas wiring on ProjectPage.

## Resolution

Open. Filed from deep code review Wave 3b (**P1-CANVAS-ERASE**). No fix landed
in this documentation pass.

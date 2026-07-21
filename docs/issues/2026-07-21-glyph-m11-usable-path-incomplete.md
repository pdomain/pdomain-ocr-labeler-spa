---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# M11 glyph annotations: scaffold without usable end-to-end path

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — advertised glyph review path is not usable; set annotations vanish and never surface in payload
- **Affected version:** workspace tree as of 2026-07-21 (M11 residual)
- **Read when:** implementing M11 residual work, wiring WordDetail Typography, or changing glyph routes / page payload
  sidecars.
- **Search terms:** M11, glyph annotations, glyph_annotations_map, GlyphAnnotationPanel, WordDetail,
  page_to_line_matches, P0-GLYPH-READ, P0-GLYPH-UI, bulk-glyph-mark.
- **Relates to:**
  [`docs/plans/2026-07-21-glyph-annotations-completion.md`](../plans/2026-07-21-glyph-annotations-completion.md),
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  [`specs/20-glyph-annotations.md`](../../specs/20-glyph-annotations.md)

## Summary

M11 glyph annotations have a substantial **scaffold** (models, routes, bulk
recipes, UI components, WordCell chips, metrics, driver testids) but the
**usable human-review path is incomplete** (~20% usable path / ~35% scaffold).
POST set / accept / bulk-apply write in-memory sidecar maps, yet those maps are
never injected into `PagePayload`, glyph routes skip durable store write
(`pass  # STUB`), `GlyphAnnotationPanel` is not mounted in `WordDetail`, FE
mutation hooks are missing, chip clicks are stubs, and bulk apply does not
invalidate the page query.

This epic covers **P0-GLYPH-READ**, **P0-GLYPH-UI**, and glyph durable persist
(**plan Task 3 / T3**). Task-level checklist lives in the glyph completion plan;
cross-cut order is Wave 2 of the deep-review continuation plan. T3 depends on
Wave **0.1** (sidecar durability strategy decision).

## Impact

- Operators cannot complete glyph review as a real product path despite UI
  chrome and API endpoints existing.
- Successful POSTs look healthy (generation bump, 200 + payload) but annotations
  do not appear on subsequent reads of the same session payload, and do not
  survive save/reload.
- Bulk mark apply closes the dialog while chips/badges stay stale until a full
  manual refresh (and still would not show marks without payload inject).
- Metrics such as `glyphs_reviewed` can count in-memory map keys while the SPA
  never renders the corresponding word-level annotations.

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Spec: `specs/20-glyph-annotations.md` (M11)
- Plans:
  - `docs/plans/2026-07-21-glyph-annotations-completion.md` (T0–T11)
  - `docs/plans/2026-07-21-deep-code-review-continuation.md` (Wave 2; Wave 0.1 gate for T3)
- Finding IDs: `P0-GLYPH-READ`, `P0-GLYPH-UI`, plus durable-persist gap shared with
  sidecar work (`P0-SIDECAR-MAP` for glyphs)
- Verified by static inspection of backend + frontend sources (2026-07-21)

## Evidence

### 1. Payload inject missing (`P0-GLYPH-READ`)

`PageState` owns `glyph_annotations_map` / `glyph_predictions_map`
(`core/project_state.py`), and routes write those maps. `_page_payload` passes
only `char_bboxes_map` and `char_ranges_map` into `page_to_line_matches` — not
glyph maps:

```643:651:src/pdomain_ocr_labeler_spa/api/pages.py
                _rec, `lms = page_to_line_matches(
                    payload_obj,
                    page_index,
                    image_path,
                    source=page_source,
                    fuzz_threshold=_fuzz,
                    char_bboxes_map=_char_bboxes_map if _char_bboxes_map else None, # pyright:
                    ignore[reportArgumentType]
                    char_ranges_map=_char_ranges_map if _char_ranges_map else None, # pyright:
                    ignore[reportArgumentType]
                )
```

`page_to_line_matches` / `_word_to_word_match` only convert
`getattr(word_obj, "glyph_annotations", None)` and leave predictions unwired:

```290:294:src/pdomain_ocr_labeler_spa/core/page_to_line_matches.py
        # Glyph annotations — propagated from ``Word.glyph_annotations`` (spec §3).
        # ``source`` defaults to "human" for envelope-loaded pages.
        # ``glyph_predictions`` is left as None here; it is injected by the
        # ``IGlyphPredictor`` adapter at payload-build time (not yet wired).
        glyph_annotations = _convert_glyph_annotations(getattr(word_obj, "glyph_annotations", None))
```

**Proves:** SPA sidecar authority after POST is invisible on `PagePayload`
word matches even in-session.

### 2. Glyph routes write map + generation, then STUB (no store write)

`set_glyph_annotations` and `accept_glyph_prediction` update
`glyph_annotations_map`, bump generation, then no-op:

```1603:1610:src/pdomain_ocr_labeler_spa/api/words.py
    with page_lock:
        if ann_dict is not None:
            pstate.glyph_annotations_map[sidecar_key] = ann_dict
        else:
            _ = pstate.glyph_annotations_map.pop(sidecar_key, None)

        pstate.generation += 1
        pass  # STUB: cached-lane retired (M5b)
```

(same `pass  # STUB` after accept-prediction at ~1676–1677.)

Bulk apply updates the map and calls `_write_cached_envelope_best_effort`, which
is itself a retired no-op stub in `pages.py` (~295–298).

**Proves:** durable persist (T3) is missing; reload / process restart loses marks.

### 3. Panel not mounted; no FE mutations; chips stubs; bulk no invalidate (`P0-GLYPH-UI`)

- `WordDetail.tsx` has **no** `GlyphAnnotationPanel` / Typography / glyph import
  (grep over `frontend/src/components/right-panel/WordDetail.tsx` is empty).
- `useWordMutations.ts` has **no** `useSetGlyphAnnotations` /
  `useAcceptGlyphPrediction` (or any glyph mutation).
- `WordCell.tsx` chip handlers are placeholders (`/* future: open panel */` at
  multiple click sites ~297–337).
- `BulkGlyphMarkDialog.handleApply` posts apply then `onClose()` only — no
  `queryClient.invalidateQueries` for `["page", projectId, pageIndex]`
  (~86–97).

Components under `frontend/src/components/glyph/` exist with unit tests; bulk
button mounts in `PageActionsCompact` — scaffold without production mount path.

### 4. Completeness (plan assessment)

| Layer | Approx. | Note |
| --- | ---: | --- |
| Scaffold (files / seams) | ~35% | Models, routes, bulk recipes, components, chips, metrics |
| Usable path | ~20% | No inject, persist, panel mount, mutation hooks, or behavior e2e |

## Root-cause hypotheses

1. **(Most likely) M11 scaffold landed ahead of wiring.** Routes and UI pieces
   were added for milestones / component isolation; the keystone read path
   (`_page_payload` + `page_to_line_matches` sidecar stamp) and WordDetail host
   were deferred. Fits residual list in the glyph completion plan.
2. **M5b envelope retirement left store writes as STUB.** Glyph mutators still
   carry `pass  # STUB: cached-lane retired (M5b)` instead of event-store
   best-effort save; bulk uses the retired envelope helper. Fits
   `P0-SIDECAR-MAP` / Wave 0 durability theme.
3. **Right-panel migration orphaned the panel.** Spec / early UI assumed a
   dialog host; production host is `WordDetail`, and the panel was never remounted
   there (`WordEditDialog` absent from `frontend/`).

## Defects to fix

Ordered for implementers (matches glyph plan T1–T11 and Wave 2 sequencing):

1. **T1 — Inject glyph sidecars into page payload** — Add
   `glyph_annotations_map` / `glyph_predictions_map` kwargs to
   `page_to_line_matches` / `_word_to_word_match`; pass maps from `_page_payload`
   (mirror char maps). Without this, every set/accept/bulk is invisible.
2. **T2 — Integration tests for glyph routes** — HTTP set / clear / accept /
   bulk dry-run+apply assert stamped `PagePayload` words and generation.
3. **T3 — Durable persist + hydrate** — After Wave **0.1** sidecar strategy
   decision, write maps on set/accept/bulk (replace STUB / no-op envelope path)
   and rehydrate on load so save/reload keeps tri-state.
4. **T4 — FE mutation hooks** — `useSetGlyphAnnotations` +
   `useAcceptGlyphPrediction` in `useWordMutations.ts` with page query
   invalidation.
5. **T5 — Mount `GlyphAnnotationPanel` in `WordDetail`** — Typography accordion;
   wire hooks; default collapsed; auto-expand when predictions pending.
6. **T6 — WordCell chip click → edit / Typography** — Remove
   `/* future: open panel */` stubs; select word and open panel path.
7. **T7 — Bulk apply invalidates page query** — After successful apply, invalidate
   `["page", projectId, pageIndex]` (or equivalent) so chips/badges refresh.
8. **T8 — Metric + save-warning honesty** — With inject fixed, verify
   `glyphs_reviewed` and `glyph_review_incomplete` warning path.
9. **T9 — Behavior e2e** — `test_glyph_panel.py`, bulk apply e2e, reload persist
   when T3 lands.
10. **T10 — Optional polish** — predictor attach, predictions overlay, per-mark
    accept (defer unless capacity).
11. **T11 — Docs / behavior close-out** — current-state, behavior specs,
    AGENTS residual accuracy after close-out.

## Next steps

1. Execute Wave 2 via
   [`docs/plans/2026-07-21-glyph-annotations-completion.md`](../plans/2026-07-21-glyph-annotations-completion.md)
   **T1 first** (payload inject) — highest leverage, unblocks visibility of
   existing POSTs.
2. Land Wave **0.1** sidecar durability decision before or with **T3** (same
   strategy as CharFixer maps; do not invent a second persist story).
3. FE stream **T4 → T5 → T6 → T7** can start after T1 (or behind a thin mock)
   but must not claim usable until inject + mount + invalidation land.
4. Close with **T8–T9** acceptance: set → visible chips → reload still present →
   bulk updates UI without manual refresh; then **T11** docs.

## What is NOT broken

- Wire models (`GlyphAnnotationsModel`, `WordMatch.glyph_*`) and OpenAPI / TS
  types for glyph routes.
- Route surfaces: POST `.../glyph-annotations`, `.../accept-prediction`,
  `.../glyph-bulk-mark` (in-memory map updates + generation bump).
- Bulk recipe engine (`core/glyph/bulk_mark.py`) and unit tests.
- Predictor seam (`IGlyphPredictor` / `NoneGlyphPredictor`) as an adapter only.
- GT ligature codepoint reject on word GT update (separate from map inject).
- Save-path **warning plumbing** for incomplete glyph review when config requires
  it (honesty of counts still depends on real review + inject).
- Isolated glyph UI components + WordCell display from payload fields when
  present; bulk dialog mount / testids.
- Core non-glyph labeling path (word/line edit, save, export) — out of this epic
  except shared sidecar strategy for T3.

## Resolution

Open. Implementation plan:
[`docs/plans/2026-07-21-glyph-annotations-completion.md`](../plans/2026-07-21-glyph-annotations-completion.md)
(T0–T11). Prioritization:
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md)
Wave 2; T3 gated on Wave 0.1.

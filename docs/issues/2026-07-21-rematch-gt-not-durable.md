---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Rematch GT updates memory only; envelope autosave is a no-op

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — rematch returns 200; GT mapping lost unless a later content save runs
- **Affected version:** tree as of 2026-07-21 deep code review
- **Read when:** fixing rematch-gt, GT matching durability, or Wave 0.3 store wiring.
- **Search terms:** P0-REMATCH, rematch-gt, rematch_page, `write_cached_envelope_best_effort, ground truth rematch,
  autosave.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md) (Wave
  0.3, 0.6)

## Summary

`POST .../pages/{idx}/rematch-gt` re-runs page-level GT matching on the live
`Page` object, bumps generation, then calls
`_write_cached_envelope_best_effort` — a retired M5b **no-op**. It never
invokes content-blob autosave (`_save_to_store_best_effort` /
`save_page_content_to_store`). The response is HTTP 200 with an updated
payload, so rematch looks successful while remaining non-durable.

Unlike pure sidecar maps, rematch **does** mutate live page GT content. The
fix is wiring that mutation to the event store, not inventing a new map
carrier.

## Impact

- User rematches after OCR or GT source changes; results vanish on reload.
- Dirty bit advances; Save Project *can* later serialize the in-memory `Page`
  if the process is still up and `page_id` is set — but a crash/reload before
  a content-blob save loses rematch.
- Pipeline scorecard marks “GT match / rematch” as PARTIAL for this reason.

## Environment / versions

```
Repo: pdomain-ocr-labeler-spa
Finding ID: P0-REMATCH
Source: docs/plans/2026-07-21-deep-code-review-continuation.md Wave 0.3
Route: src/pdomain_ocr_labeler_spa/api/pages.py rematch_gt
Matcher: src/pdomain_ocr_labeler_spa/core/ground_truth_matcher.py rematch_page
```

## Evidence

### 1. Rematch mutates then “autosaves” via no-op helper

```1184:1208:src/pdomain_ocr_labeler_spa/api/pages.py
    with page_lock:
        ok = rematch_page(page, gt_text)
        if not ok:
            return JSONResponse(
                status_code=400,
                ...
            )
        pstate.generation += 1

        # Best-effort cached-envelope autosave — spec §12 + §13.
        # Inside the lock so the cache write is serialised with the
        # mutation (prevents torn writes from concurrent rematches).
        _write_cached_envelope_best_effort(
            page=page,
            project_state=project_state,
            page_index=page_index,
            settings=settings,
        )
```

Returns 200 with `_page_payload` after the lock (lines ~1210–1218).

### 2. Envelope helper is explicitly a STUB

```288:298:src/pdomain_ocr_labeler_spa/api/pages.py
def _write_cached_envelope_best_effort(
    *,
    page: Any,
    project_state: ProjectState,
    page_index: int,
    settings: Settings,
) -> None:
    """STUB: cached-envelope lane retired (M5b). No-op until M9 wires LabelerPageStore."""
    # The UserPageEnvelope + LaneResolver path is deleted (greenfield event-store adoption).
    # M9 replaces this call with a LabelerPageStore.save_page() via save_page_to_store.
    pass  # pragma: no cover
```

Comment claims M9 will replace this; rematch still has not been wired to the
store path used by word mutators.

### 3. Working pattern exists on word routes

`api/words.py` `_save_to_store_best_effort` (~394–427) re-serializes the page
via `save_page_content_to_store` when `store` and `page_id` are present.
Rematch does not call it (and `rematch_gt` already receives optional
`page_store` via Depends but never uses it for write).

### 4. Structural edits already rematch + persist differently

`api/lines_paragraphs.py` finalizers auto-rematch then persist content (see
comments ~511–546 referencing the words.py store path). Standalone
`rematch-gt` is the gap.

## Root-cause hypotheses

1. **(Most likely) M5b left rematch on the retired envelope path** while word
   content mutators moved to event-store autosave; rematch was never updated.
2. **Assumption that Save Project would always follow rematch** — true only if
   the user saves before reload and the page has a serializable payload +
   `page_id`.
3. **Spec §12/§13 still name “cache write”** in comments, masking that the
   helper body is empty.

## Defects to fix

1. **`rematch_gt` never calls content-blob autosave** after a successful
   `rematch_page`.
2. **`_write_cached_envelope_best_effort` no-op** is still the only “persist”
   call inside the rematch lock — false sense of durability.
3. **`page_store` dependency is unused for write** on the rematch route despite
   being injected.
4. **No integration test** that rematch → process-fresh reload keeps GT
   mapping (Wave 0.6).

## Recommended next steps

1. **Wave 0.3 — wire rematch through content-blob autosave**
   (`_save_to_store_best_effort` or direct `save_page_content_to_store`) after
   successful `rematch_page`, using existing `page_store` / `page_id` patterns
   from word routes.
2. Remove or stop calling the envelope no-op from rematch (or leave only as a
   clearly dead import path elsewhere).
3. **Wave 0.6 — integration test:** rematch → reload page from store → GT
   mapping kept.
4. Confirm interaction with auto-rematch-on-structure paths so rematch is not
   double-written inconsistently.

## What is NOT broken

- **`rematch_page` matching logic** itself and in-session payload after rematch.
- **Core GT edits** that go through word mutators + store best-effort.
- **Structural-edit auto-rematch + persist** paths that already use the store
  finalizer in `lines_paragraphs.py` (verify per-route; do not regress them).
- **400 paths** (`no_ground_truth`, `rematch_failed`, `page_not_loaded`) —
  error envelopes still work.
- **Intentional no-store sessions** — missing store should no-op write, not
  invent envelopes.

## Resolution

Open. Tracked as **P0-REMATCH** in
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md)
Wave 0.3.

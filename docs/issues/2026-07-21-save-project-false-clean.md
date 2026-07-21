---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Save Project marks pages clean without durable content

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — dirty bit cleared after skip or changelog-only write; data looks saved when it is not
- **Affected version:** tree as of 2026-07-21 deep code review
- **Read when:** fixing save_project dirty-bit logic, generation accounting, or Wave 0.4.
- **Search terms:** P0-SAVE-DIRTY, last_saved_generation, save_project, page_id unset, changelog-only, dirty bit, false
  clean.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md) (Wave
  0.4, 0.6)

## Summary

The `save_project` job advances `last_saved_generation` to the current
`generation` for dirty pages even when it **did not** persist page content:
(1) `page_id` is unset so the store write is skipped, and (2) the changelog-only
fallback runs because there is no serializable live `Page` payload. The UI and
dirty predicate then treat the page as clean. Exception-path failures already
`continue` before the advance and are not the bug.

## Impact

- User clicks Save Project; job reports progress and may note skipped pages,
  but the page no longer appears dirty.
- Edits that only lived in memory (or that never got a content blob) are easy
  to lose on navigation/restart without a second dirty signal.
- Combines badly with non-durable rematch/sidecar maps: generation advanced on
  mutate, then “saved” without content.

## Environment / versions

```
Repo: pdomain-ocr-labeler-spa
Finding ID: P0-SAVE-DIRTY
Source: docs/plans/2026-07-21-deep-code-review-continuation.md Wave 0.4
Handler: src/pdomain_ocr_labeler_spa/core/jobs/handlers/save_project.py
Dirty predicate: PageState.generation > last_saved_generation
```

## Evidence

### 1. Single advance site after both success and skip paths

```142:199:src/pdomain_ocr_labeler_spa/core/jobs/handlers/save_project.py
        # Event-store save path: persist each dirty page to the store.
        # Skip pages without a registered page_id (not yet in the store —
        # no-op is safe; they'll be saved when OCR writes them to the store).
        if page_store is not None and pstate.page_id is not None:
            try:
                changes = [{"type": "save_project", "page_index": page_index}]
                ...
                if payload is not None and callable(getattr(payload, "to_dict", None)):
                    save_page_content_to_store(...)
                else:
                    # No live Page to re-serialize — record changelog only.
                    log.debug(
                        "save_project: page %d has no serializable payload — "
                        "falling back to changelog-only store write",
                        page_index,
                    )
                    save_page_to_store(
                        page_id=pstate.page_id,
                        changes=changes,
                        store=page_store,
                    )
            except Exception as exc:
                ...
                continue
        elif page_store is None:
            # No store available — treat as clean success (in-memory only session).
            log.debug("save_project: no page_store in context — skipping store write for page %d", page_index)
        else:
            # page_id not set — page not yet registered in store; track as skipped.
            log.debug("save_project: page %d has no page_id — skipping store write", page_index)
            skipped.append(page_index)
        pstate.last_saved_generation = pstate.generation
```

`last_saved_generation` is assigned **outside** the successful content-write
branch, so skip and changelog-only both clear dirty.

### 2. Changelog-only cannot rehydrate content

Handler comments (~148–155) state that `save_page_to_store` without a content
blob causes `load_page_from_store` to return None after a fresh-store reload —
yet that path still advances the clean marker.

### 3. Exception path correctly stays dirty

On store exception the handler appends to `failures`, updates progress, and
`continue`s **before** line 199 — exception failures are already excluded from
false-clean (plan Wave 0.4: do not treat exception-path as clean).

### 4. Intentional no-store session

When `page_store is None`, the handler also advances clean. That is an
in-memory-only session policy (out of scope for this issue’s product fix for
registered projects), but the same line of code is shared with the `page_id`
skip path — fix carefully so no-store behavior stays deliberate.

## Root-cause hypotheses

1. **(Most likely) Dirty-bit advance was written as “iteration completed”
   rather than “content blob durable.”** Skip bookkeeping (`skipped` list /
   notifications) was added without gating the generation update.
2. **Changelog-only fallback was meant as best-effort audit** but was treated
   as equivalent success for the dirty predicate.
3. **Assumption that `page_id is None` pages are never user-dirty** is false
   once mutators bump generation before store registration.

## Defects to fix

1. **`page_id` unset still sets `last_saved_generation`** after logging skip
   (~196–199).
2. **Changelog-only `save_page_to_store` still sets `last_saved_generation`**
   though no content blob was written (~164–175, 199).
3. **Dirty predicate cannot distinguish** “saved content” vs “save job visited
   this page.”
4. **Missing tests** that skip-page and changelog-only never clear dirty
   (Wave 0.6).

## Recommended next steps

1. **Wave 0.4 — gate the advance:** set `last_saved_generation` only after a
   successful **content** blob write (`save_page_content_to_store`). Do **not**
   advance for missing `page_id` or changelog-only fallback.
2. Keep exception path as-is (`continue` before advance).
3. Preserve intentional no-store in-memory sessions as an explicit policy (do
   not silently conflate with “store present but page unregistered”).
4. **Wave 0.6 — tests:** skip-page and changelog-only never clean dirty bit;
   content save still does.
5. **Same root cause on single-page save:** `api/pages.py` ~939–972 advances
   `last_saved_generation` after changelog-only / missing-`page_id` paths.
   Fix that path in the same change set, not as an optional follow-up.

## What is NOT broken

- **Successful content-blob save path** when `page_store` and `page_id` exist
  and payload has `to_dict` — that path is the intended durable save.
- **Exception failures** — already stay dirty via `continue`.
- **Core GT edits that already wrote content blobs** via mutator autosave —
  those survive independently of this dirty-bit bug (bug is false *clean*, not
  false *dirty*).
- **Intentional no-store sessions** — product may still treat pure memory
  sessions as “save is a no-op success”; call that out in the fix, do not
  confuse with registered store pages.

## Resolution

Open. Tracked as **P0-SAVE-DIRTY** in
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md)
Wave 0.4.

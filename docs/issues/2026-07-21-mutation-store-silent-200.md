---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Content mutators return 200 when store write fails

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — silent loss: in-memory success reported while disk store failed
- **Affected version:** tree as of 2026-07-21 deep code review
- **Read when:** changing word mutation persistence, error surfacing to the SPA, or Wave 0.5.
- **Search terms:** P1-MUTATION-200, `save_to_store_best_effort, silent 200, store write failure, best-effort persist.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md) (Wave
  0.5)

## Summary

Word (and related) content mutators call `_save_to_store_best_effort`, which
swallows all exceptions, logs a WARNING, and returns. Callers still bump
generation and return HTTP **200** with a page payload that reflects
in-memory state only. The SPA has no signal that the event store write failed,
so users believe edits are durable when they are not.

## Impact

- Disk full, permission errors, corrupt store, or transient I/O failures become
  invisible data-loss risks.
- In-memory session continues; reload from store reverts the edit.
- Combines with false-clean save (P0-SAVE-DIRTY) if a later Save Project also
  fails or skips: dirty accounting and HTTP status both understate risk.

## Environment / versions

```
Repo: pdomain-ocr-labeler-spa
Finding ID: P1-MUTATION-200
Source: docs/plans/2026-07-21-deep-code-review-continuation.md Wave 0.5
Helper: src/pdomain_ocr_labeler_spa/api/words.py _save_to_store_best_effort
Consumers: word GT/style/structure mutation routes (and any mirror helpers)
```

## Evidence

### 1. Best-effort helper swallows exceptions

```394:427:src/pdomain_ocr_labeler_spa/api/words.py
def _save_to_store_best_effort(
    *,
    pstate: PageState,
    store: Any,  # LabelerPageStore | None
    changes: list[dict[str, Any]],
) -> None:
    """Persist a word-mutation event to the store; swallow errors.
    ...
    Best-effort: a store write failure must not turn a successful in-memory
    mutation into a 500.  Logs at WARNING so problems are visible without
    being fatal.
    ...
    """
    if store is None or pstate.page_id is None:
        return
    try:
        from ..core.page_state import save_page_content_to_store, save_page_to_store

        page = _resolve_page_object(pstate)
        if page is not None and callable(getattr(page, "to_dict", None)):
            save_page_content_to_store(page_id=pstate.page_id, page=page, store=store, changes=changes)
        else:
            save_page_to_store(page_id=pstate.page_id, changes=changes, store=store)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("_save_to_store_best_effort: failed page_id=%s: %s", pstate.page_id, exc)
```

Return type is `None` with no success/failure flag for callers.

### 2. Routes always return 200 after mutate + best-effort

`_refresh_payload_response` always builds a 200 JSONResponse (~430–446).
Typical mutator pattern: lock → mutate → generation++ →
`_save_to_store_best_effort(...)` → `_refresh_payload_response(...)` with no
inspection of store outcome (e.g. GT update ~536+, and parallel sites at
~594, 656, 728, 798, 1004, 1077, 1351).

### 3. Design comment vs product honesty

The helper docstring intentionally avoids 500 on store failure so in-memory
mutation “wins.” That is a deliberate implementation choice for process
stability, but it is **not** honest to the client contract when the product
implies autosave durability for store-backed projects.

## Root-cause hypotheses

1. **(Most likely) “Best-effort” was coded as fire-and-forget** to protect
   mutation latency and avoid 500s, without a parallel warning channel to the
   SPA.
2. **Logging-only ops signal** assumes operators tail server logs; labeler
   users do not.
3. **No OpenAPI field** for partial success / `store_persisted: false`, so
   implementers defaulted to pure 200.

## Defects to fix

1. **`_save_to_store_best_effort` returns void and swallows errors** — callers
   cannot branch.
2. **HTTP 200 on store write failure** for content mutators that claim success.
3. **No FE-visible warning field or non-2xx** for durable-session store
   failures (Wave 0.5).
4. **Symmetric risk on related best-effort helpers** (e.g. image blob persist
   ~449–476) — inventory when fixing; at minimum content mutators must surface
   failure.

## Recommended next steps

1. **Wave 0.5 — surface store-write failures** for content mutators that claim
   success today: either non-200 (e.g. 503/500 with stable error code) **or**
   200 with an explicit warning / `persisted: false` field in the payload
   contract (decide and document; prefer failing closed when `store` and
   `page_id` are present).
2. Change helper to return `bool` / result object; do not log-and-forget only.
3. Keep **`store is None` / `page_id is None`** as intentional no-op success
   for tests and pre-registration loads — do not treat those as write failures.
4. FE: toast or banner when persistence fails; leave page dirty.
5. Tests: inject store failure → assert non-silent client signal; happy path
   still 200 + durable.

## What is NOT broken

- **In-memory mutation application** — GT/text/structure still update the live
  `Page` when the route succeeds.
- **Successful store writes** — happy path content blob autosave works for core
  word/line edits.
- **Intentional no-store sessions** (`store is None`) and unregistered pages
  (`page_id is None`) — early return is correct; do not force errors there.
- **Char range/bbox STUB routes** — they never call this helper (separate
  P0-SIDECAR-MAP issue); fixing 200-on-failure does not by itself make those
  durable.
- **Rematch envelope no-op** — separate P0-REMATCH (never reaches this helper).

## Resolution

Open. Tracked as **P1-MUTATION-200** in
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md)
Wave 0.5.

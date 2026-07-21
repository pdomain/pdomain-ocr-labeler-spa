---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Char ranges and char bboxes are not durable across reload

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — CharFixer Apply returns 200; maps vanish after reload/Save Project
- **Affected version:** tree as of 2026-07-21 deep code review
- **Read when:** fixing CharFixer durability, PageState sidecars, or Wave 0 persistence work.
- **Search terms:** P0-SIDECAR-MAP, char_ranges_map, char_bboxes_map, set_char_ranges, set_char_bboxes, CharFixer, STUB
  M5b, sidecar durability.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md) (Wave
  0.1–0.2, 0.6); strategy decision to record in [`docs/context/decisions.md`](../context/decisions.md)

## Summary

`POST .../char-ranges` and `POST .../char-bboxes` write only in-memory
`PageState` sidecar maps, bump generation, and return HTTP 200 with a fresh
page payload. The former cached-lane envelope write is a retired STUB (`pass`
after M5b). Nothing serializes those maps into the event store, so CharFixer
work is lost on process restart or a full page reload even after Save Project.

This issue covers **char ranges and char bboxes only**. Glyph annotation maps
share the same STUB pattern but are tracked under the M11 / glyph residual
work (Wave 2), not here.

## Impact

- CharFixer Apply reports success while data is session-only.
- Reload or restart drops ranges/bboxes; Save Project does not recover them
  because they were never written to a content blob or extension.
- Generation still advances, so the page can look dirty then clean without
  durable map content.
- Undo story is undefined: maps sit outside the content blob that undo
  rehydrates.

## Environment / versions

```
Repo: pdomain-ocr-labeler-spa
Finding ID: P0-SIDECAR-MAP (char subset)
Source: docs/plans/2026-07-21-deep-code-review-continuation.md Wave 0
Handlers: src/pdomain_ocr_labeler_spa/api/words.py
Sidecars: PageState.char_ranges_map / char_bboxes_map
```

## Evidence

### 1. `set_char_ranges` STUB after in-memory write

`src/pdomain_ocr_labeler_spa/api/words.py` stores ranges on the word and in
`pstate.char_ranges_map`, bumps generation, then no-ops persistence:

```1452:1460:src/pdomain_ocr_labeler_spa/api/words.py
        range_dicts = [r.model_dump() for r in body.ranges]
        # Store as a plain Python attribute — no pdomain-book-tools API yet.
        word.char_ranges = range_dicts
        # Write into the in-memory sidecar so the payload builder can surface
        # the values onto WordMatch.char_ranges on the next page load.
        pstate.char_ranges_map[sidecar_key] = range_dicts

        pstate.generation += 1
        pass  # STUB: cached-lane retired (M5b)
```

The route still returns 200 via `_refresh_payload_response` immediately after.

### 2. `set_char_bboxes` same STUB pattern

```1533:1539:src/pdomain_ocr_labeler_spa/api/words.py
    page_lock = project_state.get_page_lock(page_index)
    with page_lock:
        # Write into the in-memory sidecar on PageState.
        pstate.char_bboxes_map[sidecar_key] = bbox_dicts

        pstate.generation += 1
        pass  # STUB: cached-lane retired (M5b)
```

Docstring still claims envelope/`word_attributes` durability (lines ~1487–1490)
that the STUB no longer provides.

### 3. Contrast: core word mutators use event-store best-effort

Working GT/style/structure paths call `_save_to_store_best_effort` (e.g.
`words.py` ~536+). Char map routes never call it. The retired envelope helper
is an empty stub:

```479:492:src/pdomain_ocr_labeler_spa/api/words.py
def _write_cached_envelope_best_effort(
    ...
) -> None:
    """Backward-compat stub for ``lines_paragraphs.py`` import.
    ...
    migrated to ``_save_to_store_best_effort`` (the event-store path).
    """
```

### 4. In-session payload surface works

`PageState.char_ranges_map` / `char_bboxes_map` are injected in
`page_to_line_matches` / `_page_payload`, so the SPA sees maps until memory is
cleared. That makes the failure silent: UI and 200 both look correct.

## Root-cause hypotheses

1. **(Most likely) M5b retired the envelope write without a replacement for
   labeler-only sidecar maps.** Core content mutators were migrated to
   `_save_to_store_best_effort`; char map routes kept the STUB `pass`.
2. **book-tools `Word.to_dict` / `from_dict` does not carry `char_ranges` /
   char bboxes**, so even embedding requires an explicit carrier (word dict
   fields, extension blob, or LabelerEdited payload) — see comments on
   `set_char_ranges` (~1400–1408).
3. **No Wave 0.1 durability decision yet**, so implementers correctly avoided
   inventing a persistence shape without ADR.

## Defects to fix

1. **No event-store serialization for `char_ranges_map`** after
   `set_char_ranges` — only memory + generation bump + 200.
2. **No event-store serialization for `char_bboxes_map`** after
   `set_char_bboxes` — same STUB.
3. **Stale docstrings / API contract** still imply envelope durability that
   does not exist.
4. **Undo coherence undefined** for out-of-blob maps (Wave 0.1 must require
   clear/rehydrate or embed-in-blob).

## Recommended next steps

1. **Wave 0.1 — decide sidecar durability strategy** and record it in
   `docs/context/decisions.md` (options A embed in content `Page.to_dict` /
   word dicts; B extension/side blob; C separate LabelerEdited fields). Must
   cover undo: out-of-blob maps require clear/rehydrate on history restore.
   Default to A when fields fit word dicts; prefer B if book-tools rejects
   unknown keys on round-trip. Record one rejected alternative.
2. **Wave 0.2 — persist char ranges + char bboxes on mutate** using that
   strategy (replace STUB `pass` with real store write; hydrate on page load).
3. **Wave 0.6 — integration tests:** set char sidecar → reload page → present;
   **undo after sidecar mutate** leaves maps + content coherent.
4. Do **not** block this issue on glyph maps (Wave 2 T3); share the 0.1
   decision only.

## What is NOT broken

- **Core GT / word / line / structure edits** that call
  `_save_to_store_best_effort` / content-blob autosave — those do persist.
- **In-session CharFixer UX** for the current process: maps appear on the
  payload while `PageState` lives.
- **Glyph annotations / predictions** — same STUB family, but **out of scope
  for this issue** (M11 / Wave 2).
- **Intentional no-store sessions** (`store is None`) — not a false-success
  path for this defect; the defect is store-present sessions that still drop
  maps.

## Resolution

Open. Tracked as **P0-SIDECAR-MAP** (char ranges + char bboxes) in
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md)
Wave 0. No durable strategy ADR yet in `docs/context/decisions.md`.

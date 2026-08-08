---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I2
---

# ExportRequest.normalize_recognition_labels never reaches the export job

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I2
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** Medium — advertised API flag is a no-op end-to-end
- **Finding ID:** P1-NORMALIZE
- **Affected version:** verified 2026-07-21 (Wave 1 source plan)
- **Read when:** changing export request payload, text normalization, or recognition labels.json write.
- **Search terms:** normalize_recognition_labels, ExportRequest, export job payload, text normalize, P1-NORMALIZE.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md) Wave
  1.4; `src/pdomain_ocr_labeler_spa/api/export.py`; `frontend/src/components/ExportDialog.tsx`

## Summary

`ExportRequest` documents and accepts `normalize_recognition_labels` (default
`False`), intending long-s/ligature normalization of recognition `labels.json`
strings. `start_export` never copies the field into the job payload; the
export handler never reads it. The SPA hardcodes
`normalize_recognition_labels: false` on submit. The flag is dead from API
model through UI.

## Impact

- Clients that set `normalize_recognition_labels: true` get silent no-op behavior (job still 202s).
- Product surface claims a text-normalization control that cannot take effect.
- Unit tests only cover Pydantic field presence, not payload propagation or handler behavior.

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Source plan: `docs/plans/2026-07-21-deep-code-review-continuation.md` (Wave 1.4, P1-NORMALIZE)
- Related field docs: ExportRequest docstring references §18-text-normalization
- Verified against current tree on 2026-07-21

## Evidence

### 1. Request model has the field

`src/pdomain_ocr_labeler_spa/api/export.py` — `ExportRequest`:

```python
normalize_recognition_labels: bool = False
```

Docstring: when `True`, recognition `labels.json` strings are normalised
(long-s → ASCII, ligatures → ASCII); image bytes unchanged; silent ignore if
`pdomain_book_tools.text.normalize` is absent.

### 2. Job payload omits it

Same file — `start_export` submits:

```python
payload = (
    {
        "scope": body.scope.value,
        "page_index": body.page_index,
        "style_filters": body.style_filters,
        "component_filter": body.component_filter,
        "include_classification": body.include_classification,
        "detection_only": body.detection_only,
        "recognition_only": body.recognition_only,
    },
)
```

No `normalize_recognition_labels`.

### 3. Handler does not read it

`handle_export` unpacks `scope`, `style_filters`, `component_filter`,
`include_classification`, `detection_only`, `recognition_only`, `page_index`
only — no normalize flag, no call site into text normalize on labels write.

### 4. Frontend hardcodes false

`frontend/src/components/ExportDialog.tsx` (and
`frontend/src/components/drawer/BulkActions.tsx`) send
`normalize_recognition_labels: false` with no UI toggle.

### 5. Tests stop at the model

`tests/unit/test_text_normalize.py` asserts the Pydantic field defaults and
can be set `True`; it does not assert job payload or export handler behavior.

## Root-cause hypotheses

1. **(Most likely) Half-landed feature** — model + OpenAPI + FE constant were
   added for §18 text normalization; wiring through `start_export` → payload →
   `_export_page` never shipped.
2. **Product deferred the control** — FE hardcodes false intentionally, but
   the API still advertises a working switch, which is dishonest either way.

## Defects to fix

1. **Payload drop** — `start_export` does not put `normalize_recognition_labels` in the job payload.
2. **Handler ignore** — export path never applies recognition-label normalization when requested.
3. **FE dead constant** — no control; always `false` (either wire a real option or stop sending a fake capability).

## Next steps

1. **Wave 1.4:** if product still wants the flag — pass it in job payload,
   honor it in recognition `labels.json` write (shared by in-app and CLI if
   applicable), add unit/integration coverage for true → normalized strings.
2. If product does **not** want it — remove or deprecate the field from
   `ExportRequest`/OpenAPI and drop FE hardcoding after a deliberate decision.
3. Prefer honesty: either end-to-end behavior or no advertised field.

## What is NOT broken

- Other export request fields (`scope`, filters, detection/recognition modes) still reach the handler.
- Core DocTR export of images/labels without normalization still runs.
- Text-normalization helpers elsewhere (if used by other features) are out of scope unless shared by this wire-up.
- P0 export list and CLI store findings are independent
  (`2026-07-21-export-list-api-empty.md`,
  `2026-07-21-cli-export-not-store-first.md`).

## Resolution

Open. Wave 1.4 in
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md):
wire through job payload if product still wants it; otherwise retire the field
honestly.

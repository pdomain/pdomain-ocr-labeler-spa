---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# GET /exports always returns [] despite on-disk doctr-export manifests

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — export history/discovery via API is a permanent empty stub
- **Finding ID:** P0-EXPORT-LIST
- **Affected version:** verified 2026-07-21 (Wave 1 source plan)
- **Read when:** implementing export list API, export history UI, or changing doctr-export manifests.
- **Search terms:** list_exports, ExportManifest, pdomain.doctr-export-manifest, GET exports, export history,
  P0-EXPORT-LIST.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md) Wave
  1.0–1.1; `src/pdomain_ocr_labeler_spa/api/export.py`; `src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py`

## Summary

`GET /api/projects/{project_id}/exports` always returns `[]`, even after a
successful in-app export that writes a real on-disk DocTR export manifest
(`schema: "pdomain.doctr-export-manifest"`). The API model and the disk
contract do not match: API `ExportManifest` is `{job_id, scope, created_at}`;
disk is a multi-project map with `exported_at`, `page_count`, and per-task
stats. Listing must not be implemented until that contract is decided (Wave
1.0 before 1.1).

## Impact

- Export history and discovery surfaces that call the list API always look empty.
- Callers cannot discover prior export runs, page counts, or task stats via API.
- A naive “just read the file” implementation will break OpenAPI/FE types because of the shape mismatch.

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Source plan: `docs/plans/2026-07-21-deep-code-review-continuation.md` (Wave 1, P0-EXPORT-LIST)
- Verified against current tree on 2026-07-21

## Evidence

### 1. List endpoint is an unconditional empty stub

`src/pdomain_ocr_labeler_spa/api/export.py` — `list_exports`:

```python
@router.get("/{project_id}/exports", response_model=list[ExportManifest])
def list_exports(project_id: str) -> JSONResponse:
    """``GET /api/projects/{id}/exports`` — past exports (best-effort).

    Spec §5.9 line 326. Returns a list of past export manifests read
    from disk. Until the export handler writes manifests, always returns
    an empty list (spec says "best-effort").
    """
    return JSONResponse(status_code=200, content=[])
```

The docstring still claims manifests are not written; that is stale.

### 2. Handler does write a real disk manifest

`src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py` —
`_write_export_manifest` (called at end of `handle_export`) merges/updates
`<data_root>/doctr-export/manifest.json` with schema
`pdomain.doctr-export-manifest` and a `projects` map:

```text
{
  "schema": "pdomain.doctr-export-manifest",
  "version": 1,
  "generated_at": "<ISO-8601>",
  "app": "pdomain-ocr-labeler-spa",
  "projects": {
    "<project_id>": {
      "exported_at": "<ISO-8601>",
      "page_count": <int>,
      "tasks": { "<task>": {"item_count": <int>} }
    }
  }
}
```

Unit/integration coverage: `tests/unit/core/test_export_manifest.py`,
`tests/integration/test_export_manifest_integration.py`.

### 3. Shape mismatch (API vs disk)

API placeholder model in the same module:

```python
class ExportManifest(BaseModel):
    job_id: str
    scope: str
    created_at: str
```

Disk has no `job_id` or `scope`; it has `exported_at`, `page_count`, and
`tasks` under a projects map. OpenAPI/`frontend/src/api/types.ts` currently
mirror the placeholder API shape.

## Root-cause hypotheses

1. **(Most likely) Stub never replaced after Track C landed** — list route was
   scaffolded for M3 with “until handler writes manifests”; handler later
   wrote a richer ops-aligned manifest and the list route was not wired.
2. **Contract never decided** — API shape (`job_id`/`scope`) does not map
   cleanly onto the single shared doctr-export root manifest, so implementers
   left the stub rather than invent a remapping.

## Defects to fix

1. **Empty list stub** — `list_exports` never reads disk (primary user-facing defect).
2. **Stale docstring** — claims manifests are not written.
3. **Undocumented API↔disk mapping** — OpenAPI `ExportManifest` vs
   `pdomain.doctr-export-manifest` (gate for implementation).

## Next steps

1. **Wave 1.0 (contract, no list code yet):** document how disk maps to API and
   FE history — either expand OpenAPI + FE types to match disk, or define an
   explicit remap (e.g. `created_at` ← `exported_at`, synthetic `job_id` /
   `scope`). Record in decisions or a plan update.
2. **Wave 1.1:** implement `GET .../exports` per that contract (read
   doctr-export manifest; filter/project for `project_id`).
3. Wire any export-history UI only after the contract is stable.

## What is NOT broken

- In-app export job path (`POST .../export` → `handle_export`) still produces DocTR training output.
- On-disk manifest write/merge for successful exports works when `pdomain_ops` is available.
- Style enumeration (`GET .../export/styles`) is store-first and separate from this list API.
- CLI store parity is a distinct finding (`2026-07-21-cli-export-not-store-first.md`).

## Resolution

Open. Fix order is Wave 1.0 contract, then Wave 1.1 implementation per
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md).

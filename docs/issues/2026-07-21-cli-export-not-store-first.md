---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I1
---

# Headless CLI export still scans labeled-projects envelopes only

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** High — SPA-saved projects can export zero pages via CLI
- **Finding ID:** P0-CLI-STORE
- **Affected version:** verified 2026-07-21 (Wave 1 source plan)
- **Read when:** changing export CLI, store-first page resolution, or batch/headless re-export.
- **Search terms:** export_cli, `scan_labeled_pages, store-first, labeled-projects, headless export, P0-CLI-STORE.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md) Wave
  1.2–1.5; `src/pdomain_ocr_labeler_spa/core/jobs/handlers/export_cli.py`;
  `src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py`

## Summary

The headless export CLI (`pdomain-ocr-labeler-spa-export` /
`export_cli.py`) discovers pages only via `_scan_labeled_pages` under
`labeled-projects/` envelopes. The in-app `handle_export` path is
store-first (`resolve_export_page_refs` + `load_export_page`, event-store head
with envelope fallback). SPA Save writes the event store; batch/CLI re-export of
those projects can therefore find nothing and exit with zero pages.

## Impact

- Headless/batch re-export of SPA-labeled projects can silently export 0 pages.
- CLI and in-app export diverge: same project, different page sets.
- Trainer handoff and automation that assume CLI parity with SPA save are untrustworthy.
- Manifest write from CLI is also missing relative to the in-app path (Wave 1.2).

## Environment / versions

- Repo: `pdomain-ocr-labeler-spa`
- Console entry: `pdomain-ocr-labeler-spa-export` → `export_cli:main`
- Source plan: `docs/plans/2026-07-21-deep-code-review-continuation.md` (Wave 1, P0-CLI-STORE)
- Verified against current tree on 2026-07-21

## Evidence

### 1. CLI path: envelope scan only

`src/pdomain_ocr_labeler_spa/core/jobs/handlers/export_cli.py` — `_run_export`
imports `_scan_labeled_pages` / `_load_page_from_envelope_file` and, for
`all_validated`, iterates only those JSON paths:

```python
for json_path in _scan_labeled_pages(data_root, project_id):
    img = _resolve_image_path(json_path)
    if img:
        pages_to_export.append((json_path, img))
```

Scope `current` builds
`labeled-projects/.../{project_id}_{page_index:03d}.json` the same way.
There is no `page_store` / event-store open.

Module docstring still describes the CLI as reading “labeled-project envelopes
directly from disk.”

### 2. In-app path: store-first

`src/pdomain_ocr_labeler_spa/core/jobs/handlers/export.py` — `handle_export`:

```python
# --- resolve pages to export (store-first, P1.2) ---
refs = resolve_export_page_refs(
    data_root,
    project_id,
    store,
    page_index=page_index if scope == "current" else None,
)
...
page = load_export_page(ref, store)
```

Store is used when the loaded project id matches; envelope remains per-page
fallback via the shared resolvers. Integration coverage exists in
`tests/integration/test_export_store_first.py`.

### 3. Consequence

An SPA session that saves only to `.pd-pages/` (event store) without legacy
envelope files will make `_scan_labeled_pages` return empty → CLI logs
“No pages found. Nothing exported.” and returns 0.

## Root-cause hypotheses

1. **(Most likely) CLI not updated when export went store-first** — in-app
   resolver helpers landed later; CLI kept the original envelope-only design
   for FastAPI-free headless use and was never switched to the shared loaders.
2. **No store open by project_id in CLI process** — opening a store without a
   full app bootstrap needs a deliberate path (related optional Wave 1.3 for
   non-loaded projects in the server handler).

## Defects to fix

1. **CLI page discovery is envelope-only** — does not use
   `resolve_export_page_refs` / `load_export_page` (primary).
2. **CLI does not write/update the doctr-export manifest** after success
   (parity with `handle_export` / Wave 1.2).
3. **Missing integration proof** — no SPA-save → CLI-export non-zero-pages
   test (Wave 1.5).

## Next steps

1. **Wave 1.2:** make CLI export store-first — reuse in-app resolve/load helpers;
   write manifest after successful export. Keep module-level FastAPI-free
   constraint.
2. **Wave 1.3 (optional):** server export of a non-loaded project via store open
   by `project_id` (related durability of store access without session load).
3. **Wave 1.5:** integration test: SPA save → CLI export yields non-zero pages.

## What is NOT broken

- In-app export for a **loaded** project with matching `page_store` is store-first and works.
- Shared `_export_page` / `WordFilter` logic used by both paths is fine once pages are discovered.
- Envelope-only projects (legacy NiceGUI / labeled-projects JSON) can still export via CLI.
- Export list API emptiness is a separate issue
  (`2026-07-21-export-list-api-empty.md`).

## Resolution

Open. Tracked as P0-CLI-STORE in
[`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md)
Wave 1.2 / 1.5 (1.3 optional). Acceptance: SPA-saved project exports non-empty
via CLI.

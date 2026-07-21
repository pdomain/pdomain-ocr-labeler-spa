---
kind: issue
status: active
owner: maintainers
created: 2026-07-21
last_verified: 2026-07-21
level: I2
---

# Project list cards lack metadata; non-all root filters are no-ops

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I2
- **Last verified:** 2026-07-21
- **Resolution:** Open
- **Severity:** Medium — root project chrome shows placeholders; filter chips do not filter
- **Affected version:** deep code review 2026-07-21 (`P2-ROOT`); PGDP items 7+8
- **Read when:** changing RootPage cards, project enumeration API, or root filter chips.
- **Search terms:** ProjectKey, RootPage, root-filter-chip, pageCount, progressPercent, P2-ROOT, PGDP 7, PGDP 8.
- **Relates to:**
  [`docs/plans/2026-07-21-deep-code-review-continuation.md`](../plans/2026-07-21-deep-code-review-continuation.md),
  [`docs/plans/2026-07-21-pgdp-alignment-remaining.md`](../plans/2026-07-21-pgdp-alignment-remaining.md),
  [`frontend/src/pages/RootPage.tsx`](../../frontend/src/pages/RootPage.tsx),
  [`src/pdomain_ocr_labeler_spa/api/projects.py`](../../src/pdomain_ocr_labeler_spa/api/projects.py)

## Summary

`ProjectKey` exposes only `project_id`, `project_root`, and `label`. RootPage
project cards hard-code `pageCount` and `progressPercent` as `null` placeholders
(“— pages”, “—%”). Filter chips for Active / Complete / Archived intentionally
do nothing: non-`all` filters still return the full list because the API has no
status (or page/progress) metadata. This is **P2-ROOT** / PGDP alignment items
7+8 (Wave 5).

## Impact

- Users cannot see labeling progress or page counts on the project picker.
- Filter chips look interactive (`data-active`) but do not change the grid —
  product-dishonest chrome.
- Archive/complete workflows cannot be driven from the root list without new
  backend fields (archive semantics themselves are a separate docs decision,
  PGDP item 9).

## Environment / versions

- Source: deep code review Wave 5; finding **P2-ROOT**.
- Plan status (2026-07-21): PGDP item 7 **open** (project-card metadata), item 8
  **open** (root filters).
- Level **I2**: local to root list / project enumeration surface, not a
  cross-cutting data-loss defect.

## Evidence

1. **API model** — `api/projects.py` `ProjectKey`:

   ```python
   class ProjectKey(BaseModel):
       project_id: str
       project_root: Path
       label: str
   ```

   No page count, progress percent, or status field.

1. **Card placeholders** — `RootPage.tsx` `ProjectCard`:

   ```ts
   const pageCount: number | null = null; // not yet in ProjectKey API
   const progressPercent: number | null = null; // not yet in ProjectKey API
   ```

   UI renders `"— pages"` and `"—%"` with a zeroed progress bar.

1. **Filter no-op** — `ProjectListView` `useMemo`:

   ```ts
   // Status filter — "active" / "complete" / "archived" are metadata not yet exposed
   // by the API, so all non-"all" filters show all projects for now.
   return list;
   ```

   `activeFilter` is in the dependency array but never applied to `list`.

1. **PGDP plan** — items 7–8 scheduled Night 3 after export history; filters
   become real only once metadata exists (or filters are removed/disabled).

## Root-cause hypotheses

1. **(Most likely) Enumeration stayed minimal** — discovery only needed id/root/label
   for load; card redesign (P5.h) added chrome ahead of API fields.
2. **Status model undecided** — “complete” / “archived” need product rules
   (and item 9 archive decision); filters left as intentional stubs.
3. **Progress derivation cost deferred** — page/progress may require store or
   sidecar reads per project; left null to keep list cheap.

## Defects to fix

1. `ProjectKey` (and list response) omit page count and labeling progress.
2. Root cards cannot display real progress UI without those fields (or another
   endpoint).
3. Non-`all` filter chips are interactive no-ops.
4. No API `status` (or equivalent) for active/complete/archived filtering.

## Next steps

1. Decide metadata source: event-store summary, filesystem scan, or cached
   sidecar per project — document cost vs freshness.
2. Extend `ProjectKey` (or adjacent list DTO) with page count, progress, and
   optional status; run `make openapi-export`.
3. Wire RootPage cards to real fields; remove null placeholders.
4. Implement filter logic for non-`all` chips **or** disable chips with honest
   copy until status exists (coordinate with item 9 archive decision).
5. Tests: RootPage filter behavior; API schema regression for new fields.

## What is NOT broken

- Text search on label / project_id / project_root still filters the list.
- Project open, delete-with-confirm, and session restore paths.
- In-project progress (match counts, worklist) on ProjectPage.
- Backend ability to load a project by id once selected.
- Archive permanence / no reversible archive (item 9) — related product
  decision, not the same as missing page metadata.

## Resolution

Open. Wave 5 / PGDP items 7+8. Prefer shipping metadata API and filter behavior
together so chips never look active while no-op.

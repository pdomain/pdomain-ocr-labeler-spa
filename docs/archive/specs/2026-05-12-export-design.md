# pdomain-ocr-labeler-spa: Export Dialog + DocTR Export Pipeline

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pdomain-ocr-labeler-spa#24

## TL;DR

Export dialog (`<ExportDialog />`) triggered from `<PageActions />`. Scope: current page or
all validated pages. Filters: style (multi-checkbox), component (dropdown), output mode
(classification / detection / recognition). POST returns 202+job; SSE progress shown inline.
Headless CLI `pdomain-ocr-labeler-spa-export` reuses same `DocTRExportOperations` driver.

## Context

The legacy `pd-ocr-labeler` ships `export_dialog.py` + `doctr_export.py` + `cli.py`. The SPA
preserves all behaviour: style-per-subfolder output layout, `WordFilter` filtering, and the
headless CLI. Output schema (`labels.json`) is owned by `pd_book_tools` and passed through
unchanged. The dialog is opened from `<PageActions />` (spec: page-actions) and uses the same
`useJobProgress` + `<BusyOverlay>` pattern as Reload OCR / Save Project.

## Constraints

- **202+job for all export runs.** Export is slow (one write per page); SSE progress is
  mandatory.
- **Cancel mid-export deletes partial output.** `shutil.rmtree(output_root)` on cancellation.
  Run-history row not appended on cancel.
- **Output schema owned by pd_book_tools.** SPA passes `labels.json` through unmodified.
- **Style-per-subfolder matches legacy.** One subfolder per selected style label; `"all"` when
  no style filter. No combined-mode in v1.
- **No run history persistence.** History list resets when the dialog closes.
- **Headless CLI must not boot FastAPI.** `cli.py` reads envelopes directly from disk.

## Decision

### Dialog layout

shadcn `<Dialog />`, triggered from `export-button` in `<PageActions />`. Sections: Scope
radio, Style filter checkboxes (from `GET .../export/styles`), Component filter dropdown,
Output option flags (mutually exclusive), run history list, Export + Close buttons.

Scope radio: `export-scope-current` (current page) | `export-scope-all` (all validated pages).
Switching to "All Validated Pages" fires `GET /api/projects/{id}/export/styles` to enumerate
distinct style labels across saved validated pages. Style checkboxes rendered from response.

Style filter mutual exclusion: clicking "All (no style filter)" unchecks all individual styles;
clicking any individual style unchecks "All". Component filter is single-select dropdown or none.

Output flags: `include_classification`, `detection_only`, `recognition_only` — mutually
exclusive toggles. Flipping one off-toggles the others.

### Export flow

Click Export → POST `/api/projects/{id}/export` with `ExportRequest` body → `202 {job_id}`.
`useJobProgress(jobId)` streams SSE progress: "Exporting page X of N". On `complete`: append
run-history row (style + page count + word count). On `error`: sticky toast, dialog returns to
idle. On `cancelled`: dialog returns to idle, no history row.

Cancel button rendered while job is running. POST to
`/api/projects/{id}/jobs/{job_id}/cancel`; server checks `runner.is_cancelled(job.id)` between
page iterations, rmtrees partial output, emits `{type: 'cancelled'}`.

### Output layout

```
<data>/doctr-export/<project_id>/<subfolder>/
├── detection/
│   ├── images/<prefix>_<page_index>.png
│   └── labels.json
└── recognition/
    ├── images/<prefix>_<page_index>_<word>.png
    └── labels.json
```

`<subfolder>`: `"all"` | style label (e.g. `"italics"`) | `"classification"`. Prefix defaults
to project_id.

### Backend shape

`ExportRequest`: `scope`, `style_filters: list[str]`, `component_filter: str | None`,
`include_classification: bool`, `detection_only: bool`, `recognition_only: bool`,
`page_index: int | None`. Handler in `core/jobs/handlers/export.py`. Iterates pages, applies
`WordFilter` per style group, calls `DocTRExportOperations.export_for_page`.

### Headless CLI

`pdomain-ocr-labeler-spa-export` console script at `src/.../operations/export/cli.py`. Reads
envelopes from disk via `parse_envelope`, applies same `DocTRExportOperations` driver. Flags
mirror dialog options. No FastAPI boot required.

## Contract / Acceptance

- POST `/api/projects/{id}/export` with all-validated scope returns 202 + job_id.
- SSE stream delivers `progress` events with page index; terminal `complete` event fires.
- Cancel mid-export: server rmtrees partial output; `cancelled` event closes stream; dialog
  returns to idle; no history row appended.
- Output dir: `italics/detection/labels.json` and `italics/recognition/images/` present after
  style-filtered export.
- `labels.json` byte-matches legacy output (golden-file integration test).
- Headless CLI produces identical output to dialog for the same inputs.
- Style filter "All" unchecks individual styles; individual style unchecks "All".

## Trade-offs considered

**Synchronous vs 202+job for single-page export.** Single-page export is fast but still writes
files; keeping it async simplifies the UI (one code path). Chosen: 202+job for all scopes.

**Run history server-side vs client-only.** Server state for history would survive dialog close.
Adds complexity for little benefit in v1. Client-only (resets on close) chosen.

**Style-per-subfolder vs combined output.** Legacy uses per-subfolder. Preserving legacy layout
keeps downstream `pd-ocr-trainer` scripts unchanged. Combined mode deferred to v2.

**Cancel partial cleanup: rmtree vs leave.** Leaving partial output confuses trainers. rmtree
on cancel is safe because the same export re-creates from scratch. Chosen: rmtree.

## Consequences

- `GET /api/projects/{id}/export/styles` must only query saved (labeled) page envelopes, not
  in-memory state, so style list is stable across page loads.
- Output dir collision on re-run silently overwrites. Acceptable for v1; timestamp suffix
  deferred to v2.
- The CLI console script must be declared in `pyproject.toml` `[project.scripts]`.

## Open questions

None.

## References

- `specs/10-export.md` — legacy feature doc (full dialog layout and endpoint shapes)
- `specs/02-backend.md §5.9` — export endpoint definition
- `specs/08-page-actions.md` — Export button placement
- `specs/11-notifications.md` — BusyOverlay + SSE toast integration
- `core/jobs/handlers/export.py` — export job handler
- `operations/export/cli.py` — headless CLI

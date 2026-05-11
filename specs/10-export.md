# 10 — Export Dialog + DocTR Export Operation

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#24

The Export dialog drives the DocTR training-export pipeline against
labeled-projects. Output: per-page detection + recognition training
data, optionally filtered by style or component.

> Cross-refs:
> Legacy implementation —
> `pd-ocr-labeler/pd_ocr_labeler/views/projects/pages/export_dialog.py`,
> `operations/export/doctr_export.py`,
> `operations/export/cli.py`
> Backend endpoint — [`02-backend.md`](02-backend.md) §5.9

---

## 1. Dialog layout

Triggered by `Export...` button in `<PageActions />`. shadcn `<Dialog />`.

```
┌────────────────────────────────────────────────┐
│ Export DocTR training data            [×]      │
├────────────────────────────────────────────────┤
│ Scope                                          │
│ [○] Current Page                               │
│ [●] All Validated Pages                        │
│                                                │
│ Style filter                                   │
│ [☐] All (no style filter)                       │
│ [☑] italics                                     │
│ [☐] small_caps                                  │
│ [☐] blackletter                                 │
│ ...                                             │
│                                                │
│ Component filter                               │
│ [Component ▼]                                  │
│                                                │
│ Output options                                 │
│ [☐] Classification only                         │
│ [☐] Detection only                              │
│ [☐] Recognition only                            │
│                                                │
│ ┌─ Run history ────────────────────────────┐  │
│ │ italics: 12 pages, 245 words exported    │  │
│ │ all: 12 pages, 9,123 words exported       │  │
│ └───────────────────────────────────────────┘  │
│                                                │
│ [Export]                          [Close]      │
└────────────────────────────────────────────────┘
```

testids: see [`13-driver-contract.md`](13-driver-contract.md) §2.12.

---

## 2. Behaviour

### 2.1 Scope radio

| Option | data-testid | Effect |
|---|---|---|
| Current Page | `export-scope-current` | Export only the currently-loaded page |
| All Validated Pages | `export-scope-all` | Iterate every saved page where `is_fully_validated` |

Switching to "All Validated Pages" triggers
`useQuery(["export-styles", projectId])` which calls
`GET /api/projects/{id}/export/styles` to enumerate distinct style
labels seen in saved validated pages. The UI lists one checkbox per.

### 2.2 Style filter

Mutually exclusive: either "All (no style filter)" is checked OR
one or more individual styles. Implementation:

- Click "All" → uncheck all individual styles.
- Click any individual style → uncheck "All".

When at least one individual style is checked, the export will create
**one subfolder per style** in the output dir. Each subfolder contains
only words tagged with that style. The legacy uses this for style-
specific DocTR fine-tuning.

### 2.3 Component filter

Single-select dropdown of allowed components, or `(none)`. Filters
words by `word_components` containing this label.

### 2.4 Output flags

- **Classification only**: skip detection + recognition; produce only
  classification labels (per-word style/component classification dataset).
- **Detection only** / **Recognition only**: skip the other.

Mutually exclusive — flipping one off-toggles the others.

### 2.5 Run

Click `Export` → POST `/api/projects/{id}/export` with the dialog's
state. Returns `202` + `Job` id. Open `useJobProgress(jobId)`. Show
progress in the dialog (spinner + "Exporting page X of N").

On terminal `complete`, append a row to the dialog's run history:

```
italics: 12 pages, 245 words exported
```

### 2.6 Run history

Persists for the duration of the dialog being open. On close + reopen,
the list is empty (no server state for history in v1).

Format: one line per export run with the style label (or "all") +
counts.

---

## 3. Backend endpoint

```python
@router.post("/{project_id}/export", status_code=202, response_model=ExportResponse)
async def export_pages(
    project_id: str,
    request: ExportRequest,
    state: AppState = Depends(get_app_state),
    runner: JobRunner = Depends(get_job_runner),
) -> ExportResponse:
    job = await runner.submit(JobType.EXPORT, request.model_dump(), project_id)
    return ExportResponse(job_id=job.id)
```

```python
class ExportRequest(BaseModel):
    scope: Literal["current", "all_validated"]
    style_filters: list[str] = []     # empty == "All"
    component_filter: str | None = None
    include_classification: bool = False
    detection_only: bool = False
    recognition_only: bool = False
    page_index: int | None = None     # required when scope=="current"
```

The handler in `core/jobs/handlers/export.py`:

```python
async def handle_export(runner: JobRunner, job: Job) -> None:
    state: AppState = runner.app_state
    project = state.projects[job.project_id]
    req = ExportRequest(**job.payload)

    pages_to_export = _resolve_pages(state, project, req)
    total = len(pages_to_export)

    for i, (page_idx, page_state) in enumerate(pages_to_export, 1):
        runner._update_progress(job, i, total, message=f"Exporting page {page_idx + 1}")

        # WordFilter applied per style group
        for style_filter in req.style_filters or [None]:
            wf = WordFilter(style_labels=[style_filter] if style_filter else None,
                            component=req.component_filter)
            DocTRExportOperations.export_for_page(
                page=page_state.page,
                output_dir=output_dir_for(req, style_filter, project),
                word_filter=wf,
                detection=not req.recognition_only,
                recognition=not req.detection_only,
                classification=req.include_classification,
            )
```

The pd-book-tools API used:

- `Page.generate_doctr_detection_training_set`
- `Page.generate_doctr_recognition_training_set`
- `pd_ocr_labeler_spa.export.WordFilter` (port from legacy)

---

## 4. Output layout

```
<data>/doctr-export/<project_id>/<subfolder>/
├── detection/
│   ├── images/<prefix>_<page_index>.png
│   └── labels.json
└── recognition/
    ├── images/<prefix>_<page_index>_<word>.png
    └── labels.json
```

`<subfolder>` is:

- `"all"` if no style filter.
- The style label (e.g. `"italics"`) if a single style is selected.
- `"classification"` if `include_classification=true`.

`<prefix>` defaults to `<project_id>`.

`labels.json` schema is owned by `pd_book_tools` (DocTR convention);
SPA doesn't reshape it.

---

## 5. The headless CLI

The legacy ships `pd-ocr-labeler-export` as a separate console script
for headless training-data generation. The SPA ships the same:

```sh
pd-ocr-labeler-spa-export <labeled_dir> <output_dir> \
    [--prefix PREFIX] \
    [--all-pages | --require-gt] \
    [--style STYLE | --component COMPONENT | --classification] \
    [--detection-only | --recognition-only] \
    [-v]
```

Implementation: `src/pd_ocr_labeler_spa/operations/export/cli.py`.
Reuses the same `DocTRExportOperations` driver as the dialog. Doesn't
boot the FastAPI server; reads envelopes directly from disk.

---

## 6. Tests

- Backend: `tests/integration/test_export.py` — given a fixture
  project with 3 validated pages and 2 styles, run export with
  scope="all_validated" + style_filters=["italics"], assert:
  - `<output>/italics/detection/labels.json` exists
  - `<output>/italics/recognition/images/` has the right count
  - golden-file comparison of `labels.json` against legacy output
- Backend: `tests/integration/test_export_classification.py`.
- E2E: `test_export_dialog.py` — open dialog, select "All Validated"
  - "italics", click Export, see progress, see results row.
- Headless CLI: `tests/cli/test_export_cli.py` — argparse correctness,
  matches dialog output for the same inputs.

---

## 7. Open issues

- **Per-export style subfolder vs combined.** The legacy creates one
  subfolder per style. We preserve this. But the user may want a
  "combined" mode (one folder, all styles, with style as a label
  field). Out of scope for v1.
- **Cancel during export.** Long export jobs benefit from cancellation.
  Wire `useJobProgress.cancel()` in M9.
- **Output dir collision.** Re-running export with the same scope
  overwrites the previous output. Acceptable but noisy. Consider
  appending a timestamp suffix to the subfolder name in v2.

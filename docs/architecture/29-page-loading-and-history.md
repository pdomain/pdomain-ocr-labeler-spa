---
kind: architecture
status: built
owner: maintainers
created: 2026-11-07
last_verified: 2026-11-12
---

# Page loading and version history

Cold pages load through background jobs while the document shell stays interactive. Page history uses append-only
restore events, so undo, redo, and jumps preserve the audit trail.

## Cold-page progress

Opening a project creates no job. A warm stored page returns immediately without a load job. A store miss submits
one `load_page` job and returns its identifier. Concurrent requests for the same cold page share that job. The
image pane shows store lookup and OCR stages through the existing event stream; the rest of the shell remains
usable.

The OCR stage names the device. Predictor construction and OCR execution currently share one stage. A failed job
reports an error distinct from a successful page with no words, and a later request can retry. The predictor stays
lazy; eager startup warm-up was rejected on 2026-09-18.

Finer predictor-build progress still needs an upstream callback or structured-event contract. The
[page-load spec](../specs/2026-08-08-page-load-progress-design.md) retains that requirement.

## Undo, redo, and visible history

The version cursor is derived from the event-store chain. Undo and redo append restore markers rather than
rewriting the head. A real edit after moving backward discards the newer versions from the active redo chain, while
their audit records remain stored.

The drawer's History tab fetches page versions only when open. Rows show an operation label, relative time, and the
current version. A jump appends a restore event and can move backward or forward within the active chain. A target
outside that chain returns 409.

Undo and redo follow page-slot lineage when the cursor is at a boundary. At the start of the chain, undo loads
`extensions["labeler.lineage"].previous_page_id` and re-points the project slot. At the end of the chain, redo
follows `superseded_by`. That cross reloads the target aggregate's head blob and does not append a `labeler_edited`
marker. A jump stays inside the active chain and returns 409 for a target outside it. A fresh OCR aggregate still
has an empty intra-aggregate history. The HTTP undo offer can still be true through the lineage link.

Re-OCR and rotation write the same lineage record. Rotation retags `boundary_op` to `rotate` after OCR. A later
replacement while the slot sits on the older aggregate points `superseded_by` at the newest successor and keeps
that aggregate's own `previous_page_id`. The Reload OCR confirm says undo will step back across the reload, and
the undo control stays enabled on that fresh aggregate.

Undo restores the source image only when the aggregate being left is tagged `rotate`. Redo restores it only when
the aggregate being entered is tagged `rotate`. The bytes written are that target aggregate's OCR image blob.
An edit after OCR leaves that image ref on the ingest node, not on the head. If the slot save fails, the previous
file bytes are put back. A re-OCR step does not rewrite the file, even when the neighbor aggregate was born from
a rotation. The content blob is read first, so a missing blob leaves the slot where it was. The image URL stays
the display-width query. `GET` of the image still sends `Cache-Control: public, max-age=3600`, so a browser can
keep the previous image until that hour ends.

`POST /api/projects/{project_id}/maintenance/prune` unlinks only the blob names the
[undo spec](../specs/2026-06-12-event-store-undo.md) marks dead in the snapshot taken before the walk. A file
created after that snapshot stays. The live cursor and the redo blobs above it stay when a jump sits below the
undo floor, and a non-positive undo depth uses the same default of 50 as undo. Image and preprocess hashes,
unknown files, and lineage-reachable aggregates inside the retention window stay. Retention defaults to 30 days
(`PDLABELER_PRUNE_RETENTION_DAYS`). Prune does not run on a write. `PDLABELER_PRUNE_ON_OPEN` defaults to false.
U-M7, the visible history list and jump action, is unchanged.

## Evidence

- Code: `src/pdomain_ocr_labeler_spa/api/pages.py`, `core/jobs/handlers/load_page.py`, `core/page_history.py`,
  `core/page_lineage.py`, `core/page_prune.py`, `api/history.py`, and `api/maintenance.py`, under the backend
  package; `frontend/src/components/drawer/HistoryPanel.tsx`.
- Tests: `tests/integration/test_load_page_job.py` covers store miss, named stages, deduplication, failure, retry,
  and warm hits. `tests/e2e/test_page_load_progress.py` covers visible cold-open progress.
- Tests: `tests/integration/test_history_undo_redo.py`, `tests/unit/core/test_page_history.py`,
  `tests/unit/core/test_page_prune.py`, and `tests/e2e/test_history_panel.py` cover history behavior.
- Verified: 2026-11-07 by source and test inspection; history UI landed in `44b52257` and loading in `9768576`.
  Lineage undo and conservative prune were checked against those tests on 2026-11-12.

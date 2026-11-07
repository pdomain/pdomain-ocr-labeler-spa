---
kind: architecture
status: built
owner: maintainers
created: 2026-11-07
last_verified: 2026-11-07
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

Cross-OCR and rotation-boundary traversal, page-slot lineage, and conservative retention pruning remain U-M6 work
in the [undo spec](../specs/2026-06-12-event-store-undo.md). U-M7, the visible history list and jump action, has
shipped.

## Evidence

- Code: `src/pdomain_ocr_labeler_spa/api/pages.py`, `core/jobs/handlers/load_page.py`, `core/page_history.py`,
  and `api/history.py`, under the backend package; `frontend/src/components/drawer/HistoryPanel.tsx`.
- Tests: `tests/integration/test_load_page_job.py` covers store miss, named stages, deduplication, failure, retry,
  and warm hits. `tests/e2e/test_page_load_progress.py` covers visible cold-open progress.
- Tests: `tests/integration/test_history_undo_redo.py`, `tests/unit/core/test_page_history.py`, and
  `tests/e2e/test_history_panel.py` cover history behavior.
- Verified: 2026-11-07 by source and test inspection; history UI landed in `44b52257` and loading in `9768576`.

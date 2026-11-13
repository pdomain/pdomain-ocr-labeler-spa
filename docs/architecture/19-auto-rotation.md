---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-13
---

# 19 — Auto-Rotation + Manual Rotate

Manual rotation and explicit auto-rotate-all run as background jobs. Successful results update the source image,
rerun OCR and persist aggregate rotation metadata. Immutable book-source sessions reject both operations.

## Manual rotation

`POST` to the page rotate route always returns `202` with a job identifier. `RotatePageRequest` accepts
`degrees` in -90, 90 or 180 and `manual`; it has no `rerun_ocr` field. The rotate job writes the image on disk,
reruns OCR through the loader and calls `PageAggregate.rotation_updated`. Page payloads read this metadata.
The compact page actions mount clockwise/counterclockwise buttons and an always-present rotation badge.
Only automatic badges offer revert.

## Automatic rotation

The explicit auto-rotate-all job calls the public upstream `detect_best_rotation` API with an image, OCR
callback and confidence threshold 0.6. It protects manually rotated pages unless `overwrite_manual` is set,
and commits completed page results. Automatic rotation through the Tesseract adapter is unsupported.

The `method` setting is logged but is not passed to detection, and GT is not passed to that call.
`auto_rotate_on_load` is persisted/exposed but has no page-load execution consumer. These settings must not
be described as working method-specific detection or an automatic on-load pass. Their desired execution
semantics remain a design reconciliation item, not a newly approved feature.

## Persistence and history

Rotation uses the current page aggregate and content blobs, not a UserPageEnvelope version bump.
Re-OCR links the new aggregate before the project slot advances; rotation retags the lineage boundary.
Boundary undo/redo restores source bytes only for the rotation step, as described in
[page history](29-page-loading-and-history.md). A re-OCR neighbor does not independently rewrite the image.
Both rotate entry points return `422 book_source_rotation_unsupported` for immutable book-source sessions.

## Evidence

- Code: `api/pages.py` rotate route and `RotatePageRequest`; `core/jobs/handlers/rotate.py` and
  `auto_rotate_all.py`; `frontend/src/components/PageActionsCompact.tsx`, under their respective source roots.
- Tests: `tests/integration/test_rotate_router.py`, `test_rotate_job.py`, `test_auto_rotate_all_job.py`,
  `test_rotation_metadata_payload.py`, and `tests/e2e/test_rotate_parity.py`.
- Verified: 2026-11-13 by source/test inspection. No fresh browser rotation run is claimed.

## Historical implementation receipt

> **Status**: Built
> **Last updated**: 2026-07-13
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#42

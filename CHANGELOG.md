# Changelog

## Unreleased

### Breaking changes

- `UserPageEnvelope` persistence format retired (greenfield — no migration; new
  projects only).
- `api/pages.py::PagePayload` replaced by `pdomain_ops.pages.PagePayload`. Response
  shape changes: `page_record` is now an ops `PageRecord` with `extensions["labeler"]`
  carrying labeler view-state. Fields removed: `page_record.ocr_provenance`,
  `page_record.saved_provenance`, `page_record.cached_images`. Field added:
  `record.extensions`.
- Local `RotationSource`, `CachedImageSet` removed from `core/models.py` (import from
  `pdomain_ops.pages.RotationSource` instead).

### Added

- `LabelerPageExtension` — labeler view-state in `extensions["labeler"]`.
- `LabelerPageStore` — per-project event store + BlobStore.
- `save_page_to_store` — fires `LabelerEdited` events replacing `persist_page_to_file`.
- `/api/blobs/{hash}` route — blob-store image serving replacing `/image-cache/`.
- `_assemble_page_payload` — assembles ops `PagePayload` from `LabelerPageStore`.

### Dependencies

- `pdomain-book-tools>=0.17.0` (was >=0.14.1)
- `pdomain-ops>=0.7.0` (was >=0.4.0)
- `eventsourcing>=9.4` (new — ops 0.7.0 dep)

---
kind: architecture
status: built
owner: maintainers
created: 2026-05-14
last_verified: 2026-11-13
---

# 23 — Backend page payload + mutation endpoints

`api/pages.py::_page_payload` assembles the mounted workbench response from hydrated page state and shared
lifecycle data. Its fields include generation, image URL, provenance/history, image drift, regions and
load-job/error metadata. The generated OpenAPI schema defines the exhaustive wire contract.

## Page loading and payload reads

A warm memory/store hit returns without OCR. A cold miss probes with OCR disabled, submits a deduplicated
`load_page` job and returns pending-load metadata. [Page loading/history](29-page-loading-and-history.md)
owns that lifecycle. Payload reads take the per-page lock where model reads can mutate cached state.
Plaintext is built by joining line text verbatim with newlines; it does not apply a normalization profile.

## Page mutation and durability

Mutation routes acquire the per-page threading RLock. Ground-truth and structural edits serialize page
content plus Labeler sidecars into the event/blob store. Store persistence failure returns
`503 store_persist_failed`; it is not a successful mutation with a hidden warning.

Explicit Save accepts an optional generation guard and rejects a mismatch. `last_saved_generation` advances
only after a content save or intentional no-store mode. Changelog-only or missing-ID writes do not falsely
clear dirty state. Reload refreshes the current saved head rather than discarding to an old labeled JSON file.
Selection is session state: its endpoint updates selection/generation under the lock without persisting it
as a content edit.

## Ownership

PageRecord and RotationSource are shared `pdomain_ops.pages` types; `core.models` exports neither.
Labeler-only fields remain in the namespaced extension and serialized sidecars. The dated July boundary
decision retains the historical compatibility-facade stage, but that facade is removed. The service's local
HTTP PagePayload should not be confused with the separate Ops payload helper.

## Evidence

- Code: `api/pages.py::_page_payload`, `_save_to_store_best_effort`, `save_page` and the selection route;
  `api/words.py::update_word_ground_truth`; `core/project_state.py` per-page RLock;
  `core/page_state.py::save_page_content_to_store`, under the backend package.
- Tests: `tests/unit/api/test_pages_get.py`,
  `tests/integration/test_page_payload_race.py::test_concurrent_validate_and_get_never_see_empty_page`,
  `test_save_page_route_roundtrip.py::test_save_page_route_persists_content_for_fresh_store_reload`,
  `test_save_dirty_bit.py`, and `tests/unit/core/test_models_no_local_pagerecord.py`.
- Verified: 2026-11-13 by source and test inspection.

## Historical implementation receipt

> **Status**: Active (shipped — all spec-23-* child issues closed 2026-05-15).
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#291

The original receipt named `persist_page_to_file` as a shipped dependency. That writer is now retired; the
current persistence contract above supersedes the old envelope/scaffold description.

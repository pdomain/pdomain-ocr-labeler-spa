---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-11-13
---

# 09 — Persistence

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#22

Current page persistence uses project-scoped SQLite events and content-addressed blobs.
Configuration, source-project inputs and derived image caches are separate from that saved page state.

> Cross-refs:
> Schema definitions — [`01-data-models.md`](01-data-models.md) §3
> Legacy persistence —
> `pd-ocr-labeler/pd_ocr_labeler/models/user_page_persistence.py`,
> `operations/persistence/`,
> `operations/ocr/image_cache_operations.py`,
> `operations/ocr/page_operations.py`

---

## 1. Three on-disk lanes

1. Source-project inputs remain in the selected project directory.
2. Current page state lives in `.pd-pages/events.db` and `.pd-pages/blobs/`, through `LabelerPageStore`.
3. Derived image-cache files support display; they are not an authoritative page-history lane.

### Current saves and restart reads

`save_page_content_to_store` serializes page content with labeler sidecars into a content-addressed blob,
records provenance, and saves the page aggregate. Project slots identify the current aggregate. On restart,
`local_doctr.load_labeled` resolves that slot and reads its current head content. `load_cached` returns None;
there is no active cached-envelope writer. `persist_page_to_file` raises NotImplementedError for the retired
UserPageEnvelope write path.

## 2. UserPageEnvelope v2.1

This is a legacy format, not the current save contract. Its old source/labeled/cache precedence does not
describe the event-store loader. Historical envelope decisions remain in the decision log.

## 3. Provenance details

Content blobs and aggregate events retain page history. Undo, redo, jumps and cross-OCR/rotation lineage are
documented in [page loading and history](29-page-loading-and-history.md). Labeler-only sidecars accompany
the page content; shared page lifecycle fields remain owned by `pdomain-ops`.

## 4. Image cache

### 4.1 Per-image-type cache entries

Derived display images remain separate from saved page content. Image and preprocessing blob references
are protected during conservative pruning. Cache eviction is not an automatic page-history operation.

### 4.2 Cached envelopes

Cached page envelopes are retired. A display cache file is not a replacement for the current aggregate head.

## 5. project.json

`<labeled-projects>/<project_id>/project.json`:

```jsonc
{
  "schema": {"name": "pd_ocr_labeler.project", "version": "1.0"},
  "project_id": "the_four_men",
  "source_path": "/abs/path/to/project_dir",
  "version": "1.0",
  "source_lib": "doctr-pdomain-labeled",
  "total_pages": 42,
  "saved_pages": 12,
  "current_page_index": 5,
  "include_images": true,
  "copied_images": false
}
```

Written every time **Save Project** completes. Read on every project
load (used to populate `Project.saved_pages` etc.).

---

## 6. session_state.json

`<data>/session_state.json` — single file shared between binaries:

```jsonc
{"schema_version": "1.0",
 "last_project_path": "/abs/path/to/project_dir",
 "last_page_index": 5}
```

Written on every successful project load (`AppState.load_project`).
Read on app start; if the path no longer exists or doesn't contain
images, ignore.

---

## 7. config.yaml

`<config_root>/config.yaml` (where `<config_root>` is the §5 OS-aware
root which already includes the `pdomain-ocr-labeler-spa/` app-name suffix):

```yaml
source_projects_root: "/path/to/projects"
```

When no env, CLI, or absolute `source_projects_root` is set, startup
uses `<data>/labeler-books/` and creates that directory if it is
missing. A chosen path that does not exist is left missing. Single key
for v1; expand later if needed.

---

## 7a. ocr_config.json

`<data_root>/ocr_config.json` — **SPA-only** sidecar that persists
the user's OCR model selection across server restarts. Legacy
`pd-ocr-labeler` does NOT read or write this file (model selection
in legacy is in-process only, recomputed each launch). Schema:

```jsonc
{
  "schema_version": "1.0",
  "selected_detection_key": "stock",
  "selected_recognition_key": "stock",
  "hf_pinned_revision": null
}
```

Field semantics — same as the wire DTOs in
[`01-data-models.md`](01-data-models.md) lines 374–400:

- `schema_version` is the **string** `"1.0"` (parity with §6
  `session_state.json` — not an int).
- `selected_detection_key` / `selected_recognition_key` carry whatever
  string the route handler validated against the currently-exposed
  option lists. Persisted as-is; round-trip identity required so
  `OCRConfigCarrier` semantics are preserved across restart.
- `hf_pinned_revision` is `null` (default) or a string commit/tag
  pinning the HF Hub revision. Optional per the carrier's API.

**Lifecycle.** Loaded once at app startup (`build_app` lifespan
hook); the deserialized triple seeds `OCRConfigCarrier`. Saved
immediately after every successful `POST /api/ocr-config/models` (or
future `POST /api/ocr-config/rescan`) — i.e. on every state-changing
mutation, not on a debounce. Atomicity uses the same `tmp + replace`
pattern as `session_state.py`.

**Extras-tolerance.** The reader uses `extra="ignore"` (forward-compat
with future SPA versions adding additive fields). Unknown keys are
logged at **WARNING** with the stable grep-able substring
`ocr_config_extras_dropped` so a release-time CI step can detect
uncoordinated drift. Note the file is **NOT** under D-003: legacy
never touches it, so the asymmetry vs `UserPageEnvelope`'s
`extra="forbid"` is purely about future-SPA forward-compat, not
cross-binary interop.

**Failure modes (load).** Same shape as session_state — every
failure path returns `None` (file missing / unparsable / wrong shape
/ pydantic-rejected) and the caller seeds the carrier with defaults.
Startup never crashes on a corrupt sidecar; the next successful POST
overwrites it.

**Failure modes (save).** Errors are **logged at WARNING and
swallowed** — distinct from `session_state.save_session_state`, which
re-raises. Rationale: a failed model-selection-save should not turn
a 200 OCR-config POST into a 500. The in-process carrier still
holds the new selection; the user sees the change applied. The
WARNING log uses the stable substring `ocr_config_save_failed` so an
operator can spot persistent disk-side failure (e.g. read-only
data root, full disk).

**Test isolation.** Integration tests using the `client` fixture
must use a `tmp_path`-scoped `data_root` so the sidecar lives in a
fresh dir per test. The same fixture already monkeypatches
`fetch_hf_last_modified` and `_resolve_local_models_root` (slice
8c-iii-c precedent); the sidecar layer adds the analogous data-root
isolation.

---

## 8. Atomic writes

`core/persistence/atomic.py` writes to a unique hidden sibling staging path opened with O_CREAT, O_EXCL
and O_WRONLY, then replaces the destination. Exceptions clean up that staging file. Image writes encode
bytes before using the corresponding atomic helper. This avoids collisions between writers using a fixed
`.tmp` name. `tests/unit/core/persistence/test_atomic.py` covers these helpers.

## 8a. Verified images require Linux memfd sealing

Labeling-bundle and book-page loaders keep each verified image in a sealed
Linux memfd, so a later change on disk cannot alter a page already leased.
The Python build must expose `os.memfd_create`, `os.MFD_ALLOW_SEALING`, and
`os.MFD_CLOEXEC`.

A build without them cannot make that guarantee, and the supported Python
version range does not detect it. The uv-managed CPython 3.13.14 on
omarchy-main lacks `os.memfd_create`, and the mise-managed 3.13.18 has it. The loaders
refuse with `UnsupportedRuntimeError`, which the API returns as `503
unsupported_runtime`, naming the missing interfaces. There is no fallback
carrier. Batch jobs fail instead of skipping pages.

---

## 9. Concurrency

Page mutation routes acquire the per-page lock before reading or writing page state. A second mutation
sees the first mutation's completed state. The backend is a single process; the local job table is in memory,
while page history persists through the event store. This does not authorize managed database adapters.

## 10. Backups

`<data>/project-backups/`. Reserved directory; used by future
"backup before save" features. Not implemented for v1.

The legacy has the directory but doesn't use it either.

---

## 11. Migrations

Current persistence does not write or silently migrate the old UserPageEnvelope lane. The legacy typography
clean break rejects character-range payloads rather than converting or dual-writing them; see
[typography review](31-typography-review.md). Future schema decisions remain explicit owner work.

## 12. Tests

- `tests/integration/test_save_page_route_roundtrip.py` and `test_save_project_roundtrip.py` cover durable writes.
- `tests/integration/test_edit_persist_round_trip.py` covers edited-content reload.
- `tests/unit/core/persistence/test_atomic.py` covers atomic helpers.
- `tests/unit/api/test_typography_clean_break.py` covers rejection of removed legacy payloads.

Verified: 2026-11-13 by reading `core/persistence/page_store.py`, `core/page_state.py`,
`adapters/ocr/local_doctr.py`, the atomic helper and these tests.

## 13. Open issues

The old cached-envelope provenance and `original_page` reset notes describe the retired write lane.
Current provenance and restore behavior come from page aggregate history. The remaining pruning requirements
are explicit in [page loading and history](29-page-loading-and-history.md) and the partial
[undo design](../specs/2026-06-12-event-store-undo.md); they are not a new envelope migration.

---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-07-13
---

# 09 — Persistence

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#22

Every byte the SPA writes to disk. Schema-version-stable so the legacy
labeler can interop ([D-003](../../specs/17-decisions.md)). Crash-safe via the
auto-save-to-cache lane ([`08-page-actions.md`](08-page-actions.md)).

> Cross-refs:
> Schema definitions — [`01-data-models.md`](01-data-models.md) §3
> Legacy persistence —
> `pd-ocr-labeler/pd_ocr_labeler/models/user_page_persistence.py`,
> `operations/persistence/`,
> `operations/ocr/image_cache_operations.py`,
> `operations/ocr/page_operations.py`

---

## 1. Three on-disk lanes

Every page is stored in up to three places:

1. **Source lane** — the user's input directory:
   `<source_projects_root>/<project>/<image>.png` + `pages.json`.
   **Read-only** to the labeler.
2. **Labeled lane** — explicit user saves:
   `<data>/labeled-projects/<project_id>/<project_id>_<page:03d>.{png,json}`.
   The labeler is the only writer.
3. **Cached lane** — automatic snapshots after every mutation:
   `<cache>/page-images/<project_id>_<page:03d>_envelope.json` plus
   per-image-type cache entries
   `<cache>/page-images/<project>_<page:03d>_<type>_<sha>.{jpg,png}`.

Read precedence on page-load (matches legacy
`ProjectState.ensure_page_model:752`):

1. If labeled-lane envelope exists → load it. `page_source = "filesystem"`.
2. Else if cached-lane envelope exists → load it. `page_source = "cached_ocr"`.
3. Else → run OCR. `page_source = "ocr"`. Then auto-save to cached lane.
4. If OCR fails → `page_source = "fallback"`, `ocr_failed = true`.

The SPA preserves this exact precedence.

---

## 2. UserPageEnvelope v2.1

Source of truth: [`01-data-models.md`](01-data-models.md) §3. Schema:

```jsonc
{
  "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
  "provenance": {
    "saved_at": "2026-05-06T12:34:56.789Z",
    "saved_by": "Save Page" | "Save Project" | "Auto-save" | "Save Page (no-source-update)",
    "source_lane": "labeled" | "cached",
    "app": {"name": "pdomain_ocr_labeler_spa", "version": "x", "git_commit": "y"},
    "toolchain": {"python": "...", "pdomain_book_tools": "...", "opencv_python": "..."},
    "ocr": { ...OCRProvenance... }
  },
  "source": {
    "project_id": "...", "page_index": 0, "page_number": 1,
    "image_path": "001.png",
    "project_root": "/abs/path/to/project_dir",
    "image_fingerprint": {"size": 12345, "mtime_ns": 123456789, "sha256": "..."}
  },
  "payload": {
    "page": { ...pdomain_book_tools.Page.to_dict()... },
    "original_page": null | {...},
    "word_attributes": { "<word_id>": {"italic": false, "small_caps": false, ...}, ... }
  },
  "cached_images": {
    "original": "<project>_<page:03d>_original_<sha>.jpg",
    "lines":    "<project>_<page:03d>_lines_<sha>.jpg",
    ...
  }
}
```

Reader and writer live in
`src/pdomain_ocr_labeler_spa/core/persistence/user_page_envelope.py`:

```python
def is_user_page_envelope(data: Mapping) -> bool: ...
def parse_envelope(data: Mapping) -> UserPageEnvelope: ...
def build_envelope(
    *,
    page: Page,
    original_page: Page | None,
    page_record: PageRecord,
    project: Project,
    saved_by: str,
    source_lane: Literal["labeled", "cached"],
    image_fingerprint: ImageFingerprint,
    ocr_provenance: OCRProvenance,
    cached_images: CachedImageSet,
) -> dict: ...
```

Round-trip identity invariant (golden test):
```python
data = json.loads(envelope_path.read_text())
assert build_envelope(**parse_envelope(data).to_kwargs()) == data
```

(Allowing for normalised whitespace + key order — JSON read is
order-preserving in Python 3.7+.)

---

## 3. Provenance details

Built once per OCR run (`core/ocr/provenance.py`):

```python
def build_live_ocr_provenance(predictor) -> OCRProvenance:
    return OCRProvenance(
        engine="doctr",
        engine_version=doctr.__version__,
        models=[
            OCRModelProvenance(name="detection", weights_id=...),
            OCRModelProvenance(name="recognition", weights_id=...),
        ],
        config_fingerprint=hashlib.sha256(
            json.dumps({"weights": ..., "vocab": ...}, sort_keys=True).encode()
        ).hexdigest(),
    )
```

The provenance is stored on `PageRecord.ocr_provenance` after a
live OCR; on save, it's emitted in `provenance.ocr` of the envelope.

When the page is loaded from a labeled envelope, the **saved**
provenance comes from the file and is preserved in
`PageRecord.saved_provenance`. The current `ocr_provenance` reflects
the last live OCR (or None if never re-OCR'd in this session).

---

## 4. Image cache

`<cache>/page-images/`. Two kinds of files:

### 4.1 Per-image-type cache entries

`<project>_<page:03d>_<image_type>_<sha>.{jpg,png}`

- `image_type` ∈ `original | lines | words | paragraphs | matched_words`.
- `<sha>` is SHA-1 of the encoded bytes, hex, truncated to 16 chars.
  Same algorithm as legacy `compute_image_hash`.
- Encoding: JPEG quality 92, max dimension 1200 px. PNG fallback when
  JPEG round-trip differs visibly. (`_MAX_CACHED_DIMENSION = 1200`.)

These files are **content-addressable**: the same image bytes always
produce the same filename, so two writers (legacy + SPA) don't
conflict.

Eviction: never automatic. The user can run `make clean-cache` to
purge.

### 4.2 Cached envelopes

`<project>_<page:03d>_envelope.json` — same shape as labeled
envelopes, with `provenance.source_lane = "cached"`.

These are **per-page singletons** (NOT content-addressed). Each
auto-save overwrites the previous cached envelope for that page.

---

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
root which already includes the `pd-ocr-labeler/` app-name suffix):

```yaml
source_projects_root: "/path/to/projects"
```

Auto-created on first run with the OS-specific default
(`<data>/source-pgdp-data/output/`). Single key for v1; expand later
if needed.

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

Every JSON write goes through this helper to avoid partial files on
crash:

```python
def write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)   # POSIX atomic rename
```

Implementation in
`src/pdomain_ocr_labeler_spa/core/persistence/atomic.py`. Tested with a
power-fail simulation (`os._exit(1)` between write and replace).

Image writes use `cv2.imencode` to bytes, then `write_bytes_atomic`
similarly.

---

## 9. Concurrency

Single-process backend. All writes serialise through the
`AppState`-level lock per project. Two HTTP requests modifying the
same page block on the lock; the second sees the first's result.

The shared **data root** with the legacy is the racy boundary
([D-003](../../specs/17-decisions.md)). Recommended: don't run both binaries
simultaneously against the same root. M0 should print a warning at
startup if it detects another process holding the cache root open
(via a `pidfile` lockfile).

---

## 10. Backups

`<data>/project-backups/`. Reserved directory; used by future
"backup before save" features. Not implemented for v1.

The legacy has the directory but doesn't use it either.

---

## 11. Migrations

The SPA never auto-migrates envelopes. If we encounter a schema
version it doesn't understand, raise `incompatible_envelope` (status
`422`) with the version and the supported range. The SPA toast
message: "This page was saved by a newer pd-ocr-labeler. Upgrade to
read it."

When we eventually bump v2.1 → v2.2 (additive only), the rule is:

- New optional fields are fine.
- Reading v2.1 with v2.2 code: works.
- Reading v2.2 with v2.1 code: works (extra fields ignored via
  `extra="ignore"` on the nested provenance models). The schema
  version check itself is gating: top-level `extra="forbid"` makes
  v2.1 readers refuse v2.2 because `schema.version` won't match.

Document each bump in [`17-decisions.md`](../../specs/17-decisions.md).

---

## 12. Tests

- `tests/integration/test_envelope_round_trip.py` — load each fixture
  envelope, parse, build, assert byte-equal.
- `tests/integration/test_save_load_round_trip.py` — full cycle.
- `tests/integration/test_atomic_write.py` — simulate crash;
  no partial files left.
- `tests/integration/test_image_cache.py` — content-addressable filenames
  stable across runs.
- Conformance: load every fixture envelope from
  `pd-ocr-labeler/tests/browser/fixtures/` (copied into the SPA test
  tree) without modification.

---

## 13. Open issues

- **OCR provenance for cached envelopes.** When loading a cached
  envelope, the `OCRProvenance` reflects the OCR run that produced
  it — not the user's currently-selected models. After Reload OCR,
  the provenance is updated. Document the difference in the source
  badge tooltip.
- **`original_page` snapshot.** Legacy stores a pre-edit snapshot for
  potential reset-to-OCR. The SPA preserves this on read but only
  populates it on first save (when `original_page` doesn't yet
  exist). After that, all saves keep the original snapshot fixed.
  This matches legacy.

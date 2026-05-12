# pd-ocr-labeler-spa: Persistence

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#22

## TL;DR

Three on-disk lanes: source (read-only), labeled (explicit user saves), cached (auto-save
after every mutation). Read precedence: labeled → cached → OCR → fallback. `UserPageEnvelope`
v2.1 schema preserved byte-for-byte for legacy interop. All writes are atomic via tmp+replace.
Sidecar files: `session_state.json`, `project.json`, `config.yaml`, `ocr_config.json`.

## Context

The SPA shares the same data root as the legacy `pd-ocr-labeler`. Any file the SPA writes
must be readable by the legacy, and vice versa (D-003). `UserPageEnvelope` v2.1 is the
shared envelope schema. The SPA must never auto-migrate envelopes; unknown schema versions
return `422 incompatible_envelope`.

The legacy's `_auto_save_to_cache` side effect (after every mutation) is preserved: every
POST that modifies page state writes through to the cached lane before returning.

## Constraints

- **v2.1 byte-compatibility (D-003).** Round-trip golden test against legacy fixtures.
- **Atomic writes everywhere.** `write_json_atomic` (tmp + `os.replace`) prevents partial
  files on crash. Image writes use `write_bytes_atomic`.
- **No auto-migration.** Unknown schema version → `422` with a user-visible message.
- **Cached envelopes are singletons.** `<project>_<page:03d>_envelope.json` is overwritten
  on every auto-save; NOT content-addressed.
- **Image cache is content-addressed.** `<project>_<page:03d>_<type>_<sha>.{jpg,png}` —
  sha is SHA-1 of encoded bytes, hex, first 16 chars. Two writers produce the same filename.

## Decision

### Three lanes

1. **Source** — `<source_root>/<project>/<image>.png` + `pages.json`. Read-only.
2. **Labeled** — `<data>/labeled-projects/<project_id>/<project_id>_<page:03d>.{png,json}`.
   Explicit user saves only.
3. **Cached** — `<cache>/page-images/<project_id>_<page:03d>_envelope.json`. Auto-save
   after every mutation.

Read precedence on page-load: labeled → cached → OCR → fallback.

### UserPageEnvelope v2.1

Schema `pd_ocr_labeler.user_page` v2.1. `extra="forbid"` on top-level; `extra="ignore"` on
nested provenance for forward-compat. `build_envelope` / `parse_envelope` in
`core/persistence/user_page_envelope.py`. Round-trip identity invariant.

### Atomic write helper

`write_json_atomic(path, data)` writes to `path.with_suffix('.tmp')` then
`os.replace(tmp, path)`. `write_bytes_atomic` similarly. Both in
`core/persistence/atomic.py`.

### Sidecar files

- `session_state.json` — `{schema_version: "1.0", last_project_path, last_page_index}`.
  Written on every project load. Read on startup.
- `project.json` — written on every Save Project. Schema `pd_ocr_labeler.project` v1.0.
- `config.yaml` — `source_projects_root`. Auto-created on first run.
- `ocr_config.json` — SPA-only sidecar (model selection). Not read by legacy.

### Image cache

JPEG quality 92, max dimension 1200px. `_MAX_CACHED_DIMENSION = 1200`. PNG fallback when
JPEG round-trip differs visibly. SHA-1 of encoded bytes, hex, truncated to 16 chars.
Image types: `original | lines | words | paragraphs | matched_words`.

### Concurrency

Single-process backend; all writes serialize through `AppState`-level lock per project.
Startup warning if another process holds the cache root via pidfile.

## Contract / Acceptance

- Round-trip golden test: every fixture envelope from `pd-ocr-labeler/tests/` parses and
  rebuilds byte-equal.
- Power-fail simulation test: `os._exit(1)` between `write_text` and `replace`; no partial
  file left.
- Image cache: same content always produces same filename (content-addressable test).
- `session_state.json` written on project load; read on cold start restores project.

## Trade-offs considered

**Content-addressed vs per-page singleton for cached envelopes.** Content-addressed envelopes
would accumulate indefinitely. Per-page singleton means auto-save always overwrites the
previous cached envelope. Singleton chosen; images are content-addressed (so two identical
renders don't duplicate the image file).

**Atomic writes vs direct writes.** Direct writes risk partial files on crash (power loss
between open and close). `tmp + os.replace` is POSIX atomic. Cost: one extra file per write.
Chosen: atomic everywhere.

**422 vs 200+migration on unknown schema.** Auto-migration hides schema drift and can
corrupt data. `422` with a user-visible message forces a deliberate upgrade path.

## Consequences

- Any new field in `UserPageEnvelope` must be optional with a default; adding required
  fields is a v2.2 bump requiring D-003 review.
- The image cache is never automatically evicted; `make clean-cache` is the user's escape.
- `ocr_config.json` save errors are swallowed (WARNING log only); a failed save does not
  turn a successful OCR-config POST into a 500.

## Open questions

None.

## References

- `specs/09-persistence.md` — legacy feature doc (full schema and lane detail)
- `specs/01-data-models.md §3` — `UserPageEnvelope` schema definition
- `core/persistence/atomic.py` — atomic write helpers
- `core/persistence/user_page_envelope.py` — envelope reader/writer

---
kind: architecture
status: built
owner: maintainers
created: 2026-05-06
last_verified: 2026-07-13
---

# 01 — Data Models

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#6

Every Pydantic, dataclass, and on-disk JSON schema. **Compatibility
with the legacy `pd-ocr-labeler` is mandatory** for everything the
labeler reads or writes from the user's data root, because the same
data root is shared during transition ([D-003](../../specs/17-decisions.md)).

Conventions:

- Domain models live in `src/pdomain_ocr_labeler_spa/core/models.py`. They
  are reused by both the `IStorage`/`IOCREngine` Protocols and the
  wire — no separate DTO layer (mirrors pgdp-prep's
  `core/models.py:1-300`).
- Per-route ad-hoc shapes (`<Verb><Noun>Request` / `<Verb><Noun>Response`)
  live in the route module that defines them.
- All persistence schemas use Pydantic v2 with `model_config = ConfigDict(extra="forbid")`
  on top-level envelopes, `extra="ignore"` on nested provenance blocks
  so older saves still round-trip.

---

## 1. Domain models (in-memory)

### `Project`

`src/pdomain_ocr_labeler_spa/core/models.py`. Mirrors legacy
`pd_ocr_labeler/models/project_model.py:9`.

```python
class Project(BaseModel):
    project_id: str             # derived from project_root.name
    project_root: Path          # absolute path to project dir
    image_paths: list[Path]     # sorted list of page image files
    ground_truth_map: dict[str, str]  # normalized mapping
    version: str = "1.0"
    source_lib: str = "doctr-pdomain-labeled"
    total_pages: int            # == len(image_paths)
    saved_pages: int = 0
    current_page_index: int = 0
    include_images: bool = True
    copied_images: bool = False

    @property
    def page_count(self) -> int: return len(self.image_paths)
```

`from_dict` / `to_dict` for `project.json` round-trip
([`09-persistence.md`](09-persistence.md)).

### `PageRecord`

Wraps `pdomain_book_tools.ocr.page.Page` plus per-page UI/persistence
metadata. Mirrors legacy `PageModel` (`page_model.py:8`).

```python
class PageSource(StrEnum):
    OCR = "ocr"
    CACHED_OCR = "cached_ocr"
    FILESYSTEM = "filesystem"
    FALLBACK = "fallback"

class CachedImageSet(BaseModel):
    original: str | None = None
    lines: str | None = None
    paragraphs: str | None = None
    words: str | None = None
    matched_words: str | None = None

class PageRecord(BaseModel):
    page_index: int           # 0-based
    page_number: int          # 1-based
    image_path: Path          # absolute
    page_source: PageSource = PageSource.OCR
    ocr_failed: bool = False
    ocr_provenance: OCRProvenance | None = None
    saved_provenance: dict | None = None
    cached_images: CachedImageSet = CachedImageSet()
    # Note: the actual Page object lives in PageState in-memory; it
    # is NOT serialised through this model. Wire shapes that need the
    # page contents use PagePayload (see §2 below).
```

The legacy `PageModel.__getattr__` proxy is dropped: the SPA always
accesses the underlying `Page` object explicitly.

### `MatchStatus`

`pdomain_ocr_labeler_spa.core.models.MatchStatus` (StrEnum):

```
exact | fuzzy | mismatch | unmatched_ocr | unmatched_gt
```

Same five values as legacy `WordMatch.match_status`.

### `WordMatch`

```python
class WordMatch(BaseModel):
    line_index: int
    word_index: int | None    # None when unmatched_gt
    ocr_text: str
    ground_truth_text: str
    match_status: MatchStatus
    fuzz_score: float | None = None
    is_validated: bool = False
    text_style_labels: list[str] = []        # italics, small_caps, ...
    word_components: list[str] = []          # footnote_marker, drop_cap, ...
    bbox: BBox                               # always present (placeholder for unmatched_gt)
    word_id: str | None = None               # stable id from pdomain_book_tools
```

`text_style_labels` / `word_components` come from
`pdomain_book_tools.ocr.label_normalization.ALLOWED_TEXT_STYLE_LABELS` /
`ALLOWED_WORD_COMPONENT_LABELS`.

### `LineMatch`

```python
class LineMatch(BaseModel):
    line_index: int
    paragraph_index: int | None
    ocr_line_text: str
    ground_truth_line_text: str
    word_matches: list[WordMatch]
    overall_match_status: MatchStatus
    exact_count: int
    fuzzy_count: int
    mismatch_count: int
    unmatched_gt_count: int
    unmatched_ocr_count: int
    validated_word_count: int
    total_word_count: int
    is_fully_validated: bool
```

All counters are pre-computed server-side so the SPA can render line
header rollups without recomputing.

### `BBox`

```python
class BBox(BaseModel):
    x: int
    y: int
    width: int
    height: int
```

Image-coordinate space (top-left origin, source image pixels — not
display pixels). The SPA scales for display via the
`encoded_dimensions` returned alongside the page payload.

### `EncodedDims`

```python
class EncodedDims(BaseModel):
    src_width: int
    src_height: int
    display_width: int     # == src_width clamped to 1200
    display_height: int    # proportional, integer math
    scale: float           # display_width / src_width
```

Same algorithm as legacy
`image_tabs._compute_encoded_dimensions:962`. Implementation lives in
`pdomain_book_tools` so the SPA stays byte-identical with cached image
encoding.

### `Selection`

Per-page UI selection state. Backend keeps the canonical copy so two
tabs viewing the same page see consistent toolbar disabled-states.

```python
class Selection(BaseModel):
    selection_mode: Literal["paragraph", "line", "word"] = "word"
    selected_paragraphs: set[int] = set()
    selected_lines: set[int] = set()
    selected_words: set[tuple[int, int]] = set()  # (line_idx, word_idx)
```

Tuple-set serialises as list-of-pairs over the wire.

### `LineFilter`

```python
class LineFilter(StrEnum):
    UNVALIDATED = "unvalidated"   # default
    MISMATCHED = "mismatched"
    ALL = "all"
```

Translated to the legacy toggle labels for tests:
`Unvalidated Lines` / `Mismatched Lines` / `All Lines`.

---

## 2. Wire shapes (route-level Pydantic)

Only the shapes that don't appear in `core/models.py`. Naming is
strict: `<Verb><Noun>Request` / `<Verb><Noun>Response`.

### Project routes

```python
class ListProjectsResponse(BaseModel):
    projects: list[ProjectKey]   # see below
    selected: str | None
    projects_root: Path
    config_source: Literal["yaml", "cli", "default"]

class ProjectKey(BaseModel):
    project_id: str
    project_root: Path
    label: str                  # display label (project_id with dedup suffix)

class LoadProjectRequest(BaseModel):
    project_root: Path
    initial_page_index: int = 0

class LoadProjectResponse(BaseModel):
    project: Project
    current_page: PagePayload   # eagerly fetched first page

class SetSourceProjectsRootRequest(BaseModel):
    path: Path

class SetSourceProjectsRootResponse(BaseModel):
    projects_root: Path
    projects: list[ProjectKey]
```

### Page routes

```python
class PagePayload(BaseModel):
    record: PageRecord
    encoded: EncodedDims
    line_matches: list[LineMatch]
    paragraph_indices: list[int]   # which paragraph_index each line is part of
    page_text_ocr: str              # pre-built OCR plaintext
    page_text_gt: str               # pre-built GT plaintext
    image_url: str                  # /image-cache/<project>_<page>_original_<hash>.jpg
    overlay_urls: dict[str, str]    # {"lines":"/image-cache/...", ...}
    has_edited_image: bool          # True when a user-cropped or user-edited image exists in the image cache for this page, enabling the "Reload OCR (Edited)" button.

class GetPageRequest(BaseModel):
    project_id: str
    page_index: int                # 0-based
    line_filter: LineFilter = LineFilter.UNVALIDATED

class SavePageRequest(BaseModel):
    saved_by: str = "Save Page"
class SavePageResponse(BaseModel):
    page: PagePayload
    saved_path: Path

class SaveProjectResponse(BaseModel):
    saved_count: int
    skipped_count: int
    failed_count: int
    total_count: int
    failures: list[SaveFailure] = []

class SaveFailure(BaseModel):
    page_index: int
    page_number: int
    reason: str

class ReloadOCRRequest(BaseModel):
    use_edited_image: bool = False

class RematchGtRequest(BaseModel):
    pass
```

### Word routes

```python
class UpdateWordGroundTruthRequest(BaseModel):
    text: str

class ApplyStyleRequest(BaseModel):
    style: str          # one of ALLOWED_TEXT_STYLE_LABELS
    scope: Literal["whole", "part"] = "whole"

class ApplyComponentRequest(BaseModel):
    component: str      # one of ALLOWED_WORD_COMPONENT_LABELS
    enabled: bool

class ToggleValidatedRequest(BaseModel):
    validated: bool | None = None   # None means "toggle"

class ValidateBatchRequest(BaseModel):
    scope: Literal["page", "paragraph", "line", "word"]
    line_index: int | None = None
    word_indices: list[tuple[int,int]] = []
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    validated: bool

class AddWordRequest(BaseModel):
    line_index: int | None = None     # None means "auto-pick nearest"
    bbox: BBox
    text: str = ""

class ReboxWordRequest(BaseModel):
    bbox: BBox

class NudgeBboxRequest(BaseModel):
    left: int = 0   # signed pixel deltas; positive expands outward
    right: int = 0
    top: int = 0
    bottom: int = 0
    refine_after: bool = False

class SplitWordRequest(BaseModel):
    x_fraction: float                  # 0..1
    direction: Literal["horizontal", "vertical"]

class MergeWordsRequest(BaseModel):
    direction: Literal["left", "right"]   # merge with neighbour

class ErasePixelsRequest(BaseModel):
    bbox: BBox
    fill_value: int = 255              # 0..255 grayscale fill
```

### Line/paragraph routes

```python
class CopyLineGtRequest(BaseModel):
    direction: Literal["gt_to_ocr", "ocr_to_gt"]

class DeleteScopeRequest(BaseModel):
    scope: Literal["paragraph", "line", "word"]
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    word_indices: list[tuple[int,int]] = []

class MergeScopeRequest(BaseModel):
    scope: Literal["paragraph", "line"]
    paragraph_indices: list[int] = []  # ≥2
    line_indices: list[int] = []       # ≥2

class SplitParagraphAfterLineRequest(BaseModel):
    paragraph_index: int
    after_line_index: int

class SplitLineAfterWordRequest(BaseModel):
    line_index: int
    after_word_index: int

class SplitLineWithSelectedWordsRequest(BaseModel):
    line_index: int
    word_indices: list[int]
    mode: Literal["extract_to_new", "split_into_two"]

class GroupSelectedWordsIntoNewParagraphRequest(BaseModel):
    word_indices: list[tuple[int,int]]
```

### Refine routes

```python
class RefineScopeRequest(BaseModel):
    scope: Literal["page", "paragraph", "line", "word"]
    mode: Literal["refine", "expand_then_refine", "expand_only"] = "refine"
    padding_px: int = 2
    paragraph_indices: list[int] = []
    line_indices: list[int] = []
    word_indices: list[tuple[int,int]] = []
```

### OCR config

```python
class OCRModelOption(BaseModel):
    key: str               # opaque id; "stock" / "hf:<name>" / "local:<path>"
    label: str             # display
    source: Literal["stock", "huggingface", "local"]
    revision: str | None = None
    is_default: bool = False
    weights_id: str | None = None

class GetOCRConfigResponse(BaseModel):
    detection_options: list[OCRModelOption]
    recognition_options: list[OCRModelOption]
    selected_detection: str
    selected_recognition: str
    hf_pinned_revision: str | None
    selection_reason: Literal[
        "hf-latest", "hf-only", "local-newer-than-hf",
        "local-only-hf-unreachable", "hf-unreachable-no-local",
        "stock-fallback"
    ]

class SetOCRModelsRequest(BaseModel):
    detection_key: str
    recognition_key: str
    hf_pinned_revision: str | None = None
```

### Export

```python
class ExportScope(StrEnum):
    CURRENT = "current"
    ALL_VALIDATED = "all_validated"

class ExportRequest(BaseModel):
    scope: ExportScope
    style_filters: list[str] = []     # empty == "All (no style filter)"
    component_filter: str | None = None
    include_classification: bool = False
    detection_only: bool = False
    recognition_only: bool = False

class ExportResponse(BaseModel):
    job_id: str        # SSE channel /api/jobs/{job_id}/events
```

### Jobs

Mirrors pgdp-prep `core/models.py` Job.

```python
class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"

class JobType(StrEnum):
    REFINE_BBOXES_PAGE = "refine_bboxes_page"
    EXPAND_REFINE_BBOXES_PAGE = "expand_refine_bboxes_page"
    RELOAD_OCR_PAGE = "reload_ocr_page"
    EXPORT = "export"
    SAVE_PROJECT = "save_project"
    REFINE_BBOXES_PROJECT = "refine_bboxes_project"

class JobProgress(BaseModel):
    current: int = 0
    total: int = 0
    current_page: int | None = None
    message: str = ""

class Job(BaseModel):
    id: str
    type: JobType
    project_id: str | None
    status: JobStatus
    progress: JobProgress
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
```

### Notifications

```python
class NotificationKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    WARNING = "warning"
    INFO = "info"

class Notification(BaseModel):
    id: str
    kind: NotificationKind
    message: str
    created_at: datetime
```

### Error envelope

Same shape as pgdp-prep
`api/middleware/error_handler.py:18-22`:

```python
class ApiError(BaseModel):
    error: str            # snake_case stable code
    message: str
    details: Any = None
```

Status code conventions:

- `400` `validation_error` for Pydantic / domain validation failures.
- `404` for missing project / page / word.
- `409` `conflict` for autosave races (last-writer-wins; SPA refetches).
- `422` for `BoundingBox.is_geometry_normalization_error` and similar
  geometry impossibilities — distinct from generic 400 so the SPA can
  show a specific "cannot refine bbox at this geometry" toast.
- `202` for "queued a job" returns.
- `204` for delete-success / batch-validate-success.
- `500` `internal_error` catch-all.

---

## 3. On-disk schemas

### `UserPageEnvelope` v2.1 / v2.2

**Read + write byte-equivalent to legacy** (legacy
`pd_ocr_labeler/models/user_page_persistence.py:83-86`).

Schema: `{"name": "pd_ocr_labeler.user_page", "version": "2.1"}` for
files written without rotation state. **v2.2** is an additive bump
(D-032, Q-A1) introducing `source.rotation_degrees: int = 0` and
`source.rotation_source: Literal["none","auto","manual"] = "none"` to
persist auto-rotation results across save/load. Readers MUST accept
both versions; writers emit v2.2 only when rotation state is non-default
to preserve byte-equivalence with legacy v2.1 readers in the common
case. Before the first v2.2 file is written, verify that legacy's
top-level envelope `extra="forbid"` (if any) tolerates the additive
`source.rotation_degrees` / `source.rotation_source` fields — the
fields are **inside `source`**, not at the envelope root, so legacy's
root-level strictness does not apply. If legacy's `Source` model
also forbids extras, fall back to sidecar `<project>_<page:03d>.rotation.json`
per Q-A1 option (B) with auto-cleanup on next legacy save.

```jsonc
{
  "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
  "provenance": {
    "saved_at": "2026-05-06T12:34:56.789Z",
    "saved_by": "Save Page",        // human-readable trigger label
    "source_lane": "labeled",       // "labeled" | "cached" — legacy enum
    "app": {"name": "pdomain_ocr_labeler_spa", "version": "...", "git_commit": "..."},
    "toolchain": {
      "python": "3.13.x",
      "pdomain_book_tools": "...",
      "opencv_python": "..."
    },
    "ocr": { /* OCRProvenance: engine, engine_version, models[], config_fingerprint */ }
  },
  "source": {
    "project_id": "...",
    "page_index": 0,
    "page_number": 1,
    "image_path": "relative/to/project_root.png",
    "project_root": "...absolute...",
    "image_fingerprint": {
      "size": 12345,
      "mtime_ns": 123456789,
      "sha256": "..."
    }
  },
  "payload": {
    "page": { /* pdomain_book_tools.ocr.page.Page.to_dict() — verbatim */ },
    "original_page": { /* optional pre-edit snapshot */ },
    "word_attributes": {
      "<word_id>": {"italic": false, "small_caps": false, ...}
    }
  },
  "cached_images": {
    "original": "<project>_<page:03d>_original_<hash>.jpg",
    "lines":    "<project>_<page:03d>_lines_<hash>.jpg",
    "paragraphs": "<project>_<page:03d>_paragraphs_<hash>.jpg",
    "words":    "<project>_<page:03d>_words_<hash>.jpg",
    "matched_words": "<project>_<page:03d>_matched_words_<hash>.jpg"
  }
}
```

Reader (`src/pdomain_ocr_labeler_spa/core/persistence/user_page_envelope.py`):

- `is_user_page_envelope(data)` type guard.
- `parse_envelope(data) -> UserPageEnvelope` Pydantic-validating loader.
- `build_envelope(page, page_record, project, *, source_lane, saved_by, update_page_source) -> dict` writer.
- Round-trip test: load → write → load equals first load (golden file).

The legacy `payload.word_attributes` side channel is preserved on both
read and write. **Don't drop this** even though `Page.to_dict()`
already encodes the same info — older saves are read-only without it.

### `project.json`

Top of `<labeled-projects>/<project_id>/project.json`:

```jsonc
{
  "schema": {"name": "pd_ocr_labeler.project", "version": "1.0"},
  "project_id": "...",
  "source_path": "...",
  "version": "1.0",
  "source_lib": "doctr-pdomain-labeled",
  "total_pages": 42,
  "saved_pages": 12,
  "current_page_index": 5,
  "include_images": true,
  "copied_images": false
}
```

`Project.to_dict()` / `Project.from_dict()` round-trip.

### `pages.json` / `pages_manifest.json` (ground truth)

**Read-only** in the SPA. Same shape as legacy
(`project_operations.py:344-486`):

`pages_manifest.json` (multi-source, takes priority):

```jsonc
{
  "schema": "pd_ocr_labeler.pages_manifest",
  "version": "1.0",
  "sources": [
    {"file": "pages_r1.json", "offset": 0},
    {"file": "pages_r2.json", "offset": 100}
  ]
}
```

`pages.json`:

```jsonc
{
  "001.png": "Ground truth text...",
  "002": "..."
}
```

Normalisation (`_normalize_ground_truth_entries:275`):

- Apply `pdomain_book_tools.pgdp.pgdp_results.PGDPResults(key, text).processed_page_text`
  to every value (PGDP-markup → OCR-comparable Unicode).
- Add lowercase variant of every key.
- For keys without extension, add `.png/.jpg/.jpeg` variants and
  lowercased ones.

`ProjectState.find_ground_truth_text(name, map)` tries variants in
priority order: as-given → lowercased → with .png → with .jpg → with
.jpeg → lowercased ext variants.

### `session_state.json`

`<data_root>/session_state.json`:

```jsonc
{
  "schema_version": "1.0",
  "last_project_path": "/abs/path/to/project_dir",
  "last_page_index": 5
}
```

Saved on every successful project load (`AppState.load_project:402`).
Read on root-page load. **Field name compatibility** required —
legacy uses `last_project_path` (singular). The SPA must read and
write the same names so flipping between binaries works.

### `ocr_config.json`

`<data_root>/ocr_config.json` — **SPA-only** sidecar persisting OCR
model selection across restarts. Legacy `pd-ocr-labeler` does not
read/write this file. Full lifecycle + failure-mode contract in
[`09-persistence.md`](09-persistence.md) §7a:

```jsonc
{
  "schema_version": "1.0",
  "selected_detection_key": "stock",
  "selected_recognition_key": "stock",
  "hf_pinned_revision": null
}
```

Field-by-field parity with the wire DTOs in §3 above
(`GetOCRConfigResponse.selected_*`, `SetOCRModelsRequest`); the
sidecar exists so `OCRConfigCarrier` (M3 slice 8c-iv-a) keeps
state across restart.

### Image cache filenames

`<cache_root>/page-images/`:

```
<project>_<page:03d>_<image_type>_<content_hash>.{jpg|png}
```

Image types: `original`, `lines`, `words`, `paragraphs`, `matched_words`.

`content_hash` is SHA-1 of the raw bytes of the rendered overlay PNG
(legacy `image_cache_operations.compute_image_hash:24` — *check the
exact algo: SHA-1 hex truncated to 16 chars*). Max dimension 1200 px
(`_MAX_CACHED_DIMENSION`).

These names are **shared with the legacy labeler**; both can read each
other's cache entries.

### YAML config

`<config_root>/config.yaml` (note: `<config_root>` already includes the
`pdomain-ocr-labeler-spa/` app-name suffix per §5's path table):

```yaml
# Root directory containing OCR project subdirectories.
source_projects_root: "/path/to/projects"
```

Same path / same key as legacy. Auto-create on first run with default
`<data_root>/source-pgdp-data/output/`.

The SPA will write its config at the **same path** (so flipping
binaries doesn't reset the user's source root).

---

## 4. Schema versioning policy

| Schema | Bump rule |
|---|---|
| `pd_ocr_labeler.user_page` | Patch (2.1 → 2.2): new optional fields. Minor (2.x → 3.0): breaking field rename / type change. SPA refuses to write `>= 3.0` until the legacy labeler can read it too. |
| `pd_ocr_labeler.project` | Same. |
| `pd_ocr_labeler.pages_manifest` | Read-only — never written by either binary. |

Until v9 (the binary swap), the SPA writes `2.1` envelopes and never
emits anything the legacy can't read.

---

## 5. OS-aware paths

| Function | Linux | macOS | Windows |
|---|---|---|---|
| `config_root` | `${XDG_CONFIG_HOME:-~/.config}/pdomain-ocr-labeler-spa/` | `~/Library/Application Support/pdomain-ocr-labeler-spa/` | `%APPDATA%/pdomain-ocr-labeler-spa/` |
| `data_root` | `${XDG_DATA_HOME:-~/.local/share}/pdomain-ocr-labeler-spa/` | same as config_root | `%LOCALAPPDATA%/pdomain-ocr-labeler-spa/` |
| `cache_root` | `${XDG_CACHE_HOME:-~/.cache}/pdomain-ocr-labeler-spa/` | `~/Library/Caches/pdomain-ocr-labeler-spa/` | `%LOCALAPPDATA%/pdomain-ocr-labeler-spa/cache/` |
| `default_source_projects_root` | `<data>/source-pgdp-data/output/` | same | same |
| `logs_root` | `<data>/logs/` | same | same |
| `page_image_cache_root` | `<cache>/page-images/` | same | same |
| `saved_projects_root` | `<data>/labeled-projects/` | same | same |
| `project_backups_root` | `<data>/project-backups/` | same | same |

Same rules as legacy `persistence_paths_operations.py`. The directory
*name* is `pdomain-ocr-labeler-spa`. (Pre-cut-over, [D-003](../../specs/17-decisions.md)
kept the legacy `pd-ocr-labeler` name to share a data root with the
NiceGUI labeler; the cut-over is complete and the legacy is superseded,
so the SPA now owns its own `pdomain-`-prefixed root.) Override via
`PDLABELER_DATA_ROOT`, etc., in [`02-backend.md`](02-backend.md).

---

## 6. OpenAPI export rules

`make openapi-export` runs:

```sh
uv run python -c "import json; from pdomain_ocr_labeler_spa.bootstrap import build_app; \
  print(json.dumps(build_app().openapi(), indent=2))" > frontend/openapi.json
cd frontend && npx --yes openapi-typescript openapi.json -o src/api/types.ts
```

**CI gate**: re-run `make openapi-export` and `git diff --exit-code`.
This closes the pgdp-prep drift gap. PR fails if `types.ts` is out of
sync.

`frontend/src/api/types.ts` is committed. The fetch wrapper at
`frontend/src/api/client.ts` is hand-written.

---

## 7. Conformance fixtures

Carry over from legacy:

- `tests/integration/test_user_page_persistence.py` — round-trip
  envelope fixtures (legacy + new).
- A real labeled project from `pd-ocr-labeler/tests/browser/fixtures/`
  copied into the SPA test tree as a frozen golden.

The SPA must read every legacy envelope in the test tree without
mutating it. Writing one SPA envelope and reading it from the legacy
binary is a manual M9 acceptance test.

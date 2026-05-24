# F-001 — Export style filters can escape the export directory

> **Status**: Draft
> **Last updated**: 2026-05-24
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#406

## TL;DR

`style_filters` strings accepted by `POST /api/projects/{id}/export` are used
verbatim as filesystem path segments under `data_root/doctr-export/{project_id}/`.
A crafted filter such as `../../etc` escapes that tree and can create or write
training output anywhere the server process has write permission. Fix: validate
labels as identifier-safe strings at the API boundary (Pydantic validator on
`ExportRequest`) and add a containment check in the path-building helper.

## Context

The vulnerability sits at two layers.

**API layer** — `src/pd_ocr_labeler_spa/api/export.py:54`

```python
style_filters: list[str] = []
```

No validation. Any string is accepted and propagated verbatim into the job
payload.

**Handler layer** — `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py:190-197`

```python
def export_output_dir(data_root: Path, project_id: str, subfolder: str) -> Path:
    return data_root / _DOCTR_EXPORT_DIRNAME / project_id / subfolder
```

`Path.__truediv__` with an absolute segment (`/etc`) discards everything to
its left; `../` segments traverse upward. A `subfolder` such as
`../../evil` produces `data_root/doctr-export/../../evil` which resolves to
`data_root/../../evil` — outside the intended export tree entirely.

The handler then calls `output_dir.mkdir(parents=True, exist_ok=True)` (line
236) and writes detection/recognition training files into whatever directory
was produced.

`component_filter` (line 55) travels through the same code path
(`_subfolder_for_style` is also used indirectly for component exports) but is
a single string, not a list, so the attack surface is smaller. It should be
validated identically.

`project_id` from the URL path is also fed into `export_output_dir`; it is
not user-supplied at export time (it is a known project identifier) but
deserves the same treatment for defence-in-depth.

**Why it matters.** The labeler runs as the local user on a developer
workstation. A malicious export request — whether crafted by the user
themselves, by another site exploiting the wildcard CORS setting described
in F-002, or by a compromised project file — can write files to arbitrary
locations on the local filesystem.

## Goals / Non-Goals

**Goals**

- Reject any `style_filters` or `component_filter` value that is not a safe
  label string before it is stored in the job payload.
- Guarantee that the resolved export output directory is a strict descendant
  of `data_root / "doctr-export" / project_id` regardless of input.
- Add a failing test that demonstrates the traversal before the fix.
- Add a regression test that confirms the containment guard holds after the fix.

**Non-Goals**

- Changing the exported training-data format.
- Adding authentication to the export endpoint (tracked separately in F-002).
- Validating `project_id` characters beyond what is already enforced by the
  project-loading layer — that is a separate concern.

## Constraints

- The validation must not break any existing valid style-label string. Current
  style labels in the codebase are lowercase ASCII words and short phrases with
  spaces (e.g., `"italics"`, `"small caps"`, `"drop cap"`, `"footnote marker"`).
  The allowlist must admit these.
- The containment check in `export_output_dir` must remain a pure function
  (no I/O) so it can be tested in isolation.
- The Pydantic validator must raise `ValueError` (FastAPI maps this to 422) so
  callers get a structured error, not an unhandled 500.
- Do not change the `ExportRequest` wire format — the existing fields remain
  unchanged; only validation is added.

## Options Considered

### Option A — Allowlist regex on each label string (chosen)

Add a `@field_validator("style_filters", "component_filter", mode="before")`
on `ExportRequest` that rejects any string not matching
`^[A-Za-z0-9 _\-\.]{1,64}$` (or tighter: only lowercase + space + hyphen).
Additionally, add a `_assert_within_export_root` containment guard in
`export_output_dir` that calls `.resolve()` on the constructed path and
asserts it starts with `(data_root / "doctr-export" / project_id).resolve()`.

Trade-offs: simple; two independent layers so a bypass of one is caught by
the other; the regex is easy to audit.

### Option B — Sanitize (strip/replace bad chars) instead of reject

Replace `../`, `/`, and absolute-path markers silently before using the
label as a path segment. Trade-off: hides the error from the caller; a
legitimate label like `../extras` (unusual but not impossible) is silently
mutated into `..extras`, which creates a different subdirectory from what was
requested. Rejecting is safer and more honest.

### Option C — Use a deterministic hash of the label as the directory name

Hash each style filter to a fixed-length hex string; store the
label→hash mapping in a sidecar JSON next to the export directory.
Trade-off: safe against traversal, but adds complexity (sidecar file,
mapping maintenance) for no benefit when the simpler allowlist suffices.
Deferred — can be adopted later if the label character set needs to expand.

## Decision

**Option A** — dual-layer defence: Pydantic allowlist validator + path
containment guard.

Concretely:

1. **`ExportRequest` field validator** — add to `src/pd_ocr_labeler_spa/api/export.py`:

```python
import re

_SAFE_LABEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _\-]{0,62}$')

@field_validator("style_filters", mode="before")
@classmethod
def _validate_style_filters(cls, v: object) -> list[str]:
    if not isinstance(v, list):
        raise ValueError("style_filters must be a list")
    for label in v:
        if not isinstance(label, str) or not _SAFE_LABEL_RE.match(label):
            raise ValueError(
                f"Invalid style filter {label!r}: must match {_SAFE_LABEL_RE.pattern}"
            )
    return v

@field_validator("component_filter", mode="before")
@classmethod
def _validate_component_filter(cls, v: object) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str) or not _SAFE_LABEL_RE.match(v):
        raise ValueError(
            f"Invalid component_filter {v!r}: must match {_SAFE_LABEL_RE.pattern}"
        )
    return v
```

1. **Containment guard in `export_output_dir`** — add to
   `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py`:

```python
def export_output_dir(data_root: Path, project_id: str, subfolder: str) -> Path:
    """``<data_root>/doctr-export/<project_id>/<subfolder>/``.

    Raises ``ValueError`` if the resolved path is not strictly under the
    project export root.  This is a defence-in-depth guard; the API layer
    should have already rejected unsafe strings via ``ExportRequest``
    validators.
    """
    export_root = (data_root / _DOCTR_EXPORT_DIRNAME / project_id).resolve()
    candidate = (data_root / _DOCTR_EXPORT_DIRNAME / project_id / subfolder).resolve()
    if not str(candidate).startswith(str(export_root) + "/") and candidate != export_root:
        raise ValueError(
            f"Export subfolder {subfolder!r} resolves outside the project export "
            f"root: {candidate} is not under {export_root}"
        )
    return candidate
```

Note: `.resolve()` is I/O if the path exists, but returns a fully normalised
absolute path even for non-existent paths in Python 3.6+, which is sufficient
for the containment check before `mkdir` is called.

1. **Callers of `export_output_dir`** — `handle_export` already passes
   `style_filters` values as subfolders. The guard in `export_output_dir`
   means a `ValueError` raised there will propagate out of the async handler
   and be caught by the job runner as a job failure (logged, status
   `FAILED`). This is acceptable — a malicious payload results in a failed
   job, not filesystem corruption.

## Implementation Plan

Slice 1 (test-first):

- Write `tests/unit/test_export_path_containment.py` with two tests:
  - `test_traversal_via_style_filter` — submits a request with
    `style_filters=["../../evil"]` and expects a 422 response.
  - `test_export_output_dir_containment_guard` — calls `export_output_dir`
    directly with a traversal subfolder and expects `ValueError`.

Slice 2 (implementation):

- Add `_SAFE_LABEL_RE` and the two `@field_validator` methods to
  `ExportRequest` in `src/pd_ocr_labeler_spa/api/export.py`.
- Add the containment guard to `export_output_dir` in
  `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py`.
- Run `make test AI=1` to confirm the new tests pass and no existing
  tests regress.

Slice 3 (regression + cleanup):

- Add parameterised regression tests for valid labels that must not be
  rejected: `"italics"`, `"small caps"`, `"drop cap"`, `"footnote marker"`,
  `"all"`.
- Update `src/pd_ocr_labeler_spa/api/export.py` module docstring to mention
  the validation.
- Close #406 in the commit message.

## Test Plan

**Failing test (proves the bug before the fix):**

```python
# tests/unit/test_export_path_containment.py

def test_traversal_via_style_filter(test_client):
    """A crafted style_filter with ../ must be rejected 422 before the fix."""
    resp = test_client.post(
        "/api/projects/my-project/export",
        json={"scope": "all_validated", "style_filters": ["../../evil"]},
    )
    assert resp.status_code == 422

def test_export_output_dir_containment_guard(tmp_path):
    """export_output_dir must raise ValueError for a traversal subfolder."""
    from pd_ocr_labeler_spa.core.jobs.handlers.export import export_output_dir
    with pytest.raises(ValueError, match="resolves outside"):
        export_output_dir(tmp_path, "proj", "../../evil")
```

**Regression tests (valid labels must pass):**

```python
@pytest.mark.parametrize("label", ["italics", "small caps", "drop cap", "all", "a-1"])
def test_valid_style_filters_accepted(test_client, label):
    resp = test_client.post(
        "/api/projects/my-project/export",
        json={"scope": "all_validated", "style_filters": [label]},
    )
    # 202 Accepted (job enqueued); NOT 422
    assert resp.status_code == 202

@pytest.mark.parametrize("label", ["italics", "small caps", "all"])
def test_export_output_dir_valid_subfolders(tmp_path, label):
    from pd_ocr_labeler_spa.core.jobs.handlers.export import export_output_dir
    result = export_output_dir(tmp_path, "proj", label)
    assert str(result).startswith(str(tmp_path))
```

**Attack vectors that must all return 422:**

- `style_filters: ["../../etc"]` — upward traversal
- `style_filters: ["/etc/passwd"]` — absolute path
- `style_filters: ["a/b"]` — embedded separator
- `style_filters: [""]` — empty string
- `style_filters: ["a" * 65]` — over-length label
- `component_filter: "../evil"` — same class of attack on component_filter

## Open Questions

None. The approach is self-contained and does not touch any spec-governed
API wire format or data-model contract.

---
kind: issue
status: active
owner: maintainers
created: 2026-11-07
last_verified: 2026-11-07
level: I1
---

# Python builds without memfd support break labeling-bundle loading

## Agent Index

- **Kind:** issue
- **Status:** active
- **Level:** I1
- **Last verified:** 2026-11-07
- **Resolution:** Open
- **Severity:** High — verified bundle loading raises exceptions or returns HTTP 500 on the affected build.
- **Affected version:** source commit 5b0a624c; worktree Python 3.13.14 without os.memfd_create.
- **Read when:** book loading, page leases, or bundle-backed review fails under a new Python environment.
- **Search terms:** memfd_create, sealed descriptor, labeling bundle, Python build, HTTP 500, CI failures.
- **Relates to:** [persistence architecture](../architecture/09-persistence.md).

## Summary

The verified-image loaders call `os.memfd_create` without checking whether the Python build exposes it.
The documentation worktree selected a Python 3.13.14 build that lacks the function. Its book and single-bundle
load paths raise AttributeError; API callers receive a generic HTTP 500.

All 21 tests observed failing in the interrupted CI run reproduce under that build. The same 21 tests pass
in the main checkout with Python 3.13.18, which exposes the function. These are related failures of one
runtime capability requirement, not evidence of 21 independent product defects.

## Impact

Verified labeling-bundle and lazy book-image loading fail on the affected runtime. Review queues,
page-kind measurement, region detection, and page-lease tests also fail when their setup needs those loaders.
The current error does not explain the missing runtime capability to the API user.

The dependency range accepts both tested builds. A successful dependency installation therefore does not
establish that the loader's required operating-system interface exists.

## Environment / versions

Both checkouts were at commit `5b0a624cf89f520d11f8d9395773751f65ef8bb0` on omarchy-main when compared.
The host reported Linux 7.2.8-9-omarchy, x86_64, glibc 2.44.

| Checkout | Python build | memfd_create | Rerun of the 21 failed tests |
| --- | --- | --- | --- |
| Main checkout | CPython 3.13.18, Clang 23.1.3 | Present | 21 passed in 2.06 seconds |
| Documentation worktree | CPython 3.13.14, Clang 22.1.3 | Absent | 21 failed in 1.82 seconds |

The main checkout is `/mnt/work/projects/pdomain/pdomain-ocr-labeler-spa`.
The affected worktree is `/home/ntw/.codex/worktrees/2c8e/pdomain-ocr-labeler-spa`.
Each command used that checkout's `uv run` environment. The observed Python version difference does not
prove that every 3.13.14 build fails or that upgrading is the only remedy.

## Evidence

### Capability probe

Run in each checkout:

```sh
uv run python -c 'import os, sys; print(sys.version); print(hasattr(os, "memfd_create"))'
```

The worktree prints Python 3.13.14 and False. The main checkout prints Python 3.13.18 and True.

### Smallest test reproduction

Run in the affected worktree:

```sh
uv run pytest tests/unit/core/persistence/test_book_labeling_session.py \
  -k opens_first_middle_and_last_pages_with_an_edition_companion \
  -q --no-cov --tb=short
```

Observed before the aggregate rerun: one failed test in 0.66 seconds. The decisive stack frames are:

```text
core/persistence/book_labeling_session.py:370
    image_descriptor = _sealed_descriptor(image_payload)
core/persistence/book_labeling_session.py:160
    descriptor = os.memfd_create(...)
AttributeError: module 'os' has no attribute 'memfd_create'
```

Paths above are relative to `src/pdomain_ocr_labeler_spa`. The single-bundle loader has the same
unconditional call in `core/persistence/labeling_bundle.py:134`.

### Aggregate reproduction and API symptom

The 21 exact test nodes listed below were rerun with `uv run pytest`, `-q`, `--no-cov`, and
`--tb=short` in both checkouts. The affected build produced 12 direct AttributeError failures and nine
assertions that HTTP 500 should have been HTTP 200. Captured API exception traces also name the missing function.
The API response is:

```json
{"error":"internal_error","message":"Internal server error","details":null}
```

The original `make ci AI=1` run was stopped after these failures while its remaining Docker tests were
rebuilding images. It did not complete. One Docker build test passed before cancellation; cancellation is
not a Docker defect, and this report does not claim a complete CI result on either runtime.

## Root-cause hypotheses

The immediate cause is confirmed: both sealed-image helpers call a function missing from the selected
Python build. They also rely on Linux sealing behavior through fcntl. The advertised Python range is
`>=3.13,<3.14`; that version check does not express the required capability.

Why the two Python builds expose different APIs is not established. Build configuration is a hypothesis;
this investigation did not inspect the interpreter build flags or establish a kernel, permission, or
seccomp failure. Execution fails at attribute lookup, before the memfd system call can be attempted.

## Defects to fix

1. Detect or explicitly require the runtime capabilities needed by both verified-image loaders.
2. Return an actionable compatibility error instead of an unhandled AttributeError and generic HTTP 500.
3. Cover the missing-capability path without weakening immutable image leases or silently skipping their tests.

## Next steps

1. Decide whether the supported runtime must expose Linux memfd sealing or needs an equivalent immutable carrier.
2. Check both loader entry points and their API error mapping against that decision.
3. Add focused missing-capability tests, then rerun the affected nodes under both supported and unsupported builds.
4. Investigate interpreter build differences before declaring a version-specific workaround sufficient.
5. Run the complete CI gate after the compatibility behavior is fixed; the earlier interrupted run is not that proof.

## What is NOT broken

- The same 21 tests pass in the main checkout's Python 3.13.18 environment.
- These failures do not establish corruption of stored books or source images.
- The documentation cleanup changed no Python or TypeScript code.
- The new PGDP flat-image fixture is a separate filesystem-loader path; this report concerns verified bundle leases.
- macOS, Windows, other Python 3.13.14 builds, and other operating-system restrictions were not tested.

## Affected test nodes

### `tests/integration/test_review_queue_router.py`

- `test_typography_for_a_single_bundle_project_uses_the_bundles_page_id`
- `test_word_and_typography_are_unavailable_for_a_multi_page_labeling_bundle_book`
- `test_word_counts_a_single_bundle_project_from_the_real_thing`
- `test_word_reports_fully_validated_for_a_single_bundle_project`

### `tests/integration/test_projects_router.py`

- `test_post_load_auto_detects_and_retains_labeling_bundle`

### `tests/integration/test_region_proposals_router.py`

- `test_a_book_labeling_project_detector_sees_the_sealed_descriptor`
- `test_the_book_lease_is_closed_even_when_the_detector_raises`

### `tests/unit/core/jobs/test_labeling_page_lease.py`

- `test_a_book_project_resolves_a_sealed_descriptor_while_bound`
- `test_the_lease_is_closed_after_a_successful_block`
- `test_the_lease_is_closed_when_the_block_raises`

### `tests/unit/core/jobs/test_propose_page_kinds_handler.py`

- `test_a_book_labeling_project_measures_through_the_sealed_descriptor`
- `test_a_book_labeling_lease_is_closed_after_each_page_is_measured`
- `test_an_unreadable_page_is_skipped_and_the_rest_of_the_book_still_runs`

### `tests/unit/core/persistence/test_book_labeling_session.py`

- `test_rejects_later_page_with_a_different_resolver_identity`
- `test_retained_page_lease_survives_cache_eviction_and_descriptor_reuse`
- `test_opens_one_real_producer_shaped_page_without_eagerly_loading_others`
- `test_opens_first_middle_and_last_pages_with_an_edition_companion`

### `tests/unit/core/persistence/test_labeling_bundle.py`

- `test_load_validates_and_retains_external_artifacts`
- `test_loaded_bundle_context_manager_closes_its_image_descriptor`

### `tests/integration/test_book_manifest_loader.py`

- `test_loads_and_navigates_a_lazy_319_page_pgdp_book`
- `test_simultaneous_book_leases_keep_page_descriptors_independent`

## Resolution

Open. This task documents the defect; no loader, runtime, or API behavior was changed.

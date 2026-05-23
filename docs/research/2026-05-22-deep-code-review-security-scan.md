# Deep Code Review and Security Scan - 2026-05-22

Repository: `ConcaveTrillion/pd-ocr-labeler-spa`

Scope: backend/API, frontend, dependency/supply-chain, CI/release, repo conventions, driver contract, and scanner-backed security findings. Subagents reviewed independent slices and the parent pass deduplicated overlapping findings into the canonical items below.

## Scanner Summary

- `pnpm audit --json`: 2 moderate dev-dependency advisories (`esbuild`, transitive `vite@5.4.21`).
- `pnpm audit --prod --audit-level low`: no runtime frontend advisories reported by subagent.
- `npm audit --json`: failed with `ENOLOCK` because the repo tracks `pnpm-lock.yaml`, not `package-lock.json`.
- `uv lock --check`: lockfile is in sync.
- `uv export --frozen --no-dev --no-hashes | uvx pip-audit -r /dev/stdin --format json`: 2 runtime Python advisories in this parent pass (`idna`, `starlette`); dependency subagent's all-groups audit also reported `urllib3`.
- `uv run ruff check --select S src tests`: passed.
- `bandit -r src scripts -f json`: 0 high, 2 medium, 23 low.
- Secret grep for common token/private-key patterns: no high-confidence committed secrets found.
- `semgrep`, `gitleaks`, `trufflehog`, `detect-secrets`, `checkov`, `syft`, `grype`, `osv-scanner`, and `hadolint`: not installed.

## Findings

### F-001 - Export style filters can escape the export directory

Severity: High security

Evidence: `src/pd_ocr_labeler_spa/api/export.py:52`, `src/pd_ocr_labeler_spa/api/export.py:90`, `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py:190`, `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py:236`, `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py:341`.

`style_filters` are accepted as arbitrary strings, passed into the export job payload, and later used as path segments under `data_root / "doctr-export" / project_id / subfolder`. Absolute labels and `../` segments are not rejected before directories and output files are written.

Impact: A crafted export request can create or write training output outside the intended export tree wherever the server process has permission.

Recommended fix: Validate style/component labels as data, not paths. Reject absolute paths, separators, `.`, `..`, empty strings, and overly long labels. Resolve the final output path and require it to remain under `data_root / "doctr-export" / project_id`.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/406.

### F-002 - Wildcard CORS plus no-auth filesystem routes exposes local filesystem metadata

Severity: High security

Evidence: `src/pd_ocr_labeler_spa/bootstrap.py:258`, `src/pd_ocr_labeler_spa/adapters/auth/none_.py:15`, `src/pd_ocr_labeler_spa/api/fs.py:1`, `src/pd_ocr_labeler_spa/api/projects.py:619`.

CORS allows all origins, methods, and headers. The v1 auth adapter accepts every caller as the local user. `/api/fs/ls` explicitly lists arbitrary local directories without path restriction, and `/api/projects/source-root` persists any existing directory as the source root.

Impact: A malicious website can reach a running localhost labeler from the browser, read directory names, and issue state-changing POST requests because no credentials are needed.

Recommended fix: Default to same-origin only, allow the Vite dev origin explicitly in dev, and require a local CSRF/API token for filesystem and state-changing routes. Consider gating `/api/fs/*` and `/api/projects/source-root` behind an explicit local-trust setting.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/407.

### F-003 - Default 500 responses leak exception messages and traceback tail

Severity: Medium security

Evidence: `src/pd_ocr_labeler_spa/settings.py:124`, `src/pd_ocr_labeler_spa/api/middleware/error_handler.py:153`, `tests/unit/core/test_error_handler.py:175`.

`debug_unhandled_traceback` defaults to true, the catch-all handler returns `message=str(exc)`, and tests assert sensitive exception text appears in the response body.

Impact: Internal paths, exception text, and potentially sensitive values can cross the API boundary to any client, amplified by wildcard CORS.

Recommended fix: Default `debug_unhandled_traceback` to false. Expose detailed errors only under an explicit dev/debug setting and keep full tracebacks server-side with request-id correlation.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/408.

### F-004 - Page image resize endpoint has no bounds

Severity: Medium security

Evidence: `src/pd_ocr_labeler_spa/api/pages.py:1122`.

The image endpoint accepts `w: int | None = None` without `Query` bounds, then resizes the full image to `(w, new_h)` and encodes into memory.

Impact: Very large positive `w` values can force excessive memory allocation and CPU work.

Recommended fix: Constrain `w` with `Query(ge=64, le=4096)` or similar and enforce a maximum output pixel count before resizing.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/409.

### F-005 - Export request accepts contradictory modes and invalid current-page indexes

Severity: Medium correctness

Evidence: `src/pd_ocr_labeler_spa/api/export.py:52`, `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py:309`, `src/pd_ocr_labeler_spa/core/jobs/handlers/export.py:321`.

`detection_only` and `recognition_only` can both be true, disabling both outputs. `page_index` is optional and unconstrained; negative current-page exports simply produce no candidate file.

Impact: The API can report success for nonsensical requests and produce no usable dataset.

Recommended fix: Add Pydantic validation to reject `detection_only && recognition_only`, require at least one output mode, and require `page_index >= 0` for current-page export scope.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/410.

### F-006 - Python dependency advisory: `idna` CVE-2026-45409

Severity: Medium security

Evidence: `uv.lock:752` locks `idna==3.13`; `pip-audit` reports `CVE-2026-45409` with fix version `3.15`.

Impact: Specially crafted inputs to `idna.encode()` can consume significant resources.

Recommended fix: Run `uv lock --upgrade-package idna`, verify tests, and keep the lockfile updated.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/411.

### F-007 - Python dependency advisory: `starlette` PYSEC-2026-161

Severity: Medium security

Evidence: `uv.lock:2304` locks `starlette==1.0.0`; `pip-audit` reports `PYSEC-2026-161` / `GHSA-86qp-5c8j-p5mr` with fix version `1.0.1`.

Impact: Host header handling can cause inconsistent URL interpretation in Starlette-based apps.

Recommended fix: Upgrade Starlette/FastAPI lock entries to a fixed version and verify app tests.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/412.

### F-008 - Python dependency advisory: `urllib3` PYSEC-2026-141/PYSEC-2026-142

Severity: Medium security

Evidence: dependency subagent all-groups `pip-audit` reported `urllib3==2.6.3` with fixes in `2.7.0`.

Impact: HTTP client dependency exposure in dev/all-groups environments.

Recommended fix: Upgrade `urllib3` to `2.7.0` or later and verify backend/dev tooling tests.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/413.

### F-009 - Frontend dev dependency advisory: `esbuild` GHSA-67mh-4wv8-2f99

Severity: Medium security

Evidence: `frontend/pnpm-lock.yaml:2196`, `frontend/pnpm-lock.yaml:5737`, `pnpm audit` reports vulnerable `esbuild@0.21.5` via Vitest's Vite tree.

Impact: A website can abuse the development server to send requests and read responses.

Recommended fix: Upgrade Vitest/Vite or add a package-manager override so the transitive esbuild tree is patched.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/414.

### F-010 - Frontend dev dependency advisory: transitive `vite@5.4.21`

Severity: Medium security

Evidence: `frontend/pnpm-lock.yaml:3600`, `frontend/pnpm-lock.yaml:7343`, `pnpm audit` reports `GHSA-4w7w-66w2-5vf9`.

Impact: Vite optimized dependency sourcemap handling can expose files through path traversal in dev-server contexts.

Recommended fix: Upgrade Vitest/Vite so all Vite lock entries are patched.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/415.

### F-011 - CI, release, and Docker ignore the tracked pnpm lockfile

Severity: High supply-chain

Evidence: `Makefile:168` uses pnpm, only `frontend/pnpm-lock.yaml` is tracked, but `.github/workflows/ci.yml:37`, `.github/workflows/release.yml:40`, and `Dockerfile:17` bootstrap or use npm/package-lock flows.

Impact: GitHub and Docker builds can resolve a different dependency graph from local `make frontend-install`, bypassing the reviewed pnpm lock and workspace settings.

Recommended fix: Switch CI, release, Docker, and related tests to `pnpm install --frozen-lockfile`; copy `pnpm-lock.yaml`, `pnpm-workspace.yaml`, and `.npmrc` into Docker build stages.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/416.

### F-012 - Tests preserve obsolete npm/package-lock behavior

Severity: High test/CI

Evidence: `tests/unit/test_release_workflow.py:330` and `tests/unit/test_dockerfile.py` assert the npm/package-lock fallback behavior.

Impact: Tests would reject a correct migration to the repo's documented pnpm/frozen-lockfile workflow.

Recommended fix: Update tests to assert pnpm/frozen-lockfile behavior and remove npm package-lock fallback expectations.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/417.

### F-013 - Docker image and tool sources use mutable tags

Severity: Medium supply-chain

Evidence: `Dockerfile:15` uses `node:24-bookworm-slim`, `Dockerfile:37` copies from `ghcr.io/astral-sh/uv:latest`, and runtime uses `python:3.13-slim-bookworm`.

Impact: Rebuilds can silently consume changed base images or tools.

Recommended fix: Pin base images and the uv image to immutable digests or specific versioned tags plus digests.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/418.

### F-014 - Runtime container runs as root

Severity: Medium container security

Evidence: `Dockerfile:94` starts the runtime stage and `Dockerfile:140` sets the entrypoint without any `USER` directive.

Impact: A container compromise gets root inside the container.

Recommended fix: Create a non-root runtime user, chown needed app paths, and switch to `USER` before entrypoint.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/419.

### F-015 - GitHub Actions are tag-pinned instead of SHA-pinned

Severity: Medium supply-chain

Evidence: examples include `.github/workflows/ci.yml:28` and `.github/workflows/release.yml:98`.

Impact: Mutable action tags can be retargeted or compromised.

Recommended fix: Pin actions to full commit SHAs and use Dependabot/Renovate or a scheduled process for updates.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/420.

### F-016 - Runtime Docker install strips lockfile hashes before pip install

Severity: Medium supply-chain

Evidence: `Dockerfile:90` runs `uv export --no-hashes`, then `Dockerfile:122` installs with pip from the exported requirements.

Impact: Runtime install loses hash verification even though `uv.lock` contains hashes.

Recommended fix: Prefer installing from the uv lock directly or preserve and enforce hashes where pip is used.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/421.

### F-017 - Install paths execute remote scripts without checksum or signature verification

Severity: Medium supply-chain

Evidence: `install.sh:7`, `install.sh:23`, `install.ps1:4`, `install.ps1:33`, and `Makefile:122`.

Impact: Upstream, DNS, or CDN compromise becomes local code execution for users running install helpers.

Recommended fix: Avoid piping remote scripts directly. Pin release assets and verify checksums/signatures before execution.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/422.

### F-018 - Bandit B310: screenshot helper opens URLs without scheme validation

Severity: Medium security

Evidence: `scripts/take_cutover_screenshot.py:52` and `scripts/take_cutover_screenshot.py:140`.

Impact: If URL input becomes attacker-controlled, `file:` or other unexpected schemes may be opened.

Recommended fix: Validate `http`/`https` and loopback host before opening, or document/suppress if the helper is strictly internal.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/423.

### F-019 - Build backend requirements are unpinned

Severity: Low supply-chain

Evidence: `pyproject.toml:2` lists `hatchling` and `hatch-vcs` without pinned ranges.

Impact: Build isolation can pull new build tooling unexpectedly.

Recommended fix: Pin build backend requirements to reviewed version ranges and update deliberately.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/424.

### F-020 - Pre-commit hooks are tag-pinned instead of SHA-pinned

Severity: Low supply-chain

Evidence: `.pre-commit-config.yaml:22` and `.pre-commit-config.yaml:66`.

Impact: Local hook execution trusts mutable tags.

Recommended fix: Pin hook repos to commit SHAs or explicitly document the accepted risk.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/425.

### F-021 - Git and non-PyPI dependencies are skipped by pip-audit

Severity: Low supply-chain

Evidence: `uv.lock:1436` (`pd-book-tools`) and `uv.lock:1985` (`python-doctr`) are not auditable by standard PyPI advisory matching.

Impact: Standard dependency scanning has blind spots for important runtime dependencies.

Recommended fix: Add separate monitoring for Git/non-PyPI dependencies, SBOM review, or upstream advisory tracking.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/426.

### F-022 - Ignored temporary issue cache files are committed

Severity: Low information hygiene

Evidence: `.gitignore:66` ignores `.ship-issue-tmp/`, but `git ls-files` shows tracked `.ship-issue-tmp/*.json` files.

Impact: Current files expose issue metadata only, but future temp cache contents could leak private issue text or tokens.

Recommended fix: Remove the ignored temp files from git history/index where appropriate and keep the ignore.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/427.

### F-023 - Runtime asserts in non-test code disappear under optimized Python

Severity: Low security/correctness

Evidence: Bandit B101 reported runtime asserts in `src/pd_ocr_labeler_spa/adapters/ocr/local_doctr.py:281`, `src/pd_ocr_labeler_spa/api/dependencies.py`, `src/pd_ocr_labeler_spa/api/pages.py`, `src/pd_ocr_labeler_spa/api/projects.py:465`, `src/pd_ocr_labeler_spa/core/model_selection.py`, and `src/pd_ocr_labeler_spa/core/startup_discovery.py:178`.

Impact: Checks disappear under `python -O`, potentially changing runtime behavior.

Recommended fix: Replace runtime asserts with explicit exceptions or document/suppress type-narrowing-only asserts.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/428.

### F-024 - Bandit B105 flags `API_TOKEN: None` as a hardcoded token

Severity: Low scanner hygiene

Evidence: `src/pd_ocr_labeler_spa/api/env_js.py:31`.

Impact: This appears to be a false positive, but it will recur if Bandit is added to CI.

Recommended fix: Add a targeted suppression with rationale or adjust Bandit configuration if security linting becomes a CI gate.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/429.

### F-025 - GitHub CI is not equivalent to documented `make ci`

Severity: Medium CI

Evidence: `Makefile:320` runs setup, frontend install, pre-commit, typecheck, OpenAPI export, frontend build, lint, tests, frontend tests, and knip. `.github/workflows/ci.yml` omits `pre-commit-check` and `frontend-knip`.

Impact: Required local gates can pass or fail differently from remote CI.

Recommended fix: Add explicit CI jobs for `uv run pre-commit run --all-files` and `make frontend-knip`, or make GitHub CI invoke the same `make ci` contract.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/430.

### F-026 - Release workflow is not actually gated by CI

Severity: Medium release

Evidence: `.github/workflows/release.yml:3` says releases require CI, but the workflow triggers directly on tags; `.github/workflows/ci.yml:3` runs only on pushes/PRs to main.

Impact: A manually pushed tag can publish without GitHub-enforced CI.

Recommended fix: Run `make ci` in the release workflow or gate release through required checks, protected tags, or `workflow_run`.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/431.

### F-027 - CI uses bare `python3`

Severity: Low convention

Evidence: `.github/workflows/ci.yml:169` uses `python3 -m zipfile`; `CONVENTIONS.md:62` requires `uv run` for Python/tool invocation.

Impact: CI bypasses the uv-managed Python/toolchain for that step.

Recommended fix: Use `uv run python -m zipfile`.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/432.

### F-028 - OpenAPI drift check compares ignored `frontend/openapi.json`

Severity: Medium CI

Evidence: `.github/workflows/ci.yml:218` diffs `frontend/openapi.json`, but `.gitignore:36` ignores it and only `frontend/src/api/types.ts` is tracked.

Impact: Schema-file drift is not actually checked; only generated TypeScript drift is.

Recommended fix: Track `frontend/openapi.json`, or remove it from the diff and compare against a temporary schema artifact explicitly.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/433.

### F-029 - Multiple JSON API routes omit explicit `response_model`

Severity: High API contract

Evidence: `CONVENTIONS.md:165`; examples include `src/pd_ocr_labeler_spa/api/fs.py:23`, `src/pd_ocr_labeler_spa/api/projects.py:344`, `src/pd_ocr_labeler_spa/api/projects.py:513`, `src/pd_ocr_labeler_spa/api/projects.py:561`, `src/pd_ocr_labeler_spa/api/projects.py:729`, `src/pd_ocr_labeler_spa/api/export.py:109`, `src/pd_ocr_labeler_spa/api/export.py:127`, `src/pd_ocr_labeler_spa/api/lines_paragraphs.py:819`, `src/pd_ocr_labeler_spa/api/normalize.py:27`, and `src/pd_ocr_labeler_spa/api/notifications.py:61`.

Impact: FastAPI does not validate responses, OpenAPI degrades to `{}`/`unknown`, and generated frontend types lose useful contracts.

Recommended fix: Add concrete Pydantic response models for JSON routes, `response_model=None` for no-body routes, and explicit binary response metadata for image routes. Add a conformance test that fails on untyped JSON responses.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/434.

### F-030 - OpenAPI advertises 200 for routes that return 202 or 204

Severity: High API contract

Evidence: `src/pd_ocr_labeler_spa/api/refine.py:110`, `src/pd_ocr_labeler_spa/api/pages.py:869`, `src/pd_ocr_labeler_spa/api/pages.py:1023`, `src/pd_ocr_labeler_spa/api/projects.py:684`, `src/pd_ocr_labeler_spa/api/projects.py:729`, and `src/pd_ocr_labeler_spa/api/notifications.py:61`.

Impact: Generated clients and docs disagree with runtime behavior, especially for long-running job routes.

Recommended fix: Add `status_code=202` or `status_code=204, response_model=None` to decorators as appropriate and regenerate OpenAPI types.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/435.

### F-031 - Page image endpoint OpenAPI advertises JSON unknown instead of image/jpeg

Severity: Medium API contract

Evidence: `src/pd_ocr_labeler_spa/api/pages.py:1122` returns `Response(..., media_type="image/jpeg")` without response-class/schema metadata; generated types advertise JSON `unknown`.

Impact: API docs and generated clients lie about the content type.

Recommended fix: Declare `response_class=Response` and explicit OpenAPI `responses` for `image/jpeg` plus error JSON responses.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/436.

### F-032 - Route/OpenAPI tests check presence, not schema quality

Severity: Medium tests

Evidence: `tests/unit/api/test_wire_shapes.py:16`, `tests/integration/test_normalize_router.py:28`, and `tests/integration/test_export_router.py:76`.

Impact: Untyped response schemas and status-code mismatches pass CI.

Recommended fix: Add a conformance test that fails on `{}` response schemas for JSON routes and verifies documented success status codes/content types.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/437.

### F-033 - Missing SPA bundle returns 404 instead of the workspace-required 503

Severity: Low deployment

Evidence: `src/pd_ocr_labeler_spa/api/static_mounts.py:314`, `tests/unit/api/test_static_mounts.py:417`, workspace guidance in `/workspaces/ocr-container/CLAUDE.md`.

Impact: Deployment diagnostics cannot distinguish “SPA not built” from “route not found”.

Recommended fix: Return 503 for non-reserved SPA paths when `index.html` is absent and update tests accordingly.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/438.

### F-034 - Atomic writers use deterministic temp filenames

Severity: Low correctness

Evidence: `src/pd_ocr_labeler_spa/core/persistence/atomic.py:128`, `src/pd_ocr_labeler_spa/core/persistence/ocr_config.py:217`, `src/pd_ocr_labeler_spa/core/persistence/session_state.py:347`, `tests/integration/test_concurrent_mutations.py:25`.

Impact: Concurrent writes to the same sidecar can clobber temp files, fail during replace, or leave stale temp files.

Recommended fix: Use unique temp files in the same directory, then `os.replace`, with cleanup on failure. Add concurrent tests for config/session/OCR sidecars.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/439.

### F-035 - Destructive hotkeys bypass required confirmation flows

Severity: High data loss

Evidence: `frontend/src/hooks/useGlobalHotkeys.ts:8`, `frontend/src/pages/ProjectPage.tsx:328`, `frontend/src/pages/ProjectPage.tsx:372`, `frontend/src/pages/ProjectPage.tsx:541`, `frontend/src/hooks/useMatchesHotkeys.ts:7`.

`Mod+L`, `Mod+G`, and `D` are documented as destructive/confirming flows but are wired directly to mutations.

Impact: Accidental hotkeys can discard, recompute, or delete page data without user confirmation.

Recommended fix: Route destructive hotkeys through confirmation dialogs and test that mutations do not fire until confirmation.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/440.

### F-036 - Char-fixer debounced GT edits are dropped on unmount or navigation

Severity: High data loss

Evidence: `frontend/src/components/right-panel/sections/CharFixerSection.tsx:157` schedules a 500 ms save; cleanup at `frontend/src/components/right-panel/sections/CharFixerSection.tsx:169` only clears the timer.

Impact: Typing a character fix and changing word/page or closing the panel within 500 ms loses the edit.

Recommended fix: Flush pending save on cleanup/word change or commit on blur/Enter. Add a regression test that unmounts before the debounce fires.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/441.

### F-037 - Char-range edits are local-only and component labels are not serialized

Severity: High data loss

Evidence: `frontend/src/components/right-panel/sections/CharRangesSection.tsx:85`, `frontend/src/components/right-panel/sections/CharRangesSection.tsx:326`, `frontend/src/components/right-panel/sections/CharRangesSection.tsx:330`, `frontend/src/components/right-panel/sections/CharRangesSection.tsx:344`, `frontend/src/components/right-panel/sections/CharRangesSection.tsx:356`.

Existing range edits only update local state, and `toApiStyles` omits `activeComponents`.

Impact: Users can edit ranges/components in the UI and lose those changes after refresh or the next persisted add/delete.

Recommended fix: Persist existing-range edits or add an explicit Apply button, include component labels in the API payload/schema, and add tests for existing range and component persistence.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/442.

### F-038 - Project and job IDs are interpolated into URL paths without encoding

Severity: Medium security/correctness

Evidence: `frontend/src/lib/routes.ts:20`, `frontend/src/hooks/usePage.ts:53`, `frontend/src/hooks/usePageMutations.ts:43`, `frontend/src/hooks/useWordMutations.ts:47`, `frontend/src/hooks/useJobProgress.ts:49`.

Impact: Directory basenames or job IDs containing `#`, `?`, `%`, spaces, or slashes can navigate or fetch the wrong URL.

Recommended fix: Centralize URL builders and use `encodeURIComponent` for every path segment. Test IDs containing reserved URL characters.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/443.

### F-039 - Page hotkeys remain active behind dialogs

Severity: Medium data loss/accessibility

Evidence: `frontend/src/pages/ProjectPage.tsx:266`, `frontend/src/pages/ProjectPage.tsx:328`, `frontend/src/pages/ProjectPage.tsx:355`.

Dialog open state is available but not used to disable global and match hotkeys.

Impact: While a modal is open, keystrokes can mutate/delete the underlying page.

Recommended fix: Compute `anyDialogOpen` and disable all page hotkey hooks while any modal is active. Add modal-open suppression tests.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/444.

### F-040 - Modals declare `aria-modal` without focus trapping or consistent Escape handling

Severity: Medium accessibility

Evidence: `frontend/src/components/ExportDialog.tsx:219`, `frontend/src/components/OCRConfigModal.tsx:160`, `frontend/src/components/SourceFolderDialog.tsx:186`, `frontend/src/components/ConfirmDialog.tsx:47`, `frontend/src/components/right-panel/WordFooter.tsx:176`.

Impact: Keyboard and screen-reader users can tab behind modal content or be unable to dismiss consistently.

Recommended fix: Use a dialog primitive with focus trap/restore and Escape handling, or implement those behaviors centrally.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/445.

### F-041 - Char-bbox Apply clears dirty state before save succeeds

Severity: Medium correctness

Evidence: `frontend/src/components/right-panel/sections/CharFixerSection.tsx:252` calls the mutation and `frontend/src/components/right-panel/sections/CharFixerSection.tsx:260` immediately clears dirty state.

Impact: A failed save leaves the UI looking clean, so users can navigate away believing bbox edits persisted.

Recommended fix: Clear dirty only on mutation success; show an error and keep dirty on failure. Add a failed-request test.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/446.

### F-042 - OCR auto-rotate config POST silently ignores HTTP failures

Severity: Medium correctness

Evidence: `frontend/src/components/OCRConfigModal.tsx:44`, `frontend/src/components/OCRConfigModal.tsx:116`.

Impact: 4xx/5xx responses appear successful and the UI refetches without surfacing the failure.

Recommended fix: Check `resp.ok`, throw with response text, show error state/toast, and disable controls while saving.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/447.

### F-043 - Project cards navigate even when project loading fails

Severity: Low correctness

Evidence: `frontend/src/pages/RootPage.tsx:151`, `frontend/src/pages/RootPage.tsx:153`.

Impact: Failed loads send the user to a project route instead of keeping them on the list with an actionable error.

Recommended fix: Navigate only on load success and show failure state/toast on error.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/448.

### F-044 - Shared API client drops falsy bodies and always parses success as JSON

Severity: Low correctness

Evidence: `frontend/src/api/client.ts:37`, `frontend/src/api/client.ts:72`.

Impact: Valid `false`, `0`, `""`, or `null` bodies are not sent, and empty successful responses such as 204 throw during parsing.

Recommended fix: Send a body when the option key is present, not when it is truthy; handle 204 and empty responses before calling `response.json()`.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/449.

### F-045 - Tri-state chips expose no accessible state

Severity: Low accessibility

Evidence: `frontend/src/components/ui/Chip.tsx:50`.

Impact: Screen-reader users cannot tell whether a tri-state chip is off, on, or mixed.

Recommended fix: Use a native button with `aria-pressed={true | false | "mixed"}` or a checkbox pattern with `aria-checked`.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/450.

### F-046 - Driver-contract E2E test does not cover every documented testid

Severity: High test/driver contract

Evidence: `docs/architecture/13-driver-contract.md:440`, `tests/e2e/test_driver_contract.py:1`, `tests/e2e/test_driver_contract.py:41`.

Impact: Toolbar, page action, per-line, per-word, dialog, export, busy, and rail selector regressions can pass.

Recommended fix: Generate/assert the catalogue from the spec or maintain a complete explicit testid list in E2E.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/451.

### F-047 - Apply Style toolbar testids do not match the driver contract

Severity: High driver contract

Evidence: `docs/architecture/13-driver-contract.md:253`, `frontend/src/components/ToolbarActionGrid.tsx:270`, `tests/e2e/test_spec_s2_coverage.py:465`.

The spec requires `scope-select`, `apply-component-button`, `clear-component-button`, and `word-add-button`; implementation uses different IDs or lacks the controls, and tests accept aliases.

Impact: Driver selectors using documented IDs fail.

Recommended fix: Restore documented IDs or update the contract through the versioning process, then tighten tests.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/452.

### F-048 - Per-line/per-word driver IDs are missing or placed on alias attributes

Severity: High driver contract

Evidence: `docs/architecture/13-driver-contract.md:206`, `frontend/src/components/LineCard.tsx:120`, `frontend/src/components/WordCell.tsx:103`.

Required IDs such as `line-checkbox-{n}`, `paragraph-checkbox-{p}`, `word-checkbox-{l}-{w}`, `word-validate-button-{l}-{w}`, `word-image-cell-{l}-{w}`, and `word-tag-clear-button-{l}-{w}-{label}` are absent or placed on `data-testid-alias`.

Impact: Driver cannot select required match-view controls.

Recommended fix: Add documented `data-testid` values to real or stubbed controls.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/453.

### F-049 - Word edit dialog IDs diverge from the driver contract

Severity: High driver contract

Evidence: `docs/architecture/13-driver-contract.md:265`, `frontend/src/components/WordEditDialog.tsx:151`.

The spec requires `word-edit-dialog`, preview-column IDs, and `dialog-gt-input`; implementation uses different IDs and omits `dialog-gt-input`.

Impact: Driver cannot find/open/edit through the documented dialog contract.

Recommended fix: Add the contract IDs while retaining internal IDs only if needed.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/454.

### F-050 - Driver URL contract is internally inconsistent

Severity: Medium docs/driver contract

Evidence: `docs/architecture/13-driver-contract.md:34`, `docs/architecture/13-driver-contract.md:419`.

The canonical routes are `/projects/{id}/pages/pageno/{n}`, but section 7 still instructs drivers to navigate to legacy `/project/foo/page/3` and `/project/foo` paths.

Impact: Driver authors receive conflicting URL instructions.

Recommended fix: Update section 7 to canonical routes and document legacy redirects separately.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/455.

### F-051 - RUF002 is globally ignored despite the Unicode convention

Severity: Medium convention/lint

Evidence: `CONVENTIONS.md:32`, `CONVENTIONS.md:53`, `pyproject.toml:118`.

The convention says ambiguous Unicode must be escaped and calls RUF002 ignores high-confidence violations, but `pyproject.toml` globally ignores RUF002.

Impact: Ambiguous docstring Unicode can enter unchecked.

Recommended fix: Remove the global ignore and escape/name intentional characters, or revise the convention explicitly.

Issue: https://github.com/ConcaveTrillion/pd-ocr-labeler-spa/issues/456.


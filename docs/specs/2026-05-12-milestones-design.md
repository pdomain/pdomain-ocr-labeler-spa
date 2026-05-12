# pd-ocr-labeler-spa: Milestones Roadmap

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#36

## TL;DR

Ten milestones (M0–M9) plus five post-GA addenda (M9.1, M9.2, M9.5, M10, M11). Each milestone is bounded enough
for one AI coding agent in one session, with listed acceptance tests as the completion gate.
Milestones build strictly on the previous; no milestone may start before its precondition
milestone's acceptance tests pass. Each agent must write named tests first (fail), implement
until they pass, then mark complete.

## Context

The milestone structure provides a discipline: small, tested slices in dependency order. The
SPA builds domain functionality incrementally — repo scaffold → adapters → project load →
page display → image viewport → word matches → persistence → export → full assembly. Agents
must read the spec(s) listed for each milestone before starting. OPEN_QUESTIONS.md must be
checked for any item that might affect the milestone's scope. Milestone completion means ALL
listed acceptance tests pass AND CI is green.

## Constraints

- **Sequential delivery.** Milestone N cannot start until N-1 acceptance tests pass.
- **Tests-first discipline.** Implementing agents write the listed tests first, see them fail,
  then implement. No test = milestone incomplete.
- **No premature optimization.** Do not add capabilities beyond the milestone scope, even if
  "obvious". Future milestones address them deliberately.
- **OPEN_QUESTIONS.md check.** Every milestone agent reads OPEN_QUESTIONS.md before starting.
  If an open question would change the implementation, pause and surface it.
- **CI green on merge.** The PR for each milestone must pass all CI jobs (lint, test-backend,
  test-frontend, test-e2e, build-wheel, openapi-drift).

## Decision

### M0 — Repo scaffold

Outcome: repo that lints, type-checks, builds an empty wheel, boots `pd-ocr-labeler-ui`, and
serves a static "Hello" SPA. No domain logic. Acceptance: `make setup && make test` green;
`make frontend-build` produces `dist/`; `make build` produces a wheel with `static/index.html`;
`pd-ocr-labeler-ui --no-browser` serves 200 at `/healthz`; ESLint + ruff clean; Makefile
implements dev-local-aware `upgrade-deps` / `upgrade-deps-local` per deployment spec §15.

### M1 — Settings + adapters + AppState seam

Outcome: `build_app(settings)` wires `Settings`, `IStorage(filesystem)`, `IAuth(none)`,
`IOCREngine(local_doctr)` stub, `AppState` skeleton, `RequestIdMiddleware`, structured logging,
error handler. Frontend renders empty header + "No project loaded" placeholder. Acceptance:
`test_build_app_returns_fastapi`, `test_request_id_echoed`, `test_startup_shutdown_clean`;
`data-testid="project-load-button"` present in header (disabled).

### M2 — Project discovery + load

Outcome: user picks project from dropdown, clicks LOAD, sees page name + source badge. No
image, overlays, or word matches. Acceptance: GET /api/projects lists discovered projects;
POST /api/projects/load → 200; GET /api/projects/{id}/pages/0 returns partial PagePayload;
URL updates to `/projects/{id}/pages/pageno/1`; session_state.json written on load.

### M3 — Image display + tabs shell

Outcome: page image renders in the left pane. Right pane shows TextTabs shell (Matches /
Ground Truth / OCR tabs; Matches is empty; plain textarea for GT + OCR tabs). Page source
badge + page name visible. Acceptance: `image-viewport` testid present; GET image URL returns
JPEG; tab switching works; GT/OCR tabs show raw text.

### M4 — Image viewport interactions (BBoxOverlay, selection, rebox, add word, erase)

Outcome: bounding-box overlays render and are interactive. Selection rectangle, rebox mode,
add-word mode, erase pixels. Acceptance: `SelectRect.test.tsx` and `BBoxOverlay.test.tsx` unit
tests pass; Playwright: click word → highlights; drag → rebox; erase mode enters/exits.

### M5 — Word matches view (LineCard list, GT editing, validation)

Outcome: right-pane matches view shows virtualised LineCard list. Inline GT editing, per-word
and per-line validation, line actions (GT→OCR, OCR→GT, delete). Acceptance: 200-line page
renders only ~10 cards at once; Tab navigates GT inputs in reading order; validate button flips
badge; line delete shows AlertDialog.

### M6 — Toolbar actions (page/paragraph/line/word scope)

Outcome: ToolbarActionGrid wired with all scope×action cells. Bulk validate, refine bboxes
(202+job), merge, split, copy direction. Acceptance: `toolbar-page-refine` fires POST and shows
BusyOverlay; `toolbar-line-validate` validates all visible selected lines; all 14×4 cells
present or stub.

### M7 — Word edit dialog (Konva preview, nudge, merge/split/crop, refine)

Outcome: clicking edit-word-button opens WordEditDialog with Konva image preview, GT input,
nudge grid, merge/split/crop/refine actions, tag chips. Acceptance: dialog opens with correct
word image; nudge changes bbox by 1px; merge-prev POSTs and returns updated PagePayload;
split-H divides the word horizontally.

### M8 — Persistence: save page, save project, load page, auto-save to cache

Outcome: Save Page writes labeled lane; Save Project writes all labeled pages (202+job);
Load Page reloads from disk; auto-save fires after every mutation. Acceptance: Save Page →
source badge flips to LABELED; round-trip golden test against legacy fixtures passes; power-
fail test (no partial file); conformance test passes.

### M9 — Export, hotkeys, notifications, full driver-contract conformance, polish

Outcome: all features complete. Export dialog + headless CLI; full hotkey map; SSE
notification stream; driver-contract conformance test passing; axe-core zero WCAG AA
violations; all E2E suites green. Acceptance: `test_driver_contract.py` passes with zero
missing testids; `test_keyboard_only.py` completes load→navigate→validate→save without mouse;
axe-core clean on root, project, matches pages; export golden-file matches legacy output.

### M9.1 — Manual rotation (post-GA)

Outcome: Rotate ↺ / ↻ buttons in PageActions. POST `.../rotate` triggers Reload OCR job.
Rotation badge in PageActions. Acceptance: `rotate-cw-button` fires POST; image visibly
rotates; bboxes recomputed; `rotation-badge` shows correct degree + source.

### M9.2 — Auto-rotation (post-GA)

Outcome: project-load pass detects rotation per page using gt-best-match or layout algorithm.
Configurable in OCR config modal. Indicator badge distinguishes auto vs manual. Acceptance:
fixture with sideways scan → auto-rotate to 90°; badge shows "↻ 90 auto"; click revert → badge
hides.

### M9.5 — Full keyboard-driven editing audit (post-GA, D-022)

Outcome: every action reachable from keyboard; audit + fill gaps from M5–M8 keymap; document
via `?` help modal. Spec: `specs/12-hotkeys-a11y.md`. Pre-conditions: M9.

### M10 — Text normalization (post-GA, D-025)

Outcome: OCR config gains normalization toggle; `ſhall` vs `shall` reports `exact` when
toggle on; plaintext tabs can render ASCII-normalized. Pre-conditions: `pd_book_tools.text
.normalize` available (upstream delegation pending). Spec: `specs/18-text-normalization.md`.

### M11 — Glyph-level side-channel annotations (post-GA)

Outcome: per-word typography annotations (CT/ST ligatures, long-s) editable in
`<WordEditDialog>` and chip-row under each `<WordCell>`; bulk-mark dialog with driver testids;
`UserPageEnvelope` bumps to v2.2. Pre-conditions: `pd_book_tools.ocr.glyph_annotations` and
`IGlyphPredictor` adapter available upstream. Spec: `specs/20-glyph-annotations.md`.

## Contract / Acceptance

- Milestone N's PR may not merge until all acceptance tests listed above pass and CI is green.
- OPEN_QUESTIONS.md items that affect the milestone must be resolved (or explicitly deferred
  with CT sign-off) before the milestone closes.
- Every milestone PR includes the named tests from `specs/14-testing.md` as new or updated
  test files.
- M9 is the GA gate: `test_driver_contract.py` passing is mandatory for release.

## Trade-offs considered

**Sequential vs parallel milestones.** Some milestones could be parallelized (e.g., M4 and M5
are largely independent). However, the domain is complex enough that integration surprises
(shared state, testid conflicts) make strict sequencing safer. Chosen: sequential.

**One session per milestone.** Splitting a milestone across sessions risks context loss.
Each milestone is scoped so a skilled agent can deliver it in one focused session. Chosen:
single-session bound.

**No scope for M9.x polish items in M0–M8.** Shipping text-normalization and glyph annotations
in M0–M8 would delay the GA. Chosen: explicitly post-GA.

## Consequences

- Implementing agents must read this spec before starting any milestone to understand sequencing
  and the tests-first discipline.
- If a milestone's acceptance tests reveal a design problem, the spec must be updated before
  the implementation continues (specs are authoritative; code that disagrees is wrong).
- M9.1 and M9.2 are optional post-GA but the PageActions spec already reserves DOM space
  (hidden via CSS) for the rotate buttons, so M9.1 is a CSS show + endpoint wiring only.

## Open questions

None.

## References

- `specs/16-milestones.md` — legacy milestone doc (full per-milestone file lists and spec refs)
- `specs/00-overview.md` — architecture overview and milestone pre-conditions
- `specs/14-testing.md` — test discipline and coverage targets
- `OPEN_QUESTIONS.md` — open design questions that may affect milestone scope

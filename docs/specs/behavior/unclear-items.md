---
kind: spec
status: active
owner: maintainers
created: 2026-06-01
last_verified: 2026-11-13
---

# Unclear behavior inventory

These items were found during behavior capture and need product or
implementation decisions before they can be treated as locked behavior.

## Routes and root

- Singular `/project/{id}/page/{n}` is supported by backend 301 redirects. The bare plural pages/{n}
  form is not a registered canonical route. Unknown projects redirect to root.
- All/Active/Complete filters and permanent confirmed Delete are implemented; Archive remains rejected.
- Malformed/out-of-range page URL canonicalization still needs an explicit policy; current coercion is
  not proof of a canonical redirect/error contract.

## Canvas and viewport

- Add, rebox and erase callbacks are mounted. Canvas selection is client-owned without a required POST.
- Page-scoped erase and edited-image OCR are implemented; word-scoped erase is separate.
- A missed canvas hit preserves selection, and successful erase exits to select. Conflicting clear-on-miss
  or erase-stays-active expectations remain design discrepancies rather than authority to change code.
- True polygon lasso fill remains unresolved; current word lasso sends its axis-aligned bounding rectangle.

## Shell and drawer

- Search, layer toggles, Bulk-to-Worklist and drawer counts are wired. QuickSearch's keycap focuses input.
- Browser-local drawer persistence and invalid-tab fallback are not implemented; desired persistence
  remains an explicit acceptance gap. There is no universal data-active-absent rule across components.

## Right panel and glyphs

- The word editor is the mounted right panel. Manual glyph writes, chip selection and bulk query
  invalidation persist; every shared ligature kind has browser coverage definitions. No glyph predictor
  exists or will be built in this app.
- BBox Refine/Expand use real scoped jobs; the old Crop action is replaced. Rebox Snap-to-ink still
  behaves as manual geometry.
- Char bboxes survive fresh-store reload (`test_char_sidecar_store_roundtrip.py`). CharFixer still
  synthesizes initial equal boxes; downstream consumers/export semantics remain separate questions.
- Typography suggestion acceptance/editing and predecessor compensation retain the existing owner choices.

## Actions, jobs, and persistence

- Jobs SSE uses public Job-plus-event; canonical export cancellation is `/api/jobs/{job_id}/cancel`.
  `test_jobs_wire_contract.py` and useJobProgress.test.tsx cover the wire boundary.
- The toolbar is visible and dispatches real actions. Rotation changes pixels, reruns OCR and persists
  metadata; it is not a stub. Reload OCR Edited consumes use_edited_image.
- GET image-drift detection and its warning banner are wired. Save-time refusal/automatic recovery and
  a universal SaveStatus workflow remain unimplemented acceptance, not shipped behavior.
- OCR configuration sidecar failures can leave live configuration applied with logged persistence
  failures; the strength of user-visible feedback remains a product question.
- Global jobs history and the full combined browser open/edit/save/export flow are not proved by
  separate component/integration tests.

## Evidence update (2026-11-13)

Fresh source/test analysis checked ProjectPage, PageImageCanvas, Rail, QuickSearch, WordDetail,
BBoxSection, the edited-image OCR job, rotation handlers and the corresponding named test suites.
This separates resolved wiring from residual acceptance without claiming a new full browser exercise.

## Adversarial Review

**Accepted finding:** Resolved rotation, Q-A5–Q-A7, and OCR-trigger claims must not remain in
this ambiguity inventory.

**Stage:** migration-time current-state review on 2026-07-13.

**Source:** an independent read-only reviewer compared this document with current
code, tests, architecture, and git history.

**Result:** the review accepted the finding above and used it to declare the
metadata status. Residual risks remain explicit here or in
`docs/context/intent-map.md`; deferred or blocked behavior is not claimed as
shipped.

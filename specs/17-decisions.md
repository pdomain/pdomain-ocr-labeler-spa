# 17 — Architecture Decisions Log

A chronological log of design decisions: what was decided, why, and
when. New entries on top.

> Format: short, low-ceremony ADRs. One per decision. Don't replace
> existing entries — supersede them with a new entry that links back.

---

## D-001 — Adopt pgdp-prep's `build_app(settings)` factory pattern

**Date.** 2026-05-06.

**Decision.** SPA backend uses `build_app(settings: Settings) -> FastAPI`
with explicit settings parameter. `__main__.main()` reads env into a
`Settings` once, passes it in. Tests do the same with hermetic
settings.

**Why.**
- Same-as pgdp-prep pattern; one less thing to learn.
- `TestClient(build_app(settings))` is the test seam.
- Avoids global singletons, plays well with concurrent tests.

**Alternatives considered.**
- Reading settings inside FastAPI app at first request (lazy). Rejected:
  forces lazy init guards; no clean way to error on bad settings at
  boot.
- Pydantic `BaseSettings` instantiated at module load. Rejected: tests
  would need monkey-patching env vars.

**Refs.** [`02-backend.md`](02-backend.md) §2.

---

## D-002 — Drop NiceGUI, adopt React/Vite

**Date.** 2026-05-06.

**Decision.** Replace the legacy NiceGUI-based UI with a React 19 +
Vite + TypeScript SPA. Keep the FastAPI server.

**Why.**
- The legacy UI's performance ceiling is the websocket roundtrip per
  edit. Big-text editors and word-match rebuilds are server-rendered
  → measurably slow.
- Future driver tooling (and any SPA consumer) wants a typed REST
  surface. The legacy has no REST.
- Per-tab Python state in NiceGUI is expensive; the SPA pushes
  per-tab UI state to the browser cheaply.

**Alternatives considered.**
- Keep NiceGUI, optimize the slow paths. Rejected: we'd be racing
  WebSocket overhead.
- HTMX. Rejected: still server-rendered, not a clean win for the
  drag/canvas-heavy UI.
- Svelte. Rejected: pgdp-prep is React, two stacks doubles review
  cost.

**Refs.** [`00-overview.md`](00-overview.md) §Tech stack.

---

## D-003 — Preserve `pd_ocr_labeler` data root

**Date.** 2026-05-06.

**Decision.** SPA reads + writes the same `<data>/pd-ocr-labeler/`
directory the legacy uses. Both binaries can be installed simultaneously;
flipping between them preserves user data.

**Why.**
- Continuity across the transition. Users don't lose labels.
- Schema-versioned envelopes prevent mis-parses.
- Single user means simultaneous-binary races are unlikely.

**Trade-offs.**
- A second writer can race; we mitigate with `pidfile` lockfile + a
  startup warning.
- After GA, we may swap the legacy out and the data root keeps the
  legacy name forever.

**Refs.** [`OPEN_QUESTIONS.md Q1`](../OPEN_QUESTIONS.md), [`09-persistence.md`](09-persistence.md).

---

## D-004 — Adopt shadcn/ui + Radix primitives

**Date.** 2026-05-06.

**Decision.** Install shadcn/ui from day one (M0). Use `<Dialog />`,
`<Toast />`, `<Tabs />`, `<Select />`, `<Tooltip />`, `<Popover />`,
`<AlertDialog />` from there for every modal/dialog/toast/dropdown.

**Why.**
- pgdp-prep's spec mentions shadcn but the code uses raw Tailwind on
  raw HTML. Closes the divergence.
- The word-edit dialog has 8 distinct modal behaviours (focus trap,
  Escape, Apply/Reset, drag-erase, marker click, nudge grid, tag
  chips, multi-section layout) — raw Tailwind loses to Radix from
  minute one.
- Accessibility (focus trap, Escape, ARIA) for free.

**Alternatives considered.**
- Pure Tailwind (pgdp-prep's path). Rejected: too much boilerplate
  for the dialog count.
- Radix directly. Rejected: shadcn's copy-paste pattern lets us adapt
  styles per-component without forks.
- Headless UI. Rejected: smaller component set than Radix; less
  ecosystem.

**Refs.** [`OPEN_QUESTIONS.md Q12`](../OPEN_QUESTIONS.md), [`03-frontend.md`](03-frontend.md) §11.

---

## D-005 — `auth=none` only for v1, but keep the `IAuth` Protocol

**Date.** 2026-05-06.

**Decision.** Wire `IAuth` adapter Protocol with `none_` impl;
defer JWT/PKCE adapters indefinitely.

**Why.**
- Single-user use case. JWT pre-mature.
- Cheap to keep the seam; saves a refactor when (if) we go multi-tenant.

**Refs.** [`OPEN_QUESTIONS.md Q2`](../OPEN_QUESTIONS.md), [`02-backend.md`](02-backend.md) §7.

---

## D-006 — Hybrid sync/SSE for long jobs

**Date.** 2026-05-06.

**Decision.** Single-page Reload OCR uses SSE (it's slow). Page-scope
Refine + Save Project + Export use SSE. All other mutations are
synchronous JSON over HTTP.

**Why.**
- Single-page edits should feel snappy with optimistic updates.
- Long-running jobs need progress feedback.
- Mirrors pgdp-prep's job-runner pattern; avoids per-mutation SSE
  overhead.

**Refs.** [`OPEN_QUESTIONS.md Q3`](../OPEN_QUESTIONS.md), [`02-backend.md`](02-backend.md) §11.

---

## D-007 — Konva for canvas, raw HTML for everything else

**Date.** 2026-05-06.

**Decision.** Use `react-konva` for the page-image viewport and the
word-edit-dialog image. Use plain HTML/CSS + shadcn for everything
else.

**Why.**
- Konva is mature, has solid drag handles + transformer.
- pgdp-prep already uses it — no new dependency cost.
- Plain HTML for the word-match view is faster to render and lets
  React reconciliation diff at the cell level.

**Risks.**
- Konva DOM-backed Layer with ~600 word rects per page may be slow.
  Mitigation: profile in M4; fall back to single-canvas paint if
  needed.

**Refs.** [`OPEN_QUESTIONS.md Q6`](../OPEN_QUESTIONS.md), [`04-image-viewport.md`](04-image-viewport.md) §7.

---

## D-008 — Drop CodeMirror for plain `<textarea>`

**Date.** 2026-05-06.

**Decision.** OCR + GT plaintext tabs use plain `<textarea readOnly>`
with monospace CSS. Drop CodeMirror.

**Why.**
- The legacy uses CodeMirror's basic editor without syntax
  highlighting / line numbers — feature we don't need.
- Smaller bundle.
- React state for big strings is fine.

**Refs.** [`OPEN_QUESTIONS.md Q8`](../OPEN_QUESTIONS.md), [`05-word-matches.md`](05-word-matches.md) §1.

---

## D-009 — Adopt the keyboard-shortcut wishlist for v1

**Date.** 2026-05-06.

**Decision.** Implement the full hotkey wishlist from
`pd-ocr-labeler/docs/review-notes/2026-05-06-keyboard-shortcuts-coverage.md`
in v1. Use `react-hotkeys-hook`.

**Why.**
- Migrating the UI is a one-time chance to fix the keyboard story.
- The legacy 5 keybindings are preserved; the new ones are additive.

**Refs.** [`OPEN_QUESTIONS.md Q10`](../OPEN_QUESTIONS.md), [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md).

---

## D-010 — Match legacy URL grammar exactly

**Date.** 2026-05-06.

**Decision.** Use `/`, `/project/{id}`, `/project/{id}/page/{n}` (1-based)
for SPA routes, byte-identical to legacy.

**Why.**
- The driver agent depends on this URL shape.
- Diverging to `/projects/{id}/pages/{idx0}` (pgdp-prep convention)
  would force a coordinated driver-agent update.

**Refs.** [`OPEN_QUESTIONS.md Q19`](../OPEN_QUESTIONS.md), [`13-driver-contract.md`](13-driver-contract.md) §1.

---

## D-011 — Single in-process job runner; no SQLite

**Date.** 2026-05-06.

**Decision.** Jobs are stored in a `dict[str, Job]` in memory. No
SQLite jobs table. Server restart drops in-flight jobs.

**Why.**
- Single-user, single-process. SQLite jobs in pgdp-prep exist for
  multi-tenant + restart-resilience; we have neither requirement.
- The on-disk envelope is the durable record. Job runs are
  reconstructable by re-running.

**Trade-offs.**
- Crashing during a long Save Project loses the in-flight progress.
  The completed pages are still saved.

**Refs.** [`02-backend.md`](02-backend.md) §11, [`OPEN_QUESTIONS.md Q3`](../OPEN_QUESTIONS.md).

---

## D-012 — Single-process backend with per-project asyncio.Lock

**Date.** 2026-05-06.

**Decision.** All page mutations serialize per project. Two
simultaneous PUT requests to the same project block on a lock; the
second sees the first's result.

**Why.**
- Cleaner than reasoning about partial mutation state.
- Two-tab editing on the same page works because the lock guarantees
  ordering.

**Trade-offs.**
- Latency for two simultaneous edits doubles. Acceptable for
  single-user.

**Refs.** [`02-backend.md`](02-backend.md) §12.

---

## D-013 — Filesystem image cache via StaticFiles, no IStorage abstraction

**Date.** 2026-05-06.

**Decision.** `<cache_root>/page-images/` is mounted at
`/image-cache/` via FastAPI `StaticFiles(directory=...)`. No
storage-adapter abstraction for the image cache (even though we have
`IStorage` for envelopes).

**Why.**
- The labeler is a desktop app. S3-backed image cache would be
  meaningless for the v1 deploy shape.
- `IStorage` is still in place for envelopes — that abstraction earns
  its keep on labeled-projects writes.

**Risks.**
- If we ever multi-host the labeler, we need to introduce a real
  IStorage seam for the cache. Re-evaluate then.

**Refs.** [`OPEN_QUESTIONS.md Q5`](../OPEN_QUESTIONS.md), [`02-backend.md`](02-backend.md) §10.

---

## D-014 — Preserve every legacy `data-testid`

**Date.** 2026-05-06.

**Decision.** Every interactive element in the SPA carries the same
`data-testid` as the legacy labeler, exactly. New elements get new
testids; no testid is renamed.

**Why.**
- The driver agent (`pd-ocr-labeler-driver`) operates the UI through
  `data-testid` selectors. Preserving them keeps the driver agent
  working without code changes.
- The browser-test fixtures from the legacy port directly to
  Playwright e2e.

**Refs.** [`13-driver-contract.md`](13-driver-contract.md).

---

## D-015 — OpenAPI drift gate in CI

**Date.** 2026-05-06.

**Decision.** CI re-runs `make openapi-export` and fails on
`git diff --exit-code` against `frontend/src/api/types.ts` and
`frontend/openapi.json`.

**Why.**
- Closes the pgdp-prep drift gap explicitly noted in the architecture
  extract (section 4 "When this regenerates").
- Forces frontend/backend sync.

**Refs.** [`14-testing.md`](14-testing.md) §7.

---

## D-016 — `pd_ocr_labeler.user_page` v2.1 byte-equivalent reads + writes

**Date.** 2026-05-06.

**Decision.** SPA reads and writes the legacy v2.1 envelope schema
byte-for-byte. The legacy `payload.word_attributes` legacy 5-bool
side-channel is preserved on read AND write.

**Why.**
- Round-trip compatibility with the legacy. A user can save in SPA
  and re-open in legacy.
- The 5-bool side-channel was a backward-compat hack in legacy; we
  inherit it because dropping it would break older saves silently.

**Refs.** [`09-persistence.md`](09-persistence.md), [`01-data-models.md`](01-data-models.md) §3.

---

## D-017 — Server-side selection state, mirrored optimistically on the client

**Date.** 2026-05-06.

**Decision.** The canonical `Selection` lives in `PageState` on the
backend. Two tabs viewing the same page see identical
toolbar-disabled states.

**Why.**
- Disabled-state computation depends on selection cardinality. Two
  tabs differing on this would be confusing.
- Client-side optimistic updates make it feel snappy.

**Trade-offs.**
- Each viewport drag posts to the backend. Network chatter increases.
  Mitigation: debounce drag-move events.

**Refs.** [`04-image-viewport.md`](04-image-viewport.md) §4.1, [`06-toolbar-actions.md`](06-toolbar-actions.md) §5.

---

## D-018 — Full IOCREngine adapter axis (`local_doctr | modal | shared_container`)

**Date.** 2026-05-06.

**Decision.** Adopt pgdp-prep's full GPU/OCR adapter axis. Ship
`local_doctr` impl in v1; add `modal` and `shared_container`
Protocols + stubs (NotImplementedYet) so the seam is real, not
theoretical. Supersedes the relevant part of D-007 only insofar as
the OCR adapter is concerned.

**Why.**
- User answer to Q4 was **(B)**: full adapter axis like pgdp-prep.
- The labeler will eventually want off-machine GPU for large books;
  baking the seam now is cheaper than retrofitting.

**Implications.**
- M3 needs to wire all three Protocol stubs in `adapters/ocr/`. Only
  `local_doctr` works; the others raise `NotImplementedYet` if
  selected.
- `Settings.ocr_engine` becomes `Literal["local_doctr", "modal", "shared_container"]`.
- Modal adapter brings the `[modal]` extra dep (lazy-imported).

**Refs.** [`OPEN_QUESTIONS.md Q4`](../OPEN_QUESTIONS.md), [`02-backend.md`](02-backend.md) §1, §7.

---

## D-019 — Image cache via `IStorage` adapter pattern, filesystem-only impl in v1

**Date.** 2026-05-06.

**Decision.** Image cache is keyed by `IStorage` keys; `GET /image-cache/{key:path}`
serves via the storage adapter. Ship filesystem impl only;
`s3` adapter is `NotImplementedYet` but its Protocol exists.
Supersedes D-013.

**Why.**
- User answer to Q5 was **(B)**: storage adapter pattern, but S3 not
  implemented yet.
- Same seam-vs-implementation philosophy as D-005 / D-018.

**Implications.**
- `<cache>/page-images/` is no longer mounted via `StaticFiles`; it's
  served through the storage adapter's `get_bytes`.
- Per-image-type filename layout unchanged.
- `s3` adapter raises `NotImplementedYet` — same shape as `modal`
  OCR engine.

**Refs.** [`OPEN_QUESTIONS.md Q5`](../OPEN_QUESTIONS.md), [`02-backend.md`](02-backend.md) §10, [`09-persistence.md`](09-persistence.md) §4.

---

## D-020 — Defer Konva-vs-canvas decision to M4 with research subagent

**Date.** 2026-05-06.

**Decision.** Spec 04 documents the trade-offs. The actual choice
between Konva and raw canvas is deferred to a research-subagent pass
at the start of M4, against real labeled-data perf measurements.
Default-of-record: raw canvas (per user answer **B**), but Konva is
acceptable if research shows Konva handles 600 word rects per page
without measurable lag.

**Why.**
- User answered **(B)** raw canvas but acknowledged "delegate to
  subagent research tool to determine best method here."
- Premature commitment risks two months of building on a wrong stack.

**Implications.**
- Spec 04 lists both options with implementation deltas.
- M4 has a "research spike" sub-task before component implementation
  begins.

**Refs.** [`OPEN_QUESTIONS.md Q6`](../OPEN_QUESTIONS.md), [`04-image-viewport.md`](04-image-viewport.md), [`16-milestones.md`](16-milestones.md) M4.

---

## D-021 — UI prefs in localStorage; future per-user persistence

**Date.** 2026-05-06.

**Decision.** Per-browser UI prefs (filter toggle, layer visibility,
splitter, zoom level, selection mode) live in `localStorage` via
`zustand/middleware/persist`. Add a future-roadmap item to migrate
these to a per-user backend store when multi-user lands.

**Why.**
- User answered **(B)** plus "UI prefs probably should get saved per
  user later".

**Implications.**
- v1: `usePrefsStore` persists to `localStorage`.
- Future: when auth lands (D-005 follow-up), introduce
  `GET/PUT /api/user/prefs` and migrate the store.

**Refs.** [`OPEN_QUESTIONS.md Q9`](../OPEN_QUESTIONS.md), [`03-frontend.md`](03-frontend.md) §6.

---

## D-022 — Adopt the keyboard wishlist + plan a "full keyboard editing" milestone

**Date.** 2026-05-06.

**Decision.** Same as D-009 but with addition: identify additional
hotkeys for full keyboard-driven editing as a roadmap milestone (M9.5
or later).

**Why.**
- User answered "follow recommendation, identify additional hotkeys
  for full keyboard-driven editing in a roadmap/spec item".

**Implications.**
- Spec 12 ships the wishlist for v1.
- Spec 16 gets a new entry: M9.5 — "Full keyboard-driven editing
  audit" (post-GA polish).

**Refs.** [`OPEN_QUESTIONS.md Q10`](../OPEN_QUESTIONS.md), [`12-hotkeys-a11y.md`](12-hotkeys-a11y.md), [`16-milestones.md`](16-milestones.md).

---

## D-023 — Multi-tab on same page: last-writer-wins, plan optimistic locking later

**Date.** 2026-05-06.

**Decision.** v1 ships option **(A)**: same-project + same-page edits
across tabs converge via last-writer-wins on autosave. Plan optimistic
locking for multi-user phase.

**Why.**
- User answered "follow recommendation, multi-user will need some
  form of optimistic locking?".

**Implications.**
- v1: no version vector; the backend's `asyncio.Lock` per project
  serializes writes; concurrent reads always see the latest.
- Multi-user follow-up (when D-005 expands): introduce a `version`
  field on `PageRecord` + `If-Match`-style optimistic concurrency.

**Refs.** [`OPEN_QUESTIONS.md Q11`](../OPEN_QUESTIONS.md), [`02-backend.md`](02-backend.md) §12.

---

## D-024 — `pd-png-optimizer` not used by SPA

**Date.** 2026-05-06.

**Decision.** SPA does NOT depend on `pd-png-optimizer`. Q13
resolved.

**Why.**
- User: "No, labeler won't use it."

**Refs.** [`OPEN_QUESTIONS.md Q13`](../OPEN_QUESTIONS.md).

---

## D-025 — Ligature / long-s normalization moves to pd-book-tools

**Date.** 2026-05-06.

**Decision.** The SPA ships **no** ligature/long-s normalization in
v1 (matches legacy). Configurable normalization is designed in
**pd-book-tools** (`pd_book_tools.text.normalize`) and consumed
optionally by pd-ocr-cli (export/output) and pd-prep-for-pgdp
(per-package output). Default everywhere: keep Unicode glyphs as-is
in OCR output. Normalization is opt-in.

**Why.**
- User answer to Q14: "These should be configurable. Unicode glyphs
  exist for long S and ligature. We should default to glyphs with
  optional additional GT matching logic and normalization in output,
  not in labeling. Delegate to pd-ocr-cli, pgdp-prep, pd-book-tools
  agents to note this as something to add in the roadmap for those
  (likely living in pd-book-tools)."
- Keeping the SPA out of normalization preserves OCR fidelity in the
  labeled artefact.

**Implications.**
- New spec [`18-text-normalization.md`](18-text-normalization.md)
  documents the design.
- Three peer-repo agents (pd-book-tools, pd-ocr-cli, pd-prep-for-pgdp)
  add roadmap entries — delegated 2026-05-06.
- The labeler's matches view *can* opt into normalization-aware GT
  comparison so `ſhall` matches `shall` as exact, without modifying
  either string. Default off in v1; toggle exposed in M9 polish.

**Refs.** [`OPEN_QUESTIONS.md Q14`](../OPEN_QUESTIONS.md), [`18-text-normalization.md`](18-text-normalization.md).

---

## D-026 — Refine-bbox refactor delegated to pd-book-tools roadmap

**Date.** 2026-05-06.

**Decision.** v1 SPA reuses pd-book-tools APIs as-is. The
`bbox.refine_robust(...)` consolidation is a pd-book-tools roadmap
item, delegated 2026-05-06. Same as D-007 + Q15 recommendation.

**Refs.** [`OPEN_QUESTIONS.md Q15`](../OPEN_QUESTIONS.md), [`16-milestones.md`](16-milestones.md) §Cross-cutting.

---

## D-027 — DocTR export uses the existing job runner

**Date.** 2026-05-06.

**Decision.** Export endpoint queues a Job and reports progress via
SSE — same shape as Reload OCR (page) and Refine Bboxes (page).
The user noted: "don't we have a 'jobs' possibly available in our
new spec?" — yes, see [`02-backend.md`](02-backend.md) §11.

**Refs.** [`OPEN_QUESTIONS.md Q16`](../OPEN_QUESTIONS.md), [`10-export.md`](10-export.md), [`02-backend.md`](02-backend.md) §11.

---

## D-028 — Devcontainer optional; Makefile is the canonical onboarding

**Date.** 2026-05-06.

**Decision.** Don't depend on the workspace devcontainer. The
canonical onboarding is `make setup` (uv sync + npm install +
pre-commit + playwright install). Devcontainer users get a hint
that the same Make targets work; they're not required.

**Why.**
- User: "not everyone may be using dev container, we should follow
  the other makefile setup/dev that allows for developer to manage
  their env or us to 'help'".

**Refs.** [`OPEN_QUESTIONS.md Q17`](../OPEN_QUESTIONS.md), [`15-deployment-dev.md`](15-deployment-dev.md) §11.

---

## D-029 — Auto-rotation: manual buttons + project-load auto-pass + GT-best-match heuristic

**Date.** 2026-05-06.

**Decision.** Ship both **(B)** manual `Rotate 90° CW/CCW` buttons in
PageActions AND **(C)** an auto-rotation pass at project load (with
toggle to disable). When ground truth is present for a page, the
auto-rotate uses **GT-best-match rotation**: try 0/90/180/270, pick
the rotation whose OCR output has the highest fuzz score against the
GT. Indicator UI shows rotation state (e.g. badge "↻ auto" near page
name).

**Why.**
- User answer to Q18: "yes, we should enable both B and C and
  indicate auto-rotated. We should enhance auto-rotate with GT
  best-match rotation possibly too."

**Implications.**
- New spec [`19-auto-rotation.md`](19-auto-rotation.md).
- M9.x or M10 milestone (post-GA enhancement).
- `PageRecord` gains a `rotation_degrees: int = 0` field; persisted
  in the envelope (via additive v2.2 schema bump? — see Q-A1 below).
- Manual rotate button POST `/api/projects/{id}/pages/{idx}/rotate {degrees: 90 | -90 | 180}`.

**Refs.** [`OPEN_QUESTIONS.md Q18`](../OPEN_QUESTIONS.md), [`19-auto-rotation.md`](19-auto-rotation.md), [`08-page-actions.md`](08-page-actions.md).

---

## D-030 — URL grammar: pgdp-prep convention with disambiguating sub-routes

**Date.** 2026-05-06.

**Decision.** Adopt pgdp-prep convention `/projects/{id}/...` (plural)
with two explicit page-addressing sub-routes:

- `/projects/{id}/pages/index/{idx0}` — 0-based, programmatic.
- `/projects/{id}/pages/pageno/{n}` — 1-based, human-friendly.
- `/projects/{id}/pages/{n}` (no sub-route) → 301 redirect to the
  1-based form (the most common bookmark / driver default).

Legacy paths get **301 redirects**:

- `/project/{id}` → `/projects/{id}`
- `/project/{id}/page/{n}` → `/projects/{id}/pages/pageno/{n}`

Default canonical URL emitted by the SPA: the `pageno/{n}` form (human-friendly).

**Why.**
- User answer to Q19: "driver hasn't been run yet. This is ok to
  change and match pgdp-prep convention, but it might confuse someone
  using URL, could we do something like pages/index/{idx0} and
  pages/pageno/{idx0} and redirect pages/{0} to the pageno?"
- Sub-routes disambiguate index vs pageno cleanly.
- Plural matches pgdp-prep.

**Implications.**
- Driver-contract spec heavily revised.
- M2 router supports all three forms + redirects.
- `routes.ts` exposes both `buildPageIndexUrl` and `buildPageNumberUrl`.

**Refs.** [`OPEN_QUESTIONS.md Q19`](../OPEN_QUESTIONS.md), [`13-driver-contract.md`](13-driver-contract.md) §1, [`03-frontend.md`](03-frontend.md) §3.

---

## D-031 — Auto-open browser tab with `--no-browser` opt-out

**Date.** 2026-05-06. Same as D-006 sibling. Shipped per Q20
recommendation.

**Refs.** [`OPEN_QUESTIONS.md Q20`](../OPEN_QUESTIONS.md), [`02-backend.md`](02-backend.md) §2.

---

## D-032 — Auto-rotation envelope: additive v2.2 with legacy verification

**Date.** 2026-05-07. Resolves Q-A1.

**Decision.** Bump `UserPageEnvelope` to v2.2 by adding
`source.rotation_degrees: int = 0` and
`source.rotation_source: Literal["none","auto","manual"] = "none"`.
Writers continue to emit `version: "2.1"` when rotation state is
default so the common-case file remains byte-identical to legacy.
Writers emit `version: "2.2"` only when rotation state is non-default.
Verify legacy's `Source` model tolerates additive fields before the
first v2.2 file is written; if legacy rejects, fall back to sidecar
`<project>_<page:03d>.rotation.json` (Q-A1 option B) with auto-cleanup
on next legacy save.

**Refs.** [`OPEN_QUESTIONS.md Q-A1`](../OPEN_QUESTIONS.md), [`01-data-models.md`](01-data-models.md) §3, [`19-auto-rotation.md`](19-auto-rotation.md) §Persistence.

---

## D-033 — Q14 normalization toggle: project-level OCR config

**Date.** 2026-05-07. Resolves Q-A2.

**Decision.** Adopt option (A): the "Normalize for GT matching"
toggle lives in the OCR config modal and persists in `OCRConfig`.
Whole-project scope; books are typographically homogeneous within
themselves, so per-page toggling is unnecessary churn.

**Refs.** [`OPEN_QUESTIONS.md Q-A2`](../OPEN_QUESTIONS.md), [`18-text-normalization.md`](18-text-normalization.md) §Implementation.

---

## D-034 — Auto-rotation indicator UI: separate badge + tooltip

**Date.** 2026-05-07. Resolves Q-A3.

**Decision.** Adopt option (B): a separate rotation badge next to the
source badge (`[LABELED] [↻90 auto]`). Distinct concept from source
provenance gets a distinct pill. Tooltip on the badge surfaces
`rotation_source` ("auto" vs "manual"). Per the user's amendment, the
manual-rotation button itself also carries a tooltip explaining the
current rotation state so users hovering the button see the same info
without having to find the badge.

**Refs.** [`OPEN_QUESTIONS.md Q-A3`](../OPEN_QUESTIONS.md), [`19-auto-rotation.md`](19-auto-rotation.md) §UI, [`13-driver-contract.md`](13-driver-contract.md).

---

## D-035 — Legacy URL redirects use 301 Moved Permanently

**Date.** 2026-05-07. Resolves Q-A4.

**Decision.** Use `301` (not `308`) for `/project/{id}` →
`/projects/{id}` and peer redirects from D-030. SPA routes are
GET-only, so 308's method-preservation guarantee buys nothing here;
301 has the broadest support across older clients and crawlers.

**Refs.** [`OPEN_QUESTIONS.md Q-A4`](../OPEN_QUESTIONS.md), [`13-driver-contract.md`](13-driver-contract.md) §1.

---

## D-036 — Frontend toolchain via mise

**Date.** 2026-05-07. Resolves Q-A8.

**Decision.** Node 24 is provided via `mise` per `mise.toml`. Once
`mise install` has run in the devcontainer (or a developer's shell),
`npm ci` and the rest of the `make frontend-*` targets resolve cleanly
without further bootstrapping. The `make _npm` macro's `mise exec` →
PATH fallback stays in place so non-mise environments also work, but
mise is the canonical path. The previously-floated
`ghcr.io/devcontainers/features/node:1` devcontainer feature is
**superseded** — mise is the workspace-wide pin and adding a second
Node source would diverge from `mise.toml`. M1.h frontend acceptance
clauses are unblocked.

**Refs.** [`OPEN_QUESTIONS.md Q-A8`](../OPEN_QUESTIONS.md), [`15-deployment-dev.md`](15-deployment-dev.md) §10–11.

---

## Pending decisions

See [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) for any sub-questions
still open.

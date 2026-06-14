# 17 — Architecture Decisions Log

> **Status**: Active
> **Last updated**: 2026-05-14
> **Spec-Issue**: pdomain/pdomain-ocr-labeler-spa#38

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

**Refs.** [`02-backend.md`](../docs/architecture/02-backend.md) §2.

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

**Refs.** [`00-overview.md`](../docs/architecture/00-overview.md) §Tech stack.

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

**Alternatives considered.**

- New `pdomain-ocr-labeler-spa/` data root, separate from the legacy.
  Rejected: users mid-migration would lose access to existing labels
  until they ran an explicit migration script.
- Copy-on-first-open: read legacy root, write to new root. Rejected:
  creates two live copies that diverge; the pidfile approach is
  simpler and avoids the dual-copy problem.

**Refs.** [`OPEN_QUESTIONS.md Q1`](../OPEN_QUESTIONS.md), [`09-persistence.md`](../docs/architecture/09-persistence.md).

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

**Refs.** [`OPEN_QUESTIONS.md Q12`](../OPEN_QUESTIONS.md), [`03-frontend.md`](../docs/architecture/03-frontend.md) §11.

---

## D-005 — `auth=none` only for v1, but keep the `IAuth` Protocol

**Date.** 2026-05-06.

**Decision.** Wire `IAuth` adapter Protocol with `none_` impl;
defer JWT/PKCE adapters indefinitely.

**Why.**

- Single-user use case. JWT pre-mature.
- Cheap to keep the seam; saves a refactor when (if) we go multi-tenant.

**Alternatives considered.**

- Full JWT auth from day one. Rejected: over-engineering for a
  single-user desktop tool; adds key-management burden with no user benefit.
- No `IAuth` seam at all. Rejected: the Protocol costs nothing now and
  avoids a large refactor if auth ever lands.

**Refs.** [`OPEN_QUESTIONS.md Q2`](../OPEN_QUESTIONS.md), [`02-backend.md`](../docs/architecture/02-backend.md) §7.

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

**Alternatives considered.**

- WebSocket for all real-time updates. Rejected: full duplex not needed;
  SSE is simpler to implement and test for server-push-only jobs.
- Polling for long jobs. Rejected: polling adds latency and wastes
  bandwidth; SSE gives instant progress without client hammering.
- Pure async HTTP with `202 Accepted` + subsequent GET. Rejected:
  requires extra round-trips; SSE is cleaner for streaming progress.

**Refs.** [`OPEN_QUESTIONS.md Q3`](../OPEN_QUESTIONS.md), [`02-backend.md`](../docs/architecture/02-backend.md) §11.

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

**Alternatives considered.**

- Raw `<canvas>` for the image viewport from the start. Rejected for
  M1–M3: Konva's transformer and drag handles reduce boilerplate
  significantly; we defer the raw-canvas option to M4 research
  (see D-020).
- CSS-positioned `<div>` overlays for word bounding boxes. Rejected:
  accurate sub-pixel transforms and drag handles require canvas-level
  control; DOM overlay at 600 elements stresses layout/reflow.
- SVG overlays. Rejected: SVG at that element count has similar
  performance concerns as DOM; Konva already in the dep tree via
  pgdp-prep.

**Refs.** [`OPEN_QUESTIONS.md Q6`](../OPEN_QUESTIONS.md),
[`04-image-viewport.md`](../docs/architecture/04-image-viewport.md) §7.

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

**Alternatives considered.**

- Keep CodeMirror. Rejected: adds ~200 KB to the bundle for zero UX
  benefit; the plain-text tabs are read-only anyway.
- Use Monaco editor (VS Code engine). Rejected: even heavier bundle;
  designed for code editing, not plain OCR text display.

**Refs.** [`OPEN_QUESTIONS.md Q8`](../OPEN_QUESTIONS.md),
[`05-word-matches.md`](../docs/architecture/05-word-matches.md) §1.

---

## D-009 — Adopt the keyboard-shortcut wishlist for v1

**Date.** 2026-05-06.

**Decision.** Implement the full hotkey wishlist from
`pd-ocr-labeler/docs/review-notes/2026-05-06-keyboard-shortcuts-coverage.md`
in v1. Use `react-hotkeys-hook`.

**Why.**

- Migrating the UI is a one-time chance to fix the keyboard story.
- The legacy 5 keybindings are preserved; the new ones are additive.

**Alternatives considered.**

- Defer the keyboard wishlist to a post-GA milestone. Rejected: the
  migration is the natural moment to close the gap; deferring means
  shipping a regression relative to power-user expectations.
- Raw `addEventListener` / `useEffect` for keybindings. Rejected:
  `react-hotkeys-hook` handles scope/focus management and chord
  sequences; rolling bespoke hotkey logic is error-prone.

**Refs.** [`OPEN_QUESTIONS.md Q10`](../OPEN_QUESTIONS.md),
[`12-hotkeys-a11y.md`](../docs/architecture/12-hotkeys-a11y.md).

---

## D-010 — Match legacy URL grammar exactly

**Date.** 2026-05-06.

**Decision.** Use `/`, `/project/{id}`, `/project/{id}/page/{n}` (1-based)
for SPA routes, byte-identical to legacy.

**Why.**

- The driver agent depends on this URL shape.
- Diverging to `/projects/{id}/pages/{idx0}` (pgdp-prep convention)
  would force a coordinated driver-agent update.

**Alternatives considered.**

- Use pgdp-prep plural convention from day one. Rejected: would
  immediately break the Playwright driver without a coordinated update.
- Use 0-based indices. Rejected: the legacy and human-visible bookmarks
  all use 1-based; changing would confuse users comparing URLs.

**Refs.** [`OPEN_QUESTIONS.md Q19`](../OPEN_QUESTIONS.md),
[`13-driver-contract.md`](../docs/architecture/13-driver-contract.md) §1.

*Note: superseded by D-030, which adopts pgdp-prep plural convention with legacy 301 redirects.*

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

**Alternatives considered.**

- SQLite jobs table (same as pgdp-prep). Rejected: adds a migration
  layer and a second persistence file for a single-user tool that
  never needs restart-resilient job tracking.
- Redis as a job store. Rejected: external process dependency for a
  desktop tool; overkill for the single-user, single-process shape.

**Refs.** [`02-backend.md`](../docs/architecture/02-backend.md) §11, [`OPEN_QUESTIONS.md Q3`](../OPEN_QUESTIONS.md).

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

**Alternatives considered.**

- No locking at all; last writer always wins silently. Rejected: race
  windows are short but real; a fast double-click on two words could
  corrupt the saved envelope with a partial merge.
- Global server-wide lock across all projects. Rejected: unnecessarily
  serializes unrelated projects; per-project lock is the right
  granularity.

**Refs.** [`02-backend.md`](../docs/architecture/02-backend.md) §12.

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

**Alternatives considered.**

- Full `IStorage` abstraction for the image cache from day one.
  Rejected (at D-013 time): the desktop-only deploy shape made S3
  abstraction premature; StaticFiles mount is simpler and has no
  observable API difference.
- Serve images via a CDN or object-store URL embedded in API responses.
  Rejected: adds external network dependency; images are large and
  served from the local filesystem.

Note: D-013 was later superseded by D-019, which did add the storage
adapter for the image cache.

**Refs.** [`OPEN_QUESTIONS.md Q5`](../OPEN_QUESTIONS.md), [`02-backend.md`](../docs/architecture/02-backend.md) §10.

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

**Alternatives considered.**

- Use semantic role / aria-label selectors in tests. Rejected: the
  driver agent's selectors are already written against `data-testid`;
  renaming them requires a coordinated multi-repo update.
- Rename testids to match the new SPA component tree. Rejected: any
  rename breaks the driver agent immediately; old testids are stable
  identifiers, not implementation details.

**Refs.** [`13-driver-contract.md`](../docs/architecture/13-driver-contract.md).

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

**Alternatives considered.**

- Trust developers to run `make openapi-export` manually. Rejected:
  pgdp-prep had exactly this gap and accumulated silent drift.
- Generate types at frontend build time (not CI gate). Rejected:
  wouldn't catch drift that exists in the committed `openapi.json`
  between CI runs.

**Refs.** [`14-testing.md`](../docs/architecture/14-testing.md) §7.

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

**Alternatives considered.**

- Define a new v3.0 envelope schema, drop the 5-bool side-channel.
  Rejected: would break every existing `.json` save file; users mid-
  migration lose their labels.
- Strip the 5-bool side-channel on write, keep it on read. Rejected:
  round-tripping through the SPA would silently corrupt files that
  the legacy later re-opens.

**Refs.** [`09-persistence.md`](../docs/architecture/09-persistence.md),
[`01-data-models.md`](../docs/architecture/01-data-models.md) §3.

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

**Alternatives considered.**

- Pure client-side selection state with no backend sync. Rejected:
  toolbar disabled-state depends on selection cardinality; if each tab
  computes this locally, two tabs on the same page would show
  conflicting toolbar states, which is confusing.
- Backend selection state without optimistic updates (wait for server
  round-trip before re-rendering). Rejected: drag selection would feel
  laggy; optimistic updates give immediate visual feedback.

**Refs.** [`04-image-viewport.md`](../docs/architecture/04-image-viewport.md) §4.1,
[`06-toolbar-actions.md`](../docs/architecture/06-toolbar-actions.md) §5.

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

**Alternatives considered.**

- Ship only `local_doctr`; add other engines later when needed.
  Rejected: retrofitting a Protocol seam across existing callers is
  more expensive than stubbing it now; the user explicitly chose the
  full axis.
- Single `IOCREngine` class with conditional logic (`if engine ==
  "modal": ...`). Rejected: conditional branching in a monolithic class
  is harder to test than separate adapter impls behind a Protocol.

**Refs.** [`OPEN_QUESTIONS.md Q4`](../OPEN_QUESTIONS.md),
[`02-backend.md`](../docs/architecture/02-backend.md) §1, §7.

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

**Alternatives considered.**

- Keep D-013's `StaticFiles` mount and never expose a storage adapter
  for images. Rejected: the user chose option (B) — the seam is worth
  having even if S3 is not implemented.
- Implement both filesystem and S3 storage adapters immediately.
  Rejected: S3 is explicitly out of scope for v1 (D-042 deferred axis);
  shipping a stub is cheaper and keeps the adapter seam real.

**Refs.** [`OPEN_QUESTIONS.md Q5`](../OPEN_QUESTIONS.md),
[`02-backend.md`](../docs/architecture/02-backend.md) §10,
[`09-persistence.md`](../docs/architecture/09-persistence.md) §4.

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

**Alternatives considered.**

- Commit to Konva before M4 without a research spike. Rejected: user
  explicitly acknowledged uncertainty; premature commitment risks
  re-writing the viewport component if Konva proves too slow at 600
  word rects.
- Commit to raw canvas before M4. Rejected: the default-of-record
  is raw canvas (user answer B), but Konva may still be viable and
  worth confirming via measurement before discarding it.

**Refs.** [`OPEN_QUESTIONS.md Q6`](../OPEN_QUESTIONS.md),
[`04-image-viewport.md`](../docs/architecture/04-image-viewport.md),
[`16-milestones.md`](16-milestones.md) M4.

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

**Alternatives considered.**

- Server-side pref storage from day one (`config.yaml` or a prefs
  endpoint). Rejected: single-user tool; `localStorage` is sufficient
  and avoids an extra API surface and persistence file for v1.
- No pref persistence at all (reset to defaults on each load). Rejected:
  filter toggle, zoom level, and splitter position are frequent
  adjustments; losing them on every reload is a usability regression.

**Refs.** [`OPEN_QUESTIONS.md Q9`](../OPEN_QUESTIONS.md), [`03-frontend.md`](../docs/architecture/03-frontend.md) §6.

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

**Alternatives considered.**

- Ship only the 5 legacy hotkeys; defer the full wishlist entirely.
  Rejected: migration is the natural moment to close the gap;
  re-opening keyboard work post-GA costs more context-switching than
  doing it once.
- Ship the full wishlist and also complete the "full keyboard editing"
  audit in the same milestone. Rejected: scoping is already aggressive
  for v1; a dedicated M9.5 milestone is the right boundary.

**Refs.** [`OPEN_QUESTIONS.md Q10`](../OPEN_QUESTIONS.md),
[`12-hotkeys-a11y.md`](../docs/architecture/12-hotkeys-a11y.md), [`16-milestones.md`](16-milestones.md).

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

**Alternatives considered.**

- Optimistic locking with a `version` field from v1. Rejected: D-042
  deferred multi-user; adding version vectors now would ship untested
  complexity with no single-user benefit.
- WebSocket-based real-time page-state sync across tabs. Rejected:
  full-duplex WebSocket is heavier than needed; last-writer-wins via
  the asyncio.Lock is sufficient for single-user multi-tab.

**Refs.** [`OPEN_QUESTIONS.md Q11`](../OPEN_QUESTIONS.md), [`02-backend.md`](../docs/architecture/02-backend.md) §12.

---

## D-024 — `pd-png-optimizer` not used by SPA

**Date.** 2026-05-06.

**Decision.** SPA does NOT depend on `pd-png-optimizer`. Q13
resolved.

**Why.**

- User: "No, labeler won't use it."
- The labeler's job is OCR review, not image optimization; PNG
  optimization belongs in the upload/ingest pipeline, not the labeler.

**Alternatives considered.**

- Auto-optimize page images on project load to reduce memory.
  Rejected: user explicitly declined; the labeler doesn't own the
  pipeline step that produces the images.

**Refs.** [`OPEN_QUESTIONS.md Q13`](../OPEN_QUESTIONS.md).

---

## D-025 — Ligature / long-s normalization moves to pdomain-book-tools

**Date.** 2026-05-06.

**Decision.** The SPA ships **no** ligature/long-s normalization in
v1 (matches legacy). Configurable normalization is designed in
**pdomain-book-tools** (`pdomain_book_tools.text.normalize`) and consumed
optionally by pdomain-ocr-cli (export/output) and pdomain-prep-for-pgdp
(per-package output). Default everywhere: keep Unicode glyphs as-is
in OCR output. Normalization is opt-in.

**Why.**

- User answer to Q14: "These should be configurable. Unicode glyphs
  exist for long S and ligature. We should default to glyphs with
  optional additional GT matching logic and normalization in output,
  not in labeling. Delegate to pdomain-ocr-cli, pgdp-prep, pdomain-book-tools
  agents to note this as something to add in the roadmap for those
  (likely living in pdomain-book-tools)."
- Keeping the SPA out of normalization preserves OCR fidelity in the
  labeled artefact.

**Implications.**

- New spec [`18-text-normalization.md`](../docs/architecture/18-text-normalization.md)
  documents the design.
- Three peer-repo agents (pdomain-book-tools, pdomain-ocr-cli, pdomain-prep-for-pgdp)
  add roadmap entries — delegated 2026-05-06.
- The labeler's matches view *can* opt into normalization-aware GT
  comparison so `ſhall` matches `shall` as exact, without modifying
  either string. Default off in v1; toggle exposed in M9 polish.

**Alternatives considered.**

- Inline normalization directly in the SPA's GT matching logic. Rejected:
  the SPA would then own typography normalization that every downstream
  consumer also needs; pdomain-book-tools is the right library owner.
- Normalize OCR output on ingest (modify the stored labeled text).
  Rejected: destructive; labeled artefacts should preserve OCR fidelity
  so reviewers can see what the model actually produced.

**Refs.** [`OPEN_QUESTIONS.md Q14`](../OPEN_QUESTIONS.md),
[`18-text-normalization.md`](../docs/architecture/18-text-normalization.md).

---

## D-026 — Refine-bbox refactor delegated to pdomain-book-tools roadmap

**Date.** 2026-05-06.

**Decision.** v1 SPA reuses pdomain-book-tools APIs as-is. The
`bbox.refine_robust(...)` consolidation is a pdomain-book-tools roadmap
item, delegated 2026-05-06. Same as D-007 + Q15 recommendation.

**Why.**

- The refine-bbox logic lives in pdomain-book-tools; refactoring it inside
  the SPA would duplicate work and diverge from the shared library.
- Delegating to pdomain-book-tools means all consumers benefit from the
  improvement, not just the SPA.

**Alternatives considered.**

- Inline a bespoke `bbox.refine_robust` in the SPA. Rejected: code
  duplication; the SPA is not the right owner of image-processing
  geometry primitives.
- Block the SPA's M3 on the pdomain-book-tools refactor landing first.
  Rejected: the refactor is a nice-to-have; the existing API is
  sufficient for v1.

**Refs.** [`OPEN_QUESTIONS.md Q15`](../OPEN_QUESTIONS.md), [`16-milestones.md`](16-milestones.md) §Cross-cutting.

---

## D-027 — DocTR export uses the existing job runner

**Date.** 2026-05-06.

**Decision.** Export endpoint queues a Job and reports progress via
SSE — same shape as Reload OCR (page) and Refine Bboxes (page).
The user noted: "don't we have a 'jobs' possibly available in our
new spec?" — yes, see [`02-backend.md`](../docs/architecture/02-backend.md) §11.

**Why.**

- Export over a full project is a long-running operation; SSE progress
  is the only user-visible signal that work is happening.
- Reusing the existing job-runner avoids a second execution model; the
  in-memory `dict[str, Job]` is already the contract (D-011).

**Alternatives considered.**

- Synchronous blocking export endpoint. Rejected: a large project
  export could block the uvicorn thread for seconds; no progress
  feedback.
- A separate task queue (celery / arq). Rejected: single-user
  single-process; a second process adds deployment complexity for
  no benefit (D-011).

**Refs.** [`OPEN_QUESTIONS.md Q16`](../OPEN_QUESTIONS.md),
[`10-export.md`](../docs/architecture/10-export.md),
[`02-backend.md`](../docs/architecture/02-backend.md) §11.

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
- Mirrors pgdp-prep's onboarding model; keeps the two sibling repos
  consistent.

**Alternatives considered.**

- Make the devcontainer mandatory (all CI inside it). Rejected:
  forces contributors without VS Code / Docker to install extra
  tooling before seeing any output.
- Two separate onboarding paths: devcontainer and bare-metal.
  Rejected: doubles the maintenance surface; `make setup` works
  equally well inside a container or outside.

**Refs.** [`OPEN_QUESTIONS.md Q17`](../OPEN_QUESTIONS.md),
[`15-deployment-dev.md`](../docs/architecture/15-deployment-dev.md) §11.

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

- New spec [`19-auto-rotation.md`](../docs/architecture/19-auto-rotation.md).
- M9.x or M10 milestone (post-GA enhancement).
- `PageRecord` gains a `rotation_degrees: int = 0` field; persisted
  in the envelope (via additive v2.2 schema bump? — see Q-A1 below).
- Manual rotate button POST `/api/projects/{id}/pages/{idx}/rotate {degrees: 90 | -90 | 180}`.

**Alternatives considered.**

- Manual buttons only, no auto-rotation pass. Rejected: the user
  explicitly requested both (B and C); auto-rotation reduces manual
  work for uniformly mis-oriented scans.
- Auto-rotation only (no manual buttons). Rejected: auto-rotation
  heuristics can be wrong; manual override is necessary for edge cases
  where the GT-best-match heuristic fails.
- Auto-rotation using a dedicated orientation-detection model rather
  than GT-best-match. Rejected: requires an extra ML model dependency;
  GT-best-match is sufficient when ground truth is available and is
  cheaper to implement.

**Refs.** [`OPEN_QUESTIONS.md Q18`](../OPEN_QUESTIONS.md),
[`19-auto-rotation.md`](../docs/architecture/19-auto-rotation.md),
[`08-page-actions.md`](../docs/architecture/08-page-actions.md).

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

**Alternatives considered.**

- Keep legacy singular paths forever, never adopt pgdp-prep convention.
  Rejected: inconsistency across the two sibling apps makes the shared
  codebase harder to reason about; the driver hasn't run yet so the
  migration cost is low now.
- Adopt pgdp-prep convention immediately, with no redirects. Rejected:
  any existing bookmarks or driver scripts using the singular form
  would silently 404; 301 redirects preserve them at no ongoing cost.

**Refs.** [`OPEN_QUESTIONS.md Q19`](../OPEN_QUESTIONS.md),
[`13-driver-contract.md`](../docs/architecture/13-driver-contract.md) §1,
[`03-frontend.md`](../docs/architecture/03-frontend.md) §3.

---

## D-031 — Auto-open browser tab with `--no-browser` opt-out

**Date.** 2026-05-06.

**Decision.** On startup, `pd-ocr-labeler-ui` opens a browser tab
automatically (same behaviour as the legacy). A `--no-browser` flag
suppresses the auto-open for headless/CI contexts.

**Why.**

- Matches the legacy UX: the labeler is a one-command tool; the user
  should not need a separate step to open the UI.
- Mirrors pgdp-prep's auto-open pattern (`02-backend.md §2`).
- `--no-browser` is cheap to add and required for CI smoke tests and
  driver-agent headless use.

**Alternatives considered.**

- Never auto-open; always print the URL. Rejected: would regress the
  legacy UX; single-user tool should be point-and-click.
- Always auto-open with no opt-out. Rejected: breaks headless/CI
  runs; the driver agent needs `--no-browser`.

**Refs.** [`OPEN_QUESTIONS.md Q20`](../OPEN_QUESTIONS.md), [`02-backend.md`](../docs/architecture/02-backend.md) §2.

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

**Why.**

- Additive schema with a version bump preserves backward compat:
  legacy readers that ignore unknown fields continue to work for v2.1
  files; only non-default rotation state triggers v2.2.
- Keeping `version: "2.1"` for the common case (no rotation) means
  existing save files are never touched unless rotation is applied.

**Alternatives considered.**

- Always write v2.2 regardless of rotation state. Rejected: would
  make every saved file incompatible with strict legacy readers even
  for unchanged pages.
- Rotation sidecar only (no schema bump). Rejected: a separate sidecar
  file per page is messier to manage; additive envelope fields are the
  cleaner option if legacy tolerates them.

**Refs.** [`OPEN_QUESTIONS.md Q-A1`](../OPEN_QUESTIONS.md),
[`01-data-models.md`](../docs/architecture/01-data-models.md) §3,
[`19-auto-rotation.md`](../docs/architecture/19-auto-rotation.md) §Persistence.

---

## D-033 — Q14 normalization toggle: project-level OCR config

**Date.** 2026-05-07. Resolves Q-A2.

**Decision.** Adopt option (A): the "Normalize for GT matching"
toggle lives in the OCR config modal and persists in `OCRConfig`.
Whole-project scope; books are typographically homogeneous within
themselves, so per-page toggling is unnecessary churn.

**Why.**

- Books are typographically uniform — a long-s or ligature used on
  one page will appear throughout; a project-level toggle is
  sufficient granularity.
- Placing the toggle in the OCR config modal collocates it with the
  other OCR quality controls (model, confidence threshold).

**Alternatives considered.**

- Per-page normalization toggle. Rejected: adds per-page UI surface
  and storage overhead; books don't change typography mid-volume.
- Global application-level preference (not per-project). Rejected:
  different projects may use different historical scripts; project
  scope is the right isolation boundary.

**Refs.** [`OPEN_QUESTIONS.md Q-A2`](../OPEN_QUESTIONS.md),
[`18-text-normalization.md`](../docs/architecture/18-text-normalization.md) §Implementation.

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

**Why.**

- Rotation is a distinct dimension from labeling status; merging them
  into one badge conflates two independent concepts.
- The pill + tooltip pattern matches shadcn/ui conventions already
  used throughout the toolbar (D-004).

**Alternatives considered.**

- Embed rotation state into the existing source badge (e.g.
  `[LABELED ↻90]`). Rejected: conflates source provenance with
  geometric transform; each badge should have a single responsibility.
- Surface rotation state only in the button tooltip, no separate badge.
  Rejected: users who glance at the header need persistent visual
  confirmation of rotation without hovering.

**Refs.** [`OPEN_QUESTIONS.md Q-A3`](../OPEN_QUESTIONS.md),
[`19-auto-rotation.md`](../docs/architecture/19-auto-rotation.md) §UI,
[`13-driver-contract.md`](../docs/architecture/13-driver-contract.md).

---

## D-035 — Legacy URL redirects use 301 Moved Permanently

**Date.** 2026-05-07. Resolves Q-A4.

**Decision.** Use `301` (not `308`) for `/project/{id}` →
`/projects/{id}` and peer redirects from D-030. SPA routes are
GET-only, so 308's method-preservation guarantee buys nothing here;
301 has the broadest support across older clients and crawlers.

**Why.**

- The legacy routes are pure GET bookmarks; method preservation (the
  point of 308) is irrelevant.
- 301 is universally understood by browsers and HTTP clients; 308 is
  newer and less consistently cached.

**Alternatives considered.**

- Use 308 Permanent Redirect for stronger method guarantee. Rejected:
  the SPA has no POST routes at these legacy paths; 308 adds no value
  over 301 and risks compatibility with older clients.
- Use 302 Temporary Redirect. Rejected: the old paths are permanently
  deprecated; 302 would prevent browsers from updating cached
  bookmarks to the new canonical URL.

**Refs.** [`OPEN_QUESTIONS.md Q-A4`](../OPEN_QUESTIONS.md),
[`13-driver-contract.md`](../docs/architecture/13-driver-contract.md) §1.

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

**Why.**

- mise is already the workspace-wide runtime-version manager (Python
  3.13 is also pinned via `mise.toml`); using it for Node is
  consistent and avoids a second version-management tool.
- A devcontainer feature for Node would add a parallel Node source
  that could drift from the pinned version in `mise.toml`.

**Alternatives considered.**

- `ghcr.io/devcontainers/features/node:1` devcontainer feature.
  Rejected: a second Node source diverges from `mise.toml`; superseded
  by this decision.
- System Node from `apt`. Rejected: Node LTS in package repos often
  lags; users on non-devcontainer setups would get a different version.
- `.nvmrc` + nvm. Rejected: nvm is user-managed and not available in
  all CI environments; mise is already present as the workspace tool.

**Refs.** [`OPEN_QUESTIONS.md Q-A8`](../OPEN_QUESTIONS.md),
[`15-deployment-dev.md`](../docs/architecture/15-deployment-dev.md) §10–11.

---

## D-037 — ESLint flat config (`eslint.config.ts`) with typescript-eslint v8

**Date.** 2026-05-07. Resolves Q-A9.

**Decision.** Adopt option (A): a flat config at
`frontend/eslint.config.ts` using `typescript-eslint` v8 +
`@vitejs/plugin-react` recommended presets. `specs/16-milestones.md`
already names `eslint.config.ts` as an M0 file; this commits the
shape. The `lint` script in `frontend/package.json` is restored in the
same change that lands the config + devDeps so the M0 acceptance
clause "ESLint passes clean" becomes verifiable. The shape-pin test
in `tests/unit/test_frontend_config.py` flips from "if `lint` exists
then eslint must be installed" to "`lint` must exist".

**Why.**

- ESLint's legacy `.eslintrc.*` format is deprecated as of ESLint 9;
  flat config is the only supported path for new projects.
- `typescript-eslint` v8 ships a unified flat-config API that pairs
  cleanly with the existing `tsconfig.json`.

**Alternatives considered.**

- Legacy `.eslintrc.js` format. Rejected: deprecated and unsupported
  in ESLint 9+; a new repo should not start on a deprecated path.
- Biome as a combined linter + formatter. Rejected: Vite + shadcn
  tooling docs target ESLint; switching to Biome would require
  adapting the pgdp-prep scaffolding baseline and has less ecosystem
  coverage for React hooks rules.

**Refs.** [`OPEN_QUESTIONS.md Q-A9`](../OPEN_QUESTIONS.md), [`16-milestones.md`](16-milestones.md) §M0.

---

## D-038 — PyPI publishing deferred; ship via GitHub Releases + pd-index

**Date.** 2026-05-07. Resolves Q-A10.

**Decision.** Adopt option (A): publish wheels + sdists to GitHub
Releases only. `install.sh` / `install.ps1` already pull from the
Release; PyPI is not a hard requirement. Distribution will route
through the workspace's self-hosted PEP 503 index at
`pdomain/pdomain-index-pip` (consistent with other pd-* repos); the `release.yml` workflow stays
PyPI-token-free, and the existing release-workflow tests continue to
forbid `PYPI_TOKEN` references. OIDC trusted publishing (option B)
remains a future option but isn't being wired now.

**Why.**

- Consistent with every other pd-* repo's release strategy
  (workspace decision 2026-05-06).
- GitHub Releases do not require PyPI API tokens; no token management
  for a tool that is not yet public.
- `pdomain-index-pip` (self-hosted PEP 503) allows `pip install` from the org
  index without PyPI registration.

**Alternatives considered.**

- Publish directly to PyPI with OIDC trusted publishing. Rejected:
  not all pd-* repos are public yet; the pdomain-index-pip pattern is the
  agreed workspace standard; PyPI can be added later without breaking
  the existing install scripts.
- Manual wheel distribution (no release automation). Rejected: the
  release workflow already automates GitHub Releases; removing it
  would regress the distribution story.

**Refs.** [`OPEN_QUESTIONS.md Q-A10`](../OPEN_QUESTIONS.md),
[`15-deployment-dev.md`](../docs/architecture/15-deployment-dev.md) §release-pipeline.

---

## D-039 — `--log-level` CLI flag dropped; `-v/--verbose` is canonical

**Date.** 2026-05-07. Resolves Q-A13.

**Decision.** Adopt option (D): drop `--log-level` from the M1.g
flag set. Spec `15-deployment-dev.md §3` and `02-backend.md §3` name
`-v/--verbose` (count, 0–3) as the verbosity knob, mirroring legacy
`pd-ocr-labeler/cli.py:50-56`. `Settings` does not gain a `log_level`
field. If a real consumer (e.g. an external deployment doc literally
specifying `--log-level`) surfaces later, revisit with a concrete
shape — but the default rule is one verbosity flag, matching legacy.

**Refs.** [`OPEN_QUESTIONS.md Q-A13`](../OPEN_QUESTIONS.md),
[`15-deployment-dev.md`](../docs/architecture/15-deployment-dev.md) §3,
[`02-backend.md`](../docs/architecture/02-backend.md) §3.

---

## D-040 — Unhandled-exception traceback disclosure gated by `debug_unhandled_traceback` flag

**Date.** 2026-05-07. Resolves Q-A11 / pairs with B-51.
**Amended.** 2026-05-26 — default changed from `True` to `False` (F-003 / #408).

**Decision.** `Settings.debug_unhandled_traceback: bool = False`
(env `PDLABELER_DEBUG_UNHANDLED_TRACEBACK`). The 500 envelope emitted
from the `Exception` catch-all in `api/middleware/error_handler.py`
is flag-conditional:

- When `False` (default — secure): `details = null`, `message =
  "Internal server error"`. The exception text and traceback tail do
  NOT cross the API boundary. Full traceback is still emitted via
  `logger.exception(...)` server-side; correlation to the client-side
  envelope is via the `X-Request-ID` header (echoed in the response
  and stamped on every log line via `RequestIdFilter` per spec §9).
- When `True` (explicit opt-in for local dev / single-user-on-laptop):
  `details = traceback.format_exc().splitlines()[-3:]`. The `message`
  is still always `"Internal server error"` — only `details` expands.
  Browser-console triage works without server log access.

In both modes the server-side log emission is unchanged.

**Why default `False` (amendment from original `True`).** F-003 (#408)
identified that `message=str(exc)` exposed internal paths, env-specific
values, and sensitive exception text to any HTTP client. Even on a
single-user laptop the API may be reachable from the local network
(especially with wildcard CORS — see F-002). The safe default is to
never leak exception internals; a local dev who needs the detail can
set the env var once.

**Why a flag rather than always redact.** The `details` field (traceback
tail, NOT the exception message) may be legitimately surfaced to a
developer running a local instance. The flag gates only `details`; the
`message` is always the generic string regardless of flag value.

**Spec §8 amendment (security clause).** `02-backend.md §8` carries a
sub-clause naming the flag, the default, and the trade-off:

> The `Exception` catch-all always returns `{error: "internal_error",
> message: "Internal server error", details: null}` to the client.
> The full traceback is always emitted server-side via `logger.exception`.
> `Settings.debug_unhandled_traceback` (default `False`) gates only
> whether `details` is populated with the last 3 traceback lines —
> set `True` via `PDLABELER_DEBUG_UNHANDLED_TRACEBACK=true` for local
> dev triage. The message field is always the generic string.

**Refs.** [`OPEN_QUESTIONS.md Q-A11`](../OPEN_QUESTIONS.md),
[`02-backend.md`](../docs/architecture/02-backend.md) §3 (Settings field list) and §8
(error handling),
[`docs/archive/research/BUGS_FOUND.md` B-51](../docs/archive/research/BUGS_FOUND.md),
F-003 / GH #408.

---

## D-041 — `session_state.json` extras-tolerance with WARNING-level drift signal

**Date.** 2026-05-07. Resolves Q-A12 / pairs with B-58.

**Decision.** `SessionState.model_config` becomes
`ConfigDict(extra="ignore")` (the legacy `from_dict` semantic). When
the SPA reads a `session_state.json` containing keys outside the
known set (`schema_version`, `last_project_path`, `last_page_index`),
it logs the dropped keys at **WARNING** with the stable grep-able
substring `session_state_extras_dropped` and the dropped key names
in `extra=`. The user's last session is preserved; the operator gets
a loud-but-non-fatal signal.

**Why WARNING, not `info`.** Per the user's framing: an emission of
this log in a release that didn't coordinate a session_state shape
change is "*possible indication of library drift* in a release that
shouldn't have had it." That's the threshold at which an operator (or
release-time CI gate) wants to be paged, not the threshold at which a
debug-log noise filter eats it. WARNING is the closest stdlib level
to "soft fail, but loud."

**Why a stable substring (`session_state_extras_dropped`).** A
release CI step or operator can grep for it across structured/plain
log streams without parsing JSON. Stability is the contract — future
iters that change the human-readable wording must keep the substring
intact.

**Spec §6 amendment.** `09-persistence.md §6` (session_state.json)
grows the explicit reader contract:

> Readers MUST tolerate unknown keys per the D-003 forward-compat
> contract — the SPA and legacy share this file, and either may
> introduce additive fields without coordinating a release. Readers
> MUST log dropped keys at WARNING with the stable substring
> `session_state_extras_dropped` so an emission of the warning in a
> release that did not coordinate a session_state shape change is
> visible evidence of unintended SPA/legacy library drift.
>
> *Asymmetry note:* `UserPageEnvelope` (spec §11) keeps
> `extra="forbid"`. The asymmetry is deliberate: `UserPageEnvelope`
> has a versioned `schema_version` gate that session_state.json does
> not, and the envelope's strictness is the deliberate forward-compat
> circuit-breaker for that schema. session_state.json has no such
> gate and the legacy reader has historically been silent-drop, so
> the SPA matches that behaviour while still emitting an operator
> signal.

**Implementation pending.** Iter that lands the impl: flip
`core/persistence/session_state.py` `model_config`; add the WARNING
log in `load_session_state` after parse (compare parsed keys to the
known set); update the module docstring to cite spec §6 instead of
§11; pin with `test_session_state_load_ignores_unknown_keys` (loads a
JSON with an unknown key, asserts `SessionState` returned and unknown
key dropped) and `test_session_state_load_logs_warning_with_stable_substring`
(captures `caplog`, asserts WARNING level + substring +
dropped-key-name in `extra=`).

**Refs.** [`OPEN_QUESTIONS.md Q-A12`](../OPEN_QUESTIONS.md),
[`09-persistence.md`](../docs/architecture/09-persistence.md) §6 (session_state.json) — to
be amended; §11 (UserPageEnvelope) — kept strict per documented
asymmetry,
[`docs/archive/research/BUGS_FOUND.md` B-58](../docs/archive/research/BUGS_FOUND.md).

---

## D-042 — Postgres/managed-adapter axes deferred to far future (2026-05-07)

**Date.** 2026-05-07. Direct user directive on the /loop driver agent.

**Decision.** All adapter axes that imply a network-attached or multi-
user shape are **deferred to the far future**. The /loop must not pick
slices that build them out without explicit user re-authorisation. The
deferred axes are:

- **Auth.** Keep `IAuth` Protocol + `NoneAuth` impl only. No JWT, no
  PKCE, no session-cookie auth, no `verify` calls against a network
  identity provider. Reaffirms D-005.
- **Storage `s3`.** Protocol stays so the seam is real, but the impl
  stays `NotImplementedYet`. No boto3 dep, no S3 fixtures, no upload
  path. Reaffirms D-019.
- **Database / Postgres / SQLAlchemy.** No `database/` adapter axis,
  no Alembic, no ORM models, no async Postgres driver in `pyproject`,
  no `pg_*` env vars in `Settings`. Reaffirms 00-overview Non-goals
  ("Filesystem only — Single-user; no DB needed for v1").
- **Per-user prefs backend.** UI prefs stay in `localStorage` only;
  no `GET/PUT /api/user/prefs`. Reaffirms D-021.
- **Optimistic locking / version vector on `PageRecord`.** Single-
  process `asyncio.Lock` only; no `If-Match`, no `version` field.
  Reaffirms D-023.
- **Cloud-mode OCR.** `ModalOCR` and `SharedContainerOCR` stay
  `NotImplementedYet` stubs. Reaffirms D-018.

**Why.** User directive: "focus on getting local-mode functionality
working across main features first." The repo's milestone roadmap is
already structured this way (M1–M9 are all local-mode work), but the
spec body retains seams + future-facing prose that an autonomous /loop
could mistake for "near-term" work — particularly D-021's "future per-
user backend store", D-023's "Plan optimistic locking", D-019's
`s3` Protocol, and D-040's references to "any future managed/multi-
tenant shape". This ADR converts those from "soon" to "far future" so
slice picking stays bounded.

**What stays in scope (do NOT defer).** Local JSON-sidecar
persistence is **the active path** and is the kind of work to
prioritise:

- `session_state.json` (spec §6) — already shipped iter 44.
- `config.yaml` (spec §7) — pending; in scope.
- `ocr_config.json` carrier writeback (M3 slice 8c-iv+) — in scope;
  the `OCRConfigCarrier` is an in-process holder + filesystem sidecar,
  NOT a database row.
- `UserPageEnvelope` v2.1 read/write (M3) — in scope.
- Image cache via filesystem `IStorage` — in scope.

**Implications.**

- `s3` / `modal` / `shared_container` adapters keep their
  `NotImplementedYet` stubs but no further effort is spent on them.
- `auth` axis stays at `none_` only; the spec sections that mention
  "future per-user backend store" / "when multi-user lands" / "future
  managed/multi-tenant shape" remain valid future plans (don't delete)
  but are reclassified out of the active milestone path.
- The "Postgres-deferred" framing is **stricter than D-005/D-018/D-019
  alone implied** — those say "wire the Protocol now, defer the impl";
  this ADR additionally says "do not even spend an iter polishing the
  deferred Protocol's edges, do not file Q-questions about its shape,
  do not let it appear in the next-up slice list."

**Refs.** Ratifies user directive 2026-05-07 against
[`docs/ROADMAP.md` Scope freeze callout](../docs/ROADMAP.md);
this file's prior entries D-005 (auth), D-018 (OCR engine axis),
D-019 (S3 storage), D-021 (UI prefs), D-023 (multi-tab), D-040 (500
body redaction); [`00-overview.md` Non-goals](../docs/architecture/00-overview.md).

---

## D-043 — Konva renderer commitment supersedes D-020

**Date.** 2026-05-14.

**Decision.** Konva (via `react-konva` + `use-image`) is the
committed renderer for the image viewport, both `PageImageCanvas` and
all `BBoxOverlay` instances. The raw-canvas fallback option from
D-020 is dropped. The "research spike before M4 starts" gate is
removed.

**Why.**

- The 2026-05-14 parity audit
  ([`docs/PARITY_GAPS_2026_05_14.md`](../docs/PARITY_GAPS_2026_05_14.md))
  found that `PageImageCanvas.tsx` shipped as a DOM stub because
  the D-020 spike never ran. Eight months of "soon" without a
  measurement, while downstream issues (#197, #198) closed against
  the stub contracts.
- `WordImageCanvas.tsx` already proves Konva works end-to-end in our
  toolchain (jsdom Vitest mock + production bundle).
- The bbox-count budget per page (~2 400 nodes for a 200-line page
  across four layers) is well below Konva's documented
  ~10 000-node ceiling.
- The component contract in `04-image-viewport.md` is already
  Konva-shaped (Stage / Layer / Rect tree). Switching to raw canvas
  would require rewriting every downstream overlay/selection spec.

**Implications.**

- [`../docs/architecture/21-konva-renderer.md`](../docs/architecture/21-konva-renderer.md) is the implementation spec; it
  replaces `04-image-viewport.md` §0 ("research spike at M4 start").
- `OPEN_QUESTIONS.md` Q-A14 is resolved: the spike is unnecessary.
  Move Q-A14 to `docs/archive/research/QUESTIONS_RESOLVED.md` in the same
  commit that lands this ADR.
- `use-image@^1.1` is added to `frontend/package.json` as a runtime
  dependency.
- All future bbox-overlay work uses `react-konva` `<Rect>` nodes;
  test introspection moves to test-only sidecar divs (per spec 21
  §6) so driver-contract `data-testid` selectors still resolve.

**Alternatives considered.**

- Run the spike now. Rejected: the audit shows the renderer is
  already gating the entire labeling surface; another iter of
  unresolved deferral is more harmful than committing on the
  ergonomically-better stack and revisiting only if a measured
  perf failure forces it.
- Raw canvas + hand-rolled hit testing. Rejected: rewrite cost
  across overlays, selection, drag-rect preview, and hover-guide
  layers is real; the legacy comparison point ran an SVG overlay
  string render at every websocket roundtrip and is the *worse*
  reference, not the better.

**Refs.** [`OPEN_QUESTIONS.md Q-A14`](../OPEN_QUESTIONS.md),
[`21-konva-renderer.md`](21-konva-renderer.md),
[`docs/architecture/04-image-viewport.md`](../docs/architecture/04-image-viewport.md),
[`docs/PARITY_GAPS_2026_05_14.md`](../docs/PARITY_GAPS_2026_05_14.md),
D-020 (superseded).

---

## D-044 — Provenance granularity: object-level is sufficient for v1

**Date.** 2026-05-16. Closes Q-A7 (`OPEN_QUESTIONS.md`).

**Status.** Accepted.

**Decision.** Adopt **Option (A) — object-level provenance**: one `source`
string per word's `GlyphAnnotations` dict. If annotations for a single word
originate from multiple sources, record the highest-confidence or most-recent
source. Per-character provenance is deferred to v2.3 per the escape hatch
below.

**Why.**

- Real annotation traffic has not yet revealed mixed-source granularity at
  the character level within a single word. Character-level provenance would
  impose schema complexity before any observed need.
- The v2.2 schema reader (CU-1.2) and the `IGlyphPredictor` Protocol
  (CU-1.3) can be shipped with object-level source without a v2.3 bump.
- This mirrors D-032 (rotation provenance), which used the same
  single-string approach for per-page auto-rotation metadata.

**Escape hatch.** If mixed-source granularity is observed in production
traffic, a v2.3 schema bump can introduce `source_per_char: list[str] | None`
as an additive optional field. That bump does not require any change to
object-level consumers.

**Consequences.**

- `specs/20-glyph-annotations.md` §11 is updated to specify that `source`
  is always a single string (object-level).
- v2.2 envelope reader (CU-1.2) does not need to handle `source` arrays.
- M11 frontend can ship chips + accept/reject without surfacing
  per-character provenance.

**Alternatives considered.**

- **(B) Per-mark provenance now.** Add `source` to `LigatureMark`, add
  `long_s_sources: list[Literal[...]]` parallel to `long_s_positions`, and
  add `swash_source`. More complex model, but avoids a future schema bump.
  Rejected: complexity before observed need; a v2.3 bump is cheaper than
  over-engineering v2.2.
- **(C) Hybrid.** Keep `GlyphAnnotations.source` as the "dominant" signal
  plus an optional `mark_sources: dict[int, Literal[...]]` escape hatch.
  Rejected: hybrid adds parser complexity without removing the eventual
  v2.3 bump if full per-mark granularity is required.

**Refs.** [`OPEN_QUESTIONS.md Q-A7`](../OPEN_QUESTIONS.md),
[`specs/20-glyph-annotations.md`](20-glyph-annotations.md) §3 and §11,
D-032 (rotation provenance precedent).

---

## D-045 — ImageTabs sub-tabs: dropped in favor of existing Drawer + RightPanel surfaces

**Date:** 2026-05-16
**Status:** Accepted
**Closes:** GitHub issue #295; `docs/architecture/04-image-viewport.md` §3 open item

### Context

The task `docs/plan-to-usable.md` listed "ImageTabs sub-tabs vs single-canvas
decision (#295 — design Q for CT)" as a pending design question. The legacy
`pd-ocr-labeler` image pane (`image_tabs.py`) did **not** have text-overlay
sub-tabs; text overlays lived in the right-pane `text_tabs.py` (Matches /
Ground Truth / OCR). The confusion arose because the driver-contract
spec (`13-driver-contract.md §2.7`) titled that section "Text tabs / right
pane" and some planning notes described the three right-pane tabs as
"ImageTabs sub-tabs."

Issue #295 was resolved differently: `ImageTabsHeader.tsx` gained a
`mismatches-only-toggle` that dims exact/validated word bboxes in the canvas
overlay, giving the user a fast "show me the problem words" view without a
separate canvas mode.

The open question at `docs/plan-to-usable.md` line 55 and the "Out of scope"
note at line 106 collectively asked: should the SPA add three text-overlay
sub-tabs above the image (Matches canvas / GT text overlay / OCR text overlay)?

### Decision

**Do not add image-viewport text-overlay sub-tabs.** The `mismatches-only-toggle`
(shipped as part of #295) is the complete resolution for the `#295` design
question.

### Rationale

The three use-cases that text-overlay sub-tabs would serve are already covered:

- **Matches (both bboxes):** The canvas already shows bbox overlays for every
  active layer. Layer checkboxes let the user choose which layers are visible.
  The `mismatches-only-toggle` lets the user dim exact/validated words so only
  problem words are visually prominent — the primary reason to want a "Matches"
  mode.
- **Ground Truth text overlay:** `LineDetail` and `WordDetail` in the Right
  Panel show GT text with OCR comparison. The Worklist row's diff line serves
  the same scan-reading purpose as a GT text overlay on the canvas.
- **OCR text overlay:** Similarly covered by `WordDetail`'s OCR well and the
  Worklist row.

Adding text-overlay sub-tabs would duplicate these surfaces without new
affordances and would introduce text-positioning complexity over the Konva
canvas (absolute positioning of overlapping text over variable-scale images
with zoom).

Cross-reference: `docs/architecture/04-image-viewport.md`,
`docs/architecture/25-drawer-worklist.md`,
`docs/architecture/26-right-panel-detail.md`.

### Consequences

- `docs/plan-to-usable.md` "Polish" item for ImageTabs sub-tabs (#295) is
  closed. The `mismatches-only-toggle` is the shipped resolution.
- `frontend/src/components/ImageTabsHeader.tsx` does not need changes.
- The right-pane `TextTabs.tsx` (Matches / Ground Truth / OCR tabs) and its
  `text-tab-matches`, `text-tab-ground-truth`, `text-tab-ocr` testids are
  **not affected** — those are a separate component and must be preserved per
  D-014.

---

## D-046 — Deprecate legacy HeaderBar driver-contract stub testids (§2.1 project-load + dialog triggers)

**Date:** 2026-05-21
**Status:** Accepted
**Closes:** GitHub issue #401
**Supersedes:** stub-preservation rationale from commit ad71143

### Context

The hi-fi redesign (specs/2026-05-15-hifi-redesign-plan.md) relocated the
controls that previously lived inline in HeaderBar:

- **Project picker** (`project-select` / `load-project-button`) moved to the
  RootPage project card grid, rendered by
  `frontend/src/components/ProjectLoadControls.tsx`.
- **Source folder** (`source-folder-button`) moved to
  `frontend/src/components/SourceFolderDialog.tsx`, triggered via
  `ProjectLoadControls` (breadcrumb mode, `change-project-button`).
- **OCR config** (`ocr-config-trigger-button`) moved to
  `frontend/src/components/OCRConfigModal.tsx` + the ⚙ button inside
  `HeaderBar` (real button, not stub). The OCR config modal's internal
  fields (`ocr-detection-model-select`, `ocr-recognition-model-select`,
  `ocr-hf-revision-input`, `ocr-rescan-models-button`,
  `ocr-config-cancel-button`, `ocr-config-apply-button`) live in
  `OCRConfigModal.tsx`.
- **Export** (`export-trigger-button` / `export-button`) moved to
  `frontend/src/components/ExportDialog.tsx`, opened from
  `PageActionsCompact` (`page-actions-compact-export`) and `PageActions`
  (`export-button`).
- **Hotkey help** (`hotkey-help-trigger-button` / `hotkey-help-dialog`)
  moved to `frontend/src/components/HotkeyHelpModal.tsx`, opened from
  the Rail footer button `rail-hotkeys-button`
  (`frontend/src/components/shell/Rail.tsx:278`) via
  `dialogStore.open("hotkeyHelp")`.

Commit ad71143 preserved the deprecated controls as hidden stubs in
HeaderBar so the driver-contract testid requirement in
`docs/architecture/13-driver-contract.md` §2.1 was nominally satisfied.
However, the hi-fi redesign is now shipped and the driver can reach all
of these controls at their real locations. Keeping stubs conflicts with
the test suite (HeaderBar.test.tsx explicitly asserts these testids are
absent) and adds dead DOM noise.

### Decision

Remove the following elements from `HeaderBar.tsx`:

| Deprecated testid | Element type | New location | New testid(s) |
|---|---|---|---|
| `project-select` | Stub (`data-testid-stub="true"`) | `ProjectLoadControls.tsx` | `project-select` (real) |
| `load-project-button` | Stub | `ProjectLoadControls.tsx` | `load-project-button` (real) |
| `source-folder-button` | Stub | `ProjectLoadControls.tsx` (breadcrumb mode) | `source-folder-button` (real) |
| `ocr-config-trigger-button` | Real ⚙ button | `OCRConfigModal.tsx` (opened via `dialogStore.open("ocrConfig")`) | `ocr-config-modal` (the modal); modal-internal stubs kept in hidden div |
| `export-trigger-button` | Never existed in SPA | `PageActionsCompact.tsx` / `PageActions.tsx` | `page-actions-compact-export` / `export-button` |
| `hotkey-help-trigger-button` | Never existed in SPA | `Rail.tsx` footer | `rail-hotkeys-button` |

The source-folder dialog field stubs
(`source-folder-current-path-label`, `source-folder-path-input`,
`source-folder-home-button`, `source-folder-up-button`,
`source-folder-open-typed-button`, `source-folder-use-current-button`,
`source-folder-cancel-button`, `source-folder-apply-button`) are
**kept** in the HeaderBar hidden stub div — they are still needed for
driver-contract §2.2 (source folder dialog fields available before the
dialog opens). They are NOT removed.

The OCR config modal field stubs
(`ocr-detection-model-select`, `ocr-recognition-model-select`,
`ocr-hf-revision-input`, `ocr-rescan-models-button`,
`ocr-config-cancel-button`, `ocr-config-apply-button`) are also
**kept** in the HeaderBar hidden stub div — tests assert them present
(HeaderBar.test.tsx "stub ocr-config elements are in the DOM").

The nav stubs (`nav-prev-button`, `nav-next-button`, `nav-goto-button`,
`nav-page-input`, `nav-page-total-label`) are **not** deprecated —
they remain in `HeaderBar.tsx` to ensure navigability from the root
route before a project is opened.

The driver contract document (`docs/architecture/13-driver-contract.md`)
must be updated to remove §2.1 rows for the deprecated testids and
document the new paths the driver uses for each control.

### Approval

CT approved the deprecation via GH issue #401 (2026-05-21). The
OPEN_QUESTIONS.md `§2.1 testid retirement gate` (line 77–79 of
`docs/architecture/13-driver-contract.md`) is satisfied by this ADR.

### Consequences

- `HeaderBar.test.tsx` tests that assert `project-select`,
  `load-project-button`, `source-folder-button`,
  `ocr-config-trigger-button`, `export-trigger-button`, and
  `hotkey-help-trigger-button` are NOT in the DOM will now pass.
- The driver must reach project-load controls via `ProjectLoadControls`
  on the RootPage, source-folder via `SourceFolderDialog`, OCR config via
  the real ⚙ button in HeaderBar right side or `OCRConfigModal`, export
  via `PageActionsCompact`/`PageActions`, and hotkey help via the Rail
  footer `rail-hotkeys-button`.

---

## D-047 — Header → workspace-toolbar realignment (chrome-only header)

**Date:** 2026-06-14
**Status:** Accepted
**Spec:** `docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md`
**Plan:** `docs/plans/2026-06-14-labeler-spa-header-to-workspace-toolbar.md` (M1)

### Context

The AppShell `header` slot was overloaded with document/page-scoped controls
that pdomain-ui's design reserves for the app body, not chrome. `HeaderBar`
injected `navSlot` (ProjectNavigationControls), `actionsSlot`
(PageActionsCompact), a `searchSlot` (QuickSearch), an inline metrics strip,
and theme chips. pdomain-ui's documented header layout is chrome-only
(`[icon] [name] [breadcrumb] [spacer] [LauncherSlot] [SettingsSlot ⚙]`); the
documented convention for an in-app document toolbar is the `StageToolbar`
primitive (`leftSlot`/`centerSlot`/`rightSlot`).

### Decision

`HeaderBar` slims to pure chrome (logo, app name, project breadcrumb, resolved
project-root label). It no longer accepts `navSlot` / `actionsSlot` /
`searchSlot` / `pageMetrics`, and the theme chips are removed (see D-048). The
document/page-scoped controls move into a new full-width `WorkspaceToolbar`
band (a thin wrapper over the pdomain-ui `StageToolbar`,
`data-testid="workspace-toolbar"`):

| Moved control | New mount point | Slot |
|---|---|---|
| `ProjectNavigationControls` (`nav-*`) | `WorkspaceToolbar` | `leftSlot` |
| `PageActionsCompact` (`page-actions-compact-*` + undo/redo/rotate) | `WorkspaceToolbar` | `centerSlot` |
| metrics strip (`header-metrics-strip`) | `WorkspaceMetrics` in `WorkspaceToolbar` | `rightSlot` |
| `QuickSearch` (`quick-search*`) | `Drawer` worklist-header slot (`drawer-worklist-header`) | — |

**Mount point reality vs. the design wording.** The design describes mounting
the band "in StudioShell's header zone." In the shipped app the live shell is
the pdomain-ui `AppShell` (in `App.tsx`) plus `ProjectPage`'s own
`project-workspace` grid — `StudioShell` is not in the render path (it remains
a tested layout primitive). The `WorkspaceToolbar` band is therefore mounted at
the top of `ProjectPage`'s body (above `project-workspace`), which is exactly
where today's nav/actions appeared and is the project route's de-facto header
zone. The `⌘K` (Mod+K) focus hotkey moved into `ProjectPage` alongside
`QuickSearch`; focus behavior is unchanged.

**Driver-contract testid preservation (D-014).** Every moved control keeps its
exact `data-testid`; only the mount point changes. The metrics strip keeps
`header-metrics-strip` for driver continuity despite no longer living in the
header. The `display:none` driver stubs in `HeaderBar` (`nav-*`,
`source-folder-*`, `ocr-config-*` field stubs) are retained per D-046 so those
testids stay reachable on every route, including the root route.

### Consequences

- The hidden `PageActions` bar (`page-actions-bar`, driver-contract §2.5
  testids) stays mounted in `ProjectPage`. Because `PageActionsCompact` is now
  visible in the project body, the overlapping testids (`undo-button`,
  `redo-button`, `load-page-button`, `reload-ocr-edited-button`,
  `rotate-cw/ccw/180-button`, `rotation-badge`, `save-project-button`) appear in
  both surfaces. This duplication already existed in the running app (compact in
  header + hidden full bar); consolidating the §2.5 surface onto
  `PageActionsCompact` is deferred to M2 (Slice 2A).
- Tests that asserted controls were *absent* from `ProjectPage` (IS-2 era) are
  repointed to assert presence in the `WorkspaceToolbar` band.

---

## D-048 — Theme chips relocated to the SettingsModal Appearance panel

**Date:** 2026-06-14
**Status:** Accepted
**Spec:** `docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md`

### Context

`HeaderBar` rendered a local theme radio group with SPA-new testids
(`theme-chips`, `theme-chip-dark`, `theme-chip-light`, `theme-chip-system`).
These were never part of the legacy `pd-ocr-labeler` driver contract — they are
SPA-only. pdomain-ui owns theme via its `UIPrefs` provider (wired through the
AppShell `uiPrefsConfig`), which applies `data-theme` to the document and
exposes theme controls in the built-in `SettingsModal` Appearance panel
(testids `settings-appearance-theme-dark` / `settings-appearance-theme-light`).

### Decision

Remove the local `ThemeChips` from `HeaderBar`. Theme is now changed via the ⚙
SettingsModal Appearance panel that the pdomain-ui AppShell already renders into
the header zone. The legacy `theme-chips` / `theme-chip-*` testids are retired.

Because these testids are SPA-new (not in the legacy driver contract), retiring
them is permitted under D-014's "new elements get new testids" clause. The move
is surfaced here (not silent): `HeaderBar.test.tsx` is updated to assert the
chips are absent, and the driver-contract doc carries no rows for them (none
existed). Drivers that need to change theme use the Appearance panel testids
above.

### Consequences

- `ThemedToaster` still reads the local `useThemePreference` store for the
  sonner toast theme. When theme is changed via the Appearance panel, the
  visible page theme (`data-theme`) updates immediately through pdomain-ui's
  provider; the toaster theme may lag until the local store re-seeds (the same
  GAP-1 deferral that governs `/api/ui-prefs` persistence). The local
  `setTheme` path remains for programmatic callers; it is simply no longer
  surfaced as header chips.

---

## D-049 — Remove HeaderBar nav-* stubs; retire `:not([data-testid-stub])` for nav testids

**Date:** 2026-06-14
**Status:** Accepted
**Spec:** `docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md` (M2 primitive adoption)

### Context

D-047 moved `ProjectNavigationControls` into the `WorkspaceToolbar` `leftSlot`.
The `display:none` nav stubs (`nav-prev-button`, `nav-next-button`,
`nav-goto-button`, `nav-page-input`, `nav-page-total-label`) were kept in
`HeaderBar` so these testids were reachable on every route including root.
Drivers had to use `[data-testid="nav-prev-button"]:not([data-testid-stub])`
to avoid matching the stub.

The M2 primitive-adoption arc removes all three legacy display:none stub
blocks. With the stubs gone, nav testids exist ONLY in the real
`ProjectNavigationControls` in `WorkspaceToolbar`.

### Decision

Remove the 5 nav-* stubs from the `HeaderBar` hidden div. The
`ProjectNavigationControls` in `WorkspaceToolbar` `leftSlot` is the single
source of truth. The `:not([data-testid-stub])` selector convention is
**retired** for these testids — select them directly.

### Consequences

- Nav testids are only present on project routes (where `WorkspaceToolbar`
  renders). Drivers must navigate to a project page before locating them.
- The `data-testid-stub="true"` pattern remains for source-folder and
  OCR-config modal field stubs in `HeaderBar` (those stubs are retained).

---

## D-050 — Remove hidden PageActions stub; rename PageActionsCompact testids to §2.5 canonical names

**Date:** 2026-06-14
**Status:** Accepted
**Spec:** `docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md` (M2 primitive adoption)

### Context

A hidden `PageActions` component (`data-testid-stub="page-actions-hidden"`)
was mounted in `ProjectPage` to preserve driver-contract §2.5 testids
(`reload-ocr-button`, `save-page-button`, etc.). The visible
`PageActionsCompact` used its own prefixed testids
(`page-actions-compact-reload-ocr`, etc.), which differed from the contract.
Drivers had to rely on the hidden stub for the canonical testids.

### Decision

1. Remove `hiddenPageActions` from `ProjectPage` entirely.
2. Rename `PageActionsCompact` button testids to the §2.5 canonical names:
   - `page-actions-compact-reload-ocr` → `reload-ocr-button`
   - `page-actions-compact-rematch-gt` → `rematch-gt-button`
   - `page-actions-compact-save-page` → `save-page-button`
   - `page-actions-compact-export` → `export-button`
3. Add `data-testid="page-actions-bar"` wrapper div around `PageActionsCompact`.
4. Add `page-name-label` and `page-source-badge` spans to `PageActionsCompact`.
5. Replace the hand-rolled overflow menu state with `pdomain-ui` `DropdownMenu`.

### Consequences

- `PageActionsCompact` is the sole source of truth for §2.5 testids.
- The `page-actions-compact-*` interim names are retired for the four renamed
  buttons. The `page-actions-compact` container testid and
  `page-actions-compact-overflow` trigger testid are **preserved**.
- `page-actions-bar` wraps the compact bar; driver tests that wait for
  `page-actions-bar` now find a visible element (no `state="attached"` needed,
  though it is harmless).

---

## D-051 — Wire TextTabs + WordMatchView visibly into RightPanel textTabsSlot

**Date:** 2026-06-14
**Status:** Accepted
**Spec:** `docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md` (M2 primitive adoption)

### Context

`TextTabs` + `WordMatchView` + `PlaintextEditor` were mounted inside a
`display:none` `canvas-hidden-stubs` div in `ProjectPage` to keep driver-
contract §2.7/§2.8 testids in the DOM while the right panel was in use.
The virtualizer inside `WordMatchView` renders zero items when hidden.

### Decision

Remove `canvas-hidden-stubs`. Add a `textTabsSlot?: React.ReactNode` prop to
`RightPanel`. When `selection-store.level === "none"` (no selection active)
and `textTabsSlot` is provided, render it instead of the placeholder text.
`ProjectPage` passes `textTabsContent` (the `TextTabs` + `WordMatchView` tree)
as `textTabsSlot`.

### Consequences

- `TextTabs` and `WordMatchView` are now visible in the right panel whenever
  no selection is active (the default state on page load).
- Driver-contract §2.7/§2.8 testids are reachable without
  `:not([data-testid-stub])` guards.
- The virtualizer inside `WordMatchView` now has a real viewport and renders
  line cards normally.

---

## D-052 — Remove last display:none stub block; source-folder + OCR-config fields on real modal controls

**Date:** 2026-06-14
**Status:** Accepted
**Supersedes:** D-046 (partially) — the source-folder and OCR-config field stubs that D-046 kept are now removed.

### Context

`SourceFolderDialog` and `OCRConfigModal` were fully implemented as real React
components. Their driver-contract testids (`source-folder-*`, `ocr-detection-model-select`,
etc.) existed as both real controls inside those modals AND as hidden `display:none`
stubs in the `HeaderBar` `display:none` div (the last surviving stub block
after D-046/D-049/D-050/D-051 removed the others). The result was that
`data-testid-stub="true"` attributes remained in the DOM alongside real implementations,
creating a misleading dual-presence.

### Decision

Remove the entire `display:none` stub `<div>` from `HeaderBar.tsx`. The
source-folder dialog and OCR-config modal field testids now live **exclusively**
on their real visible controls inside the respective modals. To reach them, the
driver or e2e test must first OPEN the modal:

- Source-folder fields: click `source-folder-button` (in `ProjectLoadControls`)
  → `SourceFolderDialog` opens → fields are visible.
- OCR-config fields: click `ocr-config-trigger-button` (in `PageActionsCompact`
  on project routes, or in the root-route header injection in `App.tsx`) →
  `OCRConfigModal` opens → fields are visible.

Delete `PageActions.tsx` (dead file — never imported in production code after M2).
Its `PageActions.test.tsx` is deleted too.

### Consequences

- No `data-testid-stub` attributes remain in the DOM for these two groups.
- Driver/e2e tests that previously checked for stubs must open the modal first.
- E2e tests updated: `test_stub_testids_present` and `test_stub_testids_have_stub_attribute`
  replaced by `test_source_folder_stub_testids_absent_without_dialog`,
  `test_source_folder_dialog_testids_present`,
  `test_ocr_config_stub_testids_absent_without_modal`, and updated
  `test_ocr_config_modal_testids_present` (now opens the modal).
- `docs/architecture/13-driver-contract.md` §2.2 / §2.3 updated to reflect
  that the driver must open the modal before addressing these testids.

---

## Pending decisions

See [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) for any sub-questions
still open.

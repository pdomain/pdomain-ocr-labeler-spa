# pd-ocr-labeler-spa: Architecture Decisions Log

> **Status**: Draft
> **Last updated**: 2026-05-12
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#38

## TL;DR

Chronological ADR log for the SPA. Thirty-eight decisions covering framework choices (React,
FastAPI, shadcn), data-root compat, adapter protocols (auth/storage/OCR), SSE job model,
URL grammar, persistence strategy, and post-GA extensions. New entries go on top; superseded
entries link forward. This spec is normative: a new decision requires an entry here before
implementation begins.

## Context

The legacy `pd-ocr-labeler` accumulated undocumented design decisions across its NiceGUI
implementation. The SPA makes every architecture decision explicit upfront. The ADR log is the
authoritative record of WHY the system is the way it is — not just WHAT it does. Implementers
must read the relevant ADR before deviating from any spec they disagree with; deviation requires
a new ADR entry that supersedes the old one.

## Constraints

- **New decisions before implementation.** If an implementing agent discovers a design gap,
  it must draft an ADR entry and surface it to CT before coding the deviation.
- **No retroactive rewrites.** Existing entries are not rewritten. Superseding decisions link
  to the old entry with "Supersedes: D-NNN".
- **Cross-spec references.** Every ADR entry cites the spec section it governs.

## Decision

The full ADR content is maintained in `specs/17-decisions.md`. This design spec records the
meta-level decisions about how the log is maintained and what the normative entries cover.

### Normative entries (summary of D-001 through D-038)

**Framework and stack (D-001, D-002, D-004, D-006, D-008, D-036):**
`build_app(settings)` factory pattern (D-001); React 19 + Vite + TS replaces NiceGUI (D-002);
shadcn/ui + Radix primitives from day one (D-004); hybrid sync/SSE for long jobs — single-page
OCR and Save Project are SSE, word edits are synchronous (D-006); plain textarea replaces
CodeMirror for OCR/GT text tabs (D-008); Node 24 via mise (D-036).

**Data and persistence (D-003, D-007, D-009, D-025, D-026, D-027, D-030, D-035):**
Preserve `pd_ocr_labeler` data root for legacy interop (D-003); local-only filesystem adapter
for v1 (D-007); JSON-sidecar persistence, no Postgres in v1 (D-009); "OCR fidelity wins by
default; PGDP fidelity on request" for text normalization (D-025); GT is ASCII-clean, glyphs
are a side-channel (D-026); per-page singleton cached envelopes (D-027); URL grammar from
pgdp-prep plural convention with legacy 301 redirects (D-030); 301 (not 308) for legacy GET
routes (D-035).

**Adapter protocols (D-005, D-010, D-011, D-012):**
`IAuth(none)` only for v1 but seam preserved (D-005); `IStorage(filesystem)` with path-
traversal guard (D-010); `IOCREngine(local_doctr)` Protocol stub, raises NotImplementedError
until implemented (D-011); single AppState-level per-project write lock, no distributed
concurrency (D-012).

**UI and interaction (D-013, D-014, D-015, D-016, D-017, D-018, D-019, D-020):**
TanStack Query for all server state, no Redux (D-013); zustand for client-only UI state
(D-014); Konva.js for image canvas (D-015); react-hotkeys-hook for all keybindings (D-016);
`@tanstack/react-virtual` for word-match list virtualization (D-017); msw for Vitest API mocks
(D-018); single uvicorn process, no worker cluster for v1 (D-019); page-scope SSE job stream,
not WebSocket (D-020).

**Testing and CI (D-021, D-022, D-023, D-024):**
`asyncio_mode = "auto"` (D-021); axe-core in E2E as required WCAG AA gate (D-022); openapi-
drift CI job is required — not optional (D-023); conformance test against legacy fixtures is a
CI gate (D-024).

**Post-GA extensions (D-028, D-029, D-031, D-032, D-033, D-034, D-037, D-038):**
Devcontainer optional, `make setup` canonical onboarding (D-028); auto-rotation deferred to
M9.1/M9.2 (D-029); export cancel via `runner.is_cancelled` + rmtree (D-031); per-page glyph
annotations stored in envelope, not sidecar (D-032, pending Q-A5); text normalization toggle
is project-level in OCRConfig (D-033); predictions not persisted in envelope (D-034); mise
`node = "24"` is the workspace-pinned default (D-037); `UV_PYTHON = "3.13"` pinned in CI to
avoid anyio/SQLite segfault (D-038).

### ADR format convention

Each entry: **D-NNN** heading, **Date**, **Decision** (one sentence), **Why** (bullets),
**Alternatives considered** (bullets), **Refs** (spec section links). New entries prepended
at the top of `specs/17-decisions.md`.

## Contract / Acceptance

- `specs/17-decisions.md` contains an entry for every major design choice made during
  implementation (verified by code review).
- No implementing agent codes a deviation from any spec without first adding a new ADR entry
  and getting CT acknowledgment.
- Every ADR entry cites at least one spec section reference.
- The log is append-only; no existing entries are edited or deleted.

## Trade-offs considered

**Formal ADR tool vs flat markdown log.** Tools (adr-tools, log4brains) add overhead and
require installation. A flat markdown file with a consistent format is readable without
tooling and searchable with grep. Chosen: flat markdown.

**Numbered entries vs dated entries.** Numbers give stable references; dates provide context.
Chosen: both — D-NNN + Date field per entry.

**Supersede vs edit.** Editing old entries destroys the "why it changed" information. New
entries that supersede old ones preserve the full decision history. Chosen: supersede with
forward links.

## Consequences

- Every PR description should cite the relevant D-NNN if it implements or modifies a decision.
- Reviewing agents can use ADR numbers to verify spec compliance without re-reading all specs.
- If `specs/17-decisions.md` grows beyond ~50 entries, consider splitting by domain area
  (persistence, frontend, testing). In v1 a single file is fine.

## Open questions

None.

## References

- `specs/17-decisions.md` — the actual ADR log (authoritative content)
- `OPEN_QUESTIONS.md` — unresolved questions that may become new ADR entries on resolution
- `specs/00-overview.md` — the "why SPA" context that motivated D-001 through D-005

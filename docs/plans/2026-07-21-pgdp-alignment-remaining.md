---
kind: plan
status: partial
owner: maintainers
created: 2026-07-21
last_verified: 2026-11-07
---

# Remaining shared UI alignment

Most PGDP-style shell alignment has shipped or received an explicit ownership decision. The remaining work is
export-history hydration, the detail-shell comparison, and residual documentation alignment.

## Goal

Complete the remaining shared-shell work without importing PGDP's pipeline product into the labeler. This plan
replaces the June backlog and the July overnight scheduling documents.

## Architecture

Use shared pdomain-ui chrome, suite launch, jobs, status primitives, and worklist shells through local adapters.
Keep OCR and ground-truth editing, typography, glyph review, event-store operations, document layout, and domain
panels local.

[Frontend architecture](../architecture/03-frontend.md) records compute and ownership boundaries.
[Export architecture](../architecture/10-export.md) records the manifest and Trainer handoff.
[Page history](../architecture/29-page-loading-and-history.md) records the shipped History tab and jumps.

## Tech Stack

FastAPI, React, TypeScript, TanStack Query, Zustand, pdomain-ui, pytest, Vitest, and Playwright.

## Global Constraints

- Do not add PGDP's 24-stage registry, stage folders, stage runner, stage settings inheritance, downstream stale
  propagation, proof-pack, or submit workflow.
- Do not rewrite state management solely to match PGDP.
- Keep generated OpenAPI types and the driver contract aligned with any interface change.
- Auth, S3, Postgres, and managed-adapter deployment remain deferred by D-042.

## Shipped work and settled decisions

Suite launch uses real endpoints. Project cards show metadata and progress; Active and Complete filters work.
Shared jobs chrome, manual glyph review, status chips, and U-M7 visible history ship. Compute settings are
registered and warmed.

Archive/restore and shared WorkbenchLayout adoption were declined. Project deletion remains permanent with
confirmation. The existing worklist adapter, compatibility shims, and local filter/count chrome are the intended
boundary; they are not a request for a replacement.

Common appearance preferences use localStorage. App preference persistence is a no-op. Server preference
persistence remains deferred rather than becoming implicit scope for this plan.

## Remaining work

### Persisted export history in the dialog

The export manifest API can list persisted information, but ExportDialog keeps its own client-only run history.
Hydrate the dialog from persisted exports so closing and reopening it does not erase the visible history. Preserve
loading and failure states; do not infer that the API alone completes the UI requirement.

Acceptance: export a project, reopen the dialog, and see its persisted export information. A failed history read
must not masquerade as no previous export.

### Detail-panel shell comparison

Compare the local RightPanel header, collapse controls, and body routing with the shared shell. Record whether
shared framing adds value before extracting it. Preserve local domain content and selection behavior. No decision
to replace the local panel is established by this cleanup.

Acceptance: document the ownership decision with evidence. If extraction is chosen, prove selection routing and
collapse behavior remain intact.

### Remaining driver and adapter documentation

Check the driver catalogue and shell/worklist architecture against mounted components. Persistent right-panel
editing replaced WordEditDialog. The AppShell owns application chrome; ProjectPage owns the document grid. Keep the
live identifiers and explain permanent adapters instead of treating them as unfinished migrations.

Acceptance: live component routing, documented identifiers, and ownership agree. Do not rename identifiers as a
documentation-only fix.

## Evidence and provenance

The September decision log resolves metadata, filters, archive, jobs, shared layout, and adapter ownership. Commit
`44b52257` ships visible history. The current sources are `frontend/src/components/ExportDialog.tsx`,
`frontend/src/components/shell/RightPanel.tsx`, `frontend/src/components/drawer/Worklist.tsx`, and
`frontend/src/App.tsx`.

The old numbered item list and execution examples remain in Git history. Their stale assertions that launch,
glyphs, cards, and history were missing are not current requirements.

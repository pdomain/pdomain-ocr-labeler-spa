---
kind: research
status: active
owner: maintainers
created: 2026-08-22
last_verified: 2026-08-22
---

# CharRange deletion inventory

No persisted CharRange data was found, so the typography editor can make the approved clean schema break without migrating user records.

## Agent Index

- **Kind:** research
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-08-22
- **Read when:** removing the legacy CharRange contract or checking whether CharRange migration is required.
- **Search terms:** CharRange deletion, char_ranges inventory, typography clean break, grapheme editor migration.

## Goal

This report records whether persisted CharRange data exists before the approved clean schema break.

## Method

The inventory searched every JSON document and JSONL record for `char_ranges` and `char_ranges_map`. It covered the SPA repository, `/workspaces/pdomain-data/source-pgdp-data/output`, and `/workspaces/pdomain-data/source-pgdp-data/pgdp-corpus`.

Additional read-only checks inspected SQLite heads and events, scanned event states and content blobs by byte, and ran repository-wide `rg -l` searches.

The inventory changed no corpus file, event record, blob, or project state.

## Evidence

The read-only inventory found zero `char_ranges` and `char_ranges_map` payloads, and zero range items. No persisted project or record identifiers are affected.

The scan covered:

- 22 SPA JSON and JSONL fixtures;
- 1,729 JSON and JSONL files under the local PGDP project and corpus roots;
- 6 output projects and 286 PGDP corpus projects;
- 62 events, 19 aggregate heads, 0 snapshots, and 39 content blobs in event-store project `projectID629292e7559a8`.

Every JSON file parsed successfully. The byte scan also found no legacy field in event states or content blobs.

### One configured location was absent

The default data root `/home/vscode/pdomain-ocr-labeler-spa` did not exist. No `PDOMAIN` or `PD` environment override provided another SPA data root.

The inventory therefore used the local roots found under `/workspaces/pdomain-data`. Recording this absence makes the scan scope explicit.

### Only test and code references remain

The repository contains 15 test-only `char_ranges` assignments. Seven are in `CharRangesSection` tests. One is in the project-page rebox test, one is in the sidecar integration test, and six are in unit tests for labeler sidecars.

The clean break must replace or remove these active surfaces:

- backend models, request types, endpoint, page hydration, page-state map, labeler sidecar handling, and page-to-line conversion;
- `CharRangesSection`, its WordDetail wiring, mutation hook, request handlers, tests, OpenAPI schema, and generated TypeScript types;
- related integration, endpoint, unit, end-to-end, rebox, and accordion tests;
- active architecture, behavior, workflow, README, context, and lint documentation.

CharFixer behavior remains unchanged. Its legacy CharRange names must change only where they describe bounding boxes, not typography spans. Historical plans and issues remain historical unless their obsolete references would misstate active behavior.

## Conclusions

The typography design approves a clean schema break after this read-only inventory. The implementation will reject old range payloads. It will not convert, dual-write, or add a fallback reader.

The replacement must land before removing the `/char-ranges` endpoint, inclusive code-point semantics, old frontend model, and `PageState.char_ranges_map`. The canonical replacement uses stable word IDs, Unicode grapheme indices, and half-open spans.

## Next steps

Replace the legacy contract with the canonical typography API and grapheme editor. Then remove the listed code, tests, generated types, and active documentation references in the same reviewed branch.

## What this does NOT establish

This inventory does not prove that an unavailable or undisclosed data root contains no CharRange payloads. It covers the repository, discovered local roots, and available event store listed above.

It also does not approve changes to CharFixer behavior or historical records. Those remain outside the legacy typography-range deletion.

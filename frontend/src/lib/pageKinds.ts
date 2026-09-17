// pageKinds.ts — the full PageKind enumeration, shared by the page-toolbar
// kind control (PageActionsCompact.tsx) and the book-wide Review page kinds
// dialog (PageKindsDialog.tsx), so the list of kinds a person can choose
// from is defined once.
//
// Spec: pdomain-ocr-synth's docs/specs/2026-09-17-page-kind-review-design.md
//   "The page toolbar shows and confirms the current page's kind" —
//   "including its exhaustive Record over the union so a new kind fails to
//    compile until it is listed."
//
// Built from the generated PageKind type via an exhaustive Record, the same
// pattern RegionDetail.tsx's REGION_ROLE_RECORD uses for RegionRole — a new
// kind fails to compile here until it is listed.

import type { components } from "../api/types";

export type PageKind = components["schemas"]["PageKind"];

const PAGE_KIND_RECORD: Record<PageKind, true> = {
  body: true,
  "chapter opening": true,
  "title page": true,
  "half title": true,
  contents: true,
  index: true,
  dedication: true,
  preface: true,
  errata: true,
  plate: true,
  blank: true,
  advertisement: true,
  colophon: true,
  unknown: true,
};

export const PAGE_KINDS = Object.keys(PAGE_KIND_RECORD) as PageKind[];

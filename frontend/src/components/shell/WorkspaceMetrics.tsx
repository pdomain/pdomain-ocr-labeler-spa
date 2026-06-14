// WorkspaceMetrics.tsx — per-page word-match metrics strip.
//
// Spec: docs/specs/2026-06-14-labeler-spa-header-to-workspace-toolbar-design.md
//       specs/17-decisions.md D-047 (header → workspace-toolbar move)
//
// M1 (D-047): extracted verbatim from HeaderBar's inline metrics block and
// mounted in the WorkspaceToolbar rightSlot. Behavior is unchanged — the
// `header-metrics-strip` testid is preserved for driver continuity (the strip
// is still keyed off the page payload's per-word match counts). Renders nothing
// when there are no words (total === 0) or when metrics are absent.

/** Computed per-page word-match metrics. */
export interface PageMetrics {
  total: number;
  exact: number;
  fuzzy: number;
  mismatch: number;
  validated: number;
  /** Number of words with glyph_annotations !== null (spec §8). Optional — only shown when present. */
  glyphs_reviewed?: number | undefined;
}

export interface WorkspaceMetricsProps {
  /** Per-page word-match metrics. Strip is hidden when null or total === 0. */
  pageMetrics?: PageMetrics | null;
}

export function WorkspaceMetrics({ pageMetrics }: WorkspaceMetricsProps) {
  if (!pageMetrics || pageMetrics.total <= 0) return null;
  return (
    <div
      data-testid="header-metrics-strip"
      className="flex items-center gap-1.5 text-[10px] text-ink-3 shrink-0"
    >
      <span>{pageMetrics.total} words</span>
      <span>·</span>
      <span className="text-status-exact">{pageMetrics.exact} exact</span>
      <span>·</span>
      <span className="text-status-fuzzy">{pageMetrics.fuzzy} fuzzy</span>
      <span>·</span>
      <span className="text-status-mismatch">{pageMetrics.mismatch} ✗</span>
      <span>·</span>
      <span>
        {pageMetrics.validated}/{pageMetrics.total} validated
      </span>
      {pageMetrics.glyphs_reviewed !== undefined && (
        <>
          <span>·</span>
          <span>
            {pageMetrics.glyphs_reviewed}/{pageMetrics.total} glyphs
          </span>
        </>
      )}
    </div>
  );
}

WorkspaceMetrics.displayName = "WorkspaceMetrics";

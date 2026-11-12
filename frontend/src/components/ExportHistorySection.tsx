import { useExportHistory, type SavedExport } from "../hooks/useExportHistory";

interface ExportHistorySectionProps {
  projectId: string;
  completedRuns: number;
}

function formatExportedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function SavedExportRow({ saved }: { saved: SavedExport }) {
  return (
    <div
      data-testid="export-history-row"
      className="text-xs text-ink-2 bg-bg-raised border border-border-1 rounded-sm px-2 py-1"
    >
      <span className="font-medium">{formatExportedAt(saved.created_at)}</span>
      <span className="ml-2 text-ink-4">{saved.page_count} pages</span>
      {Object.entries(saved.tasks).map(([task, counts]) => (
        <span key={task} className="ml-2 text-ink-4">
          {task}: {counts["item_count"] ?? 0} items
        </span>
      ))}
    </div>
  );
}

export function ExportHistorySection({ projectId, completedRuns }: ExportHistorySectionProps) {
  const history = useExportHistory(projectId, completedRuns);

  return (
    <div data-testid="export-history">
      <div className="text-xs font-semibold text-ink-2 mb-1">Saved Export</div>
      {history.isPending ? (
        <div data-testid="export-history-loading" className="text-xs text-ink-4">
          Loading saved export...
        </div>
      ) : history.isError ? (
        <div
          data-testid="export-history-error"
          role="alert"
          className="text-xs text-status-mismatch"
        >
          Could not read the saved export history: {history.error.message}
        </div>
      ) : history.data.length === 0 ? (
        <div data-testid="export-history-empty" className="text-xs text-ink-4">
          No previous export.
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          {history.data.map((saved) => (
            <SavedExportRow key={saved.job_id} saved={saved} />
          ))}
        </div>
      )}
    </div>
  );
}

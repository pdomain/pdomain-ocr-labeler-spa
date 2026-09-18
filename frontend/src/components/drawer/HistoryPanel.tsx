// HistoryPanel.tsx — "History" drawer tab: read-only per-page version list.
//
// Spec: docs/specs/2026-06-12-event-store-undo.md "U-M7 — history panel +
// jump-to-version". A person can undo/redo without any way to see what they
// are traversing; this tab is that visibility. It is READ-ONLY except for
// the one mutation the spec itself designs (jump), which is exactly as
// append-only as the undo/redo buttons — see useJumpToVersion.tsx. Nothing
// here builds a second, competing way to mutate history: every row and
// button reads or calls the same backend routes undo/redo already use.
//
// data-testids:
//   history-panel          — outer container
//   history-loading        — shown before the first fetch resolves
//   history-empty          — shown once loaded with no history (unwired store)
//   history-error          — shown once loaded with a jump-request error
//   history-version-list   — row list container
//   history-version-row    — one row (same testid on every row; distinguish
//                             via the row's `data-node-id` attribute, per the
//                             spec's "with the version's node_id as a data
//                             attribute" — not a parameterised testid)
//   history-jump-button    — per-row jump action (omitted on the current row)

import { CheckCircle } from "@pdomain/pdomain-ui/icons";
import { useHistoryVersions, type HistoryVersionInfo } from "../../hooks/useHistoryVersions";
import { useJumpToVersion } from "../../hooks/usePageMutations";
import { formatRelativeTime } from "../../lib/relative-time";
import { cn } from "@/lib/utils";

export interface HistoryPanelProps {
  projectId: string;
  pageIndex: number;
}

interface HistoryVersionRowProps {
  version: HistoryVersionInfo;
  onJump: (nodeId: string) => void;
  jumpDisabled: boolean;
}

function HistoryVersionRow({ version, onJump, jumpDisabled }: HistoryVersionRowProps) {
  return (
    <li>
      <div
        data-testid="history-version-row"
        data-node-id={version.node_id}
        data-current={version.is_current ? "true" : undefined}
        className={cn(
          "flex items-center justify-between gap-2 px-2 py-1.5 text-[11px] border-b border-border-1/40",
          version.is_current ? "bg-bg-raised text-ink-1" : "text-ink-2",
        )}
      >
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="text-ink-1 truncate">{version.label}</span>
          <span className="text-[10px] text-ink-3">{formatRelativeTime(version.timestamp)}</span>
        </div>
        {version.is_current ? (
          <span
            data-testid="history-version-current"
            className="shrink-0 inline-flex items-center gap-1 text-[10px] text-accent font-medium"
          >
            <CheckCircle size={12} />
            Current
          </span>
        ) : (
          <button
            type="button"
            data-testid="history-jump-button"
            disabled={jumpDisabled}
            onClick={() => {
              onJump(version.node_id);
            }}
            className={cn(
              "shrink-0 px-2 py-1 text-[10px] font-medium rounded-sm transition-colors",
              "bg-bg-surface text-ink-2 border border-border-2 hover:bg-bg-raised",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            Jump
          </button>
        )}
      </div>
    </li>
  );
}

export function HistoryPanel({ projectId, pageIndex }: HistoryPanelProps) {
  const versionsQ = useHistoryVersions(projectId, pageIndex);
  const jumpM = useJumpToVersion(projectId, pageIndex);
  const versions = versionsQ.data ?? [];

  return (
    <div data-testid="history-panel" className="flex flex-col h-full">
      {jumpM.isError && (
        <p
          data-testid="history-error"
          className="px-2 py-1.5 text-[10px] text-red-500 border-b border-border-1"
        >
          {jumpM.error.message || "Jump failed."}
        </p>
      )}
      <div className="flex-1 min-h-0 overflow-auto">
        {versionsQ.isLoading ? (
          <p data-testid="history-loading" className="p-3 text-ink-3 text-[11px]">
            Loading version history…
          </p>
        ) : versions.length === 0 ? (
          <p data-testid="history-empty" className="p-3 text-ink-3 text-[11px]">
            No version history for this page.
          </p>
        ) : (
          <ul data-testid="history-version-list" className="flex flex-col">
            {versions.map((version) => (
              <HistoryVersionRow
                key={version.node_id}
                version={version}
                jumpDisabled={jumpM.isPending}
                onJump={(nodeId) => {
                  jumpM.mutate({ nodeId });
                }}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

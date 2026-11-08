import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchSourceAlignment } from "../../api/source-alignment";

export interface SourceAlignmentPanelProps {
  readonly projectId: string;
  readonly pageIndex: number;
  readonly generation: number;
  readonly alignmentId: string;
  readonly groupId: string;
  readonly onRendered: () => void;
  readonly onUnavailable: (message: string) => void;
}

export function SourceAlignmentPanel({
  projectId,
  pageIndex,
  generation,
  alignmentId,
  groupId,
  onRendered,
  onUnavailable,
}: SourceAlignmentPanelProps) {
  const query = useQuery({
    queryKey: ["source-alignment", projectId, pageIndex],
    queryFn: ({ signal }) => fetchSourceAlignment(projectId, pageIndex, signal),
    staleTime: 0,
  });
  const envelope = query.data;
  const group =
    envelope?.result?.groups.find((candidate) => candidate.group_id === groupId) ?? null;
  const isCurrent =
    envelope !== undefined &&
    !envelope.stale &&
    envelope.generation === generation &&
    envelope.result?.result_id === alignmentId &&
    group !== null;

  useEffect(() => {
    if (isCurrent) onRendered();
  }, [isCurrent, onRendered]);

  useEffect(() => {
    if (query.isError) onUnavailable("The source alignment result could not be loaded.");
    if (envelope !== undefined && !isCurrent && !query.isFetching) {
      onUnavailable("The requested source alignment group is not current for this page.");
    }
  }, [envelope, isCurrent, onUnavailable, query.isError, query.isFetching]);

  if (!isCurrent) {
    return (
      <div role="status" className="p-3">
        Loading source alignment…
      </div>
    );
  }
  const projectedHints = envelope.result.layout_hints.filter((hint) =>
    hint.group_ids.includes(groupId),
  );

  return (
    <section data-testid="source-alignment-panel" className="p-3 space-y-3">
      <header>
        <h2 className="text-sm font-semibold">Source alignment</h2>
        <p className="text-xs text-ink-3">
          {group.disposition} · {group.decision}
        </p>
      </header>
      <dl className="grid gap-2 text-sm">
        <div>
          <dt className="font-medium">F2</dt>
          <dd>{group.f2_text}</dd>
        </div>
        <div>
          <dt className="font-medium">P3</dt>
          <dd>{group.p3_text}</dd>
        </div>
        <div>
          <dt className="font-medium">OCR</dt>
          <dd>{group.ocr_text}</dd>
        </div>
      </dl>
      {group.warnings.length > 0 && (
        <ul data-testid="source-alignment-group-warnings" className="text-sm text-ink-3">
          {group.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      {projectedHints.map((hint) => (
        <section key={`${hint.source_ref}:${hint.kind}`} data-testid="source-alignment-layout-hint">
          <h3 className="text-sm font-medium">
            {hint.kind} from {hint.source}
          </h3>
          <ol className="space-y-1 text-sm">
            {hint.lines.map((line, index) => (
              <li key={`${line.text}:${String(index)}`}>
                <span>{line.text}</span>
                {line.stanza_index !== null && (
                  <span className="ml-2 text-ink-3">Stanza {line.stanza_index}</span>
                )}
                {line.indent_hint !== null && (
                  <span className="ml-2 text-ink-3">Indent {line.indent_hint}</span>
                )}
              </li>
            ))}
          </ol>
        </section>
      ))}
      {envelope.result.warnings.length > 0 && (
        <ul data-testid="source-alignment-result-warnings" className="text-sm text-ink-3">
          {envelope.result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      {envelope.result.unresolved.length > 0 && (
        <section data-testid="source-alignment-unresolved" className="text-sm text-ink-3">
          <h3 className="font-medium">Unresolved source formatting</h3>
          <ul>
            {envelope.result.unresolved.map((item) => (
              <li key={`${item.source_ref}:${item.source_kind}`}>
                {item.source_kind} {item.disposition}: {item.source_ref}
                {item.warnings.length > 0 ? ` (${item.warnings.join("; ")})` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}

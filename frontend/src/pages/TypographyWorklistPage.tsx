import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { TypographySection } from "../components/right-panel/sections/TypographySection";
import { useTypographyWorklist } from "../hooks/useTypographyReview";

function readableStatus(status: string): string {
  return status.replaceAll("_", " ");
}

export default function TypographyWorklistPage() {
  const { projectId = "", pageNo = "1" } = useParams<{
    projectId: string;
    pageNo: string;
  }>();
  const parsedPageNo = Number.parseInt(pageNo, 10);
  const pageIndex = Number.isFinite(parsedPageNo) && parsedPageNo > 0 ? parsedPageNo - 1 : 0;
  const worklist = useTypographyWorklist(projectId, pageIndex);
  const words = useMemo(() => worklist.data?.words ?? [], [worklist.data?.words]);
  const [selectedWordId, setSelectedWordId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedWordId((current) =>
      current && words.some((word) => word.word_id === current)
        ? current
        : (words[0]?.word_id ?? null),
    );
  }, [words]);

  if (worklist.isLoading) return <p className="p-4">Loading typography worklist…</p>;
  if (worklist.isError) {
    return (
      <p className="p-4" role="alert">
        Unable to load the typography worklist.
      </p>
    );
  }

  return (
    <div
      data-testid="typography-worklist-page"
      className="grid h-full min-h-0 grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)] bg-bg-base"
    >
      <aside className="min-h-0 overflow-y-auto border-r border-border-2 p-3">
        <h1 className="mb-1 text-base font-semibold text-ink-1">Typography review</h1>
        <p className="mb-3 text-xs text-ink-3">Page {pageIndex + 1} · producer word order</p>
        {words.length === 0 ? (
          <p className="text-sm text-ink-3">No producer words on this page.</p>
        ) : (
          <ol className="flex flex-col gap-1">
            {words.map((word, index) => {
              const typographyStatus =
                word.decision ?? (word.typography_reviewed ? "reviewed" : "unreviewed");
              return (
                <li key={word.word_id}>
                  <button
                    type="button"
                    data-testid={`typography-worklist-word-${String(index)}`}
                    aria-pressed={selectedWordId === word.word_id}
                    onClick={() => {
                      setSelectedWordId(word.word_id);
                    }}
                    className="w-full rounded border border-border-2 px-3 py-2 text-left text-sm aria-pressed:border-accent aria-pressed:bg-bg-raised"
                  >
                    <span className="block font-serif text-ink-1">{word.text}</span>
                    <span className="block break-all font-mono text-[0.65rem] text-ink-3">
                      {word.word_id}
                    </span>
                    <span className="mt-1 block text-xs text-ink-2">
                      Source: {readableStatus(word.source_review_state)}
                    </span>
                    <span className="mt-1 block text-xs text-ink-2">
                      Text: {word.text_reviewed ? "reviewed" : "unreviewed"} · Typography:{" "}
                      {readableStatus(typographyStatus)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </aside>
      <main className="min-h-0 overflow-y-auto p-4">
        {selectedWordId ? (
          <TypographySection projectId={projectId} pageIndex={pageIndex} wordId={selectedWordId} />
        ) : (
          <p className="text-sm text-ink-3">Select a producer word to review typography.</p>
        )}
      </main>
    </div>
  );
}

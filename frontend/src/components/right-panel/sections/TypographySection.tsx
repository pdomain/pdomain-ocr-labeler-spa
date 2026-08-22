import { useEffect, useMemo, useState } from "react";
import type { components } from "../../../api/types";
import {
  TypographyApiError,
  useAppendTypographyCorrection,
  useImportedTextValidation,
  useSetImportedTextValidation,
  useTypographyHead,
  useTypographyReview,
} from "../../../hooks/useTypographyReview";

type Decision = components["schemas"]["CorrectionDecision"];
type Span = components["schemas"]["TypographySpan"];
type Submission = components["schemas"]["TypographyCorrectionSubmission"];

export interface TypographySectionProps {
  projectId: string;
  pageIndex: number;
  wordId?: string | null;
}

export function TypographySection({ projectId, pageIndex, wordId }: TypographySectionProps) {
  const headQuery = useTypographyHead(projectId, pageIndex, wordId);
  const reviewQuery = useTypographyReview(projectId, pageIndex);
  const append = useAppendTypographyCorrection(projectId, pageIndex, wordId ?? "");
  const textValidation = useImportedTextValidation(
    projectId,
    pageIndex,
    wordId,
    headQuery.data?.imported_text_validation_available === true,
  );
  const setTextValidation = useSetImportedTextValidation(projectId, pageIndex, wordId ?? "");
  const [anchor, setAnchor] = useState<number | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  const [labels, setLabels] = useState<Set<string>>(new Set());
  const [spans, setSpans] = useState<Span[]>([]);

  const head = headQuery.data;
  const taxonomyLabels = head?.taxonomy.labels.map((label) => label.value) ?? [];
  useEffect(() => {
    setSpans(head?.correction?.replacement?.spans ?? []);
    setAnchor(null);
    setFocus(null);
    setLabels(new Set());
  }, [wordId, head?.head_token]);

  const selected = useMemo(() => {
    if (anchor === null || focus === null) return null;
    return { start: Math.min(anchor, focus), end: Math.max(anchor, focus) + 1 };
  }, [anchor, focus]);

  if (!wordId) return <p role="alert">Typography needs a stable word ID.</p>;
  if (headQuery.isLoading) return <p>Loading typography…</p>;
  if (!head) return <p role="alert">Typography data is unavailable.</p>;

  function select(index: number) {
    if (anchor === null || focus !== null) {
      setAnchor(index);
      setFocus(null);
    } else {
      setFocus(index);
    }
  }

  function replacement(nextSpans: Span[], regular = false) {
    const positive = new Set(nextSpans.map((span) => span.label));
    return {
      word_id: head!.word_id,
      text: head!.text,
      text_sha256: head!.text_sha256,
      page_content_sha256: head!.page_sha256,
      image_artifact_sha256: head!.image_sha256,
      grapheme_map_version: head!.grapheme_map_version,
      taxonomy_version: head!.taxonomy.version,
      taxonomy_hash: head!.taxonomy.taxonomy_hash,
      label_states: Object.fromEntries(
        taxonomyLabels.map((label) => [label, positive.has(label) ? "positive" : "negative"]),
      ),
      spans: nextSpans,
      source_evidence_ids: ["labeler-manual-review"],
      warnings: [],
      whole_word_labels: null,
      word_revision: head!.word_revision + 1,
      review_state: regular ? "reviewed_regular" : "reviewed",
      metadata: null,
    } satisfies components["schemas"]["WordTypography-Input"];
  }

  async function submit(decision: Decision, nextSpans = spans, regular = false) {
    const carriesReplacement = ["approved_edit", "reviewed_regular", "accept"].includes(decision);
    const body: Submission = {
      expected_head: head!.head_token,
      correction_id: crypto.randomUUID(),
      taxonomy_version: head!.taxonomy.version,
      taxonomy_hash: head!.taxonomy.taxonomy_hash,
      grapheme_map_version: head!.grapheme_map_version,
      labeler_id: "local",
      decision,
      replacement: carriesReplacement ? replacement(nextSpans, regular) : null,
      replacement_text_sha256: carriesReplacement ? head!.text_sha256 : null,
      replacement_page_sha256: carriesReplacement ? head!.page_sha256 : null,
      replacement_image_sha256: carriesReplacement ? head!.image_sha256 : null,
      replacement_page_head_sha256: carriesReplacement ? head!.page_head_sha256 : null,
      replacement_word_revision: carriesReplacement ? head!.word_revision + 1 : null,
      replacement_artifacts: [],
      replacement_artifact_payloads: [],
      model_runs: [],
      coordinate_transforms: [],
    };
    await append.mutateAsync(body);
  }

  function submitFromButton(decision: Decision, nextSpans = spans, regular = false) {
    void submit(decision, nextSpans, regular).catch(() => undefined);
  }

  function addSelection() {
    if (!selected) return;
    const additions = [...labels].map((label, offset): Span => ({
      span_id: crypto.randomUUID(),
      label,
      start: selected.start,
      end: selected.end,
      label_source: "human",
      confidence_tier: "gold",
      alignment_evidence_id: `manual-${offset}`,
      prediction_id: null,
    }));
    setSpans((current) => [...current, ...additions]);
  }

  function splitSpan(index: number) {
    setSpans((current) => {
      const span = current[index];
      if (!span || span.end - span.start < 2) return current;
      const middle = Math.floor((span.start + span.end) / 2);
      return current.flatMap((item, itemIndex) =>
        itemIndex === index
          ? [
              { ...item, span_id: crypto.randomUUID(), end: middle },
              { ...item, span_id: crypto.randomUUID(), start: middle },
            ]
          : [item],
      );
    });
  }

  function mergeSpan(index: number) {
    setSpans((current) => {
      const first = current[index];
      const second = current[index + 1];
      if (!first || !second) return current;
      if (first.label !== second.label || first.end < second.start) return current;
      return current
        .filter((_, itemIndex) => itemIndex !== index + 1)
        .map((item, itemIndex) =>
          itemIndex === index ? { ...first, end: Math.max(first.end, second.end) } : item,
        );
    });
  }

  const stale = append.error instanceof TypographyApiError && append.error.status === 409;
  const staleText =
    setTextValidation.error instanceof TypographyApiError && setTextValidation.error.status === 409;
  return (
    <section data-testid="typography-section" className="flex flex-col gap-2 py-1">
      {reviewQuery.data && (
        <p data-testid="typography-progress">
          {reviewQuery.data.typography_reviewed_words}/{reviewQuery.data.total_words} typography
          reviewed
        </p>
      )}
      {textValidation.data && (
        <div className="rounded border p-2">
          <p>Confirm the exact imported text independently:</p>
          <p className="font-serif">{textValidation.data.text}</p>
          <button
            type="button"
            disabled={setTextValidation.isPending}
            onClick={() =>
              setTextValidation.mutate({
                expected_head: textValidation.data.head_token,
                validated: !textValidation.data.validated,
              })
            }
          >
            {textValidation.data.validated ? "Unvalidate text" : "Validate exact text"}
          </button>
        </div>
      )}
      <div className="flex flex-wrap gap-1" aria-label="Graphemes">
        {head.graphemes.map((grapheme, index) => (
          <button
            key={index}
            type="button"
            data-testid={`typography-grapheme-${index}`}
            aria-pressed={
              selected ? index >= selected.start && index < selected.end : anchor === index
            }
            onClick={() => select(index)}
            className="rounded border px-2 py-1 font-serif"
          >
            {grapheme}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => {
          setAnchor(0);
          setFocus(Math.max(0, head.graphemes.length - 1));
        }}
      >
        Whole word
      </button>
      <div className="flex flex-wrap gap-1">
        {head.taxonomy.labels.map((taxonomyLabel) => {
          const label = taxonomyLabel.value;
          return (
            <button
              type="button"
              key={label}
              aria-pressed={labels.has(label)}
              onClick={() =>
                setLabels((current) => {
                  const next = new Set(current);
                  if (next.has(label)) next.delete(label);
                  else next.add(label);
                  return next;
                })
              }
            >
              {taxonomyLabel.display_name}
            </button>
          );
        })}
      </div>
      <button type="button" onClick={addSelection} disabled={!selected || labels.size === 0}>
        Add span
      </button>
      <ul>
        {spans.map((span, index) => (
          <li key={span.span_id} data-testid={`typography-span-${index}`}>
            {span.start}–{span.end} {span.label}
            <button
              type="button"
              aria-label={`Split span ${index + 1}`}
              disabled={span.end - span.start < 2}
              onClick={() => splitSpan(index)}
            >
              Split
            </button>
            <button
              type="button"
              aria-label={`Merge span ${index + 1}`}
              disabled={!spans[index + 1]}
              onClick={() => mergeSpan(index)}
            >
              Merge next
            </button>
            <button
              type="button"
              aria-label={`Delete span ${index + 1}`}
              onClick={() => setSpans((all) => all.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={() => submitFromButton("approved_edit")}>
        Save typography
      </button>
      <button type="button" onClick={() => submitFromButton("reviewed_regular", [], true)}>
        Reviewed regular
      </button>
      <button type="button" onClick={() => submitFromButton("reject_source")}>
        Reject source
      </button>
      <button type="button" onClick={() => submitFromButton("unusable_image")}>
        Quarantine
      </button>
      <button type="button" onClick={() => submitFromButton("defer")}>
        Defer
      </button>
      {stale && (
        <p role="alert">
          Stale typography head. Reloaded the latest revision; review before saving again.
        </p>
      )}
      {append.error && !stale && <p role="alert">{append.error.message}</p>}
      {staleText && <p role="alert">Text validation changed. Reloaded the current decision.</p>}
      {setTextValidation.error && !staleText && (
        <p role="alert">{setTextValidation.error.message}</p>
      )}
    </section>
  );
}

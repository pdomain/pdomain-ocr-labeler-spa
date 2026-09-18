// ReviewQueuePanel.tsx — "Queue" drawer tab: the book-wide undecided-proposal
// review queue.
//
// Spec: docs/specs/2026-09-17-book-review-queue-design.md
//   "What this increment does not build" names "a queue panel listing every
//   item" and "confidence-ordered navigation in the UI" as future work —
//   this file, and the order toggle below, are that work.
//
// Reuses the same cross-page navigation pattern `]`/`[` use
// (useRegionReviewHotkeys.ts, "Selecting after navigation needs an intent,
// not a direct call"): clicking an item on another page records a
// `review-selection-intent-store` intent and navigates; ProjectPage applies
// it once that destination page's payload loads and contains the proposal —
// surviving the page-change selection clear. Clicking the item for the
// *current* page selects directly with `selectProposal` — no navigation, no
// intent needed, since the page's payload is already loaded.
//
// Item order comes from `ui-prefs.ts`'s `reviewQueueOrder`, remembered for
// the session next to `drawerTab`, and passed straight through as
// `useReviewQueue`'s `order` argument — that hook's query key already
// separates the "reading" and "confidence" caches, so switching the toggle
// never flashes a stale list cached under the other order.
//
// The list renders directly off `useReviewQueue`'s query data, with no
// local sort/filter/removal: nothing here reorders or clears rows while a
// decision is in flight. TanStack Query keeps the last successful `data`
// visible during a refetch (it only replaces `data` once the new fetch
// resolves), so the `["review-queue", projectId]` invalidation a decision
// triggers (useRegionMutations.ts) cannot cause a mid-flight reorder here —
// there is nothing that reads or reacts to `isFetching` in this file.
//
// data-testids:
//   review-queue-panel                                    — outer container
//   review-queue-order-reading                             — order toggle: reading order (default)
//   review-queue-order-confidence                          — order toggle: lowest confidence first
//   review-queue-loading                                   — shown before the first fetch resolves
//   review-queue-empty                                     — shown once loaded with no undecided proposals
//   review-queue-list                                      — row list container
//   review-queue-item-{pageIndex}-{proposalId}              — one row
//   review-queue-item-evidence-{pageIndex}-{proposalId}     — the item's evidence signal, when it carries one

import { useNavigate } from "react-router-dom";
import { useSyncExternalStore } from "react";
import { useReviewQueue, type ReviewQueueOrder } from "../../hooks/useReviewQueue";
import {
  useBookReviewQueue,
  firstActionableKind,
  blockedByMessage,
  REVIEW_QUEUE_KIND_LABELS,
  type ReviewQueueKindEntry,
  type ReviewQueueKindName,
} from "../../hooks/useBookReviewQueue";
import { selectionStore, selectProposal } from "../../stores/selection-store";
import { setReviewSelectionIntent } from "../../stores/review-selection-intent-store";
import { useUiPrefs } from "../../stores/ui-prefs";
import { pageNoUrl } from "../../lib/routes";
import { cn } from "@/lib/utils";
import type { components } from "../../api/types";

type RegionReviewQueueItem = components["schemas"]["RegionReviewQueueItem"];

/** The panel always asks for items — the UI, unlike the bracket keys and the
 * Rail badge, needs the proposals themselves, not just the per-page summary. */
const ITEM_LIMIT = 200;

/** The evidence dict's "signal" entry, when the item carries a string one.
 *
 * Evidence is open-ended per detector, so the value is read defensively:
 * a detector that records no `signal`, or a non-string one, renders nothing.
 */
function evidenceSignal(item: RegionReviewQueueItem): string | null {
  const signal = item.evidence["signal"];
  return typeof signal === "string" ? signal : null;
}

function itemTestId(item: RegionReviewQueueItem): string {
  return `review-queue-item-${String(item.page_index)}-${item.proposal_id}`;
}

// ─── ui-prefs subscriber bridge ─────────────────────────────────────────────

function getReviewQueueOrder(): ReviewQueueOrder {
  return useUiPrefs.getState().reviewQueueOrder;
}

function setReviewQueueOrder(order: ReviewQueueOrder): void {
  useUiPrefs.setState({ reviewQueueOrder: order });
}

function getReviewQueueKind(): ReviewQueueKindName | null {
  return useUiPrefs.getState().reviewQueueKind;
}

function setReviewQueueKind(kind: ReviewQueueKindName): void {
  useUiPrefs.setState({ reviewQueueKind: kind });
}

// ─── selection-store subscriber ─────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(cb);
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

// ─── Order toggle ────────────────────────────────────────────────────────────

interface OrderOptionProps {
  testId: string;
  label: string;
  active: boolean;
  onClick: () => void;
}

function OrderOption({ testId, label, active, onClick }: OrderOptionProps) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "px-2 py-1 text-[10px] rounded-sm font-medium transition-colors",
        active
          ? "bg-accent text-accent-ink"
          : "bg-bg-surface text-ink-2 border border-border-2 hover:bg-bg-raised",
      )}
    >
      {label}
    </button>
  );
}

// ─── Row ─────────────────────────────────────────────────────────────────────

interface ReviewQueueRowProps {
  item: RegionReviewQueueItem;
  selected: boolean;
  onClick: () => void;
}

function ReviewQueueRow({ item, selected, onClick }: ReviewQueueRowProps) {
  const signal = evidenceSignal(item);
  return (
    <li>
      <button
        type="button"
        data-testid={itemTestId(item)}
        data-selected={selected ? "true" : undefined}
        aria-current={selected ? "true" : undefined}
        onClick={onClick}
        className={cn(
          "w-full flex flex-col gap-0.5 text-left px-2 py-1.5 text-[11px] border-b border-border-1/40 transition-colors",
          selected
            ? "bg-bg-raised text-ink-1"
            : "text-ink-2 hover:bg-bg-raised/60 hover:text-ink-1",
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <span>Page {item.page_index + 1}</span>
          <span className="font-mono tabular-nums text-ink-3">{item.confidence.toFixed(2)}</span>
        </div>
        <span className="text-ink-1">{item.role}</span>
        {signal !== null && (
          <span
            data-testid={`review-queue-item-evidence-${String(item.page_index)}-${item.proposal_id}`}
            className="text-[10px] text-ink-3"
          >
            {signal}
          </span>
        )}
      </button>
    </li>
  );
}

// ─── Kind selector (one-answer-to-what-to-review-next) ─────────────────────
// Spec: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-
// review-next.md "How the SPA uses the new route" — "The Queue drawer tab
// grows a kind selector, defaulting to that same kind [the rail's]."

/** The selector row's per-kind pill text — honest about what it doesn't know. */
function kindPillLabel(entry: ReviewQueueKindEntry): string {
  if (!entry.available) return "n/a";
  const prefix = entry.is_lower_bound ? "≥" : "";
  const count = `${prefix}${String(entry.outstanding)}`;
  return entry.blocked_by !== null ? `${count} · waiting` : count;
}

interface KindSelectorProps {
  kinds: readonly ReviewQueueKindEntry[];
  active: ReviewQueueKindName;
  onSelect: (kind: ReviewQueueKindName) => void;
}

function KindSelector({ kinds, active, onSelect }: KindSelectorProps) {
  if (kinds.length === 0) return null;
  return (
    <div
      data-testid="review-queue-kind-selector"
      className="flex flex-wrap gap-1 p-2 border-b border-border-1 shrink-0"
    >
      {kinds.map((entry) => (
        <button
          key={entry.kind}
          type="button"
          data-testid={`review-queue-kind-select-${entry.kind}`}
          aria-pressed={active === entry.kind}
          onClick={() => {
            onSelect(entry.kind);
          }}
          className={cn(
            "px-2 py-1 text-[10px] rounded-sm font-medium transition-colors flex items-center gap-1",
            active === entry.kind
              ? "bg-accent text-accent-ink"
              : "bg-bg-surface text-ink-2 border border-border-2 hover:bg-bg-raised",
          )}
        >
          <span>{REVIEW_QUEUE_KIND_LABELS[entry.kind]}</span>
          <span className="font-mono tabular-nums opacity-80">{kindPillLabel(entry)}</span>
        </button>
      ))}
    </div>
  );
}

/**
 * Outstanding-count sentence. `is_lower_bound` reads as "At least N" — never
 * a completion figure (design: "A count that may understate says so in the
 * response, not only in prose").
 */
function formatOutstandingCount(entry: ReviewQueueKindEntry): string {
  const prefix = entry.is_lower_bound ? "At least " : "";
  return `${prefix}${String(entry.outstanding)} of ${String(entry.total)} outstanding`;
}

interface KindSummaryProps {
  entry: ReviewQueueKindEntry;
  onStart: (pageIndex: number) => void;
}

/**
 * The non-region kinds' summary: a count and where to start, never an item
 * list (design: "What this does not build" — "Per-kind item lists for words
 * and typography... Listing every outstanding word across a book is a
 * different shape and nobody has asked for it").
 */
function KindSummary({ entry, onStart }: KindSummaryProps) {
  const label = REVIEW_QUEUE_KIND_LABELS[entry.kind];

  if (!entry.available) {
    return (
      <div data-testid="review-queue-kind-summary" className="p-3 text-[11px] flex flex-col gap-2">
        <p data-testid="review-queue-kind-unavailable" className="text-ink-3">
          {label} is unavailable: {entry.unavailable_reason ?? "no reason given"}.
        </p>
      </div>
    );
  }

  const firstPageIndex = entry.first_page_index;

  return (
    <div data-testid="review-queue-kind-summary" className="p-3 text-[11px] flex flex-col gap-2">
      <p data-testid="review-queue-kind-count" className="text-ink-1 font-medium">
        {formatOutstandingCount(entry)}
      </p>
      {entry.blocked_by !== null && (
        <p data-testid="review-queue-kind-blocked" className="text-ink-3">
          {blockedByMessage(entry.blocked_by)}
        </p>
      )}
      {entry.pages_not_counted > 0 && (
        <p data-testid="review-queue-kind-pages-not-counted" className="text-ink-3">
          {entry.pages_not_counted} page{entry.pages_not_counted === 1 ? "" : "s"} could not be
          counted.
        </p>
      )}
      {firstPageIndex !== null ? (
        <button
          type="button"
          data-testid="review-queue-kind-start"
          onClick={() => {
            onStart(firstPageIndex);
          }}
          className="self-start px-2 py-1 rounded-sm bg-accent text-accent-ink text-[10px] font-medium"
        >
          Start at page {firstPageIndex + 1}
        </button>
      ) : entry.outstanding > 0 ? (
        <p data-testid="review-queue-kind-no-start" className="text-ink-3">
          No known starting page yet.
        </p>
      ) : (
        <p data-testid="review-queue-kind-complete" className="text-ink-3">
          Nothing outstanding for {label.toLowerCase()}.
        </p>
      )}
    </div>
  );
}

// ─── Panel ───────────────────────────────────────────────────────────────────

export interface ReviewQueuePanelProps {
  projectId: string;
  /** 0-based index of the currently open page — an item for this page
   * selects without navigating (see module comment). */
  pageIndex: number;
}

export function ReviewQueuePanel({ projectId, pageIndex }: ReviewQueuePanelProps) {
  const navigate = useNavigate();
  const order = useSyncExternalStore(
    useUiPrefs.subscribe,
    getReviewQueueOrder,
    getReviewQueueOrder,
  );
  const selection = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );

  // One-answer-to-what-to-review-next: the kind selector, defaulting to
  // firstActionableKind — the same rule the Rail's "next kind" badge uses —
  // and falling back to "region" once nothing else qualifies, so this panel
  // opens on the region item list exactly as it always has when a book has
  // no other outstanding, unblocked work.
  const explicitKind = useSyncExternalStore(
    useUiPrefs.subscribe,
    getReviewQueueKind,
    getReviewQueueKind,
  );
  const bookQueueQ = useBookReviewQueue(projectId);
  const kinds = bookQueueQ.data?.kinds ?? [];
  const autoKind = firstActionableKind(kinds)?.kind;
  const resolvedKind: ReviewQueueKindName = explicitKind ?? autoKind ?? "region";
  const activeEntry = kinds.find((k) => k.kind === resolvedKind);

  const queueQ = useReviewQueue(projectId, { order, limit: ITEM_LIMIT });
  const items = queueQ.data?.items ?? [];
  // The badges count every undecided proposal in the book; the list stops at
  // ITEM_LIMIT. Say so, or a reader working the list to its end would take it
  // for the whole book.
  const totalUndecided = queueQ.data?.total_undecided ?? 0;
  const truncated = items.length < totalUndecided;

  function handleItemClick(item: RegionReviewQueueItem) {
    if (item.page_index === pageIndex) {
      selectProposal(item.proposal_id);
      return;
    }
    setReviewSelectionIntent({ pageIndex: item.page_index, proposalId: item.proposal_id });
    void navigate(pageNoUrl(projectId, item.page_index + 1));
  }

  function isSelected(item: RegionReviewQueueItem): boolean {
    return selection.level === "region" && selection.path.proposalId === item.proposal_id;
  }

  // Driver-contract §2.18 (docs/architecture/13-driver-contract.md) declares
  // review-queue-panel/review-queue-order-reading/review-queue-order-
  // confidence as always rendered once the Queue tab opens — a contract
  // predating this kind selector that pre-existing browser tests
  // (test_driver_contract.py, test_review_queue_panel.py) still exercise
  // unconditionally. So the order toggle stays mounted regardless of which
  // kind is selected; only the body area below it — the part item 5 says
  // must differ per kind — swaps between the region item list and the
  // KindSummary.
  return (
    <div data-testid="review-queue-panel" className="flex flex-col h-full">
      <KindSelector kinds={kinds} active={resolvedKind} onSelect={setReviewQueueKind} />

      {/* Honesty applies to the region kind too: a blocked region queue must
       * say what it is waiting for, even though its item list below is
       * unchanged (design item 5) — an empty-looking list must never be
       * mistaken for "nothing to do" when it is really "nothing proposed
       * yet because page kinds aren't". */}
      {resolvedKind === "region" && activeEntry?.blocked_by != null && (
        <p
          data-testid="review-queue-kind-blocked"
          className="px-3 py-1.5 text-[10px] text-ink-3 border-b border-border-1"
        >
          {blockedByMessage(activeEntry.blocked_by)}
        </p>
      )}

      <div className="flex gap-1 p-2 border-b border-border-1 shrink-0">
        <OrderOption
          testId="review-queue-order-reading"
          label="Reading order"
          active={order === "reading"}
          onClick={() => {
            setReviewQueueOrder("reading");
          }}
        />
        <OrderOption
          testId="review-queue-order-confidence"
          label="Lowest confidence first"
          active={order === "confidence"}
          onClick={() => {
            setReviewQueueOrder("confidence");
          }}
        />
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {resolvedKind !== "region" ? (
          activeEntry !== undefined ? (
            <KindSummary
              entry={activeEntry}
              onStart={(startPageIndex) => {
                void navigate(pageNoUrl(projectId, startPageIndex + 1));
              }}
            />
          ) : (
            <p data-testid="review-queue-kind-loading" className="p-3 text-ink-3 text-[11px]">
              Loading the review queue…
            </p>
          )
        ) : queueQ.isLoading ? (
          <p data-testid="review-queue-loading" className="p-3 text-ink-3 text-[11px]">
            Loading the review queue…
          </p>
        ) : items.length === 0 ? (
          <p data-testid="review-queue-empty" className="p-3 text-ink-3 text-[11px]">
            This book has no undecided proposals.
          </p>
        ) : (
          <>
            {truncated && (
              <p
                data-testid="review-queue-truncated"
                className="px-2 py-1.5 text-[10px] text-ink-3 border-b border-border-1"
              >
                Showing {items.length} of {totalUndecided}. Decide these to see the rest.
              </p>
            )}
            <ul data-testid="review-queue-list" className="flex flex-col">
              {items.map((item) => (
                <ReviewQueueRow
                  key={`${String(item.page_index)}-${item.proposal_id}`}
                  item={item}
                  selected={isSelected(item)}
                  onClick={() => {
                    handleItemClick(item);
                  }}
                />
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

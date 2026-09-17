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

// The queue item the API returns today (`RegionReviewQueueItem` in
// api/regions.py) carries no `evidence` field — only the per-page proposals
// list does (`RegionProposalView`, read by RegionDetail.tsx). This local
// extension declares that field as optional on top of the generated type,
// so the panel renders it if a future backend change adds it, without
// widening the trusted response type with an unchecked cast: every
// `RegionReviewQueueItem` already structurally satisfies this type, since
// `evidence` is optional.
type ReviewQueueItemView = RegionReviewQueueItem & {
  evidence?: Record<string, unknown> | undefined;
};

/** The evidence dict's "signal" entry, when the item carries a string one. */
function evidenceSignal(item: RegionReviewQueueItem): string | null {
  const view: ReviewQueueItemView = item;
  const evidence = view.evidence;
  if (evidence === undefined) return null;
  const signal = evidence["signal"];
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

  const queueQ = useReviewQueue(projectId, { order, limit: ITEM_LIMIT });
  const items = queueQ.data?.items ?? [];

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

  return (
    <div data-testid="review-queue-panel" className="flex flex-col h-full">
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
        {queueQ.isLoading ? (
          <p data-testid="review-queue-loading" className="p-3 text-ink-3 text-[11px]">
            Loading the review queue…
          </p>
        ) : items.length === 0 ? (
          <p data-testid="review-queue-empty" className="p-3 text-ink-3 text-[11px]">
            This book has no undecided proposals.
          </p>
        ) : (
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
        )}
      </div>
    </div>
  );
}

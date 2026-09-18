// RegionDetail.tsx — Region-level right panel: proposal review + confirmed
// region editing.
// Spec: docs/specs/2026-09-17-region-review-surface-design.md
// Plan: docs/plans/2026-09-17-region-review-surface.md — Task 4
//
// Looks the selection up in the page payload:
//   - a `regionId` selects the confirmed page.regions entry with that id;
//   - a `proposalId` selects the unconfirmed page.regions entry with that
//     id, whose evidence and disposition come from page.proposals — RegionView
//     carries no evidence of its own.
//   - an id in neither list (normal right after a decision removes a
//     proposal) renders a short "no longer on the page" message.
//
// This file also exports <CarriedRejectionsPanel> — a sibling to
// <RegionDetail>, not a part of it (see that component's own doc comment for
// why): a re-run must not ask about a rejection again, but nothing should
// suppress a proposal without a person being able to see, and undo, the
// suppression (docs/context/current-state.md "nothing in the SPA shows or
// undoes a carried rejection"). Collapsed and counted by default — a
// carried rejection is usually correct, so it stays out of the way until
// opened; only ``page.proposals`` entries whose latest decision is a
// rejection *and* names ``carried_from_proposal_id`` count, never an
// ordinary direct rejection (which already had a person's attention) or one
// already brought back (``disposition: "reopened"``, no longer rejected).
// "Bring back" posts to ``.../unreject``, appending a ``reopened`` decision
// — the decision log is append-only, so this never rewrites the rejection
// it reverses; the proposal simply becomes undecided again, same as any
// other.
//
// data-testids:
//   region-detail                       — outer container (role/proposal-or-confirmed body)
//   region-detail-role                  — role text (proposal or confirmed)
//   region-detail-confidence            — proposal confidence, two decimals
//   region-detail-stale-badge           — shown when the proposal is stale
//   region-detail-evidence-{key}        — one row per evidence entry
//   region-detail-accept                — accept the proposal, no role override
//   region-detail-accept-as-select      — role picker for "accept as"
//   region-detail-accept-as-apply       — apply the "accept as" role
//   region-detail-reject                — reject the proposal
//   region-detail-accept-error          — inline error after a failed accept
//   region-detail-reject-error          — inline error after a failed reject
//   region-detail-origin                — "From a proposal" / "Drawn by hand"
//   region-detail-change-role-select    — role picker for a confirmed region
//   region-detail-change-role-apply     — apply the changed role
//   region-detail-edit-error            — inline error after a failed edit
//   region-detail-delete                — delete a confirmed region (confirm-gated)
//   region-detail-delete-error          — inline error after a failed delete
//   carried-rejections-summary          — outer container, present only when count > 0
//   carried-rejections-toggle           — expand/collapse the list (aria-expanded)
//   carried-rejections-count            — the count text
//   carried-rejections-list             — expanded list container
//   carried-rejections-item-{proposalId}        — one row
//   carried-rejections-bring-back-{proposalId}  — un-reject that row's proposal
//   carried-rejections-error-{proposalId}       — inline error after a failed un-reject

import { useState, useSyncExternalStore } from "react";
import { selectionStore } from "../../stores/selection-store";
import { dialogStore } from "../../stores/dialog-store";
import {
  useAcceptProposal,
  useRejectProposal,
  useUnrejectProposal,
  useEditRegion,
  useDeleteRegion,
  useRegionDecisionPending,
} from "../../hooks/useRegionMutations";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type RegionView = components["schemas"]["RegionView"];
type RegionProposalView = components["schemas"]["RegionProposalView"];
type RegionRole = components["schemas"]["RegionRole"];

// ─── The role list ──────────────────────────────────────────────────────────
//
// Built from the generated RegionRole type, not BlockDetail.tsx's local
// layout list, which is a different set. TypeScript cannot enumerate a
// string-literal union at runtime, so the plan's `const` array plus a
// standalone exhaustiveness assertion was the first cut here — but this
// repo's `noUnusedLocals: true` (tsconfig.app.json) rejects an assertion
// const that nothing reads, even underscore-prefixed (that convention is an
// ESLint allowance, not a TypeScript one). This repo's own idiom for
// checking a union is complete is the exhaustive `Record`, the same shape
// `RightPanel.tsx`'s `LEVEL_PLACEHOLDER` and `Rail.tsx`'s per-target maps
// use: TypeScript requires every `RegionRole` key below, so the object
// literal itself won't compile if one is missing.
const REGION_ROLE_RECORD: Record<RegionRole, true> = {
  paragraph: true,
  sidenote: true,
  "page header": true,
  "page footer": true,
  "page number": true,
  "printers mark": true,
  blockquote: true,
  poetry: true,
  recovered: true,
  illustration: true,
  decoration: true,
  caption: true,
  figure: true,
  table: true,
  footnote: true,
  title: true,
  section: true,
  list: true,
  formula: true,
  artefact: true,
  "signature mark": true,
  catchword: true,
  "press figure": true,
  rule: true,
  brace: true,
  bracket: true,
  "group label": true,
  plate: true,
  "speaker label": true,
  "stage direction": true,
  "interlinear gloss": true,
  abandoned: true,
  "decorated initial": true,
  unknown: true,
};

// `Object.keys` widens every result to `string[]` — a documented TypeScript
// limitation, not a gap this cast papers over: the object literal above
// already proved, at compile time, that its keys are exactly `RegionRole`'s
// members, so recovering that literal type here is safe.
const REGION_ROLES = Object.keys(REGION_ROLE_RECORD) as RegionRole[];

// ─── Store bridge ─────────────────────────────────────────────────────────

function subscribeSelection(cb: () => void): () => void {
  return selectionStore.subscribe(() => {
    cb();
  });
}
function getSelectionSnapshot() {
  return selectionStore.getState();
}

// ─── Evidence formatting ────────────────────────────────────────────────────

function formatEvidenceValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return JSON.stringify(value);
}

// ─── Component ───────────────────────────────────────────────────────────────

export interface RegionDetailProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
}

export function RegionDetail({ page, projectId, pageIndex }: RegionDetailProps) {
  const state = useSyncExternalStore(
    subscribeSelection,
    getSelectionSnapshot,
    getSelectionSnapshot,
  );
  const { level, path } = state;

  const acceptProposal = useAcceptProposal(projectId, pageIndex);
  const rejectProposal = useRejectProposal(projectId, pageIndex);
  const editRegion = useEditRegion(projectId, pageIndex);
  const deleteRegion = useDeleteRegion(projectId, pageIndex);
  // Whole-branch review defect 1: a keyboard decision (useRegionReviewHotkeys,
  // a separate hook instance) shares its in-flight signal with this panel's
  // own mutations through the mutationKey, so every action button below is
  // also disabled while a keyboard-initiated decision is pending.
  const decisionPending = useRegionDecisionPending(projectId, pageIndex);

  if (level !== "region") {
    return <NotSelected />;
  }

  if (path.proposalId !== undefined) {
    const proposalId = path.proposalId;
    const region = (page.regions ?? []).find((r) => !r.confirmed && r.proposal_id === proposalId);
    if (!region) {
      return <NotFound />;
    }
    const proposal = (page.proposals ?? []).find((p) => p.proposal_id === proposalId);
    return (
      <ProposalDetail
        proposalId={proposalId}
        region={region}
        proposal={proposal}
        acceptProposal={acceptProposal}
        rejectProposal={rejectProposal}
        decisionPending={decisionPending}
      />
    );
  }

  if (path.regionId !== undefined) {
    const regionId = path.regionId;
    const region = (page.regions ?? []).find((r) => r.confirmed && r.region_id === regionId);
    if (!region) {
      return <NotFound />;
    }
    return (
      <ConfirmedRegionDetail
        regionId={regionId}
        region={region}
        editRegion={editRegion}
        deleteRegion={deleteRegion}
        decisionPending={decisionPending}
      />
    );
  }

  return <NotSelected />;
}

// ─── Carried-rejections panel ──────────────────────────────────────────────
//
// Deliberately NOT part of <RegionDetail> above: RightPanel only mounts
// RegionDetail once `selection-store.level === "region"`, which — like
// every other rail target — only happens once a person clicks an actual
// proposal or confirmed region (`selectProposal`/`selectRegion`; pressing
// `5` alone only aims `rail-store.target`, same as every other target key —
// see Rail.tsx's own comment on its region `TargetCell`). A page whose only
// work is a carried rejection has no proposal or region left to click, so
// gating the summary on `level` would make it unreachable in exactly the
// case it exists for. <CarriedRejectionsPanel> is mounted by RightPanel
// unconditionally instead (whenever a page is loaded), independent of
// selection — see RightPanel.tsx.

export interface CarriedRejectionsPanelProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
}

/** A rejected proposal whose latest decision names where it was carried from
 * — the fact this summary exists to surface. Never an ordinary direct
 * rejection (no `carried_from_proposal_id`) and never one already brought
 * back (`disposition` moves off `"rejected"` the moment a `reopened`
 * decision is appended, which is exactly what drops it out of this list). */
function isCarriedRejection(proposal: RegionProposalView): boolean {
  return proposal.disposition === "rejected" && proposal.carried_from_proposal_id != null;
}

export function CarriedRejectionsPanel({
  page,
  projectId,
  pageIndex,
}: CarriedRejectionsPanelProps) {
  const unrejectProposal = useUnrejectProposal(projectId, pageIndex);
  const decisionPending = useRegionDecisionPending(projectId, pageIndex);
  const carriedRejections = (page.proposals ?? []).filter(isCarriedRejection);

  return (
    <CarriedRejectionsSummary
      items={carriedRejections}
      unrejectProposal={unrejectProposal}
      decisionPending={decisionPending}
    />
  );
}

interface CarriedRejectionsSummaryProps {
  items: RegionProposalView[];
  unrejectProposal: ReturnType<typeof useUnrejectProposal>;
  decisionPending: boolean;
}

function CarriedRejectionsSummary({
  items,
  unrejectProposal,
  decisionPending,
}: CarriedRejectionsSummaryProps) {
  const [expanded, setExpanded] = useState(false);

  if (items.length === 0) return null;

  return (
    <div
      data-testid="carried-rejections-summary"
      className="border-b border-border-1 text-[11px] shrink-0"
    >
      <button
        type="button"
        data-testid="carried-rejections-toggle"
        aria-expanded={expanded}
        onClick={() => {
          setExpanded((prev) => !prev);
        }}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-ink-2 hover:text-ink-1 hover:bg-bg-raised/60 transition-colors"
      >
        <span data-testid="carried-rejections-count">
          {items.length} rejected proposal{items.length === 1 ? "" : "s"} carried from an earlier
          decision
        </span>
        <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
      </button>
      {expanded && (
        <ul data-testid="carried-rejections-list" className="flex flex-col">
          {items.map((item) => (
            <CarriedRejectionRow
              key={item.proposal_id}
              item={item}
              unrejectProposal={unrejectProposal}
              decisionPending={decisionPending}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

interface CarriedRejectionRowProps {
  item: RegionProposalView;
  unrejectProposal: ReturnType<typeof useUnrejectProposal>;
  decisionPending: boolean;
}

function CarriedRejectionRow({
  item,
  unrejectProposal,
  decisionPending,
}: CarriedRejectionRowProps) {
  const testSuffix = item.proposal_id;
  const isThisPending =
    unrejectProposal.isPending && unrejectProposal.variables.proposalId === item.proposal_id;
  return (
    <li
      data-testid={`carried-rejections-item-${testSuffix}`}
      className="flex items-center justify-between gap-2 px-3 py-1.5 border-t border-border-1/40"
    >
      <div className="flex flex-col">
        <span className="text-ink-1">{item.role}</span>
        <span className="text-ink-3 font-mono tabular-nums">{item.confidence.toFixed(2)}</span>
      </div>
      <div className="flex flex-col items-end gap-0.5">
        <button
          type="button"
          data-testid={`carried-rejections-bring-back-${testSuffix}`}
          disabled={unrejectProposal.isPending || decisionPending}
          onClick={() => {
            unrejectProposal.mutate({ proposalId: item.proposal_id });
          }}
          className="text-[11px] px-2 py-1 rounded-sm border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
        >
          {isThisPending ? "Bringing back…" : "Bring back"}
        </button>
        {unrejectProposal.isError && unrejectProposal.variables.proposalId === item.proposal_id && (
          <p
            data-testid={`carried-rejections-error-${testSuffix}`}
            className="text-[10px] text-status-mismatch italic"
          >
            Failed. Try again.
          </p>
        )}
      </div>
    </li>
  );
}

function NotSelected() {
  return (
    <div data-testid="region-detail" className="p-3 text-ink-3 text-sm">
      No region selected.
    </div>
  );
}

function NotFound() {
  return (
    <div data-testid="region-detail" className="p-3 text-ink-3 text-sm">
      This region is no longer on the page.
    </div>
  );
}

// ─── Role select ────────────────────────────────────────────────────────────

interface RoleSelectProps {
  testId: string;
  value: RegionRole | "";
  onChange: (role: RegionRole | "") => void;
  disabled?: boolean;
}

function RoleSelect({ testId, value, onChange, disabled }: RoleSelectProps) {
  return (
    <select
      data-testid={testId}
      aria-label="Region role"
      className="text-[11px] border border-border-2 rounded-sm px-1 py-0.5 bg-bg-sunk"
      value={value}
      disabled={disabled}
      onChange={(e) => {
        onChange(e.target.value as RegionRole | "");
      }}
    >
      <option value="" disabled>
        Choose a role…
      </option>
      {REGION_ROLES.map((role) => (
        <option key={role} value={role}>
          {role}
        </option>
      ))}
    </select>
  );
}

// ─── Proposal detail ────────────────────────────────────────────────────────

interface ProposalDetailProps {
  proposalId: string;
  region: RegionView;
  proposal: RegionProposalView | undefined;
  acceptProposal: ReturnType<typeof useAcceptProposal>;
  rejectProposal: ReturnType<typeof useRejectProposal>;
  decisionPending: boolean;
}

function ProposalDetail({
  proposalId,
  region,
  proposal,
  acceptProposal,
  rejectProposal,
  decisionPending,
}: ProposalDetailProps) {
  const [acceptAsRole, setAcceptAsRole] = useState<RegionRole | "">("");
  const evidenceEntries = Object.entries(proposal?.evidence ?? {});

  return (
    <div data-testid="region-detail" className="p-3 flex flex-col gap-3">
      <div>
        <p data-testid="region-detail-role" className="text-ink-1 text-sm font-medium">
          {region.role}
          {region.stale && (
            <span
              data-testid="region-detail-stale-badge"
              className="ml-2 text-[10px] px-1.5 py-0.5 rounded-sm border border-status-fuzzy/60 text-status-fuzzy"
            >
              Stale
            </span>
          )}
        </p>
        <p data-testid="region-detail-confidence" className="text-ink-3 text-[11px]">
          Confidence: {typeof region.confidence === "number" ? region.confidence.toFixed(2) : "—"}
        </p>
      </div>

      <div data-testid="region-detail-evidence" className="flex flex-col gap-0.5">
        <p className="text-[10px] text-ink-3 uppercase tracking-wide">Evidence</p>
        {evidenceEntries.length === 0 ? (
          <p className="text-[11px] text-ink-3">No evidence recorded.</p>
        ) : (
          evidenceEntries.map(([key, value]) => (
            <div
              key={key}
              data-testid={`region-detail-evidence-${key}`}
              className="flex justify-between gap-2 text-[11px] font-mono"
            >
              <span className="text-ink-3">{key}</span>
              <span className="text-ink-1 truncate">{formatEvidenceValue(value)}</span>
            </div>
          ))
        )}
      </div>

      <div className="flex flex-col gap-2">
        <button
          type="button"
          data-testid="region-detail-accept"
          disabled={acceptProposal.isPending || decisionPending}
          onClick={() => {
            acceptProposal.mutate({ proposalId });
          }}
          className="text-[11px] py-1.5 rounded-sm border border-status-exact/60 text-status-exact hover:bg-status-exact/10 transition-colors disabled:opacity-40"
        >
          Accept
        </button>
        {acceptProposal.isError && (
          <p
            data-testid="region-detail-accept-error"
            className="text-[10px] text-status-mismatch italic"
          >
            Accept failed. Try again.
          </p>
        )}

        <div className="flex items-center gap-1.5">
          <RoleSelect
            testId="region-detail-accept-as-select"
            value={acceptAsRole}
            onChange={setAcceptAsRole}
            disabled={acceptProposal.isPending || decisionPending}
          />
          <button
            type="button"
            data-testid="region-detail-accept-as-apply"
            disabled={acceptProposal.isPending || decisionPending || acceptAsRole === ""}
            onClick={() => {
              if (acceptAsRole === "") return;
              acceptProposal.mutate({ proposalId, role: acceptAsRole });
            }}
            className="text-[11px] px-2 py-1 rounded-sm border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
          >
            Accept as
          </button>
        </div>

        <button
          type="button"
          data-testid="region-detail-reject"
          disabled={rejectProposal.isPending || decisionPending}
          onClick={() => {
            rejectProposal.mutate({ proposalId });
          }}
          className="text-[11px] py-1.5 rounded-sm border border-status-mismatch/60 text-status-mismatch hover:bg-status-mismatch/10 transition-colors disabled:opacity-40"
        >
          Reject
        </button>
        {rejectProposal.isError && (
          <p
            data-testid="region-detail-reject-error"
            className="text-[10px] text-status-mismatch italic"
          >
            Reject failed. Try again.
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Confirmed region detail ────────────────────────────────────────────────

interface ConfirmedRegionDetailProps {
  regionId: string;
  region: RegionView;
  editRegion: ReturnType<typeof useEditRegion>;
  deleteRegion: ReturnType<typeof useDeleteRegion>;
  decisionPending: boolean;
}

function ConfirmedRegionDetail({
  regionId,
  region,
  editRegion,
  deleteRegion,
  decisionPending,
}: ConfirmedRegionDetailProps) {
  const [changeRoleValue, setChangeRoleValue] = useState<RegionRole | "">("");
  const origin = region.proposal_id ? "From a proposal" : "Drawn by hand";

  function handleDelete() {
    dialogStore.openConfirm({
      title: "Delete region?",
      body: "This will permanently remove this region. This action cannot be undone.",
      onConfirm: () => {
        deleteRegion.mutate({ regionId });
      },
    });
  }

  return (
    <div data-testid="region-detail" className="p-3 flex flex-col gap-3">
      <div>
        <p data-testid="region-detail-role" className="text-ink-1 text-sm font-medium">
          {region.role}
        </p>
        <p data-testid="region-detail-origin" className="text-ink-3 text-[11px]">
          {origin}
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-1.5">
          <RoleSelect
            testId="region-detail-change-role-select"
            value={changeRoleValue}
            onChange={setChangeRoleValue}
            disabled={editRegion.isPending || decisionPending}
          />
          <button
            type="button"
            data-testid="region-detail-change-role-apply"
            disabled={editRegion.isPending || decisionPending || changeRoleValue === ""}
            onClick={() => {
              if (changeRoleValue === "") return;
              editRegion.mutate({ regionId, role: changeRoleValue });
            }}
            className="text-[11px] px-2 py-1 rounded-sm border border-border-2 text-ink-2 hover:text-ink-1 hover:border-accent transition-colors disabled:opacity-40"
          >
            Change role
          </button>
        </div>
        {editRegion.isError && (
          <p
            data-testid="region-detail-edit-error"
            className="text-[10px] text-status-mismatch italic"
          >
            Update failed. Try again.
          </p>
        )}

        <button
          type="button"
          data-testid="region-detail-delete"
          disabled={deleteRegion.isPending || decisionPending}
          onClick={handleDelete}
          className="text-[11px] py-1.5 rounded-sm border border-status-mismatch/60 text-status-mismatch hover:bg-status-mismatch/10 transition-colors disabled:opacity-40"
        >
          Delete
        </button>
        {deleteRegion.isError && (
          <p
            data-testid="region-detail-delete-error"
            className="text-[10px] text-status-mismatch italic"
          >
            Delete failed. Try again.
          </p>
        )}
      </div>
    </div>
  );
}

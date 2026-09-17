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
// data-testids:
//   region-detail                    — outer container
//   region-detail-role               — role text (proposal or confirmed)
//   region-detail-confidence         — proposal confidence, two decimals
//   region-detail-stale-badge        — shown when the proposal is stale
//   region-detail-evidence-{key}     — one row per evidence entry
//   region-detail-accept             — accept the proposal, no role override
//   region-detail-accept-as-select   — role picker for "accept as"
//   region-detail-accept-as-apply    — apply the "accept as" role
//   region-detail-reject             — reject the proposal
//   region-detail-accept-error       — inline error after a failed accept
//   region-detail-reject-error       — inline error after a failed reject
//   region-detail-origin             — "From a proposal" / "Drawn by hand"
//   region-detail-change-role-select — role picker for a confirmed region
//   region-detail-change-role-apply  — apply the changed role
//   region-detail-edit-error         — inline error after a failed edit
//   region-detail-delete             — delete a confirmed region (confirm-gated)
//   region-detail-delete-error       — inline error after a failed delete

import { useState, useSyncExternalStore } from "react";
import { selectionStore } from "../../stores/selection-store";
import { dialogStore } from "../../stores/dialog-store";
import {
  useAcceptProposal,
  useRejectProposal,
  useEditRegion,
  useDeleteRegion,
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
      />
    );
  }

  return <NotSelected />;
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
}

function ProposalDetail({
  proposalId,
  region,
  proposal,
  acceptProposal,
  rejectProposal,
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
          disabled={acceptProposal.isPending}
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
            disabled={acceptProposal.isPending}
          />
          <button
            type="button"
            data-testid="region-detail-accept-as-apply"
            disabled={acceptProposal.isPending || acceptAsRole === ""}
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
          disabled={rejectProposal.isPending}
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
}

function ConfirmedRegionDetail({
  regionId,
  region,
  editRegion,
  deleteRegion,
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
            disabled={editRegion.isPending}
          />
          <button
            type="button"
            data-testid="region-detail-change-role-apply"
            disabled={editRegion.isPending || changeRoleValue === ""}
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
          disabled={deleteRegion.isPending}
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

// Drawer.tsx — 320px drawer panel with Worklist / Hierarchy / Text tabs and collapse.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11–12.
// Issue #324 (FO-8): use useUiPrefs.subscribe directly; no local bridge Set.
// P5.i Gap 18: tab icons + count badges + collapse chevron.
// S2.2: "Text" tab added — visible full-page GT/OCR read-only view.
//
// - Header: tab strip "Worklist" | "Hierarchy" | "Text" + icons + count badges + collapse button.
// - Body: mounts Worklist (Slice 11), Hierarchy (Slice 12), or Text (S2.2).
// - Collapse state persisted via useUiPrefs.drawerOpen.
// - Active tab persisted via useUiPrefs.drawerTab.

import { useSyncExternalStore } from "react";
import { ChevronLeft, ChevronRight } from "@pdomain/pdomain-ui/icons";
import { List, GitBranch, FileText } from "@/icons/local-shims";
import { cn } from "@/lib/utils";
import { useUiPrefs, type DrawerTab } from "../../stores/ui-prefs";
import { Worklist } from "../drawer/Worklist";
import type { WorklistProps } from "../drawer/Worklist";
import { Hierarchy } from "../drawer/Hierarchy";
import type { HierarchyProps } from "../drawer/Hierarchy";
import { PlaintextGtOcrView } from "../PlaintextGtOcrView";

// ─── Selectors (use useUiPrefs.subscribe directly — store already exposes it) ─

function getDrawerOpen(): boolean {
  return useUiPrefs.getState().drawerOpen;
}
function getDrawerTab(): DrawerTab {
  return useUiPrefs.getState().drawerTab;
}

function setDrawerOpen(open: boolean) {
  useUiPrefs.setState({ drawerOpen: open });
}
function setDrawerTab(tab: DrawerTab) {
  useUiPrefs.setState({ drawerTab: tab });
}

// ─── Tab config ──────────────────────────────────────────────────────────────

interface TabConfig {
  id: DrawerTab;
  label: string;
  testid: string;
  icon: React.ReactNode;
}

const TABS: TabConfig[] = [
  {
    id: "worklist",
    label: "Worklist",
    testid: "drawer-tab-worklist",
    icon: <List size={13} />,
  },
  {
    id: "hierarchy",
    label: "Hierarchy",
    testid: "drawer-tab-hierarchy",
    icon: <GitBranch size={13} />,
  },
  {
    // S2.2: Visible full-page GT/OCR read-only text view.
    id: "text",
    label: "Text",
    testid: "drawer-tab-text",
    icon: <FileText size={13} />,
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export interface DrawerProps extends WorklistProps, HierarchyProps {
  /** Expose a custom class on the outer element (optional). */
  className?: string;
  /** Optional item counts per tab for count badge display (Gap 18). */
  tabCounts?: Partial<Record<DrawerTab, number>>;
  /** S2.2: Full-page ground truth text for the Text tab. */
  pageTextGt?: string | null | undefined;
  /** S2.2: Full-page OCR text for the Text tab. */
  pageTextOcr?: string | null | undefined;
}

export function Drawer({
  lineMatches,
  page,
  projectId,
  pageIndex,
  className,
  tabCounts,
  pageTextGt,
  pageTextOcr,
}: DrawerProps) {
  const open = useSyncExternalStore(useUiPrefs.subscribe, getDrawerOpen, getDrawerOpen);
  const activeTab = useSyncExternalStore(useUiPrefs.subscribe, getDrawerTab, getDrawerTab);

  return (
    <div
      data-testid="drawer"
      data-open={open ? "true" : "false"}
      className={cn(
        "flex flex-col h-full bg-bg-surface border-r border-border-1 overflow-hidden transition-all",
        open ? "w-[320px]" : "w-0",
        className,
      )}
    >
      {open && (
        <>
          {/* Tab strip + collapse button */}
          <div
            data-testid="drawer-header"
            className="flex items-center border-b border-border-1 flex-shrink-0 h-9"
          >
            {TABS.map((tab) => {
              const count = tabCounts?.[tab.id];
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  data-testid={tab.testid}
                  data-active={isActive ? "true" : undefined}
                  onClick={() => {
                    setDrawerTab(tab.id);
                  }}
                  className={cn(
                    "flex-1 h-full text-[11px] font-medium transition-colors px-2",
                    "inline-flex items-center justify-center gap-1.5",
                    isActive
                      ? "text-ink-1 border-b-2 border-accent"
                      : "text-ink-3 hover:text-ink-2",
                  )}
                >
                  {/* Tab icon (Gap 18) */}
                  <span
                    data-testid={`drawer-tab-icon-${tab.id}`}
                    aria-hidden="true"
                    className="flex-shrink-0"
                  >
                    {tab.icon}
                  </span>
                  <span>{tab.label}</span>
                  {/* Count badge (Gap 18) */}
                  {count !== undefined && count > 0 && (
                    <span
                      data-testid={`drawer-tab-count-${tab.id}`}
                      className={cn(
                        "text-[9px] px-1 rounded-full leading-none py-0.5 font-semibold tabular-nums",
                        isActive ? "bg-accent text-accent-ink" : "bg-bg-raised text-ink-3",
                      )}
                    >
                      {count}
                    </span>
                  )}
                </button>
              );
            })}

            {/* Collapse button */}
            <button
              type="button"
              data-testid="drawer-collapse-btn"
              onClick={() => {
                setDrawerOpen(false);
              }}
              aria-label="Collapse drawer"
              className="w-8 h-full flex items-center justify-center text-ink-3 hover:text-ink-1 flex-shrink-0"
            >
              <ChevronLeft size={14} />
            </button>
          </div>

          {/* Body — mount active tab content */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {activeTab === "worklist" ? (
              <Worklist lineMatches={lineMatches} projectId={projectId} pageIndex={pageIndex} />
            ) : activeTab === "hierarchy" ? (
              <Hierarchy page={page} />
            ) : (
              /* S2.2: Visible full-page GT/OCR read-only text view */
              <PlaintextGtOcrView pageTextGt={pageTextGt} pageTextOcr={pageTextOcr} />
            )}
          </div>
        </>
      )}

      {/* Expand button (visible when collapsed) */}
      {!open && (
        <button
          type="button"
          data-testid="drawer-expand-btn"
          onClick={() => {
            setDrawerOpen(true);
          }}
          aria-label="Expand drawer"
          className="w-full flex items-center justify-center text-ink-3 hover:text-ink-1 py-2"
        >
          <ChevronRight size={14} />
        </button>
      )}
    </div>
  );
}

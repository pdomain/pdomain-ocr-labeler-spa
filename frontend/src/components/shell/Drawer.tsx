// Drawer.tsx — 260px drawer panel with Worklist / Hierarchy tabs and collapse.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11.
//
// - Header: tab strip "Worklist" | "Hierarchy" + collapse button.
// - Body: mounts Worklist (Slice 11) or Hierarchy (Slice 12, placeholder here).
// - Collapse state persisted via useUiPrefs.drawerOpen.
// - Active tab persisted via useUiPrefs.drawerTab.

import { useSyncExternalStore } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUiPrefs, type DrawerTab } from "../../stores/ui-prefs";
import { Worklist } from "../drawer/Worklist";
import type { WorklistProps } from "../drawer/Worklist";

// ─── Subscriber bridge for useUiPrefs (mirrors Splitter/FilterToggle pattern) ─

const uiPrefsSubscribers = new Set<() => void>();
function notifyUiPrefs() {
  uiPrefsSubscribers.forEach((fn) => fn());
}
function subscribeUiPrefs(cb: () => void): () => void {
  uiPrefsSubscribers.add(cb);
  return () => {
    uiPrefsSubscribers.delete(cb);
  };
}

function getDrawerOpen(): boolean {
  return useUiPrefs.getState().drawerOpen;
}
function getDrawerTab(): DrawerTab {
  return useUiPrefs.getState().drawerTab;
}

function setDrawerOpen(open: boolean) {
  useUiPrefs.setState({ drawerOpen: open });
  notifyUiPrefs();
}
function setDrawerTab(tab: DrawerTab) {
  useUiPrefs.setState({ drawerTab: tab });
  notifyUiPrefs();
}

// ─── Tab config ──────────────────────────────────────────────────────────────

interface TabConfig {
  id: DrawerTab;
  label: string;
  testid: string;
}

const TABS: TabConfig[] = [
  { id: "worklist", label: "Worklist", testid: "drawer-tab-worklist" },
  { id: "hierarchy", label: "Hierarchy", testid: "drawer-tab-hierarchy" },
];

// ─── Component ────────────────────────────────────────────────────────────────

export interface DrawerProps extends WorklistProps {
  /** Expose a custom class on the outer element (optional). */
  className?: string;
}

export function Drawer({ lineMatches, className }: DrawerProps) {
  const open = useSyncExternalStore(subscribeUiPrefs, getDrawerOpen, getDrawerOpen);
  const activeTab = useSyncExternalStore(subscribeUiPrefs, getDrawerTab, getDrawerTab);

  return (
    <div
      data-testid="drawer"
      data-open={open ? "true" : "false"}
      className={cn(
        "flex flex-col h-full bg-bg-surface border-r border-border-1 overflow-hidden transition-all",
        open ? "w-[260px]" : "w-0",
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
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                data-testid={tab.testid}
                data-active={activeTab === tab.id ? "true" : undefined}
                onClick={() => setDrawerTab(tab.id)}
                className={cn(
                  "flex-1 h-full text-[11px] font-medium transition-colors px-2",
                  activeTab === tab.id
                    ? "text-ink-1 border-b-2 border-accent"
                    : "text-ink-3 hover:text-ink-2",
                )}
              >
                {tab.label}
              </button>
            ))}

            {/* Collapse button */}
            <button
              type="button"
              data-testid="drawer-collapse-btn"
              onClick={() => setDrawerOpen(false)}
              aria-label="Collapse drawer"
              className="w-8 h-full flex items-center justify-center text-ink-3 hover:text-ink-1 flex-shrink-0"
            >
              <ChevronLeft size={14} />
            </button>
          </div>

          {/* Body — mount active tab content */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {activeTab === "worklist" ? (
              <Worklist lineMatches={lineMatches} />
            ) : (
              // Hierarchy tab placeholder — filled in Slice 12.
              <div
                data-testid="drawer-hierarchy-placeholder"
                className="p-4 text-ink-3 text-[11px]"
              >
                Coming soon
              </div>
            )}
          </div>
        </>
      )}

      {/* Expand button (visible when collapsed) */}
      {!open && (
        <button
          type="button"
          data-testid="drawer-expand-btn"
          onClick={() => setDrawerOpen(true)}
          aria-label="Expand drawer"
          className="w-full flex items-center justify-center text-ink-3 hover:text-ink-1 py-2"
        >
          <ChevronRight size={14} />
        </button>
      )}
    </div>
  );
}

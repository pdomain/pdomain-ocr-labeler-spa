// HotkeyHelpModal.tsx — ? help modal listing all registered hotkeys.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Hotkey help modal
//       specs/22-page-surface-wireup.md §5 (uses dialog store)
//       docs/specs/2026-05-15-hifi-redesign-plan.md Slice 25 (KeyCap + registry)
// Issues: #235 (initial), #309 (spec-22-A — wire to dialog store)
//
// Opens when ? is pressed outside a form input, OR when something calls
// `dialogStore.open('hotkeyHelp')` (e.g. the HeaderBar trigger button).
// Reads from HOTKEY_MAP (legacy scope groups) and the new hotkey-registry
// (grouped sections with KeyCap components).
// testid: hotkey-help-dialog

import { useSyncExternalStore } from "react";
import { useHotkey } from "../hooks/useHotkey";
import { dialogStore, useDialogStore } from "../stores/dialog-store";
import { KeyCap } from "./ui/KeyCap";
import {
  getPopulatedGroups,
  subscribeRegistry,
  type RegistryEntry,
  type HotkeyGroupDef,
} from "../lib/hotkey-registry";

// ─── Registry hook ───────────────────────────────────────────────────────────

function useHotkeyGroups(): HotkeyGroupDef[] {
  return useSyncExternalStore(subscribeRegistry, getPopulatedGroups, getPopulatedGroups);
}

// ─── KeyCap row ──────────────────────────────────────────────────────────────

function HotkeyRow({ entry }: { entry: RegistryEntry }) {
  return (
    <tr className="hover:bg-bg-raised/40">
      <td className="py-1 pr-4 whitespace-nowrap w-48">
        <span className="inline-flex items-center gap-1 flex-wrap">
          {entry.keyCaps.map((k, i) => (
            <KeyCap key={i} keys={k} />
          ))}
        </span>
      </td>
      <td className="py-1 text-ink-2 text-body">{entry.label}</td>
    </tr>
  );
}

// ─── Group section ───────────────────────────────────────────────────────────

function GroupSection({ group }: { group: HotkeyGroupDef }) {
  return (
    <section key={group.id} data-testid={`hotkey-group-${group.id}`}>
      <h3 className="text-[10px] font-semibold text-ink-3 uppercase tracking-wider mb-1.5 mt-3 first:mt-0">
        {group.label}
      </h3>
      <table className="w-full" data-testid={`hotkey-group-table-${group.id}`}>
        <tbody>
          {group.entries.map((entry, i) => (
            <HotkeyRow key={i} entry={entry} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

// ─── Modal ───────────────────────────────────────────────────────────────────

/**
 * Hotkey help modal.
 *
 * Register this component once near the top of the component tree so the
 * `?` listener is always active. Open-state lives in `useDialogStore` so
 * other UI surfaces (HeaderBar trigger button, future programmatic
 * callers) can open the same dialog without prop drilling.
 */
export function HotkeyHelpModal() {
  const open = useDialogStore((s) => s.hotkeyHelp.open);
  const groups = useHotkeyGroups();

  // ? key opens help outside inputs (enableOnFormTags: false is default)
  useHotkey("?", () => {
    dialogStore.open("hotkeyHelp");
  });
  // Esc closes when open
  useHotkey(
    "escape",
    () => {
      dialogStore.close("hotkeyHelp");
    },
    { enabled: open },
  );

  if (!open) return null;

  const close = () => {
    dialogStore.close("hotkeyHelp");
  };

  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- dialog backdrop click-to-dismiss; Esc handled via useHotkey above
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      data-testid="hotkey-help-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="bg-bg-surface rounded-lg max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col border border-border-2">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-1">
          <h2 className="text-heading font-semibold text-ink-1">Keyboard Shortcuts</h2>
          <button
            data-testid="hotkey-help-close"
            onClick={close}
            className="text-ink-3 hover:text-ink-1 text-lg leading-none transition-colors"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Scrollable grouped sections */}
        <div className="overflow-y-auto px-4 py-3">
          {groups.map((group) => (
            <GroupSection key={group.id} group={group} />
          ))}
        </div>
      </div>
    </div>
  );
}

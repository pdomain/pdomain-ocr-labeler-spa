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
//
// Chrome is now backed by pdomain-ui's Radix Dialog suite (@pdomain/pdomain-ui/primitives).
// Radix provides a native focus trap and Escape key handling — the manual Esc
// useHotkey handler has been removed.
// testid: hotkey-help-dialog

import { useSyncExternalStore } from "react";
import { useHotkey } from "../hooks/useHotkey";
import { dialogStore, useDialogStore } from "../stores/dialog-store";
import { KeyCap } from "@pdomain/pdomain-ui/primitives";
import {
  getPopulatedGroups,
  subscribeRegistry,
  type RegistryEntry,
  type HotkeyGroupDef,
} from "../lib/hotkey-registry";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@pdomain/pdomain-ui/primitives";

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
 * Hotkey help modal, backed by pdomain-ui's Radix Dialog suite.
 *
 * Register this component once near the top of the component tree so the
 * `?` listener is always active. Open-state lives in `useDialogStore` so
 * other UI surfaces (HeaderBar trigger button, future programmatic
 * callers) can open the same dialog without prop drilling.
 *
 * Escape is handled natively by Radix Dialog — no manual Esc useHotkey needed.
 */
export function HotkeyHelpModal() {
  const open = useDialogStore((s) => s.hotkeyHelp.open);
  const groups = useHotkeyGroups();
  const close = () => dialogStore.close("hotkeyHelp");

  // ? key opens help outside inputs (enableOnFormTags: false is default).
  //
  // Registered by *character* (`useKey: true`, matching `KeyboardEvent.key`)
  // rather than by physical code. A code-based "shift+slash" (the first fix
  // here) only matches the US-layout position of "?" — on a German or
  // French keyboard a different physical key produces "?", so a code-based
  // binding is dead there while the key that actually types "?" does
  // nothing. `useKey: true` matches what the user typed, not where their
  // fingers were, so it works on every layout. This is the deliberate
  // exception to the physical-code convention used elsewhere in this file
  // and in hotkeyMap.ts (bracketleft/bracketright, mod+o, …) — those are
  // navigation keys where physical position IS the point (see
  // useRegionReviewHotkeys.ts); "?" is a character the user is asking for,
  // not a position.
  useHotkey(
    "shift+?",
    () => {
      dialogStore.open("hotkeyHelp");
    },
    { useKey: true },
  );
  // NOTE: No manual Esc useHotkey — Radix Dialog handles Escape natively.

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) close();
      }}
    >
      {/* DialogContent auto-composes DialogPortal + DialogOverlay (pdomain-ui convention).
          primitives.css DOES define ".dialog" (positioning + chrome); the
          Tailwind classes below only add labeler-specific sizing/color on top
          of it — they must not re-supply positioning (see note below). */}
      <DialogContent
        data-testid="hotkey-help-dialog"
        // pdomain-ui's shared ".dialog" class (primitives.css) already supplies
        // `position: fixed; top/left: 50%; transform: translate(-50%, -50%)` for
        // centering. Do NOT repeat `fixed`/`top-1/2`/`left-1/2`/`-translate-*`
        // here — Tailwind's translate utilities set the CSS `translate`
        // longhand, which composes *in addition to* (not instead of) the
        // `.dialog` class's `transform` shorthand, doubling the offset and
        // pushing the dialog off-screen (see HotkeyHelpModal.test.tsx).
        className="max-w-2xl w-full mx-4 max-h-[80vh] bg-bg-surface rounded-lg border border-border-2 shadow-lg focus:outline-hidden flex flex-col p-0"
      >
        {/* Header */}
        <DialogHeader className="flex flex-row items-center justify-between px-4 py-3 border-b border-border-1">
          <DialogTitle className="text-heading font-semibold text-ink-1">
            Keyboard Shortcuts
          </DialogTitle>
          <DialogClose
            data-testid="hotkey-help-close"
            className="text-ink-3 hover:text-ink-1 text-lg leading-none transition-colors"
            aria-label="Close"
          >
            ×
          </DialogClose>
        </DialogHeader>

        {/* Scrollable grouped sections */}
        <div className="overflow-y-auto px-4 py-3">
          {groups.map((group) => (
            <GroupSection key={group.id} group={group} />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

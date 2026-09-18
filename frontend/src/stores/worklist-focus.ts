// worklist-focus.ts — single entry point for "focus this worklist line".
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 11, Slice 15.
// Issue: docs/issues/2026-07-21-match-nav-selection-desync.md (P1-MATCH-NAV).
//
// A worklist row click used to dual-write `worklistStore.selectedLineIndex`
// and `selectionStore` (via `selectLine`) directly, while the matches J/K
// hotkeys only wrote `worklistStore.selectedLineIndex`. That let the two
// stores drift: the worklist queue highlight moved, but the canvas,
// breadcrumb, and right panel (which read `selectionStore`) did not follow,
// and action hotkeys (V/U/D/O/G/M/R) could mutate a line the rest of the UI
// did not show as selected.
//
// `focusWorklistLine` is the one function both the Worklist row click and
// the matches J/K hotkey handler call, so the two stores cannot drift apart
// again — there is only one place that performs the pair of updates.

import { worklistStore } from "./worklist-store";
import { selectLine } from "./selection-store";
import { useUiPrefs } from "./ui-prefs";

/**
 * Focus a line for editing: set it as the worklist's current line, select it
 * in the hierarchical selection store (canvas / breadcrumb / right panel),
 * and reveal the right panel if it was collapsed (STB-4).
 *
 * Matches the Worklist row-click dual-write exactly — call this instead of
 * writing `worklistStore` and `selectionStore` separately, so keyboard
 * navigation and pointer navigation always stay in sync.
 *
 * `pageIndex` (0-based) is the page `lineIndex` belongs to — stamped onto
 * the selection so a later page change can tell it apart from a line
 * selected on the page now loaded (P2-SELECTION-PAGE).
 */
export function focusWorklistLine(pageIndex: number, lineIndex: number): void {
  worklistStore.setSelectedLineIndex(lineIndex);
  selectLine(pageIndex, lineIndex);
  useUiPrefs.setState({ rightPanelOpen: true });
}

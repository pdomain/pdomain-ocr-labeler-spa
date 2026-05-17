// useMatchesHotkeys.ts — matches-scope hotkeys (#237)
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Matches scope
//
// Matches hotkeys (fire at document scope, not inside GT inputs):
//   J/K          — next/prev line card (onLineNav(±1))
//   V/U          — validate/unvalidate current selection
//   D            — delete with confirm
//   R/Shift+R    — refine / expand+refine
//   M            — merge
//   O/G          — OCR→GT / GT→OCR copy
//
// Tab/Shift+Tab and Esc inside GT inputs are handled by the GT input
// itself (enableOnFormTags: ["INPUT"]) — see WordCell.

import { useHotkey } from "./useHotkey";

interface UseMatchesHotkeysOptions {
  /** Disable all matches hotkeys (e.g. when a modal is open). */
  enabled?: boolean;
  /** Called with +1 (next line) or -1 (prev line). */
  onLineNav: (delta: number) => void;
  onValidate: () => void;
  onUnvalidate: () => void;
  /** Called for Delete; caller is responsible for showing a confirm dialog. */
  onDelete: () => void;
  onRefine: () => void;
  onExpandRefine: () => void;
  onMerge: () => void;
  onOcrToGt: () => void;
  onGtToOcr: () => void;
}

/**
 * Register matches-scope hotkeys.
 *
 * Call this hook inside the component that owns the word-match list
 * (TextTabs / WordMatchView pane).
 */
export function useMatchesHotkeys({
  enabled = true,
  onLineNav,
  onValidate,
  onUnvalidate,
  onDelete,
  onRefine,
  onExpandRefine,
  onMerge,
  onOcrToGt,
  onGtToOcr,
}: UseMatchesHotkeysOptions): void {
  useHotkey(
    "j",
    () => {
      onLineNav(1);
    },
    { enabled },
  );
  useHotkey(
    "k",
    () => {
      onLineNav(-1);
    },
    { enabled },
  );
  useHotkey(
    "v",
    () => {
      onValidate();
    },
    { enabled },
  );
  useHotkey(
    "u",
    () => {
      onUnvalidate();
    },
    { enabled },
  );
  useHotkey(
    "d",
    () => {
      onDelete();
    },
    { enabled },
  );
  useHotkey(
    "r",
    () => {
      onRefine();
    },
    { enabled },
  );
  useHotkey(
    "shift+r",
    () => {
      onExpandRefine();
    },
    { enabled },
  );
  useHotkey(
    "m",
    () => {
      onMerge();
    },
    { enabled },
  );
  useHotkey(
    "o",
    () => {
      onOcrToGt();
    },
    { enabled },
  );
  useHotkey(
    "g",
    () => {
      onGtToOcr();
    },
    { enabled },
  );
}

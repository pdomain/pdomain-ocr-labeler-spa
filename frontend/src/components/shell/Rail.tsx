// Rail.tsx — 64px vertical left rail: target (B/L/W/P) + mode (V/R/A/E) selectors.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
// Hi-fi gaps P1.d (Gaps 10,11,12), P1.e (Gaps 11,13,15), P1.f (Gap 14).
//
// Sections:
//   MODE  — View / Refine / Annotate / Erase icon-card cells
//   TARGET — Block / Para / Line / Word cells with layer-color swatches
//   LAYERS — visibility toggles for each layer (from useLayerColors + useUiPrefs)
//   Footer  — Bulk + Hotkeys buttons
//
// Active target button: bg-bg-raised + 2px left accent stripe + layer-color glyph.
// Active mode button: same active treatment.
// Hotkeys: 1/2/3/4 (target), V/R/A/E (mode) — wired via useRailHotkeys.
//
// SEL-3 (bidirectional): rail-target buttons drive uiPrefs.selectionMode.
// The "block" target has no selectionMode counterpart — clicking block leaves
// selectionMode unchanged (rather than picking an arbitrary "nearest" value,
// which could confuse the user). The three others map 1:1:
// para→"paragraph", line→"line", word→"word".

import { useSyncExternalStore } from "react";
import { Eye, Plus } from "@pdomain/pdomain-ui/icons";
import { ModeErase } from "@pdomain/pdomain-ui/icons";
import { Square, Keyboard, LayoutList } from "@/icons/local-shims";
import { railStore, type RailTarget, type RailMode } from "../../stores/rail-store";
import { useRailHotkeys } from "../../hooks/useRailHotkeys";
import { useLayerColors } from "../../hooks/useLayerColors";
import { dialogStore } from "../../stores/dialog-store";
import { useUiPrefs, type LayerVisibility } from "../../stores/ui-prefs";
import { cn } from "@/lib/utils";

// ─── Mode icon + label lookup ─────────────────────────────────────────────────

const MODE_ICONS: Record<RailMode, React.ReactNode> = {
  view: <Eye size={16} aria-hidden="true" />,
  region: <Square size={16} aria-hidden="true" />,
  annotate: <Plus size={16} aria-hidden="true" />,
  erase: <ModeErase size={16} aria-hidden="true" />,
};

const MODE_LABELS: Record<RailMode, string> = {
  view: "View",
  region: "Refine",
  annotate: "Annotate",
  erase: "Erase",
};

// ─── Target layer color CSS class lookup ─────────────────────────────────────

const targetLayerClass: Record<RailTarget, string> = {
  block: "text-layer-block",
  para: "text-layer-para",
  line: "text-layer-line",
  word: "text-layer-word",
};

const targetLayerBorderClass: Record<RailTarget, string> = {
  block: "border border-layer-block",
  para: "border border-layer-para",
  line: "border border-layer-line",
  word: "border border-layer-word",
};

const TARGET_LABELS: Record<RailTarget, string> = {
  block: "Block",
  para: "Para",
  line: "Line",
  word: "Word",
};

const TARGET_HOTKEYS: Record<RailTarget, string> = {
  block: "1",
  para: "2",
  line: "3",
  word: "4",
};

// ─── Section label ────────────────────────────────────────────────────────────

function SectionLabel({ label }: { label: string }) {
  return (
    <div className="px-2 pt-2 pb-0.5 text-[9px] font-bold tracking-widest uppercase text-ink-3 select-none">
      {label}
    </div>
  );
}

// ─── Mode icon-card cell ──────────────────────────────────────────────────────

interface ModeCardProps {
  mode: RailMode;
  active: boolean;
  onClick: () => void;
}

function ModeCard({ mode, active, onClick }: ModeCardProps) {
  const testid = `rail-mode-${mode === "region" ? "region" : mode}`;
  return (
    <button
      type="button"
      data-testid={testid}
      data-active={active ? "true" : undefined}
      title={`${MODE_LABELS[mode]} mode (${mode === "view" ? "V" : mode === "region" ? "R" : mode === "annotate" ? "A" : "E"})`}
      aria-label={`${MODE_LABELS[mode]} mode`}
      onClick={onClick}
      className={cn(
        "relative w-full flex flex-col items-center justify-center gap-0.5 py-2 select-none transition-colors text-[10px] font-medium",
        active
          ? cn(
              "bg-bg-sunk text-ink-1",
              "before:absolute before:left-0 before:top-0 before:bottom-0 before:w-0.5 before:bg-accent",
            )
          : "text-ink-3 hover:text-ink-2 hover:bg-bg-raised/50",
      )}
    >
      {MODE_ICONS[mode]}
      <span className="leading-none">{MODE_LABELS[mode]}</span>
    </button>
  );
}

// ─── Target swatch cell ───────────────────────────────────────────────────────

interface TargetCellProps {
  target: RailTarget;
  active: boolean;
  swatchColor: string;
  onClick: () => void;
}

function TargetCell({ target, active, swatchColor, onClick }: TargetCellProps) {
  const testid = `rail-target-${target}`;
  return (
    <button
      type="button"
      data-testid={testid}
      data-active={active ? "true" : undefined}
      title={`${TARGET_LABELS[target]} target (${TARGET_HOTKEYS[target]})`}
      aria-label={`${TARGET_LABELS[target]} target`}
      onClick={onClick}
      className={cn(
        "relative w-full flex items-center gap-2 px-2 py-1.5 select-none transition-colors text-[11px]",
        active
          ? cn(
              "bg-bg-raised font-semibold",
              "before:absolute before:left-0 before:top-0 before:bottom-0 before:w-0.5 before:bg-accent",
              targetLayerClass[target],
              targetLayerBorderClass[target],
            )
          : "text-ink-3 hover:text-ink-2 hover:bg-bg-raised/50",
      )}
    >
      {/* Color swatch */}
      <span
        className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
        style={{ background: swatchColor }}
        aria-hidden="true"
      />
      <span>{TARGET_LABELS[target]}</span>
    </button>
  );
}

// ─── Layer visibility toggle ─────────────────────────────────────────────────

interface LayerToggleRowProps {
  testId: string;
  label: string;
  color: string;
  visible: boolean;
  onToggle: () => void;
}

function LayerToggleRow({ testId, label, color, visible, onToggle }: LayerToggleRowProps) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={visible}
      aria-label={`${visible ? "Hide" : "Show"} ${label} layer`}
      title={`${visible ? "Hide" : "Show"} ${label} layer`}
      onClick={onToggle}
      className={cn(
        "flex items-center gap-2 px-2 py-1 text-[10px] select-none text-left transition-colors hover:bg-bg-raised/50",
        visible ? "text-ink-2" : "text-ink-3 opacity-45",
      )}
    >
      <span
        className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
        style={{ background: color, opacity: visible ? 1 : 0.35 }}
        aria-hidden="true"
      />
      <span>{label}</span>
    </button>
  );
}

// ─── Rail ────────────────────────────────────────────────────────────────────

export function Rail() {
  // Wire hotkeys (registers document-level keydown listener).
  useRailHotkeys();

  // Subscribe to rail store via useSyncExternalStore for React 18+.
  const state = useSyncExternalStore(railStore.subscribe, railStore.getState, railStore.getState);
  const layerVisibility = useSyncExternalStore(
    useUiPrefs.subscribe,
    () => useUiPrefs.getState().layerVisibility,
    () => useUiPrefs.getState().layerVisibility,
  );

  const { target, mode, setTarget, setMode } = state;

  // Layer colors for swatches.
  const layerColors = useLayerColors();

  function toggleLayer(layer: keyof LayerVisibility) {
    useUiPrefs.setState((prefs) => ({
      layerVisibility: {
        ...prefs.layerVisibility,
        [layer]: !prefs.layerVisibility[layer],
      },
    }));
  }

  // SEL-3 (bidirectional sync, rail→pref): set railStore.target AND sync
  // uiPrefs.selectionMode. "block" has no selectionMode counterpart —
  // leave selectionMode unchanged when the user picks block, so it
  // continues to reflect the last word/line/para mode rather than going
  // blank or picking arbitrarily.
  function handleSetTarget(t: RailTarget) {
    setTarget(t);
    if (t === "para") {
      useUiPrefs.setState({ selectionMode: "paragraph" });
    } else if (t === "line" || t === "word") {
      useUiPrefs.setState({ selectionMode: t });
    }
    // t === "block": no selectionMode update — block has no radio counterpart.
  }

  return (
    <div
      data-testid="rail"
      className="flex flex-col h-full w-16 bg-bg-surface border-r border-border-1 overflow-y-auto"
    >
      {/* MODE section */}
      <SectionLabel label="MODE" />
      <div className="flex flex-col border-b border-border-1 pb-1">
        {(["view", "region", "annotate", "erase"] as RailMode[]).map((m) => (
          <ModeCard
            key={m}
            mode={m}
            active={mode === m}
            onClick={() => {
              setMode(m);
            }}
          />
        ))}
      </div>

      {/* TARGET section */}
      <SectionLabel label="TARGET" />
      <div className="flex flex-col border-b border-border-1 pb-1">
        <TargetCell
          target="block"
          active={target === "block"}
          swatchColor={layerColors.block}
          onClick={() => {
            handleSetTarget("block");
          }}
        />
        <TargetCell
          target="para"
          active={target === "para"}
          swatchColor={layerColors.para}
          onClick={() => {
            handleSetTarget("para");
          }}
        />
        <TargetCell
          target="line"
          active={target === "line"}
          swatchColor={layerColors.line}
          onClick={() => {
            handleSetTarget("line");
          }}
        />
        <TargetCell
          target="word"
          active={target === "word"}
          swatchColor={layerColors.word}
          onClick={() => {
            handleSetTarget("word");
          }}
        />
      </div>

      {/* LAYERS visibility section */}
      <SectionLabel label="LAYERS" />
      <div className="flex flex-col border-b border-border-1 pb-1">
        <LayerToggleRow
          testId="rail-layer-block"
          label="Block"
          color={layerColors.block}
          visible={layerVisibility.block}
          onToggle={() => {
            toggleLayer("block");
          }}
        />
        <LayerToggleRow
          testId="rail-layer-para"
          label="¶Para"
          color={layerColors.para}
          visible={layerVisibility.paragraph}
          onToggle={() => {
            toggleLayer("paragraph");
          }}
        />
        <LayerToggleRow
          testId="rail-layer-line"
          label="Line"
          color={layerColors.line}
          visible={layerVisibility.line}
          onToggle={() => {
            toggleLayer("line");
          }}
        />
        <LayerToggleRow
          testId="rail-layer-word"
          label="Word"
          color={layerColors.word}
          visible={layerVisibility.word}
          onToggle={() => {
            toggleLayer("word");
          }}
        />
      </div>

      {/* Footer — Bulk + Hotkeys */}
      <div className="mt-auto flex flex-col gap-1 p-1 border-t border-border-1">
        <button
          type="button"
          data-testid="rail-bulk-button"
          title="Bulk actions"
          aria-label="Bulk actions"
          onClick={() => {
            // Open drawer to the worklist tab so the BulkActions bar is visible.
            // TODO: add a dedicated "enter bulk mode" flag to worklistStore when
            //       the multi-select UI needs to be activated programmatically.
            useUiPrefs.setState({ drawerOpen: true, drawerTab: "worklist" });
          }}
          className="w-full flex flex-col items-center justify-center gap-0.5 py-1.5 rounded text-[9px] font-medium text-ink-3 hover:text-ink-2 hover:bg-bg-raised/50 transition-colors select-none"
        >
          <LayoutList size={14} aria-hidden="true" />
          <span>Bulk</span>
        </button>
        <button
          type="button"
          data-testid="rail-hotkeys-button"
          title="Keyboard shortcuts (?)"
          aria-label="Keyboard shortcuts"
          onClick={() => {
            dialogStore.open("hotkeyHelp");
          }}
          className="w-full flex flex-col items-center justify-center gap-0.5 py-1.5 rounded text-[9px] font-medium text-ink-3 hover:text-ink-2 hover:bg-bg-raised/50 transition-colors select-none"
        >
          <Keyboard size={14} aria-hidden="true" />
          <span>Hotkeys</span>
        </button>
      </div>
    </div>
  );
}

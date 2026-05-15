// Rail.tsx — 64px vertical left rail: target (B/L/W) + mode (V/R/A/E) selectors.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 10.
//
// Active target button: bg-bg-raised + 2px left accent stripe + layer-color glyph.
// Active mode button: same active treatment.
// Hotkeys: 1/2/3 (target), V/R/A/E (mode) — wired via useRailHotkeys.

import { useSyncExternalStore } from "react";
import { railStore, type RailTarget } from "../../stores/rail-store";
import { useRailHotkeys } from "../../hooks/useRailHotkeys";
import { cn } from "@/lib/utils";

// ─── Static lookup maps (no Tailwind string interpolation) ───────────────────

const targetLayerClass: Record<RailTarget, string> = {
  block: "text-layer-block",
  line: "text-layer-line",
  word: "text-layer-word",
};

// Layer-color border for active target buttons (B/L/W).
const targetLayerBorderClass: Record<RailTarget, string> = {
  block: "border border-layer-block",
  line: "border border-layer-line",
  word: "border border-layer-word",
};

// ─── Rail button primitives ───────────────────────────────────────────────────

interface RailBtnProps {
  label: string;
  testid: string;
  active: boolean;
  onClick: () => void;
  colorClass?: string;
  /** Optional border class applied in active state (e.g. layer-color border). */
  activeBorderClass?: string;
  title?: string;
}

function RailBtn({
  label,
  testid,
  active,
  onClick,
  colorClass,
  activeBorderClass,
  title,
}: RailBtnProps) {
  return (
    <button
      type="button"
      data-testid={testid}
      data-active={active ? "true" : undefined}
      title={title}
      onClick={onClick}
      className={cn(
        "relative w-full h-10 flex items-center justify-center text-[11px] font-bold select-none transition-colors",
        active
          ? cn(
              "bg-bg-raised",
              "before:absolute before:left-0 before:top-0 before:bottom-0 before:w-0.5 before:bg-accent",
              colorClass ?? "text-ink-1",
              activeBorderClass,
            )
          : "text-ink-3 hover:text-ink-2 hover:bg-bg-raised/50",
      )}
    >
      {label}
    </button>
  );
}

// ─── Rail ────────────────────────────────────────────────────────────────────

export function Rail() {
  // Wire hotkeys (registers document-level keydown listener).
  useRailHotkeys();

  // Subscribe to rail store via useSyncExternalStore for React 18+.
  const state = useSyncExternalStore(railStore.subscribe, railStore.getState, railStore.getState);

  const { target, mode, setTarget, setMode } = state;

  return (
    <div
      data-testid="rail"
      className="flex flex-col h-full w-16 bg-bg-surface border-r border-border-1"
    >
      {/* Target group: B / L / W */}
      <div className="flex flex-col border-b border-border-1">
        <RailBtn
          label="B"
          testid="rail-target-block"
          active={target === "block"}
          colorClass={targetLayerClass.block}
          activeBorderClass={targetLayerBorderClass.block}
          title="Block target (1)"
          onClick={() => setTarget("block")}
        />
        <RailBtn
          label="L"
          testid="rail-target-line"
          active={target === "line"}
          colorClass={targetLayerClass.line}
          activeBorderClass={targetLayerBorderClass.line}
          title="Line target (2)"
          onClick={() => setTarget("line")}
        />
        <RailBtn
          label="W"
          testid="rail-target-word"
          active={target === "word"}
          colorClass={targetLayerClass.word}
          activeBorderClass={targetLayerBorderClass.word}
          title="Word target (3)"
          onClick={() => setTarget("word")}
        />
      </div>

      {/* Mode group: V / R / A / E */}
      <div className="flex flex-col mt-1">
        <RailBtn
          label="V"
          testid="rail-mode-view"
          active={mode === "view"}
          title="View mode (V)"
          onClick={() => setMode("view")}
        />
        <RailBtn
          label="R"
          testid="rail-mode-region"
          active={mode === "region"}
          title="Region mode (R)"
          onClick={() => setMode("region")}
        />
        <RailBtn
          label="A"
          testid="rail-mode-annotate"
          active={mode === "annotate"}
          title="Annotate mode (A)"
          onClick={() => setMode("annotate")}
        />
        <RailBtn
          label="E"
          testid="rail-mode-erase"
          active={mode === "erase"}
          title="Erase mode (E)"
          onClick={() => setMode("erase")}
        />
      </div>
    </div>
  );
}

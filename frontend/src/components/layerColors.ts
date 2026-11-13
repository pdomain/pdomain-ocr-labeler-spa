import type { LayerColorSpec } from "../hooks/useLayerColors";

export type LayerName =
  | "blocks"
  | "paragraphs"
  | "lines"
  | "words"
  | "regions-confirmed"
  | "regions-proposed"
  | "regions-selected"
  | "drag-rect"
  | "selection-paragraphs"
  | "selection-lines"
  | "selection-words";

export const LAYER_COLORS: Record<LayerName, LayerColorSpec> = {
  blocks: {
    fill: "rgba(168,144,116,0.20)",
    stroke: "rgba(168,144,116,0.65)",
    strokeWidth: 1,
  },
  paragraphs: {
    fill: "rgba(34,197,94,0.20)",
    stroke: "rgba(22,163,74,0.65)",
    strokeWidth: 1,
  },
  lines: {
    fill: "rgba(236,72,153,0.20)",
    stroke: "rgba(190,24,93,0.65)",
    strokeWidth: 1,
  },
  words: {
    fill: "rgba(59,130,246,0.18)",
    stroke: "rgba(29,78,216,0.65)",
    strokeWidth: 1,
  },
  // Region layers (Task 7, region-routes-and-proposal-run): a confirmed
  // region is a person's decision — solid, saturated amber, heavier stroke,
  // higher-opacity fill, read at a glance as settled. A proposed region is
  // a machine's guess — cooler blue, lighter, lower-opacity, thinner
  // stroke. The two differ in hue as well as opacity/weight so a
  // colorblind-safe (hue-based) screenshot diff still tells them apart;
  // conflating them would invite treating model output as confirmed data.
  "regions-confirmed": {
    fill: "rgba(217,119,6,0.35)",
    stroke: "rgba(180,83,9,0.90)",
    strokeWidth: 2,
  },
  "regions-proposed": {
    fill: "rgba(14,165,233,0.15)",
    stroke: "rgba(3,105,161,0.55)",
    strokeWidth: 1,
  },
  // The selected-region highlight (Task 2, region-review-surface): a
  // person's current pick, drawn over whichever of the two layers above it
  // came from. Magenta keeps it visually distinct from both the confirmed
  // amber and the proposed blue, and the stroke is heavier than either
  // (2 px, 1 px) so the highlight always reads on top.
  "regions-selected": {
    fill: "transparent",
    stroke: "rgba(217,70,239,0.95)",
    strokeWidth: 3,
  },
  "drag-rect": {
    fill: "transparent",
    stroke: "#2563eb",
    strokeWidth: 2,
  },
  // Selection layers share legacy fill/stroke (image_tabs.py:514-519);
  // selection items carry `selected: true` so BBoxOverlay's selected
  // branch upgrades strokeWidth to SELECTION_STROKE_WIDTH (spec §6, §8).
  "selection-paragraphs": {
    fill: "rgba(37,99,235,0.20)",
    stroke: "#1d4ed8",
    strokeWidth: 1,
  },
  "selection-lines": {
    fill: "rgba(37,99,235,0.20)",
    stroke: "#1d4ed8",
    strokeWidth: 1,
  },
  "selection-words": {
    fill: "rgba(37,99,235,0.20)",
    stroke: "#1d4ed8",
    strokeWidth: 1,
  },
};

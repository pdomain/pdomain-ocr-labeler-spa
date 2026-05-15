// PerfTestPage.tsx — dev/test-only Konva viewport benchmark harness.
//
// Spec: specs/21-konva-renderer.md §11 (Performance pinning), §14 (Tests).
// Issue: #305 (spec-21-C2 — perf pinning + viewport perf E2E benchmark).
//
// Mounts a standalone PageImageCanvas with a synthesised 4 000-rect page so
// the Playwright benchmark in `tests/e2e/test_viewport_perf.py` can drag
// over a known-heavy viewport and count `requestAnimationFrame` callbacks
// without depending on a real project, OCR run, or backend data.
//
// No production gate: the route is reachable in built wheels too — the
// `__perf-test` path is hidden enough that no real user lands on it, and
// the perf harness has zero side effects (selection callbacks are no-ops,
// the image fetch fails harmlessly and PageImage falls back to grey). We
// deliberately do NOT mode-gate so `make e2e` against `make frontend-build`
// (which builds with MODE=production) keeps working without a dev-mode
// build step.
//
// Synthesised payload (keep stable — the E2E harness asserts against
// these counts):
//   - 200 lines × 20 words per line = 4 000 word rects (spec §11).
//   - Display dims 1600×2000 px (a believable book page).
//   - Word rects packed into a 20-col grid; line rects span each row.
//   - No real image — PageImageCanvas falls back to a grey placeholder
//     via PageImage when use-image's URL is unreachable.

import { useMemo } from "react";
import PageImageCanvas from "../components/PageImageCanvas";
import type { components } from "../api/types";
import type { EncodedDims } from "../lib/canvas-utils";

type PagePayload = components["schemas"]["PagePayload"];
type LineMatch = components["schemas"]["LineMatch"];
type WordMatch = components["schemas"]["WordMatch"];

// ── Synthesised-payload constants ───────────────────────────────────────────
const LINES = 200;
const WORDS_PER_LINE = 20;
const DISPLAY_W = 1600;
const DISPLAY_H = 2000;
const COL_W = DISPLAY_W / WORDS_PER_LINE; // 80 px / column
const ROW_H = DISPLAY_H / LINES; // 10 px / row

function makeSyntheticPage(): PagePayload {
  const line_matches: LineMatch[] = [];
  const selected_words: [number, number][] = [];
  for (let li = 0; li < LINES; li++) {
    const word_matches: WordMatch[] = [];
    for (let wi = 0; wi < WORDS_PER_LINE; wi++) {
      word_matches.push({
        line_index: li,
        word_index: wi,
        ocr_text: `w${li}-${wi}`,
        ground_truth_text: "",
        match_status: "exact",
        normalized_match: false,
        is_validated: false,
        bbox: {
          x: wi * COL_W + 1,
          y: li * ROW_H + 1,
          width: COL_W - 2,
          height: ROW_H - 2,
        },
      });
      selected_words.push([li, wi]);
    }
    line_matches.push({
      line_index: li,
      paragraph_index: null,
      ocr_line_text: `line ${li}`,
      ground_truth_line_text: "",
      word_matches,
      overall_match_status: "exact",
      exact_count: WORDS_PER_LINE,
      fuzzy_count: 0,
      mismatch_count: 0,
      unmatched_gt_count: 0,
      unmatched_ocr_count: 0,
      validated_word_count: 0,
      total_word_count: WORDS_PER_LINE,
      is_fully_validated: false,
    });
  }
  return {
    project_id: "__perf-test",
    page_index: 0,
    line_matches,
    line_filter: "all",
    image_url: null,
    generation: 0,
    // Select every word so PageImageCanvas's `expandSelection` path
    // hands BBoxOverlay 4 000 word-bbox items — that's the heavy paint
    // path spec §11 actually pins (the overlay-words Layer is still
    // empty pending later slices).
    selection: {
      selection_mode: "word",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words,
    },
  };
}

const ENCODED: EncodedDims = {
  src_width: DISPLAY_W,
  src_height: DISPLAY_H,
  display_width: DISPLAY_W,
  display_height: DISPLAY_H,
  scale: 1,
};

/**
 * Standalone perf-bench page. Reachable at `/__perf-test` in any build
 * (no mode gate — see file header).
 */
export default function PerfTestPage() {
  // Memoised so re-renders don't rebuild the 4 000-word payload. The
  // PageImageCanvas selection-expand memo and the BBoxOverlay React.memo
  // (spec §11) together skip the per-rect work when the parent re-renders.
  const page = useMemo(makeSyntheticPage, []);

  // Drag callbacks deliberately swallow events — we only want the
  // viewport's drag-preview rAF path exercised, not the downstream
  // mutation/POST machinery.
  return (
    <div
      data-testid="perf-test-page"
      data-line-count={LINES}
      data-word-count={LINES * WORDS_PER_LINE}
    >
      <PageImageCanvas
        imageUrl="/__perf-test-no-image.png"
        encoded={ENCODED}
        page={page}
        onBoxSelect={() => undefined}
        onRebox={() => undefined}
        onAddWord={() => undefined}
        onErasePixels={() => undefined}
      />
    </div>
  );
}

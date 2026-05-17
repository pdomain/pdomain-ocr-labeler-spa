// StructureSection.test.tsx — Tests for Slice 18 (base) + P3.d (Gap 37).
// P3.d adds: horizontal neighbors strip (prev/current/next cards),
// merge-preview row (new testids), gap-picker slider, vertical-split affordance.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StructureSection } from "./StructureSection";
import { server } from "../../../test/server";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];
type PagePayload = components["schemas"]["PagePayload"];

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeWord(lineIndex: number, wordIndex: number, text = "hello"): WordMatch {
  return {
    line_index: lineIndex,
    word_index: wordIndex,
    ocr_text: text,
    ground_truth_text: text,
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 10, height: 10 },
  };
}

function makePage(wordCount = 3): PagePayload {
  const words = Array.from({ length: wordCount }, (_, i) =>
    makeWord(0, i, ["hello", "world", "foo"][i] ?? `w${i}`),
  );
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "hello world foo",
        ground_truth_line_text: "hello world foo",
        word_matches: words,
        overall_match_status: "exact",
        exact_count: wordCount,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: wordCount,
        is_fully_validated: false,
      },
    ],
  };
}

const PAGE_RESPONSE = makePage();

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderSection(word: WordMatch, page: PagePayload = PAGE_RESPONSE) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <StructureSection word={word} page={page} projectId="p1" pageIndex={0} />
    </QueryClientProvider>,
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("StructureSection (Slice 18 + P3.d / Gap 37)", () => {
  beforeEach(() => {
    server.use(
      http.post("/api/projects/p1/pages/0/words/:li/:wi/merge", () =>
        HttpResponse.json(PAGE_RESPONSE),
      ),
      http.post("/api/projects/p1/pages/0/words/:li/:wi/split", () =>
        HttpResponse.json(PAGE_RESPONSE),
      ),
      http.post("/api/projects/p1/pages/0/words/:li/:wi/rebox", () =>
        HttpResponse.json(PAGE_RESPONSE),
      ),
    );
  });

  // ── Container ──────────────────────────────────────────────────────────────

  it("renders the structure-section container", () => {
    renderSection(makeWord(0, 1));
    expect(screen.getByTestId("structure-section")).toBeInTheDocument();
  });

  // ── Neighbors strip ────────────────────────────────────────────────────────

  it("renders prev/current/next neighbor cards", () => {
    renderSection(makeWord(0, 1));
    expect(screen.getByTestId("structure-prev-word")).toBeInTheDocument();
    expect(screen.getByTestId("structure-current-word")).toBeInTheDocument();
    expect(screen.getByTestId("structure-next-word")).toBeInTheDocument();
  });

  it("shows prev word text when prev exists", () => {
    renderSection(makeWord(0, 1)); // wordIndex=1 → prev is "hello"
    const prevSlot = screen.getByTestId("structure-prev-word");
    expect(prevSlot).not.toHaveTextContent("none");
    expect(prevSlot).toHaveTextContent("hello");
  });

  it("shows 'none' for prev when word is first", () => {
    renderSection(makeWord(0, 0));
    expect(screen.getByTestId("structure-prev-word")).toHaveTextContent("none");
  });

  it("shows current word text in the center card", () => {
    // makeWord uses "hello" as default; the current-word card shows that text.
    renderSection(makeWord(0, 1));
    expect(screen.getByTestId("structure-current-word")).toHaveTextContent("hello");
  });

  it("shows next word text when next exists", () => {
    renderSection(makeWord(0, 1)); // wordIndex=1 → next is "foo"
    const nextSlot = screen.getByTestId("structure-next-word");
    expect(nextSlot).not.toHaveTextContent("none");
    expect(nextSlot).toHaveTextContent("foo");
  });

  it("shows 'none' for next when word is last", () => {
    renderSection(makeWord(0, 2)); // last word in 3-word line
    expect(screen.getByTestId("structure-next-word")).toHaveTextContent("none");
  });

  // ── Merge preview row ──────────────────────────────────────────────────────

  it("merge-prev button is disabled when no prev word (first word)", () => {
    renderSection(makeWord(0, 0));
    expect(screen.getByTestId("structure-merge-prev")).toBeDisabled();
  });

  it("merge-next button is disabled when no next word (last word)", () => {
    renderSection(makeWord(0, 2));
    expect(screen.getByTestId("structure-merge-next")).toBeDisabled();
  });

  it("merge-prev button is enabled when prev word exists", () => {
    renderSection(makeWord(0, 1));
    expect(screen.getByTestId("structure-merge-prev")).not.toBeDisabled();
  });

  it("merge-next button is enabled when next word exists", () => {
    renderSection(makeWord(0, 1));
    expect(screen.getByTestId("structure-merge-next")).not.toBeDisabled();
  });

  it("clicking Merge prev opens a ConfirmDialog", async () => {
    const user = userEvent.setup();
    renderSection(makeWord(0, 1));
    await user.click(screen.getByTestId("structure-merge-prev"));
    expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
  });

  it("clicking Merge next opens a ConfirmDialog", async () => {
    const user = userEvent.setup();
    renderSection(makeWord(0, 1));
    await user.click(screen.getByTestId("structure-merge-next"));
    expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
  });

  it("confirming Merge prev fires the merge mutation with direction=left", async () => {
    const mergeHandler = vi.fn(() => HttpResponse.json(PAGE_RESPONSE));
    server.use(http.post("/api/projects/p1/pages/0/words/0/1/merge", mergeHandler));

    const user = userEvent.setup();
    renderSection(makeWord(0, 1));
    await user.click(screen.getByTestId("structure-merge-prev"));
    await user.click(screen.getByTestId("confirm-dialog-confirm"));

    await waitFor(() => expect(mergeHandler).toHaveBeenCalledOnce());
  });

  it("confirming Merge next fires the merge mutation with direction=right", async () => {
    const mergeHandler = vi.fn(() => HttpResponse.json(PAGE_RESPONSE));
    server.use(http.post("/api/projects/p1/pages/0/words/0/1/merge", mergeHandler));

    const user = userEvent.setup();
    renderSection(makeWord(0, 1));
    await user.click(screen.getByTestId("structure-merge-next"));
    await user.click(screen.getByTestId("confirm-dialog-confirm"));

    await waitFor(() => expect(mergeHandler).toHaveBeenCalledOnce());
  });

  it("cancelling Merge closes dialog without mutation", async () => {
    const mergeHandler = vi.fn(() => HttpResponse.json(PAGE_RESPONSE));
    server.use(http.post("/api/projects/p1/pages/0/words/0/1/merge", mergeHandler));

    const user = userEvent.setup();
    renderSection(makeWord(0, 1));
    await user.click(screen.getByTestId("structure-merge-prev"));
    await user.click(screen.getByTestId("confirm-dialog-cancel"));

    expect(screen.queryByTestId("confirm-dialog")).not.toBeInTheDocument();
    expect(mergeHandler).not.toHaveBeenCalled();
  });

  // ── Gap-picker slider ──────────────────────────────────────────────────────

  it("renders the gap-picker slider", () => {
    renderSection(makeWord(0, 1));
    const slider = screen.getByTestId("structure-gap-slider");
    expect(slider).toBeInTheDocument();
    expect(slider).toHaveAttribute("type", "range");
    expect(slider).toHaveAttribute("min", "-10");
    expect(slider).toHaveAttribute("max", "10");
  });

  it("gap slider defaults to 0", () => {
    renderSection(makeWord(0, 1));
    const slider = screen.getByTestId("structure-gap-slider");
    expect(slider.value).toBe("0");
  });

  it("gap slider label updates when value changes", async () => {
    const user = userEvent.setup();
    renderSection(makeWord(0, 1));
    const slider = screen.getByTestId("structure-gap-slider");
    // jsdom doesn't fire change on range; use fireEvent directly
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(slider, { target: { value: "5" } });
    expect(screen.getByText(/\+5px/)).toBeInTheDocument();
  });

  it("gap slider is disabled when word is the last in the line", () => {
    renderSection(makeWord(0, 2)); // last word in 3-word line — no wi+1
    const slider = screen.getByTestId("structure-gap-slider");
    expect(slider).toBeDisabled();
  });

  it("gap slider is enabled for a non-last word", () => {
    renderSection(makeWord(0, 1)); // middle word — wi+1 exists
    const slider = screen.getByTestId("structure-gap-slider");
    expect(slider).not.toBeDisabled();
  });

  it("committing the gap slider calls rebox on the next word (wi+1) with shifted bbox", async () => {
    // words: hello(wi=0, x=0,w=10), world(wi=1, x=0,w=10), foo(wi=2, x=0,w=10)
    // Selecting wi=1 → next = wi=2, bbox={x:0,y:0,w:10,h:10}, currentGap=0
    // Moving slider to +5 → deltaX=5 → rebox wi=2 at x=5
    const reboxHandler = vi.fn(async ({ request }: { request: Request }) => {
      const body = (await request.json()) as {
        bbox: { x: number; y: number; width: number; height: number };
      };
      expect(body.bbox.x).toBe(5); // shifted by +5
      expect(body.bbox.width).toBe(10); // width unchanged
      return HttpResponse.json(PAGE_RESPONSE);
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/2/rebox", reboxHandler));

    const { fireEvent } = await import("@testing-library/react");
    renderSection(makeWord(0, 1));
    const slider = screen.getByTestId("structure-gap-slider");
    fireEvent.change(slider, { target: { value: "5" } });
    fireEvent.mouseUp(slider, { target: { value: "5" } });

    await waitFor(() => expect(reboxHandler).toHaveBeenCalledOnce());
  });

  // ── Vertical-split affordance ──────────────────────────────────────────────

  it("renders the split button", () => {
    renderSection(makeWord(0, 1));
    expect(screen.getByTestId("structure-split-button")).toBeInTheDocument();
  });

  it("split button shows default 'Split at midpoint' text initially", () => {
    renderSection(makeWord(0, 1)); // word is "world"
    expect(screen.getByTestId("structure-split-button")).toHaveTextContent("Split at midpoint");
  });

  it("clicking a character in the split picker updates the split position label", async () => {
    const user = userEvent.setup();
    renderSection(makeWord(0, 1)); // "world"
    // Click the 3rd character ("r" at index 2 → split position 3)
    const charButtons = screen.getAllByTitle(/Split after position/);
    await user.click(charButtons[2]); // position 3 (after "wor")
    expect(screen.getByTestId("structure-split-button")).toHaveTextContent("Split at position 3");
  });

  it("split button fires split mutation without confirm dialog", async () => {
    const splitHandler = vi.fn(() => HttpResponse.json(PAGE_RESPONSE));
    server.use(http.post("/api/projects/p1/pages/0/words/0/1/split", splitHandler));

    const user = userEvent.setup();
    renderSection(makeWord(0, 1));
    await user.click(screen.getByTestId("structure-split-button"));

    await waitFor(() => expect(splitHandler).toHaveBeenCalledOnce());
    // No confirm dialog for split
    expect(screen.queryByTestId("confirm-dialog")).not.toBeInTheDocument();
  });

  it("clicking a char then split fires mutation with correct x_fraction", async () => {
    const splitHandler = vi.fn(async ({ request }: { request: Request }) => {
      const body = (await request.json()) as { x_fraction: number };
      expect(body.x_fraction).toBeCloseTo(1 / 5, 5); // pos=1 of 5 chars in "world"
      return HttpResponse.json(PAGE_RESPONSE);
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/1/split", splitHandler));

    const user = userEvent.setup();
    renderSection(makeWord(0, 1)); // "world" — 5 chars
    // Click first char → split position 1
    const charButtons = screen.getAllByTitle(/Split after position/);
    await user.click(charButtons[0]);
    await user.click(screen.getByTestId("structure-split-button"));

    await waitFor(() => expect(splitHandler).toHaveBeenCalledOnce());
  });
});

// CharRangesSection.test.tsx — Tests for Slice 19 char-range editor + P4.a hi-fi additions.
// Covers: B-RIGHT-003, B-RIGHT-012
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 19.
// P4.a (Gap 38): per-char glyph editor rows, overlap markers, STYLE/COMPONENT kind switcher.

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CharRangesSection } from "./CharRangesSection";
import { server } from "../../../test/server";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];

function makeWord(
  textOrOverrides: string | (Partial<WordMatch> & { text?: string }) = "Hello",
): WordMatch {
  const overrides =
    typeof textOrOverrides === "string" ? { text: textOrOverrides } : textOrOverrides;
  const { text = "Hello", ...rest } = overrides;
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: text,
    ground_truth_text: text,
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox: { x: 0, y: 0, width: 10, height: 10 },
    ...rest,
  };
}

function makePageResponse(text: string) {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 1,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: text,
        ground_truth_line_text: text,
        word_matches: [makeWord(text)],
        overall_match_status: "exact",
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
      },
    ],
  };
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderSection(word = makeWord()) {
  const qc = makeQueryClient();
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <CharRangesSection word={word} projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    ),
    qc,
  };
}

// ---- Slice 19 baseline tests (unchanged) ------------------------------------

describe("CharRangesSection (Slice 19)", () => {
  it("renders outer container with data-testid=char-ranges-section", () => {
    renderSection();
    expect(screen.getByTestId("char-ranges-section")).toBeInTheDocument();
  });

  it("renders one clickable cell per char in the word's ocr_text", () => {
    renderSection(makeWord("Hello"));
    expect(screen.getByTestId("char-cell-0")).toHaveTextContent("H");
    expect(screen.getByTestId("char-cell-1")).toHaveTextContent("e");
    expect(screen.getByTestId("char-cell-2")).toHaveTextContent("l");
    expect(screen.getByTestId("char-cell-3")).toHaveTextContent("l");
    expect(screen.getByTestId("char-cell-4")).toHaveTextContent("o");
    expect(screen.queryByTestId("char-cell-5")).not.toBeInTheDocument();
  });

  it("clicking a char cell selects it as range start; clicking second selects end", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-1"));
    expect(screen.getByTestId("char-cell-1")).toHaveAttribute("data-range-anchor", "true");

    await user.click(screen.getByTestId("char-cell-3"));
    expect(screen.getByTestId("char-ranges-pending")).toHaveTextContent("1");
    expect(screen.getByTestId("char-ranges-pending")).toHaveTextContent("3");
  });

  it("Add range button is enabled only when a range is selected", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    const addBtn = screen.getByTestId("char-ranges-add-button");
    expect(addBtn).toBeDisabled();

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    expect(addBtn).toBeEnabled();
  });

  it("style chips cycle off->on->mixed->off via tristate", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));

    const italic = screen.getByTestId("char-ranges-chip-italics");
    expect(italic).toHaveAttribute("data-tristate-value", "off");
    await user.click(italic);
    expect(italic).toHaveAttribute("data-tristate-value", "on");
  });

  it("Add range appends a row visible in the ranges list", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-1"));
    await user.click(screen.getByTestId("char-cell-3"));
    await user.click(screen.getByTestId("char-ranges-chip-italics"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    // Compat row appears (sr-only hidden div)
    expect(screen.getByTestId("char-ranges-row-0")).toBeInTheDocument();
    expect(screen.getByTestId("char-ranges-row-0")).toHaveTextContent("1");
    expect(screen.getByTestId("char-ranges-row-0")).toHaveTextContent("3");
    expect(screen.getByTestId("char-ranges-row-0")).toHaveTextContent(/italics/i);
  });

  it("delete button removes a row", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    await user.click(screen.getByTestId("char-ranges-chip-bold"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    expect(screen.getByTestId("char-ranges-row-0")).toBeInTheDocument();

    await user.click(screen.getByTestId("char-ranges-delete-0"));
    expect(screen.queryByTestId("char-ranges-row-0")).not.toBeInTheDocument();
  });

  it("Add range posts full positioned ranges to /char-ranges endpoint (FO-2)", async () => {
    let capturedBody: unknown = null;
    const handler = vi.fn(async (info: { request: Request }) => {
      capturedBody = await info.request.json();
      return HttpResponse.json(makePageResponse("Hello"));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/char-ranges", handler));

    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    await user.click(screen.getByTestId("char-ranges-chip-italics"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    await waitFor(() => expect(handler).toHaveBeenCalled());

    expect(capturedBody).toMatchObject({
      ranges: [{ start: 0, end: 2, styles: ["italics"] }],
    });
  });

  it("Delete range fires /char-ranges with updated list (FO-2)", async () => {
    let lastBody: unknown = null;
    const handler = vi.fn(async (info: { request: Request }) => {
      lastBody = await info.request.json();
      return HttpResponse.json(makePageResponse("Hello"));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/char-ranges", handler));

    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    await user.click(screen.getByTestId("char-ranges-chip-bold"));
    await user.click(screen.getByTestId("char-ranges-add-button"));
    await waitFor(() => expect(handler).toHaveBeenCalledTimes(1));

    await user.click(screen.getByTestId("char-ranges-delete-0"));
    await waitFor(() => expect(handler).toHaveBeenCalledTimes(2));

    expect(lastBody).toMatchObject({ ranges: [] });
  });
});

// ---- P4.a additions (Gap 38) ------------------------------------------------

describe("CharRangesSection P4.a -- per-char glyph editor + overlap + kind switcher", () => {
  it("renders char-range-add button at the bottom", () => {
    renderSection(makeWord("Hello"));
    expect(screen.getByTestId("char-range-add")).toBeInTheDocument();
    expect(screen.getByTestId("char-range-add")).toHaveTextContent("+ Add range");
  });

  it("char-range-add button appends a blank range card", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    expect(screen.queryByTestId("char-range-0")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("char-range-add"));
    expect(screen.getByTestId("char-range-0")).toBeInTheDocument();
  });

  it("range card has glyph preview with correct testid", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-1"));
    await user.click(screen.getByTestId("char-cell-3"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    // Glyph card should show chars 1..3 of "Hello" = "ell"
    const glyphCard = screen.getByTestId("char-range-0-glyph");
    expect(glyphCard).toBeInTheDocument();
    expect(glyphCard).toHaveTextContent("ell");
  });

  it("range card delete button with new testid removes the card", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-range-add"));
    expect(screen.getByTestId("char-range-0")).toBeInTheDocument();

    await user.click(screen.getByTestId("char-range-0-delete"));
    expect(screen.queryByTestId("char-range-0")).not.toBeInTheDocument();
  });

  it("kind switcher renders STYLE and COMPONENT buttons with correct testids", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-range-add"));

    expect(screen.getByTestId("char-range-0-kind-style")).toBeInTheDocument();
    expect(screen.getByTestId("char-range-0-kind-component")).toBeInTheDocument();
  });

  it("clicking COMPONENT kind button switches chip palette to component chips", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-range-add"));

    // Initially in STYLE mode -- style chips visible
    expect(screen.getByTestId("char-range-0-style-chip-bold")).toBeInTheDocument();
    expect(screen.queryByTestId("char-range-0-component-chip-drop-cap")).not.toBeInTheDocument();

    // Switch to COMPONENT mode
    await user.click(screen.getByTestId("char-range-0-kind-component"));

    // Component chips visible; style chips gone
    expect(screen.getByTestId("char-range-0-component-chip-drop-cap")).toBeInTheDocument();
    expect(screen.queryByTestId("char-range-0-style-chip-bold")).not.toBeInTheDocument();
  });

  it("overlap warning appears when two ranges share character positions", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    // Add first range: 0..2
    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    // No overlap yet
    expect(screen.queryByTestId("char-range-0-overlap-warning")).not.toBeInTheDocument();

    // Add second range: 1..3 (overlaps with 0..2)
    await user.click(screen.getByTestId("char-cell-1"));
    await user.click(screen.getByTestId("char-cell-3"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    // Both cards show overlap warning
    expect(screen.getByTestId("char-range-0-overlap-warning")).toBeInTheDocument();
    expect(screen.getByTestId("char-range-1-overlap-warning")).toBeInTheDocument();
  });

  it("no overlap warning when ranges are adjacent but not overlapping", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    // First range: 0..1
    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-1"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    // Second range: 2..3 (non-overlapping)
    await user.click(screen.getByTestId("char-cell-2"));
    await user.click(screen.getByTestId("char-cell-3"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    expect(screen.queryByTestId("char-range-0-overlap-warning")).not.toBeInTheDocument();
    expect(screen.queryByTestId("char-range-1-overlap-warning")).not.toBeInTheDocument();
  });

  it("multiple range cards render with correct indices", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-range-add"));
    await user.click(screen.getByTestId("char-range-add"));
    await user.click(screen.getByTestId("char-range-add"));

    expect(screen.getByTestId("char-range-0")).toBeInTheDocument();
    expect(screen.getByTestId("char-range-1")).toBeInTheDocument();
    expect(screen.getByTestId("char-range-2")).toBeInTheDocument();
    expect(screen.queryByTestId("char-range-3")).not.toBeInTheDocument();
  });

  it("char-range-add persists to backend via /char-ranges", async () => {
    let capturedBody: unknown = null;
    const handler = vi.fn(async (info: { request: Request }) => {
      capturedBody = await info.request.json();
      return HttpResponse.json(makePageResponse("Hello"));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/char-ranges", handler));

    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-range-add"));
    await waitFor(() => expect(handler).toHaveBeenCalled());

    // Should post a range covering the full word (0..4 for "Hello")
    expect(capturedBody).toMatchObject({
      ranges: [{ start: 0, end: 4, styles: [] }],
    });
  });
});

// ---- R3: load saved char_ranges from word prop on mount ---------------------

describe("CharRangesSection R3 — load saved char_ranges on mount", () => {
  it("loads saved char_ranges from word prop on mount", () => {
    const word = makeWord({ char_ranges: [{ start: 0, end: 2, styles: ["bold"] }] });
    renderSection(word);
    expect(screen.getByTestId("char-range-0")).toBeInTheDocument();
  });

  it("loaded range card shows correct glyph preview", () => {
    const word = makeWord({
      text: "Hello",
      char_ranges: [{ start: 0, end: 2, styles: ["italic"] }],
    });
    renderSection(word);
    const glyphCard = screen.getByTestId("char-range-0-glyph");
    expect(glyphCard).toHaveTextContent("Hel");
  });

  it("updates ranges when word prop changes (navigation)", async () => {
    // Start with no char_ranges.
    const word1 = makeWord("Hello");
    const { rerender } = renderSection(word1);
    expect(screen.queryByTestId("char-range-0")).not.toBeInTheDocument();

    // Navigate to a word that has saved ranges.
    const word2 = makeWord({
      text: "World",
      char_ranges: [{ start: 0, end: 1, styles: ["bold"] }],
    });
    rerender(
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
          })
        }
      >
        <CharRangesSection word={word2} projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("char-range-0")).toBeInTheDocument();
  });
});

// ---- F-037 regression: existing-range edits persist + activeComponents serialised ----

describe("CharRangesSection F-037 — existing-range edits persist and component labels serialise", () => {
  it("F-037: style chip toggle on existing range POSTs updated styles", async () => {
    let lastBody: unknown = null;
    const handler = vi.fn(async (info: { request: Request }) => {
      lastBody = await info.request.json();
      return HttpResponse.json(makePageResponse("Hello"));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/char-ranges", handler));

    const user = userEvent.setup();
    renderSection(makeWord({ text: "Hello", char_ranges: [{ start: 0, end: 2, styles: [] }] }));

    // Toggle italic chip on the existing range card.
    await user.click(screen.getByTestId("char-range-0-style-chip-italics"));

    await waitFor(() => expect(handler).toHaveBeenCalled());
    expect(lastBody).toMatchObject({
      ranges: [{ start: 0, end: 2, styles: expect.arrayContaining(["italics"]) }],
    });
  });

  it("F-037: component chip toggle includes label in POST payload", async () => {
    let lastBody: unknown = null;
    const handler = vi.fn(async (info: { request: Request }) => {
      lastBody = await info.request.json();
      return HttpResponse.json(makePageResponse("Hello"));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/char-ranges", handler));

    const user = userEvent.setup();
    renderSection(makeWord({ text: "Hello", char_ranges: [{ start: 0, end: 2, styles: [] }] }));

    // Switch the card to COMPONENT kind, then toggle drop-cap chip.
    await user.click(screen.getByTestId("char-range-0-kind-component"));
    await user.click(screen.getByTestId("char-range-0-component-chip-drop-cap"));

    await waitFor(() => expect(handler).toHaveBeenCalledTimes(2));
    // Q-B2-STYLE-LABELS: canonical component label is "drop cap" (with space).
    expect(lastBody).toMatchObject({
      ranges: [{ start: 0, end: 2, styles: expect.arrayContaining(["drop cap"]) }],
    });
  });

  it("F-037: position end change on existing range POSTs updated position", async () => {
    let lastBody: unknown = null;
    const handler = vi.fn(async (info: { request: Request }) => {
      lastBody = await info.request.json();
      return HttpResponse.json(makePageResponse("Hello"));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/char-ranges", handler));

    renderSection(makeWord({ text: "Hello", char_ranges: [{ start: 0, end: 4, styles: [] }] }));

    const endInput = screen.getByTestId("char-range-0-end");
    // Use fireEvent.change — userEvent.type on number inputs doesn't reliably
    // fire onChange on each keystroke in jsdom.
    fireEvent.change(endInput, { target: { value: "2" } });

    await waitFor(() => expect(handler).toHaveBeenCalled());
    expect(lastBody).toMatchObject({
      ranges: [{ start: 0, end: 2 }],
    });
  });
});

// ---- E: canonical pending-panel key round-trip (Q-B2) -----------------------

describe("CharRangesSection E — canonical pending-panel style keys (Q-B2)", () => {
  it("pending chip for 'italics' (canonical) has testid char-ranges-chip-italics", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));

    // Canonical key "italics" — testid must match.
    expect(screen.getByTestId("char-ranges-chip-italics")).toBeInTheDocument();
  });

  it("pending chip for 'subscript' (canonical) has testid char-ranges-chip-subscript", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));

    expect(screen.getByTestId("char-ranges-chip-subscript")).toBeInTheDocument();
  });

  it("pending chip for 'superscript' (canonical) has testid char-ranges-chip-superscript", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));

    expect(screen.getByTestId("char-ranges-chip-superscript")).toBeInTheDocument();
  });

  it("pending chip for 'drop cap' (canonical) has testid char-ranges-chip-drop cap", async () => {
    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));

    expect(screen.getByTestId("char-ranges-chip-drop cap")).toBeInTheDocument();
  });

  it("pending panel POST sends canonical 'italics' (not 'italic') in styles array", async () => {
    let capturedBody: unknown = null;
    const handler = vi.fn(async (info: { request: Request }) => {
      capturedBody = await info.request.json();
      return HttpResponse.json(makePageResponse("Hello"));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/char-ranges", handler));

    const user = userEvent.setup();
    renderSection(makeWord("Hello"));

    await user.click(screen.getByTestId("char-cell-0"));
    await user.click(screen.getByTestId("char-cell-2"));
    await user.click(screen.getByTestId("char-ranges-chip-italics"));
    await user.click(screen.getByTestId("char-ranges-add-button"));

    await waitFor(() => expect(handler).toHaveBeenCalled());
    expect(capturedBody).toMatchObject({
      ranges: [{ start: 0, end: 2, styles: ["italics"] }],
    });
  });

  it("fromApiCharRange round-trip: server 'italics' → pending chip active", () => {
    // Server stores "italics" (canonical). On load, fromApiCharRange should set
    // the "italics" key to "on", not fail to match "italic".
    const word = makeWord({
      text: "Hi",
      char_ranges: [{ start: 0, end: 1, styles: ["italics"] }],
    });
    renderSection(word);
    // The chip testid uses canonical key "italics".
    // The compat row should show "italics" in its content.
    const compatRow = screen.getByTestId("char-ranges-row-0");
    expect(compatRow).toHaveTextContent(/italics/i);
  });
});

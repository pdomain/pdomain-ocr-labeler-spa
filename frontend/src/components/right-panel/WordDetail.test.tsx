// WordDetail.test.tsx — Tests for Slice 16 word detail accordion scaffold.
// Covers: B-RIGHT-001, B-RIGHT-005, B-RIGHT-006, B-RIGHT-007, B-RIGHT-008, B-RIGHT-010, B-RIGHT-011, B-RIGHT-012, B-RIGHT-013
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16.
//
// WordDetail → CharFixerSection (P4.b) → CharFixerCanvas → react-konva, and
// WordDetail → ReboxSection (P4.a) → ReboxCanvas → react-konva. react-konva's
// node entry imports the native `canvas` module which isn't available under
// jsdom, so we mock react-konva + PageImage with passthrough divs before any
// other import resolves.

import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("react-konva", () => ({
  Stage: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="konva-stage-mock">{children}</div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => null,
  Image: () => null,
}));
vi.mock("../PageImage", () => ({ PageImage: () => null }));
vi.mock("../../hooks/useRefineAvailable", () => ({
  useRefineAvailable: () => ({ data: { available: true } }),
}));

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { WordDetail, resolveWord } from "./WordDetail";
import { clearSelection, selectWord } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function makePage(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    image_url: "/api/projects/p1/image/0",
    encoded_dims: {
      src_width: 1600,
      src_height: 1200,
      display_width: 800,
      display_height: 600,
      scale: 0.5,
    },
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "hello",
        ground_truth_line_text: "hello",
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 10, y: 20, width: 30, height: 15 },
          },
        ],
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

function makePageWithLogicalWordIndex(wordIndex: number): PagePayload {
  const page = makePage();
  page.line_matches![0]!.word_matches[0]!.word_index = wordIndex;
  return page;
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("WordDetail (Slice 16)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("shows 'No word selected' when no word in selection-store", () => {
    renderWithQuery(<WordDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("word-detail")).toHaveTextContent(/no word selected/i);
  });

  it("renders 6 accordion items when word is selected", () => {
    selectWord(0, 0);
    renderWithQuery(<WordDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("word-detail")).toBeInTheDocument();
    // 6 accordion triggers
    const triggers = screen.getAllByRole("button");
    const triggerLabels = triggers.map((t) => t.textContent ?? "");
    expect(triggerLabels).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Bounding Box"),
        expect.stringContaining("Rebox"),
        expect.stringContaining("Erase Pixels"),
        expect.stringContaining("Structure"),
        expect.stringContaining("Char Ranges"),
        expect.stringContaining("Char Fixer"),
      ]),
    );
  });

  it("shows word identity label in the header (P2.a)", () => {
    selectWord(0, 0);
    renderWithQuery(<WordDetail page={makePage()} projectId="p1" pageIndex={0} />);
    // P2.a: header now shows "Line N · Word N", not the raw OCR text
    expect(screen.getByTestId("word-header-id")).toHaveTextContent("Line 1 · Word 1");
  });

  it("resolves selected words by logical word_index, not array position", () => {
    const word = resolveWord(makePageWithLogicalWordIndex(3), 0, [0, 3]);
    expect(word?.ocr_text).toBe("hello");
  });

  it("passes the page image and word bbox to the word image crop preview", () => {
    selectWord(0, 0);
    renderWithQuery(<WordDetail page={makePage()} projectId="p1" pageIndex={0} />);

    const crop = screen.getByTestId("word-image-crop");
    expect(crop).toHaveAttribute("viewBox", "10 20 30 15");
    expect(crop.querySelector("image")).toHaveAttribute("href", "/api/projects/p1/image/0");
  });

  it("disables prev/next pager buttons by word order, not logical word_index value", () => {
    selectWord(0, 3);
    renderWithQuery(
      <WordDetail page={makePageWithLogicalWordIndex(3)} projectId="p1" pageIndex={0} />,
    );

    expect(screen.getByTestId("word-detail")).not.toHaveTextContent(/word not found/i);
    expect(screen.getByTestId("word-header-prev")).toBeDisabled();
    expect(screen.getByTestId("word-header-next")).toBeDisabled();
  });
});

// ─── P1.4 (B-41): style chip toggle must send enabled on/off ────────────────

describe("WordDetail style chip toggle (P1.4 / B-41)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("clicking an inactive style chip POSTs enabled:true", async () => {
    const calls: Record<string, unknown>[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/style", async ({ request }) => {
        calls.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(makePage());
      }),
    );

    selectWord(0, 0);
    renderWithQuery(<WordDetail page={makePage()} projectId="p1" pageIndex={0} />);
    fireEvent.click(screen.getByTestId("style-chip-italics"));

    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0]).toEqual(
      expect.objectContaining({ style: "italics", scope: "whole", enabled: true }),
    );
  });

  it("clicking an ACTIVE style chip POSTs enabled:false (removes the style)", async () => {
    const calls: Record<string, unknown>[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/style", async ({ request }) => {
        calls.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(makePage());
      }),
    );

    const page = makePage();
    page.line_matches![0]!.word_matches[0]!.text_style_labels = ["italics"];
    selectWord(0, 0);
    renderWithQuery(<WordDetail page={page} projectId="p1" pageIndex={0} />);
    fireEvent.click(screen.getByTestId("style-chip-italics"));

    await waitFor(() => expect(calls.length).toBe(1));
    // Off-toggle used to re-APPLY the same style (silent no-op, B-41).
    expect(calls[0]).toEqual(
      expect.objectContaining({ style: "italics", scope: "whole", enabled: false }),
    );
  });
});

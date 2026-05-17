// BBoxSection.test.tsx — Tests for Slice 16 bounding-box editor + P3.a (Gaps 33, 34).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16.
// P3.a: bboxHint(), nudge sub-row, refine/expand+refine/crop buttons.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BBoxSection } from "./BBoxSection";
import { bboxHint } from "./bboxUtils";
import { server } from "../../../test/server";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];
type BBox = components["schemas"]["BBox"];

const DEFAULT_BBOX: BBox = { x: 10, y: 20, width: 30, height: 15 };

function makeWord(bbox = DEFAULT_BBOX): WordMatch {
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: "hello",
    ground_truth_text: "hello",
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox,
  };
}

function makePageResponse(bbox: BBox) {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 1,
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
            bbox,
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

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderBBox(word = makeWord()) {
  const qc = makeQueryClient();
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <BBoxSection word={word} projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    ),
    qc,
  };
}

// ─── bboxHint unit tests (Gap 33) ────────────────────────────────────────────

describe("bboxHint (P3.a Gap 33)", () => {
  it("formats bbox as x,y → x2,y2", () => {
    expect(bboxHint({ x: 10, y: 20, width: 30, height: 15 })).toBe("10,20 → 40,35");
  });

  it("handles zero-origin bbox", () => {
    expect(bboxHint({ x: 0, y: 0, width: 100, height: 50 })).toBe("0,0 → 100,50");
  });

  it("handles large coordinates", () => {
    expect(bboxHint({ x: 500, y: 300, width: 200, height: 80 })).toBe("500,300 → 700,380");
  });
});

// ─── BBoxSection rendering (Slice 16 original) ───────────────────────────────

describe("BBoxSection (Slice 16 + P3.a)", () => {
  beforeEach(() => {
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", () =>
        HttpResponse.json(makePageResponse(DEFAULT_BBOX)),
      ),
    );
  });

  it("renders four numeric inputs with initial bbox values", () => {
    renderBBox();
    const x = screen.getByTestId("bbox-input-x");
    const y = screen.getByTestId("bbox-input-y");
    const w = screen.getByTestId("bbox-input-w");
    const h = screen.getByTestId("bbox-input-h");
    expect(x.value).toBe("10");
    expect(y.value).toBe("20");
    expect(w.value).toBe("30");
    expect(h.value).toBe("15");
  });

  it("renders a Reset button", () => {
    renderBBox();
    expect(screen.getByTestId("bbox-reset-button")).toBeInTheDocument();
  });

  it("fires word PATCH (rebox) mutation on input blur with changed value", async () => {
    const handler = vi.fn((_req: Request) =>
      Promise.resolve(HttpResponse.json(makePageResponse(DEFAULT_BBOX))),
    );
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/rebox", handler));

    const user = userEvent.setup();
    renderBBox();

    const xInput = screen.getByTestId("bbox-input-x");
    await user.clear(xInput);
    await user.type(xInput, "99");
    await user.tab(); // triggers blur

    await waitFor(() => expect(handler).toHaveBeenCalledOnce());
  });

  it("Reset button shows original bbox values by resetting draft state", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", async ({ request }) => {
        const body = (await request.json()) as { bbox: BBox };
        return HttpResponse.json(makePageResponse(body.bbox));
      }),
    );

    const word = makeWord({ x: 5, y: 6, width: 7, height: 8 });
    const user = userEvent.setup();
    renderBBox(word);

    // Initial values should match bbox
    expect(screen.getByTestId("bbox-input-x").value).toBe("5");
    expect(screen.getByTestId("bbox-input-y").value).toBe("6");

    // Reset without any edits should fire mutation with original values
    const handler = vi.fn(async (info: { request: Request }) => {
      const body = (await info.request.json()) as { bbox: BBox };
      return HttpResponse.json(makePageResponse(body.bbox));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/rebox", handler));

    await user.click(screen.getByTestId("bbox-reset-button"));

    // Mutation should have been called with the original bbox
    await waitFor(() => expect(handler).toHaveBeenCalledOnce());
  });

  it("shows outer container with data-testid=bbox-section", () => {
    renderBBox();
    expect(screen.getByTestId("bbox-section")).toBeInTheDocument();
  });

  // ─── P3.a: Nudge sub-row (Gap 34) ────────────────────────────────────────

  it("renders nudge step input and L/R/T/B direction buttons (P3.a gap 34)", () => {
    renderBBox();
    expect(screen.getByTestId("bbox-nudge-step")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-nudge-left")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-nudge-right")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-nudge-top")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-nudge-bottom")).toBeInTheDocument();
  });

  it("nudge right fires rebox mutation with x + step", async () => {
    let capturedBbox: BBox | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", async ({ request }) => {
        const body = (await request.json()) as { bbox: BBox };
        capturedBbox = body.bbox;
        return HttpResponse.json(makePageResponse(body.bbox));
      }),
    );

    const user = userEvent.setup();
    renderBBox(); // DEFAULT_BBOX.x = 10, step = 1

    await user.click(screen.getByTestId("bbox-nudge-right"));

    await waitFor(() => expect(capturedBbox).toBeDefined());
    expect(capturedBbox!.x).toBe(11); // 10 + 1
  });

  it("nudge top fires rebox mutation with y - step", async () => {
    let capturedBbox: BBox | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", async ({ request }) => {
        const body = (await request.json()) as { bbox: BBox };
        capturedBbox = body.bbox;
        return HttpResponse.json(makePageResponse(body.bbox));
      }),
    );

    const user = userEvent.setup();
    renderBBox(); // DEFAULT_BBOX.y = 20, step = 1

    await user.click(screen.getByTestId("bbox-nudge-top"));

    await waitFor(() => expect(capturedBbox).toBeDefined());
    expect(capturedBbox!.y).toBe(19); // 20 - 1
  });

  // ─── P3.a: Refine / Expand+Refine / Crop buttons (Gap 33) ─────────────────

  it("renders Refine, Expand+Refine, and Crop buttons (P3.a gap 33)", () => {
    renderBBox();
    expect(screen.getByTestId("bbox-refine-button")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-expand-refine-button")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-crop-button")).toBeInTheDocument();
  });

  it("Expand+Refine fires rebox with bbox expanded by 4px on each side", async () => {
    let capturedBbox: BBox | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", async ({ request }) => {
        const body = (await request.json()) as { bbox: BBox };
        capturedBbox = body.bbox;
        return HttpResponse.json(makePageResponse(body.bbox));
      }),
    );

    const user = userEvent.setup();
    renderBBox(); // DEFAULT_BBOX = { x: 10, y: 20, width: 30, height: 15 }

    await user.click(screen.getByTestId("bbox-expand-refine-button"));

    await waitFor(() => expect(capturedBbox).toBeDefined());
    expect(capturedBbox!.x).toBe(6); // 10 - 4
    expect(capturedBbox!.y).toBe(16); // 20 - 4
    expect(capturedBbox!.width).toBe(38); // 30 + 8
    expect(capturedBbox!.height).toBe(23); // 15 + 8
  });
});

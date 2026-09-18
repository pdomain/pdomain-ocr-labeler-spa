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

// ─── sonner mock ──────────────────────────────────────────────────────────
// Needed only by the "collapses mid-job" describe block below (the real
// useBboxRefineTracking hook shows toasts) — mirrors BBoxSection.test.tsx /
// useBboxRefineTracking.test.tsx.
const toastMock = vi.hoisted(() => {
  const fn = Object.assign(vi.fn(), { loading: vi.fn(), success: vi.fn(), error: vi.fn() });
  return fn;
});
vi.mock("sonner", () => ({ toast: toastMock }));

import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { WordDetail, resolveWord } from "./WordDetail";
import { clearSelection, selectWord } from "../../stores/selection-store";
import { useBboxRefineTracking } from "../../hooks/useBboxRefineTracking";
import type { UseBboxRefineTrackingResult } from "../../hooks/useBboxRefineTracking";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

/** Static no-op stand-in for `bboxRefine` — none of the tests in this
 * describe block open the "Bounding Box" accordion item, so BBoxSection
 * never actually mounts and reads it. The "collapses mid-job" describe
 * block below uses the real `useBboxRefineTracking` hook instead, since
 * that is exactly the behavior it proves. */
const NOOP_BBOX_REFINE: UseBboxRefineTrackingResult = {
  jobId: null,
  word: null,
  outcome: null,
  start: () => undefined,
};

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

/** M11 Task 5: a page whose single word carries glyph annotations/predictions. */
function makePageWithGlyph(glyph: {
  annotations?: components["schemas"]["GlyphAnnotationsModel"] | null;
  predictions?: components["schemas"]["GlyphAnnotationsModel"] | null;
}): PagePayload {
  const page = makePage();
  const word = page.line_matches![0]!.word_matches[0]!;
  word.glyph_annotations = glyph.annotations ?? null;
  word.glyph_predictions = glyph.predictions ?? null;
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
    renderWithQuery(
      <WordDetail page={makePage()} projectId="p1" pageIndex={0} bboxRefine={NOOP_BBOX_REFINE} />,
    );
    expect(screen.getByTestId("word-detail")).toHaveTextContent(/no word selected/i);
  });

  it("renders 7 accordion items when word is selected", () => {
    selectWord(0, 0);
    renderWithQuery(
      <WordDetail page={makePage()} projectId="p1" pageIndex={0} bboxRefine={NOOP_BBOX_REFINE} />,
    );
    expect(screen.getByTestId("word-detail")).toBeInTheDocument();
    // 7 accordion triggers
    const triggers = screen.getAllByRole("button");
    const triggerLabels = triggers.map((t) => t.textContent ?? "");
    expect(triggerLabels).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Bounding Box"),
        expect.stringContaining("Rebox"),
        expect.stringContaining("Erase Pixels"),
        expect.stringContaining("Glyphs"),
        expect.stringContaining("Structure"),
        expect.stringContaining("Typography"),
        expect.stringContaining("Char Fixer"),
      ]),
    );
  });

  it("shows word identity label in the header (P2.a)", () => {
    selectWord(0, 0);
    renderWithQuery(
      <WordDetail page={makePage()} projectId="p1" pageIndex={0} bboxRefine={NOOP_BBOX_REFINE} />,
    );
    // P2.a: header now shows "Line N · Word N", not the raw OCR text
    expect(screen.getByTestId("word-header-id")).toHaveTextContent("Line 1 · Word 1");
  });

  it("resolves selected words by logical word_index, not array position", () => {
    const word = resolveWord(makePageWithLogicalWordIndex(3), 0, [0, 3]);
    expect(word?.ocr_text).toBe("hello");
  });

  it("passes the page image and word bbox to the word image crop preview", () => {
    selectWord(0, 0);
    renderWithQuery(
      <WordDetail page={makePage()} projectId="p1" pageIndex={0} bboxRefine={NOOP_BBOX_REFINE} />,
    );

    const crop = screen.getByTestId("word-image-crop");
    expect(crop).toHaveAttribute("viewBox", "10 20 30 15");
    expect(crop.querySelector("image")).toHaveAttribute("href", "/api/projects/p1/image/0");
  });

  it("disables prev/next pager buttons by word order, not logical word_index value", () => {
    selectWord(0, 3);
    renderWithQuery(
      <WordDetail
        page={makePageWithLogicalWordIndex(3)}
        projectId="p1"
        pageIndex={0}
        bboxRefine={NOOP_BBOX_REFINE}
      />,
    );

    expect(screen.getByTestId("word-detail")).not.toHaveTextContent(/word not found/i);
    expect(screen.getByTestId("word-header-prev")).toBeDisabled();
    expect(screen.getByTestId("word-header-next")).toBeDisabled();
  });
});

// ─── GlyphAnnotationPanel mount (M11 Task 5) ────────────────────────────────
//
// Spec: specs/20-glyph-annotations.md §5.1/§5.4. Issue
// docs/issues/2026-07-21-glyph-m11-usable-path-incomplete.md — the panel
// existed as an isolated component with no production mount point. The
// "Glyphs" accordion item hosts it here (not "Typography" — that label is
// already taken by TypographySection's grapheme/taxonomy review, a separate
// feature from docs/specs/2026-08-21-typography-review-and-training-export-design.md).

describe("WordDetail — GlyphAnnotationPanel mount (M11 Task 5)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("selecting a word and opening the Glyphs accordion item renders the glyph panel", async () => {
    selectWord(0, 0);
    const user = userEvent.setup();
    renderWithQuery(
      <WordDetail
        page={makePageWithGlyph({})}
        projectId="p1"
        pageIndex={0}
        bboxRefine={NOOP_BBOX_REFINE}
      />,
    );

    expect(screen.queryByTestId("glyph-panel-0-0")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /glyphs/i }));

    expect(await screen.findByTestId("glyph-panel-0-0")).toBeInTheDocument();
  });

  it("marking reviewed with no marks posts an empty annotations body", async () => {
    let body: unknown;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/glyph-annotations", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makePageWithGlyph({}));
      }),
    );

    selectWord(0, 0);
    const user = userEvent.setup();
    renderWithQuery(
      <WordDetail
        page={makePageWithGlyph({})}
        projectId="p1"
        pageIndex={0}
        bboxRefine={NOOP_BBOX_REFINE}
      />,
    );

    await user.click(screen.getByRole("button", { name: /glyphs/i }));
    await user.click(await screen.findByTestId("glyph-panel-mark-reviewed-empty"));

    await waitFor(() =>
      expect(body).toEqual({
        annotations: { ligatures: [], long_s_positions: [], swash: false, source: "human" },
      }),
    );
  });

  it("double-clicking Mark reviewed while the write is in flight posts once", async () => {
    let postCount = 0;
    let resolvePost!: () => void;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/glyph-annotations", async ({ request }) => {
        postCount += 1;
        await request.json();
        return new Promise<Response>((resolve) => {
          resolvePost = () => resolve(HttpResponse.json(makePageWithGlyph({})));
        });
      }),
    );

    selectWord(0, 0);
    const user = userEvent.setup();
    renderWithQuery(
      <WordDetail
        page={makePageWithGlyph({})}
        projectId="p1"
        pageIndex={0}
        bboxRefine={NOOP_BBOX_REFINE}
      />,
    );

    await user.click(screen.getByRole("button", { name: /glyphs/i }));
    const markReviewedButton = await screen.findByTestId("glyph-panel-mark-reviewed-empty");

    await user.click(markReviewedButton);
    await waitFor(() => expect(markReviewedButton).toBeDisabled());

    // A second click while the first write is still in flight must not
    // fire a second POST. userEvent respects the native `disabled`
    // attribute the same way a real double-click would.
    await user.click(markReviewedButton);

    resolvePost();
    await waitFor(() => expect(postCount).toBe(1));
  });

  it("accepts a prediction, posting to the accept-prediction route", async () => {
    let called = false;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/accept-prediction", async ({ request }) => {
        called = true;
        await request.json();
        return HttpResponse.json(makePageWithGlyph({}));
      }),
    );

    selectWord(0, 0);
    const user = userEvent.setup();
    renderWithQuery(
      <WordDetail
        page={makePageWithGlyph({
          predictions: {
            ligatures: [{ kind: "ct", char_span: [0, 2] }],
            long_s_positions: [],
            swash: false,
            source: "predicted",
          },
        })}
        projectId="p1"
        pageIndex={0}
        bboxRefine={NOOP_BBOX_REFINE}
      />,
    );

    // Predictions with no confirmed annotations auto-open the Glyphs item —
    // no manual click needed to reveal the accept button.
    const acceptButton = await screen.findByTestId("glyph-panel-accept-prediction-ct");
    await user.click(acceptButton);

    await waitFor(() => expect(called).toBe(true));
  });

  it("collapses the Glyphs item by default when there are no pending predictions", () => {
    selectWord(0, 0);
    renderWithQuery(
      <WordDetail
        page={makePageWithGlyph({})}
        projectId="p1"
        pageIndex={0}
        bboxRefine={NOOP_BBOX_REFINE}
      />,
    );

    expect(screen.queryByTestId("glyph-panel-0-0")).not.toBeInTheDocument();
  });

  it("auto-opens the Glyphs item when predictions are pending review (annotations still null)", async () => {
    selectWord(0, 0);
    renderWithQuery(
      <WordDetail
        page={makePageWithGlyph({
          predictions: {
            ligatures: [{ kind: "ct", char_span: [0, 2] }],
            long_s_positions: [],
            swash: false,
            source: "predicted",
          },
        })}
        projectId="p1"
        pageIndex={0}
        bboxRefine={NOOP_BBOX_REFINE}
      />,
    );

    expect(await screen.findByTestId("glyph-panel-0-0")).toBeInTheDocument();
  });

  it("does not auto-open once the word already has confirmed (even empty) annotations", () => {
    selectWord(0, 0);
    renderWithQuery(
      <WordDetail
        page={makePageWithGlyph({
          annotations: { ligatures: [], long_s_positions: [], swash: false, source: "human" },
          predictions: {
            ligatures: [{ kind: "ct", char_span: [0, 2] }],
            long_s_positions: [],
            swash: false,
            source: "predicted",
          },
        })}
        projectId="p1"
        pageIndex={0}
        bboxRefine={NOOP_BBOX_REFINE}
      />,
    );

    expect(screen.queryByTestId("glyph-panel-0-0")).not.toBeInTheDocument();
  });
});

// ─── Review finding 3 (high): refine job tracking survives an accordion
// collapse ──────────────────────────────────────────────────────────────
//
// BBoxSection lives inside `Accordion.Content`, which Radix removes from
// the DOM when the "Bounding Box" item collapses. Before this fix, the
// refine_bboxes job tracker (SSE subscription + terminal-status
// invalidation) lived inside BBoxSection itself, so collapsing the item
// mid-job closed the EventSource and the completed refine never
// invalidated the page query — the refined bbox was lost from the UI until
// something unrelated refetched it. `useBboxRefineTracking` is now owned by
// whichever ancestor calls it (ProjectPage, in production); this harness
// calls it at the same level `renderWithQuery`'s callers render WordDetail
// from, to prove the tracking is unaffected by BBoxSection's own mount
// state.

/** Build a synthetic SSE frame in the real wire shape — mirrors
 * BBoxSection.test.tsx / useBboxRefineTracking.test.tsx's `jobFrame`. */
function jobFrame(input: {
  job_id: string;
  status: string;
  result?: Record<string, unknown> | null;
}) {
  return {
    id: input.job_id,
    type: "refine_bboxes",
    project_id: "p1",
    status: input.status,
    progress: { current: 0, total: 0, message: "" },
    error_message: null,
    result: input.result ?? null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    event: input.status,
  };
}

function mockEventSource() {
  let progressListener: ((e: MessageEvent) => void) | null = null;
  const mockES = {
    addEventListener: vi.fn((type: string, fn: unknown) => {
      if (type === "progress" || type === "complete" || type === "error") {
        progressListener = fn as (e: MessageEvent) => void;
      }
    }),
    removeEventListener: vi.fn(),
    close: vi.fn(),
    readyState: 1 as number,
  };
  vi.stubGlobal(
    "EventSource",
    vi.fn(function () {
      return mockES;
    }),
  );
  return {
    dispatch(data: Parameters<typeof jobFrame>[0]) {
      act(() => {
        progressListener?.({ data: JSON.stringify(jobFrame(data)) } as MessageEvent);
      });
    },
  };
}

/** Mirrors how ProjectPage wires WordDetail: calls the real tracking hook
 * once, at a level that stays mounted regardless of what WordDetail (or
 * BBoxSection, underneath it) does with the accordion. */
function BboxRefineHarness({
  page,
  projectId,
  pageIndex,
}: {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
}) {
  const bboxRefine = useBboxRefineTracking(projectId, pageIndex);
  return (
    <WordDetail page={page} projectId={projectId} pageIndex={pageIndex} bboxRefine={bboxRefine} />
  );
}

describe("WordDetail + useBboxRefineTracking: collapses mid-job (review finding 3)", () => {
  beforeEach(() => {
    clearSelection();
    vi.clearAllMocks();
  });

  it("collapsing the Bounding Box accordion mid-job still invalidates the page query when the job completes", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () =>
        HttpResponse.json({ job_id: "job-collapse-1" }, { status: 202 }),
      ),
    );

    selectWord(0, 0);
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const es = mockEventSource();
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={qc}>
        <BboxRefineHarness page={makePage()} projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    );

    // Open the "Bounding Box" accordion item — its content (BBoxSection)
    // only attaches to the DOM once opened (Radix removes closed content).
    const bboxTrigger = screen.getByRole("button", { name: /bounding box/i });
    await user.click(bboxTrigger);
    const refineButton = await screen.findByTestId("bbox-refine-button");

    await user.click(refineButton);
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    // Collapse the accordion item — BBoxSection unmounts. The job is still
    // running server-side; nothing in this component tree is watching its
    // SSE stream from inside the collapsed content anymore.
    await user.click(bboxTrigger);
    await waitFor(() => expect(screen.queryByTestId("bbox-refine-button")).not.toBeInTheDocument());

    // The job completes after the collapse. If tracking lived inside
    // BBoxSection, this event would arrive on a closed EventSource and
    // never be observed.
    es.dispatch({ job_id: "job-collapse-1", status: "complete", result: { refined: 1 } });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["page", "p1", 0] }),
      ),
    );

    vi.unstubAllGlobals();
  });
});
